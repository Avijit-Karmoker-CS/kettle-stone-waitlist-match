"""Reads the plain-text settings files that Julie can edit with Notepad."""
import configparser
import os
import unicodedata


def plain(text):
    """Lower case, no accents, single spaces."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())


def _read(path):
    cp = configparser.ConfigParser(interpolation=None, strict=False,
                                   inline_comment_prefixes=None)
    cp.optionxform = str  # keep case of keys (therapist names)
    with open(path, encoding="utf-8-sig") as fh:
        cp.read_file(fh)
    return cp


def _list(value):
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


class Settings:
    def __init__(self, folder):
        self.folder = folder
        self.errors = []
        self.clinic = self._load("clinic.ini")
        self.columns = self._load("columns.ini")
        self.shorthand = self._load("shorthand.ini")
        self.addons = self._load("addons.ini")
        self._build()

    def _load(self, name):
        path = os.path.join(self.folder, name)
        try:
            return _read(path)
        except FileNotFoundError:
            self.errors.append(f"Settings file missing: {name}")
        except Exception as exc:  # broken edit by hand
            self.errors.append(f"Settings file {name} could not be read ({exc}).")
        return configparser.ConfigParser(interpolation=None)

    def get(self, cp, section, key, default=None):
        try:
            value = cp.get(section, key)
            return value if value.strip() != "" else default
        except Exception:
            return default

    def _build(self):
        c = self.clinic
        self.clinic_name = self.get(c, "clinic", "name", "Kettle & Stone Massage Therapy")
        self.therapists = {}
        if c.has_section("therapists"):
            for name, sex in c.items("therapists"):
                self.therapists[name.strip()] = plain(sex)
        self.female = {t for t, s in self.therapists.items() if s.startswith("f")}
        self.male = {t for t, s in self.therapists.items() if s.startswith("m")}
        self.prenatal = set(_list(self.get(c, "rules", "prenatal_therapists", "")))
        num = lambda k, d: float(self.get(c, "rules", k, d))
        self.stale_months = int(num("out_of_date_after_months", 2))
        self.still_waiting_days = int(num("still_waiting_check_after_days", 42))
        self.hard_to_place_days = int(num("hard_to_place_after_days", 28))
        self.default_length = int(num("default_length_minutes", 60))
        self.default_notice = num("default_notice_hours", 2)
        self.max_names = int(num("max_names", 3))
        self.voicemail_wait = int(num("voicemail_wait_minutes", 20))
        self.new_client_limits = {}
        if c.has_section("new_client_limits"):
            for t, h in c.items("new_client_limits"):
                try:
                    self.new_client_limits[t.strip()] = float(h)
                except ValueError:
                    pass

        s = self.shorthand
        self.therapist_words = {}
        if s.has_section("therapist_words"):
            for w, t in s.items("therapist_words"):
                self.therapist_words[plain(w)] = t.strip()
        self.day_words = {}
        if s.has_section("day_words"):
            for w, d in s.items("day_words"):
                self.day_words[plain(w)] = d.strip()[:3].title()
        self.nicknames = {}
        if s.has_section("nicknames"):
            for short, longs in s.items("nicknames"):
                group = {plain(short)} | {plain(x) for x in _list(longs)}
                for name in group:
                    self.nicknames.setdefault(name, set()).update(group)
        self.stale_phrases = {}
        if s.has_section("out_of_date_phrases"):
            for phrase, reason in s.items("out_of_date_phrases"):
                self.stale_phrases[plain(phrase)] = reason.strip()
        self.health_words = {plain(w) for w in _list(self.get(s, "health_words", "words", ""))}
        self.ignore_words = {plain(w) for w in _list(self.get(s, "ignore_words", "words", ""))}

        self.column_map = {}
        for section in ("waitlist", "appointments", "openings"):
            if self.columns.has_section(section):
                self.column_map[section] = {k: _list(v) for k, v in self.columns.items(section)}

    def first_names_match(self, a, b):
        a, b = plain(a), plain(b)
        if not a or not b:
            return False
        if a == b:
            return True
        return b in self.nicknames.get(a, set()) or a in self.nicknames.get(b, set())

    def first_name(self, therapist):
        return therapist.split()[0] if therapist else ""

    def therapist_by_first(self, text):
        p = plain(text)
        for t in self.therapists:
            if plain(t) == p or plain(t.split()[0]) == p:
                return t
        return self.therapist_words.get(p)
