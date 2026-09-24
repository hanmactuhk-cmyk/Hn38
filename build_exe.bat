@echo off
python -m pip install -r requirements.txt
python -m playwright install chromium
pyinstaller --noconfirm --clean --windowed --name Hn38videoAItool desktop/main.py
pause
