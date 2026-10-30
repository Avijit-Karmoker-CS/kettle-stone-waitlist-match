"""The matching engine: clean the waitlist, then find who fits an opening."""
import datetime as dt
import os
import re
from dataclasses import dataclass, field

from .files import (FileProblem, files_like, newest_file, parse_date, parse_datetime, parse_line_date,
                    parse_number, parse_time, phone_digits, pretty_phone, read_table)
from .settings import plain
from .shorthand import DAYS_ORDER, Needs, ShorthandReader

CANCELLED = {"cancelled", "canceled", "late cancel", "late cancellation", "no-show", "no show", "noshow"}


# ------------------------------------------------------------------ models
@dataclass
class Line:
    number: int
    label: str          # "W12"
    added: dt.date
    name: str
    phone: str          # digits
    phone_raw: str
    note: str
    needs: Needs


@dataclass
class Person:
    pid: str                          # label of the newest line, e.g. "W51"
    lines: list = field(default_factory=list)
    name: str = ""
    phone: str = ""
    first_asked: dt.date = None
    last_contact: dt.date = None
    # merged needs
    therapists: set = None
    not_therapists: set = field(default_factory=set)
    female_only: bool = False
    male_only: bool = False
    prenatal: bool = False
    days: set = None
    not_days: set = field(default_factory=set)
    earliest: dt.time = None
    latest_start: dt.time = None
    end_by: dt.time = None
    lengths: set = None
    notice_hours: float = None
    next_day: bool = False
    available_from: dt.date = None
    until: dt.date = None
    new_client: bool = False
    contact: str = None
    doubts: list = field(default_factory=list)
    # status
    status: str = "active"            # active | out_of_date | hold
    reason: str = ""


@dataclass
class Opening:
    key: str
    therapist: str
    date: dt.date
    start: dt.time
    length: int
    kind: str = "late cancel"
    cancelled_at: dt.datetime = None
    notice_hours: float = None
    label: str = ""                   # e.g. "O05" from a file

    @property
    def is_no_show(self):
        k = plain(self.kind)
        return "no-show" in k or "no show" in k or k == "noshow"

    @property
    def day(self):
        return DAYS_ORDER[self.date.weekday()]

    def describe(self, settings):
        first = settings.first_name(self.therapist)
        t = self.start.strftime("%I:%M").lstrip("0")
        return f"{first} · {self.day} {self.date.strftime('%b')} {self.date.day} · {t} · {self.length} min"


# ------------------------------------------------------------------ helpers
def _t(t):
    return t.strftime("%I:%M %p").lstrip("0").replace(":00", "").lower().replace(" ", "")


def _d(day):
    return f"{day:%b} {day.day}"


def _hours_text(h):
    if h is None:
        return ""
    if h < 1:
        return f"{int(round(h * 60))} min notice"
    return f"{h:g}h notice"


def name_parts(name):
    words = [w for w in re.split(r"[\s]+", plain(name).replace(".", " ")) if w]
    if not words:
        return "", ""
    return words[0], " ".join(words[1:])


def _surname_key(s):
    return re.sub(r"[^a-z]", "", plain(s))


def _close(a, b):
    """Two different surnames that look alike (for the uncertain flag)."""
    if not a or not b or a == b:
        return False
    if a.startswith(b) or b.startswith(a):
        return True
    # edit distance <= 1
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    if len(a) > len(b):
        a, b = b, a
    return any(b[:i] + b[i + 1:] == a for i in range(len(b)))


def months_before(day, months):
    y, m = day.year, day.month - months
    while m <= 0:
        m += 12
        y -= 1
    import calendar
    last = calendar.monthrange(y, m)[1]
    return dt.date(y, m, min(day.day, last))


# ------------------------------------------------------------------ engine
class Clinic:
    """Everything loaded from the Data folder for one run."""

    def __init__(self, settings, data_folder, today=None, now=None):
        self.s = settings
        self.data = data_folder
        self.today = today or dt.date.today()
        self.now = now or dt.datetime.combine(self.today, dt.datetime.now().time())
        self.reader = ShorthandReader(settings)
        self.problems = []      # shown on the home screen
        self.warnings = []
        self.lines = []
        self.persons = []
        self.appointments = []
        self.waitlist_path = None
        self.appointments_path = None
        self.openings_path = None
        self.file_openings = []
        self._load()

    # ------------------------------------------------------------- loading
    def _pick(self, words, label):
        """Use the newest file of one kind; warn when older ones are still in Data."""
        found = files_like(self.data, words)
        if len(found) > 1:
            older = ", ".join(os.path.basename(f) for f in found[1:])
            self.warnings.append(f"More than one {label} file in the Data folder. Using the newest: "
                                 f"{os.path.basename(found[0])}. Move the older one out of Data: {older}.")
        return found[0] if found else None

    def _load(self):
        self.waitlist_path = self._pick(["waitlist", "wait list", "wait-list"], "waitlist")
        if not self.waitlist_path:
            self.problems.append("No waitlist file in the Data folder. Save the typed waitlist "
                                 "there as CSV (name it waitlist.csv).")
        else:
            try:
                self._load_waitlist(self.waitlist_path)
            except FileProblem as exc:
                self.problems.append(str(exc))
        # Booking exports add up: an older export still shows who got in earlier.
        # Read them all, newest first; the same appointment in two files counts once.
        booking_files = files_like(self.data, ["appointment", "booking", "export", "kneadly",
                                               "daily-report", "daily report"])
        self.appointments_paths = booking_files
        self.appointments_path = booking_files[0] if booking_files else None
        if not booking_files:
            self.warnings.append("No booking export in the Data folder. People who booked since "
                                 "joining the list cannot be found until Julie saves one there.")
        seen = set()
        for path in booking_files:
            try:
                self._load_appointments(path, seen)
            except FileProblem as exc:
                self.problems.append(str(exc))
        self.openings_path = self._pick(["late-opening", "late opening", "openings"], "openings")
        if self.openings_path:
            try:
                self._load_openings(self.openings_path)
            except FileProblem as exc:
                self.problems.append(str(exc))
        self._build_people()

    def _load_waitlist(self, path):
        rows = read_table(path, "waitlist", self.s)
        for i, r in enumerate(rows, start=1):
            num = parse_number(r.get("line"))
            number = int(num) if num else i
            added = parse_line_date(r.get("added", ""), self.today)
            needs = self.reader.read(r.get("notes", ""), added)
            self.lines.append(Line(number, f"W{number:02d}", added, r.get("name", "").strip(),
                                   phone_digits(r.get("phone", "")), r.get("phone", ""),
                                   r.get("notes", ""), needs))

    def _load_appointments(self, path, seen=None):
        seen = set() if seen is None else seen
        rows = read_table(path, "appointments", self.s)
        for r in rows:
            aid = (r.get("appointment_id") or "").strip()
            if aid:
                if aid in seen:
                    continue
                seen.add(aid)
            r["_date"] = parse_date(r.get("date"))
            r["_start"] = parse_time(r.get("start"))
            r["_booked"] = parse_datetime(r.get("booked_at"))
            r["_cancelled"] = parse_datetime(r.get("cancelled_at"))
            r["_status"] = plain(r.get("status"))
            r["_first"], r["_last"] = name_parts(r.get("client_name", ""))
            self.appointments.append(r)

    def _load_openings(self, path):
        rows = read_table(path, "openings", self.s)
        for i, r in enumerate(rows, start=1):
            therapist = self.therapist_name(r.get("therapist", ""))
            date = parse_date(r.get("date"))
            start = parse_time(r.get("start"))
            if not (therapist and date and start):
                self.warnings.append(f"Opening row {i} in {os.path.basename(path)} is missing the "
                                     "therapist, date or time and was skipped.")
                continue
            length = int(parse_number(r.get("length_min"), self.s.default_length))
            op = self.make_opening(therapist, date, start, length, r.get("kind") or "late cancel",
                                   parse_datetime(r.get("cancelled_at")),
                                   parse_number(r.get("hours_notice")), label=r.get("opening_id") or f"O{i:02d}")
            self.file_openings.append(op)

    def therapist_name(self, text):
        p = plain(text)
        for t in self.s.therapists:
            if plain(t) == p:
                return t
        return self.s.therapist_by_first(p.split()[0] if p else "")

    def make_opening(self, therapist, date, start, length, kind="late cancel", cancelled_at=None,
                     notice_hours=None, label=""):
        slot = dt.datetime.combine(date, start)
        if cancelled_at and notice_hours is None:
            notice_hours = (slot - cancelled_at).total_seconds() / 3600
        if notice_hours is None:
            notice_hours = 0.0
        key = f"{date.isoformat()} {start.strftime('%H:%M')} {therapist}"
        return Opening(key, therapist, date, start, int(length), kind, cancelled_at,
                       round(notice_hours, 2), label)

    # ------------------------------------------------------------ people
    def _same_person(self, person, line):
        known = max((ln.name for ln in person.lines), key=len)
        f1, l1 = name_parts(known)
        f2, l2 = name_parts(line.name)
        if not self.s.first_names_match(f1, f2):
            return False
        a, b = _surname_key(l1), _surname_key(l2)
        if not a or not b:
            return True
        return a == b or a[0] == b[0] and (len(a) == 1 or len(b) == 1)

    def _build_people(self):
        people = []
        by_phone = {}
        for line in self.lines:
            target = None
            if line.phone and line.phone in by_phone:
                target = by_phone[line.phone]
            if target is None and (not line.phone or "same" in plain(line.phone_raw)):
                for p in reversed(people):
                    if self._same_person(p, line):
                        target = p
                        break
            if target is None:
                for p in people:
                    if _surname_key(p.name) and plain(p.name) == plain(line.name):
                        target = p
                        break
            if target is None:
                target = Person(pid=line.label)
                people.append(target)
            target.lines.append(line)
            if line.phone:
                by_phone[line.phone] = target
        for p in people:
            self._merge(p)
            self._status(p)
        self.persons = people

    def _merge(self, p):
        p.lines.sort(key=lambda ln: ln.number)
        p.pid = p.lines[-1].label
        names = sorted((ln.name for ln in p.lines), key=lambda n: (len(name_parts(n)[1]) > 1, len(n)))
        p.name = names[-1]
        p.phone = next((ln.phone for ln in reversed(p.lines) if ln.phone), "")
        dates = [ln.added for ln in p.lines if ln.added]
        p.first_asked = min(dates) if dates else None
        p.last_contact = max(dates) if dates else None
        set_at = {}
        for ln in p.lines:
            n = ln.needs
            if n.therapists or n.not_therapists or n.female_only or n.male_only or n.any_therapist:
                p.therapists = set(n.therapists) if n.therapists else None
                p.not_therapists = set(n.not_therapists or ())
                p.female_only = bool(n.female_only)
                p.male_only = bool(n.male_only)
            p.prenatal = p.prenatal or n.prenatal
            p.new_client = p.new_client or n.new_client
            if n.days:
                p.days = set(n.days)
            if n.not_days:
                p.not_days = set(n.not_days) if not p.not_days else p.not_days | n.not_days
            if n.allow_days:
                p.not_days = set(p.not_days) - n.allow_days
            for attr in ("earliest", "latest_start", "end_by"):
                if getattr(n, attr) is not None:
                    setattr(p, attr, getattr(n, attr))
                    set_at[attr] = ln.number
            if n.lengths:
                p.lengths = (p.lengths or set()) | n.lengths if n.lengths_add else set(n.lengths)
            if n.notice_hours is not None or n.next_day:
                p.notice_hours = n.notice_hours
                p.next_day = bool(n.next_day)
            if n.available_from:
                p.available_from = max(filter(None, [p.available_from, n.available_from]))
            if n.until:
                p.until = n.until
            if n.contact:
                p.contact = n.contact
            for d in n.doubts:
                p.doubts.append((ln.label, d))
        # A newer time limit that contradicts an older one wins.
        if p.earliest and p.latest_start and p.earliest > p.latest_start:
            if set_at.get("earliest", 0) > set_at.get("latest_start", 0):
                p.latest_start = None
            else:
                p.earliest = None
        if p.days and p.not_days:
            p.days = p.days - p.not_days or p.days

    def _status(self, p):
        latest = p.lines[-1]
        if latest.needs.out_of_date:
            p.status, p.reason = "out_of_date", latest.needs.out_of_date.capitalize()
            return
        if p.until and p.until < self.today:
            p.status, p.reason = "out_of_date", f"Date passed (only until {_d(p.until)})"
            return
        cutoff = months_before(self.today, self.s.stale_months)
        if p.last_contact and p.last_contact < cutoff:
            p.status = "out_of_date"
            p.reason = f"No contact since {_d(p.last_contact)} (over {self.s.stale_months} months)"
            return
        sure, unsure = self._bookings_since(p)
        if sure:
            a = sure[0]
            p.status = "out_of_date"
            who = self.s.first_name(self.therapist_name(a.get("therapist", "")) or a.get("therapist", ""))
            p.reason = (f"Booked since joining the list: booked {_d(a['_booked'])} "
                        f"with {who} for {_d(a['_date'])}")
            return
        if unsure:
            a = unsure[0]
            p.status = "hold"
            p.reason = (f"Possible booking found for {a.get('client_name')} on {_d(a['_date'])} - "
                        "please check before offering")
            return
        p.status, p.reason = "active", ""

    def _bookings_since(self, p):
        if not p.last_contact:
            return [], []
        f, l = name_parts(p.name)
        sur = _surname_key(l)
        sure, unsure = [], []
        for a in self.appointments:
            if a["_status"] in CANCELLED or not a["_booked"]:
                continue
            if a["_booked"].date() < p.last_contact:
                continue
            af, al = a["_first"], _surname_key(a["_last"])
            first_ok = self.s.first_names_match(f, af)
            if first_ok and sur and len(sur) > 1 and al == sur:
                sure.append(a)
            elif first_ok and sur and (len(sur) == 1 and al[:1] == sur or _close(al, sur)):
                # Spelled a little differently. If the desk filled it from the waitlist,
                # it is this person; otherwise hold them back for a check by hand.
                if len(sur) > 1 and "waitlist" in plain(a.get("desk_notes", "")):
                    sure.append(a)
                else:
                    unsure.append(a)
            elif al == sur and len(sur) > 1 and af[:3] == f[:3] and not first_ok:
                unsure.append(a)
        sure.sort(key=lambda a: a["_booked"])
        return sure, unsure

    # ------------------------------------------------------------ matching
    def fits(self, p, op):
        """Return (True, None) or (False, reason) for one person and one opening."""
        allowed = set(self.s.therapists)
        if p.therapists:
            allowed &= p.therapists
        allowed -= p.not_therapists
        if p.female_only:
            allowed &= self.s.female
        if p.male_only:
            allowed &= self.s.male
        if p.prenatal and self.s.prenatal:
            allowed &= self.s.prenatal
        if op.therapist not in allowed:
            return False, "therapist"
        if p.days and op.day not in p.days:
            return False, "day"
        if op.day in p.not_days:
            return False, "day"
        if p.available_from and op.date < p.available_from:
            return False, "away"
        if p.until and op.date > p.until:
            return False, "date"
        want = min(p.lengths) if p.lengths else self.s.default_length
        if op.length < want:
            return False, "length"
        if p.earliest and op.start < p.earliest:
            return False, "time"
        if p.latest_start and op.start > p.latest_start:
            return False, "time"
        if p.end_by:
            end = (dt.datetime.combine(op.date, op.start) + dt.timedelta(minutes=want)).time()
            if end > p.end_by:
                return False, "time"
        if p.next_day:
            if not op.cancelled_at or op.cancelled_at.date() >= op.date:
                return False, "notice"
        else:
            need = p.notice_hours if p.notice_hours is not None else self.s.default_notice
            if op.notice_hours + 1e-9 < need:
                return False, "notice"
        return True, None

    def reason_for(self, p):
        parts = []
        if p.prenatal and self.s.prenatal:
            allowed = set(self.s.prenatal)
            if p.therapists:
                allowed &= p.therapists
            parts.append(" or ".join(sorted(self.s.first_name(t) for t in allowed - p.not_therapists)))
        elif p.therapists:
            parts.append(" or ".join(sorted(self.s.first_name(t) for t in p.therapists)))
        elif p.female_only:
            parts.append("any female therapist")
        elif p.male_only:
            parts.append("any male therapist")
        elif p.not_therapists:
            parts.append("anyone but " + " or ".join(sorted(self.s.first_name(t) for t in p.not_therapists)))
        else:
            parts.append("any therapist")
        if p.days:
            parts.append("/".join(d for d in DAYS_ORDER if d in p.days))
        elif p.not_days:
            parts.append("not " + "/".join(d for d in DAYS_ORDER if d in p.not_days))
        times = []
        if p.earliest and p.end_by:
            times.append(f"{_t(p.earliest)}-{_t(p.end_by)}")
        else:
            if p.earliest:
                times.append("afternoons" if p.earliest == dt.time(12, 0) else f"from {_t(p.earliest)}")
            if p.latest_start:
                times.append("mornings" if p.latest_start == dt.time(11, 59) else f"start by {_t(p.latest_start)}")
            if p.end_by:
                times.append(f"done by {_t(p.end_by)}")
        parts.extend(times)
        if p.lengths:
            parts.append(" or ".join(str(x) for x in sorted(p.lengths)) + " min")
        else:
            parts.append(f"{self.s.default_length} min")
        if p.next_day:
            parts.append("day-before notice")
        elif p.notice_hours is not None:
            parts.append(_hours_text(p.notice_hours))
        return " · ".join(parts)

    def match_all(self, op):
        """Everyone who fits, in order (used to refill the list after a yes elsewhere)."""
        res = self.match(op, limit=None)
        return res["names"] + res["maybe"]

    def match(self, op, limit=-1):
        """Feature 13: up to max_names people, plus a separate maybe list."""
        if limit == -1:
            limit = self.s.max_names
        result = {"opening": op, "names": [], "maybe": [], "nobody_reason": ""}
        if op.is_no_show:
            result["nobody_reason"] = "No-show: we only know once they are 15 minutes late, so there is no time to offer it."
            return result
        candidates = []
        for p in self.persons:
            if p.status == "out_of_date":
                continue
            ok, _ = self.fits(p, op)
            if not ok:
                continue
            entry = {"pid": p.pid, "name": p.name, "phone": pretty_phone(p.phone),
                     "reason": self.reason_for(p), "contact": p.contact or "",
                     "first_asked": p.first_asked, "line": p.lines[0].number}
            why_maybe = None
            if p.status == "hold":
                why_maybe = p.reason
            elif p.doubts:
                words = ", ".join(sorted({d for _, d in p.doubts}))
                why_maybe = f"Note has words the program could not read ({words}) - check line {p.pid}"
            elif p.new_client and self.s.new_client_limits.get(op.therapist) is not None \
                    and op.notice_hours < self.s.new_client_limits[op.therapist]:
                why_maybe = f"New client - ask {self.s.first_name(op.therapist)} first"
            entry["why_maybe"] = why_maybe
            candidates.append(entry)
        candidates.sort(key=lambda e: (e["first_asked"] or dt.date.max, e["line"]))
        result["names"] = [c for c in candidates if not c["why_maybe"]][:limit]
        result["maybe"] = [c for c in candidates if c["why_maybe"]]
        if not result["names"]:
            result["nobody_reason"] = ("Nobody on the list fits this opening."
                                       if not result["maybe"] else
                                       "Nobody fits for certain. See 'check by hand' below.")
        return result

    # ------------------------------------------------------------ line status (for the answer key)
    def line_status(self):
        out = {}
        for p in self.persons:
            for ln in p.lines:
                if p.status == "out_of_date":
                    out[ln.label] = ("stale", p.reason)
                elif ln.label == p.pid:
                    out[ln.label] = ("active" if p.status == "active" else "hold", p.reason)
                else:
                    out[ln.label] = (f"duplicate of {p.pid}", "")
        return out

    # ------------------------------------------------------------ data age (feature 24)
    def data_age(self):
        if not self.appointments:
            return None
        stamps = [a["_booked"] for a in self.appointments if a["_booked"]]
        stamps += [a["_cancelled"] for a in self.appointments if a["_cancelled"]]
        if not stamps:
            return None
        newest = max(stamps)
        age_days = (self.now - newest).total_seconds() / 86400
        return newest, age_days

    def data_age_message(self):
        age = self.data_age()
        if age is None:
            return "No booking file yet: bookings made since people joined the list are not checked."
        newest, days = age
        if days <= 1.25:
            return ""
        return (f"Booking file is {int(days)} days old (newest entry {_d(newest)}). "
                f"Anyone who booked after {_d(newest)} may still show - check Kneadly before offering.")

    def daily_report_fresh(self, max_age_hours=30):
        age = self.data_age()
        return bool(age and age[1] * 24 <= max_age_hours)
