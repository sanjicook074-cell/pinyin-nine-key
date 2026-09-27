# -*- coding: utf-8 -*-
"""把全部拼音录音内联进单文件 HTML。

为什么必须内联（而不是靠浏览器缓存）：
    每次给 <audio> 换 src 都是一次真实加载。手机 4G 下逐段累积成"卡" —— 练习页一次
    拼读要串 3~5 段，尖刀就出在这里。装进本地后每段都是 0 延迟，而且断网也能用。

用法：
    python build/inline_audio.py                  # 下载（有缓存就跳过）并写入 HTML
    python build/inline_audio.py --dry-run        # 只报告体积，不改文件
    python build/inline_audio.py --force          # 忽略本地缓存重新下载

名单从哪来：
    _check/audio_inventory.html —— 在无头 Chrome 里用 app 自己的逻辑（INITIAL_AUDIO /
    FINAL_AUDIO / WORDS[].sylInfo）去重统计，导出成 build/audio_names.json。
    词表变了就要重跑一次它。

落点：
    HTML 里 <!-- AUDIO_INLINE:BEGIN --> … <!-- AUDIO_INLINE:END --> 之间的整段。
    跑本脚本会**整段替换**，不要手改那一段。
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HTML = os.path.join(ROOT, "pinyin-nine-key.html")
NAMES = os.path.join(HERE, "audio_names.json")
CACHE = os.path.join(HERE, "audio_cache")

BASES = [
    "https://hanyu-word-pinyin-short.cdn.bcebos.com/",
    "https://cdn.jsdelivr.net/gh/linjialiang/hanzi-audio@main/",
]

# 故意绕开系统代理：本机 shell 里的 http_proxy 会让这些 CDN 请求失败/变慢
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

HEAD = """<!-- AUDIO_INLINE:BEGIN —— 这段由 build/inline_audio.py 生成，不要手改 -->"""
JS_HEAD = """<script>
/* 内联音频：把全部 mp3 以 base64 装进页面，播放时转成 blob 地址，**零网络请求**。
   为什么必须内联（而不是靠浏览器缓存）：
     每次给 <audio> 换 src 都是一次真实加载 —— 手机 4G 下逐段累积成"卡"，
     而练习页一次拼读要串 3~5 段。装进本地后每段都是 0 延迟，断网也能用。
   体积：%(n)d 个文件 / %(raw).0f KB → base64 后约 %(b64).0f KB。
   重新生成：python build/inline_audio.py */
const AUDIO_INLINE = {"""
JS_TAIL = """};
</script>
<!-- AUDIO_INLINE:END -->"""


def fetch_one(name):
    """取一个 mp3 的字节。先查本地缓存，再按顺序试各个源。"""
    path = os.path.join(CACHE, name + ".mp3")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return name, f.read(), "cache"
    last = None
    for base in BASES:
        try:
            with OPENER.open(base + name + ".mp3", timeout=25) as r:
                data = r.read()
            if len(data) > 500:                      # 小于 500 字节肯定是错误页
                with open(path, "wb") as f:
                    f.write(data)
                return name, data, base.split("/")[2]
            last = "too small (%d B)" % len(data)
        except Exception as e:                       # noqa: BLE001
            last = "%s: %s" % (type(e).__name__, e)
    return name, None, last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="忽略缓存重新下载")
    ap.add_argument("--names", default=NAMES)
    args = ap.parse_args()

    if not os.path.exists(args.names):
        sys.exit("找不到名单文件 %s" % args.names)
    os.makedirs(CACHE, exist_ok=True)
    if args.force:
        for f in os.listdir(CACHE):
            os.remove(os.path.join(CACHE, f))

    names = json.load(open(args.names, encoding="utf-8"))
    print("名单 %d 个音频，开始取（缓存目录 %s）…" % (len(names), CACHE))

    got, missing = {}, []
    with ThreadPoolExecutor(max_workers=10) as ex:
        for name, data, src in ex.map(fetch_one, names):
            if data is None:
                missing.append((name, src))
            else:
                got[name] = data

    raw = sum(len(v) for v in got.values())
    print("成功 %d / %d，原始 %.0f KB（平均 %.1f KB）" % (
        len(got), len(names), raw / 1024, raw / len(got) / 1024 if got else 0))
    if missing:
        print("⚠️ 取不到 %d 个：" % len(missing))
        for n, why in missing[:10]:
            print("   %-10s %s" % (n, why))
        sys.exit("先解决缺失再内联，否则页面里会有哑音（会回落到 CDN）")

    # 生成 JS。每个条目一行，方便以后看 diff。
    lines = [JS_HEAD % {"n": len(got), "raw": raw / 1024,
                        "b64": raw * 4 / 3 / 1024}]
    for i, name in enumerate(sorted(got)):
        b64 = base64.b64encode(got[name]).decode("ascii")
        lines.append('"%s":"%s"%s' % (name, b64, "," if i < len(got) - 1 else ""))
    lines.append(JS_TAIL)
    block = "\n".join(lines)

    html = open(HTML, encoding="utf-8", newline="").read()
    pat = re.compile(r"<!-- AUDIO_INLINE:BEGIN.*?<!-- AUDIO_INLINE:END -->", re.S)
    if not pat.search(html):
        sys.exit("HTML 里找不到 AUDIO_INLINE 标记块，先在页面里放好占位再跑")

    new_html = pat.sub(lambda m: HEAD + "\n" + block, html, count=1)
    a, b = len(html.encode("utf-8")), len(new_html.encode("utf-8"))
    print("\n页面：%.0f KB → %.0f KB（+%.0f KB）" % (a / 1024, b / 1024, (b - a) / 1024))

    if args.dry_run:
        print("--dry-run：未写文件")
        return
    with open(HTML, "w", encoding="utf-8", newline="") as f:
        f.write(new_html)
    print("已写入 %s" % HTML)


if __name__ == "__main__":
    main()
