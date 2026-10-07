@echo off
chcp 65001 >nul
echo ============================================================
echo   Asklaion v2.0 - EXE Build Script
echo   Erstellt ausfuehrbare Dateien fuer Server und Client
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
echo [1/2] Baue server.exe (Praxisserver) ...
echo ============================================================
python -m PyInstaller --onedir --console --noconfirm ^
    --name server ^
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
    --hidden-import=multipart ^
    --hidden-import=python_multipart ^
    --hidden-import=ctranslate2 ^
    --hidden-import=soundfile ^
    --hidden-import=rapidfuzz ^
    --hidden-import=sherpa_onnx ^
    --collect-all=sherpa_onnx ^
    --collect-all=faster_whisper ^
    --collect-data soundfile ^
    server.py

if errorlevel 1 (
    echo [FEHLER] Build von server fehlgeschlagen!
    pause
    exit /b 1
)

echo.
echo [2/2] Baue Komplettscript_2_0.exe (Client) ...
echo ============================================================
python -m PyInstaller --onedir --console --noconfirm ^
    --name Komplettscript_2_0 ^
    --hidden-import=sounddevice ^
    --hidden-import=_sounddevice_data ^
    --collect-data sounddevice ^
    --hidden-import=scipy.io.wavfile ^
    --hidden-import=PyPDF2 ^
    --hidden-import=windnd ^
    --hidden-import=pyperclip ^
    Komplettscript_2_0.py

if errorlevel 1 (
    echo [FEHLER] Build von Komplettscript_2_0 fehlgeschlagen!
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   FERTIG! Alle EXE-Dateien wurden erstellt.
echo ============================================================
echo.
echo   Ausgabe in: dist\
echo     - dist\server\server.exe                       (Praxisserver)
echo     - dist\Komplettscript_2_0\Komplettscript_2_0.exe (Client)
echo.
echo   HINWEIS: Beim Weitergeben den kompletten Ordner kopieren,
echo   nicht nur die .exe-Datei! Neben server.exe gehoeren
echo   vokabular_medizin.txt (optional) und der Ordner models\
echo   (wird sonst beim ersten Start automatisch geladen).
echo.
echo   GPU-Server: NVIDIA-Treiber reicht, cuBLAS/cuDNN kommen
echo   aus den pip-Paketen nvidia-cublas-cu12 / nvidia-cudnn-cu12.
echo ============================================================
pause
