@echo off
title Waitlist Match - answer-key test
rem Scores the program against Tanya's answer key on the sample data (run date Oct 21, 2026).
"%~dp0..\python\python.exe" "%~dp0..\app\check.py" --data "%~dp0..\Sample data" --today 2026-10-21
pause
