"""Front-desk services: logs, offers, lists, reports and add-ons.

Everything is stored as plain CSV in the clinic's Data folder (feature 29).
Nothing here connects to the internet (feature 28).
"""
import csv
import datetime as dt
import glob
import hashlib
import os
import shutil

from .engine import CANCELLED, Clinic, _surname_key, name_parts
from .files import FileProblem, newest_file, phone_digits, pretty_phone, read_rows
from .settings import Settings, plain
from .shorthand import DAYS_ORDER

LOG_FIELDS = {
    "run-log.csv": ["time", "opening", "therapist", "date", "start", "length", "notice_hours",
                    "names_shown", "maybe_count", "source"],
    "offers.csv": ["time", "opening", "person", "name", "status"],
    "openings-entered.csv": ["time", "therapist", "date", "start", "length", "kind", "cancelled_at"],
    "messages.csv": ["time", "opening", "person", "name", "message", "result"],
}
FINAL = {"yes", "no"}


class Desk:
    def __init__(self, root, data=None, today=None, fixed_now=None):
        self.root = root
        self.data = data or os.path.join(root, "Data")
        self.settings_dir = os.path.join(root, "settings")
        self.logs = os.path.join(self.data, "logs")
        self.work = os.path.join(self.data, ".work")
        self.fixed_today = today
        self.fixed_now = fixed_now
        os.makedirs(self.logs, exist_ok=True)
        os.makedirs(self.work, exist_ok=True)

    # ------------------------------------------------------------ time
    def now(self):
        if self.fixed_now:
            return self.fixed_now
        n = dt.datetime.now().replace(second=0, microsecond=0)
        if self.fixed_today:
            return dt.datetime.combine(self.fixed_today, n.time())
        return n

    def today(self):
        return self.now().date()

    # ------------------------------------------------------------ loading
    def _signature(self):
        sig = [self.today().isoformat()]
        for folder in (self.data, self.settings_dir):
            for f in sorted(glob.glob(os.path.join(folder, "*"))):
                if os.path.isfile(f):
                    st = os.stat(f)
                    sig.append((f, st.st_mtime, st.st_size))
        return tuple(sig)

    def load(self):
        """Read settings and files. Re-reads only when a file has changed."""
        sig = self._signature()
        cached = getattr(self, "_cache", None)
        if cached and cached[0] == sig:
            s, c = cached[1], cached[2]
            c.now = self.now()
            return s, c
        s = Settings(self.settings_dir)
        c = Clinic(s, self.data, today=self.today(), now=self.now())
        self._cache = (sig, s, c)
        return s, c

    # ------------------------------------------------------------ logs
    def _log_path(self, name):
        return os.path.join(self.logs, name)

    def append_log(self, name, row):
        path = self._log_path(name)
        new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=LOG_FIELDS[name], extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow(row)

    def read_log(self, name):
        path = self._log_path(name)
        if not os.path.exists(path):
            return []
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    # ------------------------------------------------------------ self-check (feature 31)
    def self_check(self):
        items = []
        ok = True
        try:
            s, c = self.load()
        except Exception as exc:  # should never happen; reported in plain words
            return {"ready": False, "items": [("problem", f"The program could not start: {exc}")]}
        for e in s.errors:
            items.append(("problem", e))
            ok = False
        if not os.access(self.data, os.W_OK):
            items.append(("problem", "The Data folder is read-only. Julie: allow changes to the Data folder."))
            ok = False
        for p in c.problems:
            items.append(("problem", p))
            ok = False
        for w in c.warnings:
            items.append(("warning", w))
        msg = c.data_age_message() if c.appointments_path else ""
        if msg:
            items.append(("warning", msg))
        try:
            import numbers_parser  # noqa: F401
            numbers = True
        except Exception:
            numbers = False
        if any(str(p or "").lower().endswith(".numbers") for p in (c.waitlist_path, c.appointments_path)) and not numbers:
            items.append(("problem", "A Numbers file is in the Data folder. Please save it as CSV."))
            ok = False
        active = sum(p.status == "active" for p in c.persons)
        info = {
            "waitlist": os.path.basename(c.waitlist_path) if c.waitlist_path else None,
            "bookings": os.path.basename(c.appointments_path) if c.appointments_path else None,
            "lines": len(c.lines), "people": len(c.persons), "active": active,
            "out_of_date": sum(p.status == "out_of_date" for p in c.persons),
            "check": sum(1 for p in c.persons if p.status == "hold" or (p.status == "active" and p.doubts)),
            "today": self.today().isoformat(),
        }
        return {"ready": ok, "items": items, "info": info}

    # ------------------------------------------------------------ matching
    def opening_from(self, c, form):
        therapist = c.therapist_name(form.get("therapist", ""))
        if not therapist:
            raise FileProblem("Please pick a therapist.")
        try:
            date = dt.date.fromisoformat(form.get("date") or self.today().isoformat())
            start = dt.time.fromisoformat(form["start"])
        except Exception:
            raise FileProblem("Please enter the date and the start time.")
        length = int(form.get("length") or c.s.default_length)
        cancelled = form.get("cancelled_at")
        cancelled_at = dt.datetime.fromisoformat(cancelled) if cancelled else self.now()
        return c.make_opening(therapist, date, start, length, form.get("kind") or "late cancel", cancelled_at)

    def match(self, form, save=True, source="desk"):
        s, c = self.load()
        op = self.opening_from(c, form)
        result = c.match(op)
        if save:
            self.append_log("openings-entered.csv", {
                "time": self.now().isoformat(sep=" "), "therapist": op.therapist,
                "date": op.date.isoformat(), "start": op.start.strftime("%H:%M"),
                "length": op.length, "kind": op.kind,
                "cancelled_at": op.cancelled_at.isoformat(sep=" ") if op.cancelled_at else ""})
        self.log_run(op, result, source)
        return self.present(s, c, result)

    def log_run(self, op, result, source):
        self.append_log("run-log.csv", {
            "time": self.now().isoformat(sep=" "), "opening": op.key, "therapist": op.therapist,
            "date": op.date.isoformat(), "start": op.start.strftime("%H:%M"), "length": op.length,
            "notice_hours": op.notice_hours,
            "names_shown": "; ".join(n["name"] for n in result["names"]),
            "maybe_count": len(result["maybe"]), "source": source})

    def _said_yes(self):
        """People who already took another opening (from the offer tracker)."""
        latest = {}
        for r in self.read_log("offers.csv"):
            latest[(r["opening"], r["person"])] = r["status"]
        return {(op, pid) for (op, pid), st in latest.items() if st == "yes"}

    def present(self, s, c, result):
        op = result["opening"]
        taken = {pid: o for (o, pid) in self._said_yes() if o != op.key}
        if taken:
            keep = [n for n in result["names"] if n["pid"] not in taken]
            def nice(key):
                d, t, th = key.split(" ", 2)
                tt = dt.time.fromisoformat(t)
                return f"{s.first_name(th)} {tt.strftime('%I:%M').lstrip('0')} on {dt.date.fromisoformat(d):%b} {int(d[-2:])}"
            moved = [dict(n, why_maybe=f"Already said yes to another opening ({nice(taken[n['pid']])})")
                     for n in result["names"] if n["pid"] in taken]
            # refill up to the limit from the remaining people who fit
            result = dict(result, names=keep, maybe=moved + result["maybe"])
            if len(keep) < s.max_names:
                extra = [p for p in c.match_all(op) if p["pid"] not in taken
                         and p["pid"] not in {n["pid"] for n in keep} and not p["why_maybe"]]
                result["names"] = keep + extra[: s.max_names - len(keep)]
            if not result["names"] and not result["nobody_reason"]:
                result["nobody_reason"] = "Nobody else on the list fits this opening."
        offers = self.offer_state(op.key, result["names"], s)
        return {
            "key": op.key, "label": op.label, "title": op.describe(s),
            "auto": bool(op.label and op.label.startswith("A-")),
            "therapist": op.therapist, "date": op.date.isoformat(),
            "start": op.start.strftime("%H:%M"), "length": op.length,
            "notice": round(op.notice_hours, 1), "no_show": op.is_no_show,
            "names": [{k: v for k, v in n.items() if k in ("pid", "name", "phone", "reason", "contact")}
                      for n in result["names"]],
            "maybe": [{k: v for k, v in n.items() if k in ("pid", "name", "phone", "reason", "why_maybe")}
                      for n in result["maybe"]],
            "nobody_reason": result["nobody_reason"],
            "offers": offers,
            "warning": c.data_age_message(),
        }

    # ------------------------------------------------------------ offer tracker (feature 23)
    def offer_state(self, opening_key, names, s):
        rows = [r for r in self.read_log("offers.csv") if r["opening"] == opening_key]
        latest = {}
        for r in rows:
            latest[r["person"]] = r
        filled_by = next((r for r in rows if r["status"] == "yes"), None)
        now = self.now()
        state = {"filled_by": filled_by["name"] if filled_by else "", "current": None, "people": {}}
        for n in names:
            r = latest.get(n["pid"])
            st = r["status"] if r else ""
            when = dt.datetime.fromisoformat(r["time"]) if r else None
            wait_left = 0
            if st == "voicemail" and when:
                wait_left = max(0, s.voicemail_wait - int((now - when).total_seconds() // 60))
            state["people"][n["pid"]] = {"status": st, "time": when.strftime("%H:%M") if when else "",
                                         "wait_left": wait_left}
        if not filled_by:
            for n in names:
                p = state["people"][n["pid"]]
                if p["status"] == "no":
                    continue
                if p["status"] == "voicemail" and p["wait_left"] == 0:
                    continue  # waited long enough: move on, they can still say yes
                state["current"] = n["pid"]
                break
        return state

    def set_offer(self, opening_key, pid, name, status):
        if status not in ("called", "voicemail", "yes", "no", "undo"):
            raise FileProblem("Unknown offer status.")
        rows = [r for r in self.read_log("offers.csv") if r["opening"] == opening_key]
        if status == "yes" and any(r["status"] == "yes" and r["person"] != pid for r in rows):
            raise FileProblem("This opening is already filled. Only one person can say yes.")
        self.append_log("offers.csv", {"time": self.now().isoformat(sep=" "), "opening": opening_key,
                                       "person": pid, "name": name,
                                       "status": "" if status == "undo" else status})

    # ------------------------------------------------------------ morning list (features 18 and 37)
    def morning(self):
        s, c = self.load()
        today = self.today()
        out = {"entered": [], "automatic": [], "auto_on": c.daily_report_fresh(self._max_age(s)),
               "warning": c.data_age_message()}
        seen = set()
        for r in self.read_log("openings-entered.csv"):
            if r["date"] != today.isoformat():
                continue
            try:
                op = c.make_opening(r["therapist"], dt.date.fromisoformat(r["date"]),
                                    dt.time.fromisoformat(r["start"]), int(r["length"]), r["kind"],
                                    dt.datetime.fromisoformat(r["cancelled_at"]) if r["cancelled_at"] else None)
            except Exception:
                continue
            if op.key in seen:
                continue
            seen.add(op.key)
            out["entered"].append(self.present(s, c, c.match(op)))
        if out["auto_on"]:
            for op in self.auto_openings(c):
                if op.key in seen:
                    continue
                seen.add(op.key)
                res = c.match(op)
                out["automatic"].append(self.present(s, c, res))
        return out

    def _max_age(self, s):
        try:
            return float(s.get(s.addons, "daily_report", "max_age_hours", 30))
        except ValueError:
            return 30

    def auto_openings(self, c):
        """Feature 37: late cancellations from the daily report, not yet filled."""
        now = self.now()
        since = now - dt.timedelta(hours=18)
        rebooked = {a.get("rebooked_into") for a in c.appointments if a.get("rebooked_into")}
        ops = []
        for a in c.appointments:
            if a["_status"] not in ("late cancel", "late cancellation"):
                continue
            if not a["_date"] or not a["_start"] or not a["_cancelled"]:
                continue
            if a["_cancelled"] < since or a.get("rebooked_into"):
                continue
            slot = dt.datetime.combine(a["_date"], a["_start"])
            if slot < now or slot > now + dt.timedelta(hours=36):
                continue
            therapist = c.therapist_name(a.get("therapist", ""))
            if not therapist:
                continue
            length = int(float(a.get("length_min") or c.s.default_length))
            ops.append(c.make_opening(therapist, a["_date"], a["_start"], length, "late cancel",
                                      a["_cancelled"], label=a.get("appointment_id", "")))
        ops.sort(key=lambda o: (o.date, o.start))
        return ops

    # ------------------------------------------------------------ no-show risk (feature 38)
    def noshow_risk(self):
        s, c = self.load()
        today = self.today()
        target = today + dt.timedelta(days=1)
        if target.weekday() == 6:  # closed Sunday
            target += dt.timedelta(days=1)
        upcoming = [a for a in c.appointments if a["_date"] == target and a["_status"] not in CANCELLED
                    and a["_status"] not in ("completed", "complete", "attended")]
        if not upcoming:
            return {"available": False, "date": target.isoformat(),
                    "message": "Needs the daily Kneadly report. Once Marc switches it on and the file is "
                               "saved in the Data folder each morning, tomorrow's clients most likely to "
                               "miss appear here."}
        history = {}
        for a in c.appointments:
            if a["_date"] and a["_date"] < today:
                key = a.get("client_id") or plain(a.get("client_name"))
                h = history.setdefault(key, {"visits": 0, "noshow": 0, "unconfirmed": 0})
                h["visits"] += 1
                h["noshow"] += a["_status"] in ("no-show", "no show", "noshow")
                h["unconfirmed"] += plain(a.get("confirmation")) in ("none", "", "no")
        rows = []
        for a in upcoming:
            conf = plain(a.get("confirmation"))
            if conf not in ("none", "", "no", "unconfirmed"):
                continue
            key = a.get("client_id") or plain(a.get("client_name"))
            h = history.get(key, {"visits": 0, "noshow": 0, "unconfirmed": 0})
            why, score = [], 1
            if h["noshow"]:
                why.append(f"missed {h['noshow']} before")
                score += 3 * h["noshow"]
            if h["visits"] and h["unconfirmed"] == h["visits"]:
                why.append("has never confirmed")
                score += 2
            if h["visits"] == 0:
                why.append("first visit")
                score += 1
            rows.append({"name": a.get("client_name"), "time": a.get("start"),
                         "therapist": s.first_name(c.therapist_name(a.get("therapist", "")) or a.get("therapist", "")),
                         "why": ", ".join(why) or "not confirmed yet", "score": score})
        rows.sort(key=lambda r: (-r["score"], r["time"]))
        reminder_on = plain(s.get(s.addons, "second_reminder", "kneadly_reminder_on", "no")) in ("yes", "on", "true")
        return {"available": True, "date": target.isoformat(), "rows": rows,
                "call_only": [r for r in rows if r["score"] > 1],
                "reminder_on": reminder_on}

    # ------------------------------------------------------------ lists (features 25-27, 6, 15)
    def lists(self):
        s, c = self.load()
        today = self.today()
        cross, check, still, hard, unknown = [], [], [], [], []
        for p in c.persons:
            if p.status == "out_of_date":
                cross.append({"lines": ", ".join(ln.label for ln in p.lines), "name": p.name,
                              "reason": p.reason})
            else:
                older = [ln.label for ln in p.lines if ln.label != p.pid]
                if older:
                    cross.append({"lines": ", ".join(older), "name": p.name,
                                  "reason": f"Repeat line - this person is now on line {p.pid}"})
            if p.status == "hold":
                check.append({"line": p.pid, "name": p.name, "reason": p.reason})
            elif p.status == "active" and p.doubts:
                words = ", ".join(sorted({d for _, d in p.doubts}))
                check.append({"line": p.pid, "name": p.name,
                              "reason": f"Words the program could not read: {words}. "
                                        "Rewrite the line in the usual shorthand, or add the word to the word list."})
            if p.status == "active" and p.last_contact:
                days = (today - p.last_contact).days
                if days >= s.still_waiting_days:
                    still.append({"line": p.pid, "name": p.name, "phone": pretty_phone(p.phone),
                                  "last": f"{p.last_contact:%b} {p.last_contact.day}", "days": days})
        # Hard to place: waiting a while and no opening in the booking file fitted them.
        history = self._history_openings(c)
        for p in c.persons:
            if p.status != "active" or not p.first_asked:
                continue
            waited = (today - p.first_asked).days
            if waited < s.hard_to_place_days:
                continue
            if history and any(c.fits(p, op)[0] for op in history):
                continue
            hard.append({"line": p.pid, "name": p.name, "waited": waited,
                         "needs": c.reason_for(p)})
        for ln in c.lines:
            for w in sorted(set(ln.needs.doubts)):
                unknown.append({"line": ln.label, "word": w, "effect": "held for checking by hand"})
            for w in sorted(set(ln.needs.unknown)):
                unknown.append({"line": ln.label, "word": w, "effect": "ignored as a comment"})
        cross.sort(key=lambda r: int(r["lines"].split(",")[0][1:]))
        still.sort(key=lambda r: -r["days"])
        hard.sort(key=lambda r: -r["waited"])
        return {"cross_off": cross, "check": check, "still_waiting": still, "hard_to_place": hard,
                "unknown_words": unknown, "history_count": len(history)}

    def _history_openings(self, c):
        ops = list(c.file_openings)
        for a in c.appointments:
            if a["_status"] in ("late cancel", "late cancellation") and a["_date"] and a["_start"]:
                therapist = c.therapist_name(a.get("therapist", ""))
                if therapist:
                    length = int(float(a.get("length_min") or c.s.default_length))
                    ops.append(c.make_opening(therapist, a["_date"], a["_start"], length, "late cancel",
                                              a["_cancelled"]))
        for r in self.read_log("openings-entered.csv"):
            try:
                ops.append(c.make_opening(r["therapist"], dt.date.fromisoformat(r["date"]),
                                          dt.time.fromisoformat(r["start"]), int(r["length"]), r["kind"],
                                          dt.datetime.fromisoformat(r["cancelled_at"]) if r["cancelled_at"] else None))
            except Exception:
                pass
        return [o for o in ops if not o.is_no_show]

    # ------------------------------------------------------------ add to waitlist (feature 22)
    def lookup(self, phone="", name=""):
        s, c = self.load()
        digits = phone_digits(phone)
        found = []
        for p in c.persons:
            hit = digits and p.phone and (p.phone == digits or p.phone.endswith(digits[-7:]))
            if not hit and name and not digits:
                f1, l1 = name_parts(name)
                f2, l2 = name_parts(p.name)
                hit = s.first_names_match(f1, f2) and (not l1 or _surname_key(l2).startswith(_surname_key(l1)[:1]))
            if hit:
                found.append({"line": p.pid, "name": p.name, "phone": pretty_phone(p.phone),
                              "status": {"active": "on the list", "hold": "on the list (check by hand)",
                                         "out_of_date": "out of date"}[p.status],
                              "reason": p.reason, "needs": c.reason_for(p),
                              "since": f"{p.first_asked:%b} {p.first_asked.day}" if p.first_asked else ""})
        return found

    def add_to_waitlist(self, name, phone, note):
        name, note = (name or "").strip(), (note or "").strip()
        if not name:
            raise FileProblem("Please type the person's name.")
        s, c = self.load()
        path = c.waitlist_path
        today = self.today()
        added = f"{today:%b} {today.day}"
        if path and path.lower().endswith(".csv"):
            rows = read_rows(path)
            header = rows[0]
            target = path
        else:
            header = ["line", "added", "name", "phone", "notes"]
            rows = read_rows(path) if path else [header]
            if path:
                header = rows[0]
            target = os.path.join(self.data, f"waitlist-{today.isoformat()}.csv")
        numbers = [ln.number for ln in c.lines]
        new_no = (max(numbers) if numbers else 0) + 1
        values = {"line": str(new_no), "added": added, "name": name, "phone": phone.strip(), "notes": note}
        cmap = s.column_map.get("waitlist", {})
        new_row = []
        for h in header:
            canon = next((k for k, names in cmap.items() if plain(h) in [plain(n) for n in names]), None)
            new_row.append(values.get(canon, ""))
        if target != path:
            with open(target, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                for r in rows:
                    w.writerow(r)
                w.writerow(new_row)
        else:
            self._backup(path)
            needs_newline = False
            with open(path, "rb") as fh:
                fh.seek(0, 2)
                if fh.tell():
                    fh.seek(-1, 2)
                    needs_newline = fh.read(1) not in (b"\n", b"\r")
            with open(path, "a", newline="", encoding="utf-8") as fh:
                if needs_newline:
                    fh.write("\r\n")
                csv.writer(fh).writerow(new_row)
        return {"line": f"W{new_no:02d}", "file": os.path.basename(target)}

    def _backup(self, path):
        folder = os.path.join(self.data, "backups")
        os.makedirs(folder, exist_ok=True)
        stamp = self.now().strftime("%Y-%m-%d")
        dest = os.path.join(folder, f"{os.path.splitext(os.path.basename(path))[0]}-{stamp}.csv")
        if not os.path.exists(dest):
            shutil.copy2(path, dest)
        old = sorted(glob.glob(os.path.join(folder, "*.csv")))
        for f in old[:-30]:  # keep the last 30 copies
            os.remove(f)

    # ------------------------------------------------------------ monthly summary (feature 33)
    def summary(self, month=None):
        s, c = self.load()
        month = month or self.today().strftime("%Y-%m")
        late = [a for a in c.appointments if a["_date"] and a["_date"].strftime("%Y-%m") == month
                and a["_status"] in ("late cancel", "late cancellation", "no-show", "no show")]
        late_cancels = [a for a in late if a["_status"].startswith("late")]
        refilled = [a for a in late if a.get("rebooked_into")]
        runs = [r for r in self.read_log("run-log.csv") if r["time"][:7] == month]
        offers = [r for r in self.read_log("offers.csv") if r["time"][:7] == month]
        yes = {r["opening"] for r in offers if r["status"] == "yes"}
        value = 0.0
        prices = {30: 70, 45: 90, 60: 115, 90: 160}
        empty = [a for a in late if not a.get("rebooked_into")]
        for a in empty:
            try:
                value += prices.get(int(float(a.get("length_min") or 60)), 115)
            except ValueError:
                value += 115
        return {
            "month": month,
            "openings": len(late), "late_cancels": len(late_cancels),
            "no_shows": len(late) - len(late_cancels),
            "refilled": len(refilled),
            "rate": round(100 * len(refilled) / len(late)) if late else 0,
            "empty_value": round(value),
            "program_runs": len({r["opening"] for r in runs}),
            "names_shown": sum(len([x for x in r["names_shown"].split(";") if x.strip()]) for r in runs),
            "offers_made": len({(r["opening"], r["person"]) for r in offers if r["status"] in ("called", "voicemail", "yes", "no")}),
            "filled_by_program": len(yes),
            "source": os.path.basename(c.appointments_path) if c.appointments_path else "",
        }

    # ------------------------------------------------------------ add-ons (features 40-42)
    UNLOCK_SALT = "kettle-stone-waitlist-match|kneadly-direct|v1"

    @classmethod
    def valid_unlock(cls, code):
        code = (code or "").strip().upper().replace(" ", "")
        parts = code.split("-")
        if len(parts) != 4 or parts[0] != "KSW":
            return False
        body = "-".join(parts[:3])
        check = hashlib.sha256((cls.UNLOCK_SALT + body).encode()).hexdigest()[:4].upper()
        return parts[3] == check

    def addons(self):
        s, c = self.load()
        g = lambda sec, key, d="": s.get(s.addons, sec, key, d)
        text_on = plain(g("text_offers", "enabled", "no")) in ("yes", "on", "true")
        provider = plain(g("text_offers", "provider", "none"))
        unlocked = self.valid_unlock(g("kneadly_direct", "unlock_code", ""))
        connected = unlocked and bool(g("kneadly_direct", "api_key", "")) and bool(g("kneadly_direct", "account_id", ""))
        return {
            "daily_report": {"on": c.daily_report_fresh(self._max_age(s)),
                             "text": "On - using today's booking file." if c.daily_report_fresh(self._max_age(s))
                             else "Off - waiting for Marc to switch on the daily Kneadly report."},
            "text_offers": {"on": text_on and provider not in ("", "none"),
                            "text": ("On" if text_on and provider not in ("", "none") else
                                     "Off - messages are only previewed, never sent. Needs Marc's approval, "
                                     "a texting service, slot holds and text consent.")},
            "second_reminder": {"on": plain(g("second_reminder", "kneadly_reminder_on", "no")) in ("yes", "on", "true"),
                                "text": "This is a Kneadly setting. Julie switches it on in Kneadly, then sets "
                                        "kneadly_reminder_on = yes in settings/addons.ini."},
            "kneadly_direct": {"unlocked": unlocked, "connected": connected,
                               "text": ("Locked - optional add-on. Needs the higher Kneadly plan. "
                                        "Enter an unlock code to switch it on." if not unlocked else
                                        "Unlocked. Waiting for the Kneadly connection details (api_key and "
                                        "account_id in settings/addons.ini) from Kneadly support."
                                        if not connected else
                                        "Unlocked and set up. The program reads bookings straight from Kneadly "
                                        "instead of the saved file.")},
        }

    def unlock(self, code):
        if not self.valid_unlock(code):
            raise FileProblem("That unlock code is not valid. Please check it and try again.")
        path = os.path.join(self.settings_dir, "addons.ini")
        with open(path, encoding="utf-8-sig") as fh:
            lines = fh.read().splitlines()
        out, in_sec, done = [], False, False
        for ln in lines:
            st = ln.strip()
            if st.startswith("["):
                in_sec = st.lower() == "[kneadly_direct]"
            if in_sec and st.lower().startswith("unlock_code") and not done:
                ln = f"unlock_code = {code.strip().upper()}"
                done = True
            out.append(ln)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")
        return self.addons()

    def preview_text(self, opening_key, pid):
        """Feature 40: build the offer text. While text offers are off it is only previewed."""
        s, c = self.load()
        person = next((p for p in c.persons if p.pid == pid), None)
        if not person:
            raise FileProblem("Person not found on the list.")
        date_s, time_s, therapist = opening_key.split(" ", 2)
        d = dt.date.fromisoformat(date_s)
        t = dt.time.fromisoformat(time_s)
        day = "today" if d == self.today() else ("tomorrow" if d == self.today() + dt.timedelta(days=1)
                                                 else f"{DAYS_ORDER[d.weekday()]} {d:%b} {d.day}")
        template = s.get(s.addons, "text_offers", "template",
                         "Kettle & Stone: an opening {day} at {time} with {therapist}. Reply YES to take it, or NO.")
        msg = template.format(day=day, time=t.strftime("%I:%M").lstrip("0"), therapist=s.first_name(therapist))
        words = {w.strip(".,:;!?()").lower() for w in msg.split()}
        if words & (s.health_words - {"back", "low", "light", "left", "right", "side", "l", "due", "form", "intake"}):
            raise FileProblem("This message would include a health word, so it was blocked. Check the template.")
        info = self.addons()["text_offers"]
        if not info["on"]:
            result = "preview only - not sent (text offers are off)"
        else:
            result = "not sent - no texting service connected yet"
        consent = "prefers text (Tanya's note)" if person.contact == "prefers text" else \
            "no text consent on file - call instead"
        self.append_log("messages.csv", {"time": self.now().isoformat(sep=" "), "opening": opening_key,
                                         "person": pid, "name": person.name, "message": msg, "result": result})
        return {"message": msg, "result": result, "consent": consent}

    # ------------------------------------------------------------ clean-up (feature 29)
    def cleanup(self):
        for f in glob.glob(os.path.join(self.work, "*")):
            try:
                if os.path.isdir(f):
                    shutil.rmtree(f)
                elif not f.endswith("server.json"):
                    os.remove(f)
            except OSError:
                pass
