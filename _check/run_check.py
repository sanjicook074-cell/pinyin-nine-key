import sys, re, html, json, subprocess, os, tempfile

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def uniq_safe(a):
    return sorted(set(a), key=lambda x: (x is None, x))

def run(page, budget=4000, extra=None):
    tmp = tempfile.mkdtemp(prefix="cp_")
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-proxy-server",
           "--allow-file-access-from-files", "--user-data-dir=" + tmp,
           "--virtual-time-budget=%d" % budget, "--dump-dom",
           "file:///C:/Users/38439/WorkBuddy/2026-09-26-15-35-27/_check/" + page]
    if extra:
        cmd[1:1] = extra
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    title = re.search(r"<title>([^<]*)</title>", out)
    m = re.search(r'<pre id="out">(.*?)</pre>', out, re.S)
    body = html.unescape(m.group(1)) if m else "(no out)"
    return (title.group(1) if title else "?"), body

if __name__ == "__main__":
    page = sys.argv[1] if len(sys.argv) > 1 else "speedgap.html"
    t, b = run(page)
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
