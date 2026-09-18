@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
rem Keys live OUTSIDE the repo (tagger/keys.txt is gitignored) so they never
rem get committed. Accept either location.
set "KEYFILE="
if exist "..\_keys.txt" set "KEYFILE=..\_keys.txt"
if exist "tagger\keys.txt" set "KEYFILE=tagger\keys.txt"
if not defined KEYFILE (
    echo ERROR: no key file. Create "..\_keys.txt" or "tagger\keys.txt" with one API key per line.
    exit /b 1
)
echo using key file: !KEYFILE!
set "KEYS="
set "FIRST="
for /f "usebackq delims=" %%k in ("!KEYFILE!") do (
    if not defined FIRST set "FIRST=%%k"
    if defined KEYS (set "KEYS=!KEYS!,%%k") else (set "KEYS=%%k")
)
set "OPENCODE_API_KEYS=!KEYS!"
set "OPENCODE_API_KEY=!FIRST!"
echo first key: !FIRST:~0,14!...
if /i "%~1"=="plan" (
    python -u -m tagger.run_corpus --shards 4
) else (
    python -u -m tagger.run_corpus --shards 4 --go %*
)
