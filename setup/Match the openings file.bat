@echo off
title Waitlist Match - openings file
rem Matches every opening in the late-openings file in the Data folder and saves Data\reports\matches.csv
"%~dp0..\python\python.exe" "%~dp0..\app\main.py" --cli
pause
