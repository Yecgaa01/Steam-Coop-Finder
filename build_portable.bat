@echo off
cd /d %~dp0

if not exist .venv\Scripts\python.exe (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 exit /b 1
)

.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

.venv\Scripts\pyinstaller.exe ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name SteamCoopFinder ^
  main.py

if errorlevel 1 exit /b 1

echo.
echo Build complete:
echo dist\SteamCoopFinder\SteamCoopFinder.exe
echo.
pause
