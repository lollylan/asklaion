import os
import sys
import shutil
import importlib.util
import uvicorn
from fastapi import FastAPI, UploadFile, File

# ---  DLL & PATH FIX ---
if os.name == 'nt':
    print("--- Diagnostic: Searching for NVIDIA DLLs ---")
    nvidia_packages = ['nvidia.cublas', 'nvidia.cudnn']
    
    for pkg in nvidia_packages:
        spec = importlib.util.find_spec(pkg)
        if spec and spec.submodule_search_locations:
            # Den absoluten Pfad zum 'bin' Ordner des Pakets ermitteln
            bin_path = os.path.abspath(os.path.join(spec.submodule_search_locations[0], 'bin'))
            if os.path.exists(bin_path):
                # 1. Den Pfad für Python registrieren (Windows-Sicherheitsfeature)
                os.add_dll_directory(bin_path)
                # 2. Den Pfad in die PATH-Variable schieben, damit die C++ Engine ihn findet
                os.environ["PATH"] = bin_path + os.pathsep + os.environ["PATH"]
                
                print(f"Adding to PATH: {bin_path}")
            else:
                print(f"WARNING: Path not found: {bin_path}")
    print("------------------------------------------")

# Whisper-Engine laden
from faster_whisper import WhisperModel

app = FastAPI()

# --- CONFIGURATION (GPU + LARGE-V3) ---
MODEL_SIZE = "large-v3"   
DEVICE = "cuda"
COMPUTE_TYPE = "float16" 

print(f"Loading Whisper Model ({MODEL_SIZE}) on {DEVICE}...")
model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
print(f"Model {MODEL_SIZE} loaded! Ready to transcribe.")

@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    temp_filename = f"temp_{file.filename}"
    
    with open(temp_filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        # Transkription startet
        segments, info = model.transcribe(
            temp_filename, 
            beam_size=5, 
            language="de",
            condition_on_previous_text=False
        )
        
        # Hier findet die eigentliche Berechnung statt
        transcription = " ".join([segment.text for segment in segments]).strip()
        
        print(f"Transcribed: {transcription[:100]}...") 
        
        return {
            "text": transcription,
            "language": info.language,
            "probability": info.language_probability
        }
        
    finally:
        # Aufräumen: Temporäre Datei löschen
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)