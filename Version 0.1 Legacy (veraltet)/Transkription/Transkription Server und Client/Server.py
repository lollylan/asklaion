from flask import Flask, request, jsonify
import whisper
import numpy as np
import os
import torch
from concurrent.futures import ThreadPoolExecutor

# Workaround for OpenMP error
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"

# Initialize Flask app and load Whisper model
app = Flask(__name__)
MODEL = whisper.load_model("turbo").to("cuda")

# Create a thread pool for parallel requests
executor = ThreadPoolExecutor(max_workers=4)

@app.route("/transcribe", methods=["POST"])
def transcribe():
    try:
        data = request.get_json()
        audio_data = np.array(data["audio_data"], dtype=np.float32)
        language = data["language"]

        def transcribe_audio():
            with torch.no_grad():
                result = MODEL.transcribe(audio_data, language=language)
            return result

        future = executor.submit(transcribe_audio)
        result = future.result()
        return jsonify({"text": result["text"]})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    from waitress import serve  # Use Waitress for production WSGI server
    print("Starting transcription server...")
    serve(app, host="0.0.0.0", port=5000)
