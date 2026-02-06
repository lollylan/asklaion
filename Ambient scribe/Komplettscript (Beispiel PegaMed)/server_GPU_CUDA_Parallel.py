import os
import sys
import shutil
import importlib.util
import uvicorn
import uuid  # Für eindeutige Dateinamen bei parallelen Anfragen
from fastapi import FastAPI, UploadFile, File

# --- DLL & PATH FIX (Speziell für Windows/NVIDIA Umgebungen) ---
if os.name == 'nt':
    print("--- Diagnostic: Searching for NVIDIA DLLs ---")
    nvidia_packages = ['nvidia.cublas', 'nvidia.cudnn']
    
    for pkg in nvidia_packages:
        spec = importlib.util.find_spec(pkg)
        if spec and spec.submodule_search_locations:
            bin_path = os.path.abspath(os.path.join(spec.submodule_search_locations[0], 'bin'))
            if os.path.exists(bin_path):
                os.add_dll_directory(bin_path)
                os.environ["PATH"] = bin_path + os.pathsep + os.environ["PATH"]
                print(f"Adding to PATH: {bin_path}")
            else:
                print(f"WARNING: Path not found: {bin_path}")
    print("------------------------------------------")

# Whisper-Engine laden
from faster_whisper import WhisperModel

app = FastAPI()

# --- KONFIGURATION (GPU + LARGE-V3) ---
MODEL_SIZE = "large-v3"   
DEVICE = "cuda"
COMPUTE_TYPE = "float16" 

print(f"Loading Whisper Model ({MODEL_SIZE}) on {DEVICE}...")
# Das Modell wird einmal beim Start in den VRAM geladen
model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
print(f"Model {MODEL_SIZE} loaded! Ready to transcribe.")

@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    # Erzeuge einen absolut eindeutigen Dateinamen pro Anfrage
    # Das verhindert, dass sich Zimmer 1 und Zimmer 2 gegenseitig Dateien überschreiben
    request_id = uuid.uuid4().hex
    temp_filename = f"temp_{request_id}_{file.filename}"
    
    # Datei vom Client empfangen und zwischenspeichern
    with open(temp_filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        # Transkription starten
        # segments ist ein Generator, die Arbeit passiert erst beim Iterieren
        segments, info = model.transcribe(
            temp_filename, 
            beam_size=5, 
            language="de",
            condition_on_previous_text=False
        )
        
        # Zusammenfügen der Textsegmente
        transcription = " ".join([segment.text for segment in segments]).strip()
        
        # Log-Ausgabe auf der Server-Konsole
        print(f"[{request_id}] Transcribed: {transcription[:100]}...") 
        
        return {
            "text": transcription,
            "language": info.language,
            "probability": info.language_probability,
            "id": request_id
        }
        
    except Exception as e:
        print(f"Error during transcription: {e}")
        return {"error": str(e)}
        
    finally:
        # Aufräumen: Die temporäre Datei nach der Verarbeitung sofort löschen
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except Exception as e:
                print(f"Could not delete temp file {temp_filename}: {e}")

if __name__ == "__main__":
    # Startet den Server auf allen Netzwerkschnittstellen (wichtig für Zugriff aus Zimmern)
    uvicorn.run(app, host="0.0.0.0", port=8000)