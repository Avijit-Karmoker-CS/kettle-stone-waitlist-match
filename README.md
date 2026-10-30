# Kettle & Stone Waitlist Match

When a client cancels late, this program shows the front desk up to 3 people from the waitlist who fit the open slot and still want in, or "nobody" if nobody fits. Each name comes with a phone number and a short reason. Health details are never shown.

It runs only on the clinic's desk computer. It sends nothing, does not connect to Kneadly, and costs $0 a month.

## Download and run (Windows, Mac or Linux)

1. Go to **[Releases](../../releases/latest)** and download **Kettle-and-Stone-Waitlist-Match.zip**. It includes Python for Windows and Mac, so nothing else needs installing.
2. Unzip it.
3. Install it once:
   - **Windows:** double-click **Install (run once).bat**. If Windows says "Windows protected your PC", click **More info**, then **Run anyway**.
   - **Mac:** right-click **Install (run once).command** and choose **Open**, then click **Open** again.
   - **Linux:** no install. Run `./start-linux.sh` (needs Python 3.10 or later).
4. Put the waitlist, the Kneadly booking export and the late-openings file in the **Data** folder. CSV or Numbers files both work.
5. In the **setup** folder, run **Match the openings file** (`.bat` on Windows, `.command` on Mac, `./start-linux.sh --cli` on Linux). You get up to 3 names per opening, or "nobody".

To use it at the desk, double-click **Waitlist Match** on the desktop and click **Find people for a slot**.

Full steps are in [Guides/How to run it.md](Guides/How%20to%20run%20it.md).

## Run from this repository (Mac, Linux or Windows with Python 3.10 or later)

```
python3 app/check.py --data "Test data/Sample (CSV)"
python3 app/main.py --cli --data "Test data/Sample (CSV)" --today 2026-10-21
python3 app/main.py --data "Test data/Sample (CSV)" --today 2026-10-30
```

1. **Answer-key test.** Expect `RESULT: PASS`.
2. **Match every opening in the file.**
3. **Open the desk window in your browser.**

The program uses only the Python standard library. Numbers files also need `pip install numbers-parser`.

## Results on Tanya's answer key

| Check | Result |
|---|---|
| Openings correct | 44 of 44 (target 31) |
| Wrong names shown | 0 |
| Out-of-date lines found | 20 of 20 |
| Waitlist lines matching Tanya's status | 60 of 60 |

## What's in the repository

| Folder | Contents |
|---|---|
| `app/` | The program: shorthand reader, matching, desk window, answer-key test |
| `settings/` | Plain-text settings Julie can edit in Notepad: therapists, rules, shorthand words, column names, add-ons |
| `setup/` | Self-check, answer-key test, match the openings file, test windows and uninstall (`.bat` for Windows, `.command` for Mac) |
| `Data/` | Where the clinic's files go (empty) |
| `Sample data/` | The sprint's sample files (Numbers) and Tanya's answer key |
| `Test data/` | CSV copies of the sample, plus a daily-report test set |
| `Guides/` | How to run it, guide for Julie and Tanya, one-page note for Marc, aftercare plan, desk card |

## Out of scope

- No real messages are sent. Text offers are preview-only and switched off.
- No connection to a real booking system. The program only reads files saved in the Data folder.
