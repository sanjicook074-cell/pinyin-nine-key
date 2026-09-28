"""把所有自检页跑一遍，只报「过 / 不过」，用来确认一次改动没把别的地方碰坏。

用法：
    python _check/sweep.py            # 全部判定型自检页
    python _check/sweep.py timer      # 只看名字含 timer 的
    python _check/sweep.py -v         # 顺带把每页的日志打出来
    python _check/sweep.py -a         # 连信息型页面也跑一遍（只看有没有报错）

判定型 vs 信息型
----------------
这个目录里的 html 分两类，混在一起统计会得出"16 个不过"这种假警报：

  · 判定型：页面自己声明结论 —— 源码里有 'PASS'/'FAIL'，会写进 <title>
    和 <pre id="out"> 的 JSON。**只有这类参与过/不过统计。**
  · 信息型：量个尺寸、列个音频清单、探一下接口，把数据打出来给人看
    （measure / audiolist / probe_ok / letter / state / speed… 都是）。
    它们没有"过"可言，`-a` 时才跑，只用来确认页面本身没抛异常。

特例 persist.html 不在这里跑 —— 它要「同一个 user-data-dir 跑两次」才成立，
属于跨会话协议，单独按它文件头的说明跑（见 _check/persist.html 顶部注释）。
"""
import os, re, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run_check import run, find_chrome          # noqa: E402

# 截图壳子不算自检页
SKIP = {"shot.html"}
# 需要特殊协议、不能当单页自检跑的（会被排除，不参与统计）
SPECIAL = {"persist.html"}
TWO_PHASE_HINT = ("persist.html 没跑 —— 它要「同一个 --user-data-dir 跑两次」才成立，"
                  "属于跨会话协议，单独按该文件顶部的说明跑")

# 默认虚拟时间预算，够跑完一两个 setTimeout 就够
BUDGET = 4000
# 个别页面要跑好几轮完整播放，得单独给时间（不然 dump 下来还是 pending）
PAGE_BUDGET = {
    "speedgap_time.html": 45000,   # 4 轮播放 × 每轮约 10 秒虚拟时间
}


def classify(path):
    """verdict = 页面自己会写 PASS/FAIL；info = 只打印数据

    判据是「源码里出现带引号的 PASS」—— `title = ok ? 'PASS' : 'FAIL'`、
    `title = ok ? 'PASS ' + n : ...` 都算（audio_inventory 就是后面这种，
    一开始按 `'PASS'` 整串去匹配，把它错当成信息型页面漏掉了）。
    """
    with open(path, encoding="utf-8", errors="replace") as fh:
        src = fh.read()
    if 'id="out"' not in src:
        return None                                  # 连输出都没有，不是自检页
    if re.search(r"""['"]PASS""", src):
        return "verdict"
    return "info"


def discover():
    verdict, info = [], []
    for name in sorted(os.listdir(HERE)):
        if not name.endswith(".html") or name in SKIP or name in SPECIAL:
            continue
        if name.startswith("_"):                     # A/B 之类的一次性临时页
            continue
        kind = classify(os.path.join(HERE, name))
        if kind == "verdict":
            verdict.append(name)
        elif kind == "info":
            info.append(name)
    return verdict, info


def show_log(body):
    """把 out JSON 里的 log 数组打出来。

    ⚠️ 别用 `s.encode('utf-8').decode('unicode_escape')` 解 JSON 转义 ——
    那是按 latin-1 还原的，中文会变成乱码。老老实实交给 json。"""
    for line in re.findall(r'"log": \[(.*?)\]', body, re.S):
        for item in re.findall(r'"((?:[^"\\]|\\.)*)"', line):
            try:
                text = json.loads('"' + item + '"')
            except Exception:
                text = item
            print("       ·", text)


def probe(page):
    """跑一页；输出还是 pending 就说明断言没跑完，加大虚拟时间再来一次。

    `speedgap_time` 这种要跑四轮完整播放的，4 秒连第一轮都跑不完，
    靠重试要一路加码 —— 所以直接查表给它一次到位。"""
    budget = PAGE_BUDGET.get(page, BUDGET)
    title, body = run(page, budget=budget)
    if body.strip() == "pending" or '"pending"' in body:
        title, body = run(page, budget=max(budget * 8, 15000))
    return title, body


def main(argv):
    verbose = "-v" in argv
    all_pages = "-a" in argv
    wanted = [a for a in argv if not a.startswith("-")]

    verdict, info = discover()
    if wanted:
        verdict = [p for p in verdict if any(w in p for w in wanted)]
        info = [p for p in info if any(w in p for w in wanted)]

    find_chrome()                                    # 找不到就直接报错，别跑到一半
    bad, err = [], []

    print("== 判定型自检页 ==")
    width = max([len(p) for p in verdict] or [10])
    for p in verdict:
        title, body = probe(p)
        if body.strip() in ("", "pending"):
            # 加大预算还是没跑完：多半是这个页面本来就用真实时间在量，
            # 光靠虚拟时间喂不动它。单独报出来，别混进"不过"里。
            print("%-*s  PENDING（加大虚拟时间仍未跑完，可能依赖真实时间）" % (width, p))
            bad.append(p)
            continue
        # 标题可能是 'PASS' 也可能是 'PASS 86'（后面跟着数字），
        # 所以按**前缀**判，别用 == 把带数字的当成失败。
        passed = title.startswith("PASS")
        print("%-*s  %s" % (width, p, "PASS" if passed else "FAIL  " + title))
        if not passed:
            bad.append(p)
        if verbose or not passed:
            show_log(body)
            if not passed:
                print("      raw:", body.strip()[:600])

    if all_pages and info:
        print("\n== 信息型页面（只确认没抛异常）==")
        for p in info:
            title, body = probe(p)
            if body.strip() in ("", "pending"):
                flag = "EMPTY"
                err.append(p)
            else:
                flag = "ok   "
            print("%-*s  %s  title=%s  %d 字节" %
                  (width, p, flag, title, len(body)))
            if verbose:
                print("      ", body.strip().replace("\n", " ")[:400])

    if not wanted:
        print("\n(" + TWO_PHASE_HINT + ")")

    print("\n%d 个判定型，%d 个不过%s" %
          (len(verdict), len(bad), ("：" + "、".join(bad)) if bad else ""))
    if all_pages:
        print("%d 个信息型，%d 个没出东西%s" %
              (len(info), len(err), ("：" + "、".join(err)) if err else ""))
    return 1 if (bad or err) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
