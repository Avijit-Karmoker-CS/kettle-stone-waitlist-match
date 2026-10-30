# How to run Waitlist Match

Kettle & Stone Massage Therapy · steps anyone can follow · about 10 minutes · works on Windows, Mac and Linux

## What you need

- The program folder **Kettle & Stone Waitlist**: download the zip from the link in the comment, then unzip it. Python is included for Windows and Mac, so nothing else needs installing.
- Three files from the clinic:
  - the typed waitlist
  - the Kneadly booking export
  - for a test run, the list of late openings.

## Step 1: Unzip

- **Windows:** right-click the zip, choose **Extract All**, then click **Extract**.
- **Mac:** double-click the zip.

Then open the new folder **Kettle & Stone Waitlist**.

## Step 2: Install (once)

**Windows**

1. Double-click **Install (run once).bat**.
2. If Windows says "Windows protected your PC", click **More info**, then **Run anyway**.
3. Wait until it says **Done**, then press any key.

**Mac**

1. **Right-click** (or Control-click) **Install (run once).command** and choose **Open**.
2. If the Mac says it is from an unidentified developer, click **Open**. You only need to do this once.
3. Wait until it says **Done**, then press any key.

Either way, a green **Waitlist Match** icon is now on the Desktop. It also opens the morning list at 8:00 on weekdays.

**Linux**

- No install step. In a terminal, run `./start-linux.sh`. It needs Python 3.10 or later, which most Linux computers already have.

## Step 3: Add the files

1. Open the **Data** folder.
2. Copy the waitlist, the booking export and (for a test run) the late-openings file into it.
3. CSV or Numbers files both work. Excel files must be saved as CSV first.

## Step 4a: Match a list of openings (test run)

1. Open the **setup** folder.
2. Run the matching file for your computer:
   - **Windows:** double-click **Match the openings file.bat**.
   - **Mac:** double-click **Match the openings file.command**.
   - **Linux:** run `./start-linux.sh --cli`.
3. For each opening you see up to 3 names, each with a phone number and a reason, or "nobody".
4. "Check by hand" names are **not** offers.
5. The results are also saved in **Data/reports/matches.csv**.

## Step 4b: Use it at the desk (every day)

1. Double-click **Waitlist Match** on the Desktop.
2. Click **Find people for a slot**.
3. Click the therapist, enter the start time, and pick the length.
4. Click **Find people**.
5. Call the person with the **green border** first. Mark what happens: **Called**, **Voicemail**, **Yes** or **No**.
6. After a **Yes**, book the person in Kneadly and link the new booking to the cancelled one.

## Check that it works (optional, 1 minute)

1. In **setup**, run the **Answer-key test (sample)** file:
   - **Windows:** the .bat file.
   - **Mac:** the .command file.
   - **Linux:** `python3 app/check.py`.
2. It should end with **RESULT: PASS** and **Wrong names shown: 0**.

## If something goes wrong

- The window says what is wrong in plain words, for example "save this file as CSV" or "export has changed - call Julie".
- For a full check, run **Self-check** in the setup folder:
  - **Windows:** the .bat file.
  - **Mac:** the .command file.
  - **Linux:** `./start-linux.sh --self-check`.
- Until it is fixed, use the green notebook as before.
