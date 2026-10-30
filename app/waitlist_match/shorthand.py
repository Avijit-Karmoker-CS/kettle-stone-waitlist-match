"""Reads Tanya's shorthand notes (feature 4) into clear needs.

Every rule below is written for the way the front desk writes the notebook:
"J only", "AB Dave", "AM", "90", "needs 3h", "next day only", "not Thurs" ...
Anything the reader does not understand is reported (feature 6), and a line
with a word that looks like it matters but is not understood is held back
for checking by hand (features 14 to 16) instead of guessed.
"""
import datetime as dt
import re
from dataclasses import dataclass, field

from .files import MONTHS
from .settings import plain

DAYS_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAYS = set(DAYS_ORDER[:5])
NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
            "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "noon": 12}
NUM = r"(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|noon)"
TIME = NUM + r"(?::(\d\d))?\s*(am|pm|a\.m\.?|p\.m\.?)?"
MONTH_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
DATE = (r"(?:end of\s+" + MONTH_RE + r"|" + MONTH_RE + r"\s+(\d{1,2})(?:st|nd|rd|th)?"
        r"|(\d{1,2})/(\d{1,2}))")
LENGTHS = r"(30|45|60|75|90|120)"
HOURS_WORD = r"(?:h|hr|hrs|hour|hours)"
CLOSE_WORDS = ["morning", "mornings", "afternoon", "afternoons", "evening", "evenings",
               "weekday", "weekdays", "weekend", "weekends", "only", "after", "before",
               "until", "female", "notice", "lunch"]


@dataclass
class Needs:
    """What one notebook line says. None means 'not said on this line'."""
    therapists: set = None          # allowed therapists (full names)
    not_therapists: set = None      # excluded therapists
    female_only: bool = None
    male_only: bool = None
    any_therapist: bool = False     # line says "any"
    prenatal: bool = False
    days: set = None                # allowed days
    not_days: set = None            # excluded days
    allow_days: set = None          # "can do Thurs now": a day that is no longer excluded
    earliest: dt.time = None        # start at or after
    latest_start: dt.time = None    # start at or before
    end_by: dt.time = None          # finished by
    lengths: set = None             # acceptable lengths in minutes
    lengths_add: bool = False       # "60 ok too"
    notice_hours: float = None
    next_day: bool = None
    available_from: dt.date = None
    until: dt.date = None
    out_of_date: str = None         # reason, from words like "moved"
    new_client: bool = False
    contact: str = None             # "prefers text", "landline"
    doubts: list = field(default_factory=list)     # words that may matter
    unknown: list = field(default_factory=list)    # words ignored as comments
    understood_anything: bool = False


def _num(token):
    token = plain(token)
    if token in NUMWORDS:
        return NUMWORDS[token]
    try:
        return int(token)
    except ValueError:
        return None


def _hour(h, minute, ampm):
    if h is None:
        return None
    m = int(minute or 0)
    ap = (ampm or "").replace(".", "")
    if ap.startswith("p") and h < 12:
        h += 12
    elif ap.startswith("a"):
        h = 0 if h == 12 else h
    elif 1 <= h <= 7:  # clinic is open 9 to 8: "after 5" means 5 p.m.
        h += 12
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return dt.time(h, m)


def _date_from(groups, ref):
    """groups from DATE: (end_month, month, day, num_month, num_day)."""
    end_month, month, day, n_month, n_day = groups
    try:
        if end_month:
            mo = MONTHS[end_month[:3]]
            y = _year_for(mo, ref)
            nxt = dt.date(y + (mo == 12), mo % 12 + 1, 1)
            return nxt - dt.timedelta(days=1)
        if month:
            mo = MONTHS[month[:3]]
            return dt.date(_year_for(mo, ref), mo, int(day))
        if n_month:
            mo, d = int(n_month), int(n_day)
            return dt.date(_year_for(mo, ref), mo, d)
    except (ValueError, KeyError):
        return None
    return None


def _year_for(month, ref):
    # A date in a note is close to the day the line was written.
    if month < ref.month - 6:
        return ref.year + 1
    if month > ref.month + 6:
        return ref.year - 1
    return ref.year


def _edit1(a, b):
    if abs(len(a) - len(b)) > 1 or a == b:
        return a == b
    if len(a) == len(b):
        diff = sum(x != y for x, y in zip(a, b))
        if diff == 1:
            return True
        # swapped letters
        idx = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        return len(idx) == 2 and a[idx[0]] == b[idx[1]] and a[idx[1]] == b[idx[0]]
    if len(a) > len(b):
        a, b = b, a
    for i in range(len(b)):
        if b[:i] + b[i + 1:] == a:
            return True
    return False


class ShorthandReader:
    def __init__(self, settings):
        self.s = settings
        days = sorted(settings.day_words, key=len, reverse=True)
        self.DAY = r"(?:" + "|".join(re.escape(d) for d in days) + r")"
        ths = sorted(settings.therapist_words, key=len, reverse=True)
        self.TH = r"(?:" + "|".join(re.escape(t) for t in ths) + r")(?:'s)?"
        self.keywords = set(settings.therapist_words) | set(settings.day_words) | set(CLOSE_WORDS)

    # ------------------------------------------------------------ helpers
    def _take(self, state, pattern, handler=None):
        """Find pattern in the working text; consume each match the handler accepts.

        When the handler turns a match down, the search starts again one letter
        later, so an overlapping match is not missed."""
        rx = re.compile(pattern)
        pos = 0
        hits = []
        while True:
            m = rx.search(state["work"], pos)
            if not m:
                break
            if m.end() == m.start():
                pos = m.end() + 1
                continue
            ok = handler(m) if handler else True
            if ok is False:
                pos = m.start() + 1
                continue
            hits.append(m)
            w = state["work"]
            state["work"] = w[:m.start()] + " " * (m.end() - m.start()) + w[m.end():]
            state["any"] = True
            pos = m.end()
        return hits

    def _days_in(self, text):
        out = set()
        for tok in re.findall(r"[a-z]+", text):
            if tok in self.s.day_words:
                out.add(self.s.day_words[tok])
        return out

    def _therapists_in(self, text):
        out = set()
        for tok in re.findall(r"[a-z]+(?:'s)?", text):
            tok = tok[:-2] if tok.endswith("'s") else tok
            if tok in self.s.therapist_words:
                out.add(self.s.therapist_words[tok])
        return out

    # --------------------------------------------------------------- read
    def read(self, note, line_date):
        n = Needs()
        text = plain(note)
        ref = line_date or dt.date.today()
        state = {"work": text, "any": False}
        T = self._take

        # Out of date words (feature 8). Not consumed: they are reasons, not limits.
        for phrase, reason in self.s.stale_phrases.items():
            if re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", text):
                n.out_of_date = reason
                break
        for phrase in sorted(self.s.stale_phrases, key=len, reverse=True):
            T(state, r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])")

        # Pregnancy -> clinic prenatal rule (feature 12).
        def preg(m):
            n.prenatal = True
        T(state, r"\bpregnan\w*|\bprenatal\b|\b\d(?:st|nd|rd|th)\s*tri\w*", preg)
        if n.prenatal:  # "30 wks" only means pregnancy when pregnancy is mentioned
            T(state, r"\b\d{1,2}\s*(?:wks?|weeks?)\b(?:\s*along)?")

        def newc(m):
            n.new_client = True
        T(state, r"\bnew\s+(?:client|patient|pt)\b|\bfirst (?:visit|time)\b|\bnever been\b", newc)

        # How to reach them (shown as a hint, never a health detail).
        def text_pref(m):
            n.contact = "prefers text"
        T(state, r"\b(?:text|txt)(?:s|ing)?\b(?:\s*(?:only|pls|please|don'?t call|dont call|not call|no calls?))?", text_pref)

        def landline(m):
            n.contact = n.contact or "landline - call"
        T(state, r"\blandline\b", landline)
        T(state, r"\bcall (?:his|her|their) (?:son|daughter|husband|wife|partner|mom|mum|dad|mother|father)\b",
          lambda m: setattr(n, "contact", "see notebook before calling"))

        # "Kelsey says ..." is a source, not a therapist choice.
        T(state, r"\b" + self.TH + r"\s+(?:says|said|told|thinks|mentioned)\b")

        # ---------------------------------------------------- dates
        def away(m):
            d = _date_from(m.groups()[-5:], ref)
            if not d:
                return False
            n.available_from = d + dt.timedelta(days=1)
        T(state, r"\b(?:away|gone|out of town|hunting|travel\w*|vacation|holidays?|on leave)\b[^-;|,.]*?"
                 r"\b(?:til|till|until|thru|through|to)\s+" + DATE, away)

        def until(m):
            d = _date_from(m.groups()[-5:], ref)
            if not d:
                return False
            n.until = d
        T(state, r"\b(?:only\s+)?(?:here\s+)?(?:til|till|until|up to|through)\s+" + DATE, until)

        def before(m):
            d = _date_from(m.groups()[-5:], ref)
            if not d:
                return False
            n.until = d - dt.timedelta(days=1)
        T(state, r"\b(?:before|by)\s+(?:(?:her|his|the|my|their)\s+)?(?:[a-z]+\s+)?" + DATE, before)

        def from_date(m):
            d = _date_from(m.groups()[-5:], ref)
            if not d:
                return False
            n.available_from = d
        T(state, r"\b(?:from|starting|after|back on|back)\s+" + DATE, from_date)

        # "called 10/9" is a contact note.
        T(state, r"\b(?:called|phoned|spoke|talked|since|on)\s+" + DATE)

        # ---------------------------------------------------- notice
        def nextday(m):
            n.next_day = True
        T(state, r"\bnext[- ]day(?: only)?\b|\b(?:the )?(?:day|night) before\b|\bday'?s notice\b"
                 r"|\b24\s*h(?:rs?|ours?)?\s*notice\b", nextday)

        def need_hours(m):
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else a
            n.notice_hours = max(a, b)
        T(state, r"\b(?:needs?|requires?|wants?|at least)\s+(?:at least\s+)?(\d+(?:\.\d+)?)"
                 r"(?:\s*(?:-|to|or)\s*(\d+(?:\.\d+)?))?\s*" + HOURS_WORD + r"\b(?:\s*notice)?", need_hours)
        T(state, r"\b(?:needs?|requires?)\s+(?:an|one|1)\s+(?:hr|hour)\b(?:\s*notice)?",
          lambda m: setattr(n, "notice_hours", 1.0))

        def come_min(m):
            n.notice_hours = int(m.group(1)) / 60
        T(state, r"\b(?:can |could )?come(?: in)?(?: within)?\s+(\d{1,3})\s*(?:min|mins|minutes)\b", come_min)
        T(state, r"\b(?:can |could )?come(?: in)?(?: within)?\s+(?:an|one|1)\s*(?:hr|hour)\b",
          lambda m: setattr(n, "notice_hours", 1.0))

        def come_hours(m):
            n.notice_hours = float(m.group(1))
        T(state, r"\b(?:can |could )?come(?: in)?(?: within)?\s+(\d+(?:\.\d+)?)\s*" + HOURS_WORD + r"\b", come_hours)
        T(state, r"\b(\d{1,3})\s*(?:min|mins|minutes)\s*notice(?:\s*(?:ok|fine|is fine))?",
          lambda m: setattr(n, "notice_hours", int(m.group(1)) / 60))
        T(state, r"\b(\d+(?:\.\d+)?)\s*" + HOURS_WORD + r"\s*notice\b",
          lambda m: setattr(n, "notice_hours", float(m.group(1))))
        T(state, r"\b(?:can )?come quick(?:ly)?\b|\bshort notice (?:ok|fine)\b|\bon short notice\b",
          lambda m: setattr(n, "notice_hours", 0.5))
        T(state, r"\bsame day (?:ok|fine)\b")

        # ---------------------------------------------------- times
        def setmax(attr, value):
            cur = getattr(n, attr)
            setattr(n, attr, value if cur is None else max(cur, value))

        def setmin(attr, value):
            cur = getattr(n, attr)
            setattr(n, attr, value if cur is None else min(cur, value))

        def window(m):
            g = m.groups()
            t1 = _hour(_num(g[0]), g[1], g[2])
            t2 = _hour(_num(g[3]), g[4], g[5])
            if not t1 or not t2:
                return False
            if t2 <= t1 and t2.hour < 12:  # "12-1" means 12:00 to 1 p.m.
                t2 = dt.time(t2.hour + 12, t2.minute) if t2.hour + 12 <= 23 else t2
            if t2 <= t1:
                return False
            setmax("earliest", t1)
            setmin("end_by", t2)
        T(state, r"\b(?:lunch\w*\s*)?(?:between\s+)?" + TIME + r"\s*(?:-|to|and)\s*" + TIME + r"(?!\s*(?:" + HOURS_WORD + r"|min))\b", window)

        def not_before(m):
            t = _hour(_num(m.group(1)), m.group(2), m.group(3))
            if not t:
                return False
            setmax("earliest", t)
        T(state, r"\b(?:not before|not b4|no earlier than|can'?t (?:do )?before|cant (?:do )?before|not (?:till|til|until))\s+" + TIME, not_before)
        T(state, r"\b(?:after|from|starting(?: at)?|at or after)\s+" + TIME + r"(?!\s*(?:" + HOURS_WORD + r"|min|wk|week))\b", not_before)

        def end_by(m):
            t = _hour(_num(m.group(1)), m.group(2), m.group(3))
            if not t:
                return False
            setmin("end_by", t)
        T(state, r"\b(?:(?:has|needs|have|must) to be\s+)?(?:done|finished|out|gone|home|leave)\s+by\s+" + TIME, end_by)
        T(state, r"\b(?:before|b4|til|till|until)\s+" + TIME + r"(?!\s*(?:" + HOURS_WORD + r"|min))\b", end_by)

        def latest(m):
            t = _hour(_num(m.group(1)), m.group(2), m.group(3))
            if not t:
                return False
            setmin("latest_start", t)
        T(state, r"\b(?:not after|no later than|can'?t (?:do )?after|cant (?:do )?after|latest)\s+" + TIME, latest)

        T(state, r"\blunch\w*\b", lambda m: (setmax("earliest", dt.time(12, 0)), setmin("end_by", dt.time(13, 0))))
        T(state, r"\b(?:am|a\.m\.|mornings?|morn)\b(?:\s*only)?", lambda m: setmin("latest_start", dt.time(11, 59)))
        T(state, r"\b(?:pm|p\.m\.|afternoons?|aft)\b(?:\s*only)?", lambda m: setmax("earliest", dt.time(12, 0)))
        T(state, r"\b(?:evenings?|eves?|nights?)\b(?:\s*only)?", lambda m: setmax("earliest", dt.time(17, 0)))

        # ---------------------------------------------------- days
        def add_days(target, days):
            cur = getattr(n, target) or set()
            setattr(n, target, cur | days)
        T(state, r"\b(?:wkdays?|weekdays?|week days?|mon\s*-\s*fri|m-f)\b", lambda m: add_days("days", set(WEEKDAYS)))
        T(state, r"\b(?:wkends?|weekends?)\b", lambda m: add_days("days", {"Sat", "Sun"}))
        DAYLIST = self.DAY + r"\b(?:\s*(?:/|,|or|and|&|\+)\s*" + self.DAY + r"\b)*"
        T(state, r"\b(?:can do|can now do|can also do|ok for|okay for|can make|now ok for)\s+(" + DAYLIST + r")(?:\s*(?:now|too|also|as well|again))?",
          lambda m: add_days("allow_days", self._days_in(m.group(1))))
        T(state, r"\b(?:not|no|except|can'?t do|cant do|can'?t|cant|never|but not)\s+(" + DAYLIST + r")",
          lambda m: add_days("not_days", self._days_in(m.group(1))))
        T(state, r"\b" + DAYLIST + r"(?:\s*only)?", lambda m: add_days("days", self._days_in(m.group(0))))

        # ---------------------------------------------------- therapists
        T(state, r"\b" + self.TH + r"\s*(?:pref|prefd|preferred|prefers|if poss\w*|ideally|would be nice)\b")
        THLIST = self.TH + r"\b(?:\s*(?:/|,|or|and|&|\+)\s*" + self.TH + r"\b)*"

        def not_th(m):
            got = self._therapists_in(m.group(1))
            if not got:
                return False
            n.not_therapists = (n.not_therapists or set()) | got
        T(state, r"\b(?:anyone but|any but|anybody but|ab|not|no|except|never|but not)\s+(" + THLIST + r")", not_th)

        def female(m):
            n.female_only = True
        T(state, r"\b(?:any\s+)?(?:female|women|woman|lady|ladies)(?:\s+(?:only|therapist|rmt))?\b", female)
        T(state, r"\b(?:any\s+)?(?:male|man|men)\s+(?:only|therapist|rmt)\b",
          lambda m: setattr(n, "male_only", True))

        def pos_th(m):
            got = self._therapists_in(m.group(0))
            if not got:
                return False
            n.therapists = (n.therapists or set()) | got
        T(state, r"\b" + THLIST + r"(?:\s*only)?", pos_th)

        def any_th(m):
            n.any_therapist = True
        T(state, r"\b(?:any(?:one|body)?(?:\s+(?:therapist|rmt))?)\b(?:\s+(?:is )?(?:ok|fine))?", any_th)

        # ---------------------------------------------------- lengths
        def add_len(values):
            n.lengths = (n.lengths or set()) | set(values)
        T(state, r"\b(?:can do|could do|maybe)\s+" + LENGTHS + r"\s*(?:min\w*)?\s+if\b")  # only if ... : ignored
        T(state, r"\b" + LENGTHS + r"\s*(?:min\w*)?\s*only\b", lambda m: setattr(n, "lengths", {int(m.group(1))}))
        T(state, r"\b" + LENGTHS + r"\s*(?:min\w*)?\s*(?:or|/|-|to)\s*" + LENGTHS + r"\s*(?:min\w*)?\b"
                 r"(?:\s*(?:ok|fine|is fine))?",
          lambda m: add_len([int(m.group(1)), int(m.group(2))]))
        T(state, r"\b" + LENGTHS + r"\s*(?:min\w*)?\s*(?:if poss\w*|pref\w*|ideally)",
          lambda m: add_len([int(m.group(1))]))

        def too(m):
            add_len([int(m.group(1))])
            n.lengths_add = True
        T(state, r"\b" + LENGTHS + r"\s*(?:min\w*)?\s*(?:ok|fine|is fine)?\s*(?:too|also|as well)\b", too)
        T(state, r"\b(?:1\.5|one and a half)\s*" + HOURS_WORD + r"\b|\bhour and a half\b", lambda m: add_len([90]))
        T(state, r"\bhalf (?:an )?hour\b", lambda m: add_len([30]))
        T(state, r"\b(?:1|one|an)\s*(?:hr|hour)\b(?:\s*(?:ok|fine))?", lambda m: add_len([60]))
        T(state, r"\b2\s*(?:hrs|hours)\b(?!\s*notice)", lambda m: add_len([120]))
        T(state, r"\b" + LENGTHS + r"\s*(?:min\w*)?\b(?:\s*(?:ok|fine))?", lambda m: add_len([int(m.group(1))]))

        # Dates not tied to a limit: outside brackets they may matter -> doubt.
        loose_dates = []
        T(state, r"\b" + DATE, lambda m: loose_dates.append(m.start()))
        T(state, r"\bthe\s+\d{1,2}(?:st|nd|rd|th)\b", lambda m: loose_dates.append(m.start()))

        n.understood_anything = state["any"]
        self._leftovers(n, text, state["work"], loose_dates)
        return n

    def _leftovers(self, n, original, work, loose_dates):
        # Positions inside (brackets) are comments.
        inside = [False] * len(original)
        depth = 0
        for i, ch in enumerate(original):
            if ch == "(":
                depth += 1
            inside[i] = depth > 0
            if ch == ")" and depth:
                depth -= 1
        for pos in loose_dates:
            if not inside[pos]:
                n.doubts.append("date")
        for m in re.finditer(r"[a-z0-9][a-z0-9']*", work):
            tok = m.group(0)
            word = tok[:-2] if tok.endswith("'s") else tok
            if word in self.s.health_words:
                continue  # never reported, never shown
            if word in self.s.ignore_words or tok in self.s.ignore_words:
                continue
            in_brackets = inside[m.start()]
            if in_brackets:
                n.unknown.append(word)
                continue
            if any(c.isdigit() for c in word):
                n.doubts.append(word)
            elif len(word) <= 3:
                n.doubts.append(word)
            elif any(len(k) >= 4 and (_edit1(word, k) or (len(word) >= 3 and k.startswith(word)))
                     for k in self.keywords):
                n.doubts.append(word)
            else:
                n.unknown.append(word)
