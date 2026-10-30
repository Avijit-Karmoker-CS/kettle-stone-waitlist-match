"""Kettle & Stone Waitlist Match - start here.

Double-click the desktop icon (it runs this file), or from a command line:
  main.py                 open the window
  main.py --morning       open the window on the morning list (used at 8:00)
  main.py --cli           print matches for the openings file in Data, no window
  main.py --self-check    print the self-check and stop
Testing only:  --today 2026-10-21   --data "<folder>"
"""
import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from waitlist_match.desk import Desk          # noqa: E402
from waitlist_match.server import serve       # noqa: E402

# When started from the desktop icon there is no console; keep output safe.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


def open_window(url):
    """Open a plain app window (Microsoft Edge app mode) or the normal browser."""
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.path.join(os.environ.get("LOCALAPPDATA", ""), "")):
            edge = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.exists(edge):
                subprocess.Popen([edge, f"--app={url}", "--window-size=760,900",
                                  "--no-first-run", "--disable-features=Translate"])
                return
    if sys.platform == "darwin":
        for app in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"):
            if os.path.exists(app):
                subprocess.Popen([app, f"--app={url}", "--window-size=760,900", "--no-first-run"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        subprocess.Popen(["open", url])  # Safari or the default browser
        return
    webbrowser.open(url)


def running_instance(desk):
    path = os.path.join(desk.work, "server.json")
    try:
        with open(path) as fh:
            info = json.load(fh)
        port = info["port"]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=2) as r:
            if r.status == 200:
                return port
    except Exception:
        return None
    return None


def run_cli(desk):
    s, c = desk.load()
    print(f"Kettle & Stone Waitlist Match - run date {desk.today():%a %b %d %Y}")
    for p in c.problems:
        print("PROBLEM:", p)
    for w in c.warnings:
        print("Note:", w)
    msg = c.data_age_message()
    if msg:
        print("Note:", msg)
    if not c.file_openings:
        print("No openings file in the Data folder.")
    out_dir = os.path.join(desk.data, "reports")
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for op in c.file_openings:
        res = c.match(op)
        desk.log_run(op, res, "command line")
        print()
        print(f"{op.label}  {op.describe(s)}  ·  {op.notice_hours:g}h notice")
        if not res["names"]:
            print(f"   nobody - {res['nobody_reason']}")
        for i, n in enumerate(res["names"], 1):
            extra = f"  [{n['contact']}]" if n["contact"] else ""
            print(f"   {i}. {n['name']:<20} {n['phone']:<13} {n['reason']}{extra}")
            rows.append([op.label, op.date, op.start.strftime("%H:%M"), op.therapist, op.length,
                         i, n["pid"], n["name"], n["phone"], n["reason"]])
        if not res["names"]:
            rows.append([op.label, op.date, op.start.strftime("%H:%M"), op.therapist, op.length,
                         "", "", "nobody", "", res["nobody_reason"]])
        for m in res["maybe"]:
            print(f"   check by hand: {m['name']} ({m['pid']}) - {m['why_maybe']}")
    with open(os.path.join(out_dir, "matches.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["opening", "date", "start", "therapist", "length", "rank", "line", "name", "phone", "reason"])
        w.writerows(rows)
    lists = desk.lists()
    with open(os.path.join(out_dir, "cross-off.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["lines", "name", "reason"])
        for r in lists["cross_off"]:
            w.writerow([r["lines"], r["name"], r["reason"]])
    print()
    print("Cross off the notebook:")
    for r in lists["cross_off"]:
        print(f"   {r['lines']:<12} {r['name']:<22} {r['reason']}")
    if lists["check"]:
        print("Check by hand:")
        for r in lists["check"]:
            print(f"   {r['line']:<6} {r['name']:<22} {r['reason']}")
    print()
    print(f"Saved: {os.path.join(out_dir, 'matches.csv')} and cross-off.csv")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kettle & Stone Waitlist Match")
    ap.add_argument("--morning", action="store_true")
    ap.add_argument("--cli", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--no-window", action="store_true")
    ap.add_argument("--today")
    ap.add_argument("--now")
    ap.add_argument("--data")
    ap.add_argument("--port", type=int, default=0)
    a = ap.parse_args(argv)

    today = dt.date.fromisoformat(a.today) if a.today else None
    now = dt.datetime.fromisoformat(a.now) if a.now else None
    desk = Desk(ROOT, data=a.data, today=today, fixed_now=now)

    if a.self_check:
        sc = desk.self_check()
        print("READY" if sc["ready"] else "NOT READY")
        for kind, text in sc["items"]:
            print(f" - {kind}: {text}")
        print(" - info:", sc.get("info"))
        return 0 if sc["ready"] else 1
    if a.cli:
        run_cli(desk)
        return 0

    page = "#morning" if a.morning else ""
    port = running_instance(desk)
    if port and not a.port:
        if not a.no_window:
            open_window(f"http://127.0.0.1:{port}/{page}")
        return 0

    def ready(p):
        with open(os.path.join(desk.work, "server.json"), "w") as fh:
            json.dump({"port": p, "pid": os.getpid(), "started": time.time()}, fh)
        if not a.no_window:
            threading.Timer(0.4, open_window, args=(f"http://127.0.0.1:{p}/{page}",)).start()
        print(f"Waitlist Match is running at http://127.0.0.1:{p}/ (this computer only)")

    serve(desk, port=a.port, idle_minutes=0 if a.no_window else 15, ready=ready)
    return 0


if __name__ == "__main__":
    sys.exit(main())
