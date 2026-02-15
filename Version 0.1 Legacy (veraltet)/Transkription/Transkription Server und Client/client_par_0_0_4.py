import tkinter as tk
from tkinter import messagebox, ttk
import sounddevice as sd
import numpy as np
import threading
import requests
import queue
import os
import pyperclip
import datetime

# Workaround for OpenMP error
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"

SERVER_URL = "http://192.168.10.128:5000/transcribe"  # Default server URL, configurable by user

audio_queue = queue.Queue()
running = False
paused = False
BUFFER_DURATION = 30
final_transcription = ""
input_source = "microphone"  # Default input source

# Ensure the "Transkripte" directory exists
TRANSCRIPTS_DIR = "Transkripte"
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

def record_audio():
    global running, paused, input_source
    samplerate = 16000
    channels = 1 if input_source == "microphone" else 2  # Adjust channels based on input source
    audio_buffer = []

    def callback(indata, frames, time, status):
        if running and not paused:
            if status:
                print(f"Audio input error: {status}")
            audio_buffer.append(indata.copy())

            if len(audio_buffer) * frames >= samplerate * BUFFER_DURATION:
                audio_data = np.concatenate(audio_buffer, axis=0)
                audio_queue.put(audio_data)
                audio_buffer.clear()

    with sd.InputStream(samplerate=samplerate, channels=channels, callback=callback):
        while running:
            sd.sleep(1000)

    if audio_buffer:
        audio_data = np.concatenate(audio_buffer, axis=0)
        audio_queue.put(audio_data)

def transcribe_audio(text_widget, language):
    global final_transcription
    while running or not audio_queue.empty():
        try:
            audio_chunk = audio_queue.get(timeout=10)
            audio_data = np.squeeze(audio_chunk).tolist()

            response = requests.post(SERVER_URL, json={"audio_data": audio_data, "language": language})
            response.raise_for_status()
            result = response.json()

            if "text" in result:
                text_widget.insert(tk.END, result["text"] + "\n")
                text_widget.see(tk.END)
                final_transcription += result["text"] + "\n"
            else:
                text_widget.insert(tk.END, f"Error: {result.get('error', 'Unknown error')}\n")
        except queue.Empty:
            continue
        except Exception as e:
            text_widget.insert(tk.END, f"Error during transcription: {e}\n")

def finalize_transcription(patient_info_field, text_widget, additional_input_field):
    global final_transcription
    patient_info = patient_info_field.get("1.0", tk.END).strip()
    transcription = text_widget.get("1.0", tk.END).strip()
    additional_input = additional_input_field.get("1.0", tk.END).strip()

    final_output = f"{patient_info}\n*****\n{transcription}\n{additional_input}"

    timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    filename = os.path.join(TRANSCRIPTS_DIR, f"Transkription-{timestamp}.txt")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(final_output)

    pyperclip.copy(final_output)
    messagebox.showinfo("Transcription Saved", f"The transcription has been saved to {filename} and copied to clipboard.")

def start_transcription(patient_info_field, text_widget, additional_input_field, language_selection, start_button, pause_button, stop_button, status_label, clipboard=False):
    global running, paused, final_transcription
    if not running:
        running = True
        paused = False
        final_transcription = ""
        language = language_selection.get()

        patient_info_field.delete("1.0", tk.END)
        text_widget.delete("1.0", tk.END)
        additional_input_field.delete("1.0", tk.END)

        if clipboard:
            clipboard_content = pyperclip.paste()
            patient_info_field.insert(tk.END, clipboard_content)

        start_button.config(state=tk.DISABLED)
        pause_button.config(state=tk.NORMAL, text="Pause")
        stop_button.config(state=tk.NORMAL)
        status_label.config(text="Status: Recording")

        threading.Thread(target=record_audio, daemon=True).start()
        threading.Thread(target=transcribe_audio, args=(text_widget, language), daemon=True).start()

def stop_transcription(patient_info_field, text_widget, additional_input_field, start_button, pause_button, stop_button, status_label, language_selection):
    global running, paused
    running = False
    paused = False

    def finalize():
        while not audio_queue.empty():
            audio_chunk = audio_queue.get()
            audio_data = np.squeeze(audio_chunk).tolist()

            try:
                response = requests.post(SERVER_URL, json={"audio_data": audio_data, "language": language_selection.get()})
                response.raise_for_status()
                result = response.json()

                if "text" in result:
                    text_widget.insert(tk.END, result["text"] + "\n")
                    text_widget.see(tk.END)
                    global final_transcription
                    final_transcription += result["text"] + "\n"
            except Exception as e:
                text_widget.insert(tk.END, f"Error during transcription: {e}\n")

        while threading.active_count() > 2:
            threading.Event().wait(0.1)

        finalize_transcription(patient_info_field, text_widget, additional_input_field)
        start_button.config(state=tk.NORMAL)
        pause_button.config(state=tk.DISABLED)
        stop_button.config(state=tk.DISABLED)
        status_label.config(text="Status: Stopped")

    threading.Thread(target=finalize, daemon=True).start()

def toggle_pause(pause_button, status_label):
    global paused
    paused = not paused
    if paused:
        pause_button.config(text="Resume")
        status_label.config(text="Status: Paused")
    else:
        pause_button.config(text="Pause")
        status_label.config(text="Status: Recording")

def main():
    global input_source
    root = tk.Tk()
    root.title("Live Transcription Client")

    status_label = tk.Label(root, text="Status: Ready", font=("Helvetica", 10))
    status_label.pack()

    patient_info_label = tk.Label(root, text="Patient Information:", font=("Helvetica", 10))
    patient_info_label.pack(pady=5)

    patient_info_field = tk.Text(root, wrap=tk.WORD, height=5, width=80)
    patient_info_field.pack(padx=10, pady=5)

    text_widget = tk.Text(root, wrap=tk.WORD, height=15, width=80)
    text_widget.pack(padx=10, pady=10)

    additional_input_label = tk.Label(root, text="Additional Input:", font=("Helvetica", 10))
    additional_input_label.pack(pady=5)

    additional_input_field = tk.Text(root, wrap=tk.WORD, height=5, width=80)
    additional_input_field.pack(padx=10, pady=5)

    language_selection_label = tk.Label(root, text="Language:", font=("Helvetica", 10))
    language_selection_label.pack(pady=5)

    language_selection = ttk.Combobox(root, values=["de", "en", "fr", "es", "it", "nl"])
    language_selection.set("de")
    language_selection.pack()

    input_source_label = tk.Label(root, text="Input Source:", font=("Helvetica", 10))
    input_source_label.pack(pady=5)

    input_source_selection = ttk.Combobox(root, values=["microphone", "microphone + computer audio"])
    input_source_selection.set("microphone")
    input_source_selection.pack()

    def set_input_source(event):
        global input_source
        input_source = input_source_selection.get()

    input_source_selection.bind("<<ComboboxSelected>>", set_input_source)

    button_frame = tk.Frame(root)
    button_frame.pack(pady=10)

    start_button = tk.Button(button_frame, text="Start Transcription", width=20,
                              command=lambda: start_transcription(patient_info_field, text_widget, additional_input_field, language_selection,
                                                                  start_button, pause_button, stop_button, status_label))
    start_button.grid(row=0, column=0, padx=5)

    start_clipboard_button = tk.Button(button_frame, text="Start with Clipboard", width=20,
                                       command=lambda: start_transcription(patient_info_field, text_widget, additional_input_field, language_selection,
                                                                           start_button, pause_button, stop_button, status_label, clipboard=True))
    start_clipboard_button.grid(row=0, column=1, padx=5)

    pause_button = tk.Button(button_frame, text="Pause", width=20, state=tk.DISABLED,
                              command=lambda: toggle_pause(pause_button, status_label))
    pause_button.grid(row=1, column=0, padx=5)

    stop_button = tk.Button(button_frame, text="Stop Transcription", width=20, state=tk.DISABLED,
                             command=lambda: stop_transcription(patient_info_field, text_widget, additional_input_field,
                                                                 start_button, pause_button, stop_button, status_label, language_selection))
    stop_button.grid(row=1, column=1, padx=5)

    root.mainloop()

if __name__ == "__main__":
    main()
