@echo off
title AI Trading Copilot Server (HFM MT5)
color 0A

echo =====================================================================
echo           AI Trading Copilot - Terminal Windows
echo =====================================================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [INFO] Virtual environment belum ditemukan.
    echo Menjalankan setup otomatis...
    call setup_windows.bat
)

echo [*] Mengaktifkan virtual environment...
call venv\Scripts\activate.bat

echo.
echo =====================================================================
echo  Server Dashboard : http://localhost:8000
echo  Default Login    : admin
echo  Default Password : password123 (dapat diganti di config.json)
echo =====================================================================
echo.
echo Menjalankan server FastAPI...
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
