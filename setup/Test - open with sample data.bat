@echo off
rem Opens the program on the SAMPLE data as if today were Fri Oct 30, 2026. Does not touch the real Data folder.
start "" "%~dp0..\python\pythonw.exe" "%~dp0..\app\main.py" --data "%~dp0..\Sample data" --today 2026-10-30
