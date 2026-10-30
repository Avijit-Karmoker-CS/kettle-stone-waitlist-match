"""Reading the clinic's files: CSV (preferred) or Apple Numbers."""
import csv
import datetime as dt
import glob
import os
import re

from .settings import plain


class FileProblem(Exception):
    """A problem Tanya or Julie can fix. The message is shown as written."""


MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ---------------------------------------------------------------- reading
def _clean_cell(value):
    if value is None:
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat(sep=" ") if isinstance(value, dt.datetime) else value.isoformat()
    text = str(value).strip()
    if re.fullmatch(r"-?\d+\.0", text):  # 5065550105.0 -> 5065550105
        text = text[:-2]
    return text


def _read_csv(path):
    last_error = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, newline="", encoding=enc) as fh:
                sample = fh.read(4096)
                fh.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                except csv.Error:
                    dialect = csv.excel
                rows = list(csv.reader(fh, dialect))
            return [[_clean_cell(c) for c in r] for r in rows]
        except UnicodeDecodeError as exc:
            last_error = exc
    raise FileProblem(f"{os.path.basename(path)} could not be read ({last_error}). "
                      "Please save this file as CSV.")


def _read_numbers(path):
    try:
        from numbers_parser import Document  # optional
    except Exception:
        raise FileProblem(f"{os.path.basename(path)} is a Numbers file. "
                          "Please save this file as CSV (File > Export To > CSV) "
                          "and put the CSV in the Data folder.")
    try:
        doc = Document(path)
        table = doc.sheets[0].tables[0]
        return [[_clean_cell(c) for c in r] for r in table.rows(values_only=True)]
    except Exception:
        raise FileProblem(f"{os.path.basename(path)} could not be opened. "
                          "Please save this file as CSV.")


def read_rows(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".numbers":
        rows = _read_numbers(path)
    elif ext in (".csv", ".txt", ".tsv"):
        rows = _read_csv(path)
    elif ext in (".xlsx", ".xls"):
        raise FileProblem(f"{os.path.basename(path)} is an Excel file. "
                          "Please save this file as CSV.")
    else:
        raise FileProblem(f"{os.path.basename(path)} is not a file type the program knows. "
                          "Please save this file as CSV.")
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise FileProblem(f"{os.path.basename(path)} is empty.")
    return rows


def read_table(path, kind, settings):
    """Return a list of dicts using the program's own column names.

    Stops with a clear message if a needed column is missing (feature 30).
    """
    rows = read_rows(path)
    header = [h.strip() for h in rows[0]]
    lookup = {plain(h): i for i, h in enumerate(header)}
    wanted = settings.column_map.get(kind, {})
    index = {}
    missing = []
    for canon, names in wanted.items():
        found = None
        for n in names or [canon]:
            if plain(n) in lookup:
                found = lookup[plain(n)]
                break
        if found is None:
            missing.append(canon)
        else:
            index[canon] = found
    optional = {"waitlist": {"line"},
                "appointments": {"appointment_id", "client_id", "rebooked_into", "desk_notes",
                                 "confirmation", "length_min"},
                "openings": {"opening_id", "cancelled_at", "hours_notice", "kind",
                             "length_min"}}.get(kind, set())
    hard_missing = [m for m in missing if m not in optional]
    if hard_missing:
        raise FileProblem(
            f"The {kind} file has changed: {os.path.basename(path)} has no column for "
            f"{', '.join(hard_missing)}. Export has changed - call Julie. "
            "(Julie: add the new column name in settings/columns.ini.)")
    out = []
    for r in rows[1:]:
        rec = {}
        for canon, i in index.items():
            rec[canon] = r[i].strip() if i < len(r) else ""
        out.append(rec)
    return out


# ------------------------------------------------------------ choosing files
_DATE_IN_NAME = re.compile(r"(20\d\d)[-_.]?(\d\d)[-_.]?(\d\d)")


def _name_date(path):
    dates = _DATE_IN_NAME.findall(os.path.basename(path))
    if not dates:
        return None
    y, m, d = dates[-1]  # the last date in the name is the "to" date
    try:
        return dt.date(int(y), int(m), int(d))
    except ValueError:
        return None


def _mtime(path):
    """Last change time. A Numbers file can be a folder (package): use its newest part."""
    t = os.path.getmtime(path)
    if os.path.isdir(path):
        for base, _dirs, files in os.walk(path):
            for f in files:
                try:
                    t = max(t, os.path.getmtime(os.path.join(base, f)))
                except OSError:
                    pass
    return t


def files_like(folder, words):
    """All files of one kind, newest first.

    Newest means: the date in the file name, or (if the name has no date) the day
    the file was saved. A file saved later the same day wins."""
    found = []
    for path in glob.glob(os.path.join(folder, "*")):
        base = plain(os.path.basename(path))
        if base.startswith("~") or base.startswith("."):
            continue
        if not os.path.splitext(path)[1].lower() in (".csv", ".numbers", ".xlsx", ".xls", ".txt", ".tsv"):
            continue
        if any(w in base for w in words):
            mt = _mtime(path)
            nd = _name_date(path) or dt.date.fromtimestamp(mt)
            found.append((nd, mt, path))
    found.sort(reverse=True)
    return [f[2] for f in found]


def newest_file(folder, words):
    """Feature 3: the newest file whose name contains one of the words."""
    found = files_like(folder, words)
    return found[0] if found else None


# -------------------------------------------------------------- values
def parse_line_date(text, today):
    """Dates as Tanya writes them: 'Jul 6', '7/14', 'Sept 1', '10/1', '2026-10-01'."""
    t = plain(text).replace(",", " ")
    if not t:
        return None
    m = re.fullmatch(r"(20\d\d)-(\d{1,2})-(\d{1,2}).*", t)
    if m:
        return dt.date(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?", t)
    if m:
        month, day = int(m[1]), int(m[2])
        year = int(m[3]) if m[3] else None
        if year and year < 100:
            year += 2000
        return _with_year(month, day, year, today)
    m = re.fullmatch(r"([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?", t)
    if m and m[1][:3] in MONTHS:
        return _with_year(MONTHS[m[1][:3]], int(m[2]), int(m[3]) if m[3] else None, today)
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,9})\.?(?:\s+(\d{4}))?", t)
    if m and m[2][:3] in MONTHS:
        return _with_year(MONTHS[m[2][:3]], int(m[1]), int(m[3]) if m[3] else None, today)
    return None


def _with_year(month, day, year, today):
    try:
        if year:
            return dt.date(year, month, day)
        d = dt.date(today.year, month, day)
        if d > today + dt.timedelta(days=31):  # written last year
            d = dt.date(today.year - 1, month, day)
        return d
    except ValueError:
        return None


def parse_datetime(text):
    t = (text or "").strip()
    if not t:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S",
                "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(t, fmt)
        except ValueError:
            pass
    return None


def parse_date(text):
    d = parse_datetime(text)
    return d.date() if d else None


def parse_time(text):
    t = plain(text).replace(".", ":")
    m = re.fullmatch(r"(\d{1,2})(?::(\d\d))?(?::\d\d)?\s*(am|pm|a|p)?", t)
    if not m:
        return None
    h, mi = int(m[1]), int(m[2] or 0)
    if m[3] and m[3].startswith("p") and h < 12:
        h += 12
    if m[3] and m[3].startswith("a") and h == 12:
        h = 0
    if h > 23 or mi > 59:
        return None
    return dt.time(h, mi)


def parse_number(text, default=None):
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return default


def phone_digits(text):
    digits = re.sub(r"\D", "", _clean_cell(text))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) >= 7 else ""


def pretty_phone(digits):
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return digits
