@echo off
cd /d "%~dp0"
python -c "import PySide6, bleak" >nul 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    python -m pip install -r requirements.txt
)
where pythonw >nul 2>nul
if errorlevel 1 (
    python main.py
) else (
    start "" pythonw main.py
)
