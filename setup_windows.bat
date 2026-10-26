@echo off
title AI Trading Copilot - Windows Setup
color 0B

echo =====================================================================
echo           AI Trading Copilot - Setup Lingkungan Windows
echo =====================================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python tidak terdeteksi! Pastikan Python 3.10 / 3.11 / 3.12 
    echo sudah diinstal dan dicentang opsi "Add Python to PATH" saat instalasi.
    echo Unduh dari: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [*] Mengecek versi Python...
python --version

echo.
echo [*] Membuat virtual environment (venv)...
if not exist "venv" (
    python -m venv venv
    echo [OK] Virtual environment 'venv' berhasil dibuat.
) else (
    echo [INFO] Folder 'venv' sudah ada. Melewati pembuatan venv.
)

echo.
echo [*] Mengaktifkan virtual environment dan mengupgrade pip...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip

echo.
echo [*] Menginstal seluruh dependensi dari requirements.txt...
echo (Ini mencakup FastAPI, MetaTrader5 native Windows, SQLAlchemy, PyMySQL, dsb.)
pip install -r requirements.txt

echo.
echo =====================================================================
echo [SUKSES] Instalasi selesai!
echo Sekarang Anda dapat menjalankan aplikasi cukup dengan klik:
echo   --^> run.bat
echo =====================================================================
echo.
pause
