@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
if not exist "tagger\keys.txt" (
    echo ERROR: missing tagger\keys.txt - one key per line, first one is used first
    exit /b 1
)
set "KEYS="
set "FIRST="
for /f "usebackq delims=" %%k in ("tagger\keys.txt") do (
    if not defined FIRST set "FIRST=%%k"
    if defined KEYS (set "KEYS=!KEYS!,%%k") else (set "KEYS=%%k")
)
set "OPENCODE_API_KEYS=!KEYS!"
set "OPENCODE_API_KEY=!FIRST!"
echo keys: first=!FIRST:~0,14!...  total=4  (one independent account per shard)
if /i "%~1"=="plan" (
    python -u -m tagger.run_corpus --shards 4
) else (
    python -u -m tagger.run_corpus --shards 4 --go %*
)
