"""开发期自检：用无头 Chrome 打开 _check/ 里的自检页，把断言结果打印出来。

用法：
    python _check/run_check.py speedgap.html
    python _check/run_check.py offline.html
    python _check/run_check.py timersuspend.html 8000      # 可选的虚拟时间预算（毫秒）
    CHROME_PATH=/path/to/chrome python _check/run_check.py twinit.html

⚠️ 虚拟时间预算默认 4000ms。自检页内部 setTimeout 链加起来超过它的话，
   页面会在断言跑完之前就被 dump 下来，输出停在 "pending" —— 这时把预算调大。
   （timerpause / timersuspend 这类要"真等几秒"的，给 8000。）

自检页把结果写进 <pre id="out"> 里的 JSON（也会显示在页面标题上），
本脚本只负责打开、取出、打印，不做判断 —— 判断在页面里。
"""
import sys, re, html, json, subprocess, os, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))

CHROME_CANDIDATES = [
    os.environ.get("CHROME_PATH"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    shutil.which("chrome"),
    shutil.which("google-chrome"),
    shutil.which("chromium"),
]


def find_chrome():
    for p in CHROME_CANDIDATES:
        if p and os.path.exists(p):
            return p
    raise SystemExit("找不到 Chrome —— 用 CHROME_PATH 环境变量指定它的完整路径")


def uniq_safe(a):
    return sorted(set(a), key=lambda x: (x is None, x))


def run(page, budget=4000, extra=None):
    tmp = tempfile.mkdtemp(prefix="cp_")
    url = "file:///" + os.path.join(HERE, page).replace("\\", "/")
    cmd = [find_chrome(), "--headless=new", "--disable-gpu", "--no-sandbox",
           "--no-proxy-server",
           "--allow-file-access-from-files", "--user-data-dir=" + tmp,
           "--virtual-time-budget=%d" % budget, "--dump-dom", url]
    if extra:
        cmd[1:1] = extra
    out = subprocess.run(cmd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stdout
    title = re.search(r"<title>([^<]*)</title>", out)
    m = re.search(r'<pre id="out">(.*?)</pre>', out, re.S)
    body = html.unescape(m.group(1)) if m else "(no out)"
    return (title.group(1) if title else "?"), body


if __name__ == "__main__":
    page = sys.argv[1] if len(sys.argv) > 1 else "speedgap.html"
    budget = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
    t, b = run(page, budget=budget)
    print("TITLE:", t)
    try:
        o = json.loads(b)
        print("ok =", o.get("ok"))
        print("problems =", o.get("problems"))
        for k in ["word", "wordSteps", "sylStepCount", "letterStepCount",
                  "tracksFollow", "tracksPinned", "pinnedDuringDrag", "followDuringDrag",
                  "voiceRateAfterLeave"]:
            if k in o:
                print(" ", k, "=", o[k])
        for line in o.get("log") or []:
            print("   ·", line)
        for k in ["slow", "norm", "fast"]:
            if k in o:
                r = o[k]
                print("  ---", k, "rate=", r["rate"], "word=", r["hanzi"],
                      "syls=", r["syls"], "letters=", r["letters"], "segVoices=", r["segVoices"])
                print("      整字:", r["han"]["names"], "调用=", uniq_safe(r["han"]["args"]), "实际=", uniq_safe(r["han"]["played"]))
                print("      整词:", r["word"]["names"], "调用=", uniq_safe(r["word"]["args"]), "实际=", uniq_safe(r["word"]["played"]))
                print("      拼读:", r["seg"]["names"], "调用=", uniq_safe(r["seg"]["args"]), "实际=", uniq_safe(r["seg"]["played"]))
                print("      排期:", r["delays"], " 键亮:", r["pulses"], " 脉冲数:", r["pulseCount"])
    except Exception:
        print(b[:3000])
