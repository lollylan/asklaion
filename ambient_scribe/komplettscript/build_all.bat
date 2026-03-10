@echo off
chcp 65001 >nul
echo ============================================================
echo   Asklaion - EXE Build Script
echo   Erstellt ausfuehrbare Dateien fuer alle Komponenten
echo ============================================================
echo.

REM Pruefen ob PyInstaller installiert ist
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] PyInstaller ist nicht installiert!
    echo Bitte installieren mit: pip install pyinstaller
    pause
    exit /b 1
)

REM Build-Verzeichnis saeubern
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [1/4] Baue server_CPU.exe ...
echo ============================================================
python -m PyInstaller --onedir --console --noconfirm ^
    --name server_CPU ^
    --hidden-import=uvicorn.logging ^
    --hidden-import=uvicorn.loops ^
    --hidden-import=uvicorn.loops.auto ^
    --hidden-import=uvicorn.protocols ^
    --hidden-import=uvicorn.protocols.http ^
    --hidden-import=uvicorn.protocols.http.auto ^
    --hidden-import=uvicorn.protocols.http.h11_impl ^
    --hidden-import=uvicorn.protocols.http.httptools_impl ^
    --hidden-import=uvicorn.protocols.websockets ^
    --hidden-import=uvicorn.protocols.websockets.auto ^
    --hidden-import=uvicorn.protocols.websockets.wsproto_impl ^
    --hidden-import=uvicorn.lifespan ^
    --hidden-import=uvicorn.lifespan.on ^
    --hidden-import=uvicorn.lifespan.off ^
    --hidden-import=anyio._backends._asyncio ^
    --hidden-import=ctranslate2 ^
    server_CPU.py

if errorlevel 1 (
    echo [FEHLER] Build von server_CPU fehlgeschlagen!
    pause
    exit /b 1
)

echo.
echo [2/4] Baue server_GPU_CUDA_Parallel.exe ...
echo ============================================================
python -m PyInstaller --onedir --console --noconfirm ^
    --name server_GPU_CUDA_Parallel ^
    --hidden-import=uvicorn.logging ^
    --hidden-import=uvicorn.loops ^
    --hidden-import=uvicorn.loops.auto ^
    --hidden-import=uvicorn.protocols ^
    --hidden-import=uvicorn.protocols.http ^
    --hidden-import=uvicorn.protocols.http.auto ^
    --hidden-import=uvicorn.protocols.http.h11_impl ^
    --hidden-import=uvicorn.protocols.http.httptools_impl ^
    --hidden-import=uvicorn.protocols.websockets ^
    --hidden-import=uvicorn.protocols.websockets.auto ^
    --hidden-import=uvicorn.protocols.websockets.wsproto_impl ^
    --hidden-import=uvicorn.lifespan ^
    --hidden-import=uvicorn.lifespan.on ^
    --hidden-import=uvicorn.lifespan.off ^
    --hidden-import=anyio._backends._asyncio ^
    --hidden-import=ctranslate2 ^
    server_GPU_CUDA_Parallel.py

if errorlevel 1 (
    echo [FEHLER] Build von server_GPU_CUDA_Parallel fehlgeschlagen!
    pause
    exit /b 1
)

echo.
echo [3/4] Baue Komplettscript_1_0.exe ...
echo ============================================================
python -m PyInstaller --onedir --console --noconfirm ^
    --name Komplettscript_1_0 ^
    --hidden-import=sounddevice ^
    --hidden-import=_sounddevice_data ^
    --collect-data sounddevice ^
    --hidden-import=scipy.io.wavfile ^
    --hidden-import=PyPDF2 ^
    --hidden-import=windnd ^
    --hidden-import=pyperclip ^
    Komplettscript_1_0.py

if errorlevel 1 (
    echo [FEHLER] Build von Komplettscript_1_0 fehlgeschlagen!
    pause
    exit /b 1
)

echo.
echo [4/4] Baue Komplettscript_Full_Backup.exe ...
echo ============================================================
python -m PyInstaller --onedir --console --noconfirm ^
    --name Komplettscript_Full_Backup ^
    --hidden-import=sounddevice ^
    --hidden-import=_sounddevice_data ^
    --collect-data sounddevice ^
    --hidden-import=scipy.io.wavfile ^
    --hidden-import=PyPDF2 ^
    --hidden-import=windnd ^
    --hidden-import=pyperclip ^
    Komplettscript_Full_Backup.py

if errorlevel 1 (
    echo [FEHLER] Build von Komplettscript_Full_Backup fehlgeschlagen!
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   FERTIG! Alle EXE-Dateien wurden erstellt.
echo ============================================================
echo.
echo   Ausgabe in: dist\
echo     - dist\server_CPU\server_CPU.exe
echo     - dist\server_GPU_CUDA_Parallel\server_GPU_CUDA_Parallel.exe
echo     - dist\Komplettscript_1_0\Komplettscript_1_0.exe
echo     - dist\Komplettscript_Full_Backup\Komplettscript_Full_Backup.exe
echo.
echo   HINWEIS: Beim Weitergeben den kompletten Ordner kopieren,
echo   nicht nur die .exe-Datei!
echo.
echo   GPU-Server benoetigt CUDA-Toolkit auf dem Zielrechner.
echo ============================================================
pause
