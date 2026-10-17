@echo off
chcp 65001 >nul
echo ============================================
echo WorkBuddy AI Proxy - Build EXE
echo ============================================
echo.

REM 检查 PyInstaller
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    pip install pyinstaller
)

echo [1/3] Cleaning old build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/3] Building single-file EXE...
python -m PyInstaller ^
    --onefile ^
    --name workbuddy-proxy ^
    --console ^
    --hidden-import urllib.request ^
    --hidden-import http.server ^
    workbuddy_proxy.py

echo.
echo [3/3] Build complete!
if exist dist\workbuddy-proxy.exe (
    echo EXE: dist\workbuddy-proxy.exe
    for %%A in (dist\workbuddy-proxy.exe) do echo Size: %%~zA bytes
) else (
    echo [ERROR] Build failed!
)

echo.
pause
