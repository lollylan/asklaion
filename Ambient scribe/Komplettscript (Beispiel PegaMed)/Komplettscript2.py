import tkinter as tk
from tkinter import messagebox, scrolledtext
import sounddevice as sd
import numpy as np
import threading
import requests
import scipy.io.wavfile as wav
import io
import time
import pyperclip
from datetime import datetime
import os
import json

# --- CONFIGURATION ---
SERVER_URL = "http://192.168.10.177:8000/transcribe" 
SAMPLE_RATE = 16000
CHUNK_DURATION = 30 

# --- LLM / OPENWEBUI CONFIGURATION ---
OPENWEBUI_URL = "http://192.168.10.177:3000/api/chat/completions"
# Ihr API Key (unverändert übernommen)
OPENWEBUI_API_KEY = "API KEY"

# HIER NUTZEN WIR JETZT DAS CUSTOM MODEL
LLM_MODEL_NAME = "asklaion-v1" 



# --- NORMBEFUNDE ---
STANDARD_FINDINGS = {
    "Herz": "Cor: Herztöne rein, regelmäßig, rhythmisch. Keine vitientypischen Neben- oder Strömungsgeräusche.",
    "Lunge": "Pulmo: Vesikuläratmen bds., sonorer Klopfschall, keine Rasselgeräusche, seitengleich belüftet.",
    "Abdomen": "Abdomen: Bauchdecke weich, kein Druckschmerz, keine Abwehrspannung, keine Resistenzen tastbar. Peristaltik regelrecht.",
    "Rachen": "Rachen: Mundschleimhaut feucht, rosig. Rachenhinterwand reizlos. Tonsillen nicht vergrößert, kein Belag.",
    "Ohren": "Otoksopie: Gehörgänge bds. frei, reizlos. Trommelfelle grau, spiegelnd, intakt, Lichtreflex erhalten.",
    "Wirbelsäule": "Wirbelsäule: Lotgerecht, Dornfortsätze in Reihe, kein Klopf- oder Stauchungsschmerz. Paravertebralmuskulatur weich.",
    "Niere": "Nieren: Nierenlager beidseits indolent, kein Klopfschmerz.",
    "Lymphknoten": "Lymphknoten: Zervikal, axillär und inguinal nicht vergrößert tastbar, indolent.",
    "Beine/Venen": "Extremitäten: Keine Ödeme, Waden weich/indolent, Fußpulse tastbar, keine trophischen Störungen.",
    "Neuro-Basis": "Neuro: Grobe Kraft/Sensibilität seitengleich. Pupillen isokor/lichtreagibel. Stand/Gang sicher.",
    "Haut": "Haut: Rosig, warm, Turgor regelrecht. Keine Effloreszenzen, kein Ikterus.",
    "Schilddrüse": "Schilddrüse: Nicht vergrößert, schluckverschieblich, knotenfrei.",
    "Psyche/AZ": "Psych/AZ: Wach, allseits orientiert. Stimmung ausgeglichen. AZ gut."
}

class AudioRecorder:
    def __init__(self, root):
        self.root = root
        self.root.title("Doctor's Visit Recorder - Dr. Rasche (Model: asklaion-v1)")
        self.root.geometry("600x600") 
        
        self.is_recording = False
        self.audio_buffer = []
        self.full_transcription = []
        
        # UI Elements
        self.status_label = tk.Label(root, text="Bereit", font=("Arial", 14))
        self.status_label.pack(pady=10)
        
        # Control Buttons
        self.frame_controls = tk.Frame(root)
        self.frame_controls.pack(pady=10)

        self.btn_start = tk.Button(self.frame_controls, text="Aufnahme Starten", command=self.start_recording, bg="green", fg="white", font=("Arial", 12))
        self.btn_start.pack(side=tk.LEFT, padx=10)
        
        self.btn_stop = tk.Button(self.frame_controls, text="Stop & LLM-Verarbeitung", command=self.stop_recording, bg="red", fg="white", font=("Arial", 12), state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=10)

        # Normbefunde Frame
        self.frame_findings = tk.LabelFrame(root, text="Normbefunde einfügen", font=("Arial", 10, "bold"), padx=10, pady=10)
        self.frame_findings.pack(pady=10, fill="both", expand="yes", padx=20)

        self.finding_buttons = []
        row = 0
        col = 0
        for name, text in STANDARD_FINDINGS.items():
            btn = tk.Button(self.frame_findings, text=name, 
                            command=lambda t=text, n=name: self.insert_finding(t, n),
                            height=2, width=15, state=tk.DISABLED)
            btn.grid(row=row, column=col, padx=5, pady=5)
            self.finding_buttons.append(btn)
            col += 1
            if col > 2:
                col = 0
                row += 1

        self.log_text = tk.Text(root, height=8, width=60)
        self.log_text.pack(pady=10)

    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def insert_finding(self, text, name):
        if self.is_recording:
            formatted_text = f"\n[BEFUND {name.upper()}: {text}]\n"
            self.full_transcription.append(formatted_text)
            self.log(f"-> Normbefund '{name}' eingefügt.")
        else:
            self.log("Bitte erst Aufnahme starten.")

    def audio_callback(self, indata, frames, time, status):
        if self.is_recording:
            self.audio_buffer.append(indata.copy())

    def process_audio_thread(self):
        last_chunk_time = time.time()
        while self.is_recording:
            time.sleep(1)
            current_time = time.time()
            if current_time - last_chunk_time >= CHUNK_DURATION:
                self.send_chunk()
                last_chunk_time = time.time()

    def send_chunk(self, is_final=False):
        if not self.audio_buffer:
            if is_final: self._upload_task(None, True) 
            return

        chunk_data = np.concatenate(self.audio_buffer, axis=0)
        if not is_final:
            self.audio_buffer = [] 

        wav_io = io.BytesIO()
        wav.write(wav_io, SAMPLE_RATE, chunk_data)
        wav_io.seek(0)
        
        threading.Thread(target=self._upload_task, args=(wav_io, is_final)).start()

    def _upload_task(self, wav_file, is_final):
        if wav_file:
            try:
                self.log(f"Sende {'letzten ' if is_final else ''}Audio-Chunk...")
                files = {'file': ('chunk.wav', wav_file, 'audio/wav')}
                response = requests.post(SERVER_URL, files=files)
                
                if response.status_code == 200:
                    text = response.json().get("text", "")
                    if text:
                        self.full_transcription.append(text + " ")
                        self.log("Chunk transkribiert.")
                else:
                    self.log(f"Fehler: Server antwortet mit {response.status_code}")
            except Exception as e:
                self.log(f"Verbindungsfehler: {e}")

        if is_final:
            self.finalize_transcription()

    def start_recording(self):
        self.is_recording = True
        self.audio_buffer = []
        self.full_transcription = []
        
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        for btn in self.finding_buttons:
            btn.config(state=tk.NORMAL, bg="#e1f5fe")
            
        self.status_label.config(text="Aufnahme läuft...", fg="red")
        
        self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, callback=self.audio_callback)
        self.stream.start()
        
        self.timer_thread = threading.Thread(target=self.process_audio_thread)
        self.timer_thread.start()

    def stop_recording(self):
        self.is_recording = False
        self.stream.stop()
        self.stream.close()
        
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        for btn in self.finding_buttons:
            btn.config(state=tk.DISABLED, bg="SystemButtonFace")
            
        self.status_label.config(text="Verarbeite... Bitte warten.", fg="blue")
        
        self.send_chunk(is_final=True)

    def finalize_transcription(self):
        raw_text = "".join(self.full_transcription)
        
        # 1. Rohdaten speichern
        output_dir = "Transkripte_Raw"
        if not os.path.exists(output_dir): os.makedirs(output_dir)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        with open(os.path.join(output_dir, f"raw_{timestamp}.txt"), "w", encoding="utf-8") as f:
            f.write(raw_text)
            
        self.log("Transkription abgeschlossen. Sende an OpenWebUI (asklaion-v1)...")
        
        # 2. An OpenWebUI senden
        threading.Thread(target=self.process_with_llm, args=(raw_text,)).start()

    def process_with_llm(self, text):
        headers = {
            "Authorization": f"Bearer {OPENWEBUI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Wir senden KEINEN System-Prompt mehr, da 'asklaion-v1' 
        # diesen bereits in OpenWebUI integriert hat.
        payload = {
            "model": LLM_MODEL_NAME,
            "messages": [
                {"role": "user", "content": text}
            ]
        }
        
        try:
            response = requests.post(OPENWEBUI_URL, headers=headers, json=payload)
            
            if response.status_code == 200:
                result_json = response.json()
                llm_response = result_json['choices'][0]['message']['content']
                self.root.after(0, lambda: self.show_llm_result(llm_response))
            else:
                err_msg = f"LLM Fehler: {response.status_code} - {response.text}"
                self.root.after(0, lambda: self.log(err_msg))
                
        except Exception as e:
            self.root.after(0, lambda: self.log(f"LLM Verbindungsfehler: {e}"))

    def show_llm_result(self, text):
        self.status_label.config(text="Fertig!", fg="green")
        
        # --- FIX FÜR PEGAMED ---
        clean_text = text.replace("**", "").replace("##", "")
        clean_text = clean_text.replace('\r\n', '\n').replace('\n', '\r\n')
        
        # Speichern
        output_dir = "Befunde_Fertig"
        if not os.path.exists(output_dir): os.makedirs(output_dir)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filepath = os.path.join(output_dir, f"befund_{timestamp}.txt")
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(clean_text)
            
        # Clipboard mit Windows-Zeilenumbrüchen
        pyperclip.copy(clean_text)
        
        # Popup Fenster
        result_window = tk.Toplevel(self.root)
        result_window.title("LLM Ergebnis (asklaion-v1)")
        result_window.geometry("600x600")
        
        lbl = tk.Label(result_window, text=f"Gespeichert und für Pegamed kopiert!", fg="green")
        lbl.pack(pady=5)
        
        text_area = scrolledtext.ScrolledText(result_window, wrap=tk.WORD, font=("Arial", 11))
        text_area.pack(fill="both", expand=True, padx=10, pady=10)
        text_area.insert(tk.END, clean_text)

if __name__ == "__main__":
    root = tk.Tk()
    app = AudioRecorder(root)
    root.mainloop()