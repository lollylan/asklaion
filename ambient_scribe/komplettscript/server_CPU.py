import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from fastapi import FastAPI, UploadFile, File
from faster_whisper import WhisperModel
import shutil
from security_utils import ensure_tls_certs

app = FastAPI()

# --- CONFIGURATION (CPU MODE) ---
MODEL_SIZE = "medium"   # Try "small" if this is too slow
DEVICE = "cpu"          # Forces CPU usage (No GPU drivers needed)
COMPUTE_TYPE = "int8"   # Optimized for CPU speed

print(f"Loading Whisper Model ({MODEL_SIZE}) on {DEVICE}...")
model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
print("Model loaded! Ready to transcribe.")

@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    temp_filename = f"temp_{file.filename}"
    
    with open(temp_filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Transcribe
    segments, info = model.transcribe(temp_filename, beam_size=5, language="de")
    
    transcription = " ".join([segment.text for segment in segments])
    
    os.remove(temp_filename)
    
    print(f"Transcribed: {transcription[:50]}...") 
    return {"text": transcription}

if __name__ == "__main__":
    cert_file, key_file, ca_cert_file, ip = ensure_tls_certs()
    print(f"\n✅ Server läuft auf: https://{ip}:8000")
    print(f"📋 CA-Zertifikat (einmalig auf jeden Client-PC kopieren): {ca_cert_file}\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, ssl_certfile=cert_file, ssl_keyfile=key_file)