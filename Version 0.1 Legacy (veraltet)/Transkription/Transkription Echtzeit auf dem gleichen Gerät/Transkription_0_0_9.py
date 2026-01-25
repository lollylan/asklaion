import tkinter as tk
from tkinter import filedialog
import torch
import whisper
import sounddevice as sd
import numpy as np
import threading
import queue
import pyperclip
import wave
import librosa
import datetime

# Check for GPU, prefer CUDA if available
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Load Whisper model
MODEL = whisper.load_model("large", device=DEVICE)

# Queue for audio data
audio_queue = queue.Queue()

# Transcription thread flag
running = False

# Buffer to store audio chunks
audio_buffer = []
BUFFER_DURATION = 5  # Minimum duration of audio (in seconds) to transcribe

def record_audio():
    """Record audio and add it to the queue."""
    global running, audio_buffer
    samplerate = 16000  # Whisper expects 16kHz

    def callback(indata, frames, time, status):
        global audio_buffer  # Ensure we use the global variable
        if running:
            if status:
                print(f"Audio input error: {status}")
            audio_buffer.append(indata.copy())

            # If buffer reaches the required duration, enqueue data
            if len(audio_buffer) * frames >= samplerate * BUFFER_DURATION:
                audio_data = np.concatenate(audio_buffer, axis=0)
                audio_queue.put(audio_data)
                audio_buffer = []  # Clear the buffer

    with sd.InputStream(samplerate=samplerate, channels=1, callback=callback):
        while running:
            sd.sleep(1000)  # Sleep for 1 second

def save_audio_to_file(audio_data, filename="debug_audio.wav"):
    """Save audio data to a WAV file for debugging."""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)  # Mono
        wf.setsampwidth(2)  # 16-bit audio
        wf.setframerate(16000)  # 16kHz
        wf.writeframes(audio_data.tobytes())

def transcribe_audio(output_file, text_widget):
    """Continuously transcribe audio from the queue."""
    global running
    transcription = ""
    with open(output_file, "a", encoding="utf-8") as f:
        while running:
            try:
                audio_chunk = audio_queue.get(timeout=10)
                audio_data = np.squeeze(audio_chunk)

                print(f"Audio chunk size: {audio_data.size}")  # Log the size of the audio data

                # Ensure correct format using librosa
                audio_data = librosa.resample(audio_data.astype(np.float32), orig_sr=16000, target_sr=16000)

                # Save audio for debugging (optional)
                save_audio_to_file(np.int16(audio_data * 32767), filename="debug_audio.wav")

                # Transcribe using Whisper
                result = MODEL.transcribe(audio_data, fp16=torch.cuda.is_available(), language="de")
                text = result["text"].strip()

                # Handle empty or invalid transcription
                if not text:
                    text = "(Unklarer Text erkannt)"

                # Update the GUI
                text_widget.insert(tk.END, text + "\n")
                text_widget.see(tk.END)

                # Append to transcription
                transcription += text + "\n"

                # Write to file
                f.write(text + "\n")
                f.flush()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error during transcription: {e}")
    # Copy complete transcription to clipboard
    pyperclip.copy(transcription)

def start_transcription(text_widget, start_button, stop_button):
    """Start recording and transcription."""
    global running
    if not running:
        running = True
        start_button.config(state=tk.DISABLED)
        stop_button.config(state=tk.NORMAL)

        # Generate unique output file name
        timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        output_file = f"transcription_{timestamp}.txt"

        # Start threads for recording and transcription
        threading.Thread(target=record_audio, daemon=True).start()
        threading.Thread(target=transcribe_audio, args=(output_file, text_widget), daemon=True).start()

def stop_transcription(start_button, stop_button):
    """Stop recording and transcription."""
    global running
    running = False
    start_button.config(state=tk.NORMAL)
    stop_button.config(state=tk.DISABLED)

def main():
    """Main function to set up the GUI."""
    # Create the GUI window
    root = tk.Tk()
    root.title("Live Transcription")

    # Title label
    title_label = tk.Label(root, text="Askleion Live Transkription", font=("Helvetica", 16, "bold"))
    title_label.pack(pady=10)

    # Text widget to display transcription
    text_widget = tk.Text(root, wrap=tk.WORD, height=20, width=80)
    text_widget.pack(padx=10, pady=10)

    # Buttons
    button_frame = tk.Frame(root)
    button_frame.pack(pady=10)

    start_button = tk.Button(button_frame, text="Start", width=10, 
                              command=lambda: start_transcription(text_widget, start_button, stop_button))
    start_button.grid(row=0, column=0, padx=5)

    stop_button = tk.Button(button_frame, text="Stop", width=10, state=tk.DISABLED,
                             command=lambda: stop_transcription(start_button, stop_button))
    stop_button.grid(row=0, column=1, padx=5)

    # Run the GUI event loop
    root.mainloop()

if __name__ == "__main__":
    main()
