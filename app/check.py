"""Feature 34 - answer-key test.

Scores the program against Tanya's answer key:
  * openings correct  (every name shown is on Tanya's list; "nobody" when she says none)
  * wrong names shown (must be 0)
  * out-of-date lines found
Usage:
  check.py --data "<folder with waitlist, openings, appointments>" --key <answer key file> --today 2026-10-21
"""
import argparse
import datetime as dt
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from waitlist_match.engine import Clinic           # noqa: E402
from waitlist_match.files import read_rows         # noqa: E402
from waitlist_match.settings import Settings       # noqa: E402


def load_key(path):
    rows = read_rows(path)
    head = [h.strip().lower() for h in rows[0]]
    idx = {h: i for i, h in enumerate(head)}
    openings, lines = {}, {}
    for r in rows[1:]:
        rid = r[idx["id"]].strip()
        answer = r[idx["answer"]].strip()
        note = r[idx.get("note", len(r) - 1)] if idx.get("note") is not None else ""
        if rid.upper().startswith("O"):
            names = set() if answer.lower() == "none" else set(re.findall(r"\b(W\d+)\b", answer))
            openings[rid] = (names, note)
        elif rid.upper().startswith("W"):
            lines[rid] = (answer.lower(), note)
    return openings, lines


def main(argv=None):
    root = os.path.dirname(HERE)
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(root, "Sample data"))
    ap.add_argument("--key", default=None)
    ap.add_argument("--today", default="2026-10-21")
    ap.add_argument("--settings", default=os.path.join(root, "settings"))
    ap.add_argument("--key-date", default="2026-10-21",
                    help="the day Tanya marked the answer key")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    key_path = a.key
    if not key_path:
        cands = [f for f in os.listdir(a.data) if "answer" in f.lower() and "key" in f.lower()]
        if not cands:
            print("No answer key found. Use --key <file>.")
            return 2
        key_path = os.path.join(a.data, sorted(cands)[-1])
    today = dt.date.fromisoformat(a.today)
    settings = Settings(a.settings)
    clinic = Clinic(settings, a.data, today=today)
    for p in clinic.problems:
        print("PROBLEM:", p)
    key_open, key_lines = load_key(key_path)

    correct = wrong_names = missed = 0
    possible = 0
    detail = []
    for op in clinic.file_openings:
        res = clinic.match(op)
        shown = [n["pid"] for n in res["names"]]
        want, _ = key_open.get(op.label, (set(), ""))
        bad = [s for s in shown if s not in want]
        wrong_names += len(bad)
        if want:
            possible += 1
        ok = (not bad) and (bool(shown) == bool(want))
        correct += ok
        if want and not shown:
            missed += 1
        mark = "OK " if ok else "XX "
        detail.append(f"{mark}{op.label} {op.describe(settings)} | shown: {', '.join(shown) or 'nobody'}"
                      f" | Tanya: {', '.join(sorted(want)) or 'none'}"
                      + (f" | WRONG: {', '.join(bad)}" if bad else "")
                      + (f" | maybe: {', '.join(m['pid'] for m in res['maybe'])}" if res["maybe"] else ""))

    status = clinic.line_status()
    key_day = dt.date.fromisoformat(a.key_date)
    status_on_key_day = status if key_day == today else Clinic(settings, a.data, today=key_day).line_status()
    expected = []
    stale_key = {w for w, (ans, _) in key_lines.items() if ans == "stale"}
    stale_found = {w for w, (st, _) in status.items() if st == "stale"}
    line_ok = 0
    line_detail = []
    for w, (ans, _) in sorted(key_lines.items()):
        mine = status.get(w, ("missing", ""))[0]
        same = mine.lower() == ans.lower()
        if not same and status_on_key_day.get(w, ("", ""))[0].lower() == ans.lower():
            # Right on the day Tanya marked the key; only the calendar has moved on.
            expected.append(f"-- {w}: now '{mine}' ({status[w][1]}); Tanya marked '{ans}' on {key_day:%b} {key_day.day}")
            same = True
        line_ok += same
        if not same:
            line_detail.append(f"XX {w}: program says '{mine}', Tanya says '{ans}'")

    n = len(clinic.file_openings)
    if not a.quiet:
        print("\n".join(detail))
        if line_detail:
            print("\n".join(line_detail))
        if expected:
            print("Changed only because the run date is later than the answer key (expected):")
            print("\n".join(expected))
    print()
    print(f"Run date:                 {today:%a %b %d %Y}")
    print(f"Openings correct:         {correct} of {n}   (target 31)")
    print(f"Openings with a name:     {possible - missed} of {possible} that Tanya could fill")
    print(f"Wrong names shown:        {wrong_names}   (target 0)")
    print(f"Out-of-date lines found:  {len(stale_found & stale_key)} of {len(stale_key)}"
          f"   (newly out of date since {key_day:%b} {key_day.day}: {len(expected)})")
    print(f"Waitlist lines matching Tanya's status: {line_ok} of {len(key_lines)}")
    passed = wrong_names == 0 and correct >= 31 and line_ok == len(key_lines)
    print("RESULT:", "PASS" if passed else "NOT YET")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
