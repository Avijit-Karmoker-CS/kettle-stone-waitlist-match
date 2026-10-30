@echo off
rem Opens the program on the DAILY REPORT test data as if it were 8:05 on Fri Oct 30, 2026. Does not touch the real Data folder.
start "" "%~dp0..\python\pythonw.exe" "%~dp0..\app\main.py" --data "%~dp0..\Test data\Daily report" --now 2026-10-30T08:05
