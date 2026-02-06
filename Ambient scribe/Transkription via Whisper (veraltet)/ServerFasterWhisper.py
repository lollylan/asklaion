from flask import Flask, request, jsonify
import numpy as np
import os
from concurrent.futures import ThreadPoolExecutor
from faster_whisper import WhisperModel

# Workaround for OpenMP error
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"

# Initialize Flask app and load faster-whisper model
app = Flask(__name__)
MODEL = WhisperModel("large", device="cuda", compute_type="float16")

# Create a thread pool for parallel requests
executor = ThreadPoolExecutor(max_workers=4)

@app.route("/transcribe", methods=["POST"])
def transcribe():
    try:
        data = request.get_json()
        audio_data = np.array(data["audio_data"], dtype=np.float32)
        language = data["language"]

        def transcribe_audio():
            segments, _ = MODEL.transcribe(audio_data, language=language)
            result_text = "".join(segment.text for segment in segments)
            return {"text": result_text}

        future = executor.submit(transcribe_audio)
        result = future.result()
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    from waitress import serve  # Use Waitress for production WSGI server
    print("Starting transcription server...")
    serve(app, host="0.0.0.0", port=5000)
