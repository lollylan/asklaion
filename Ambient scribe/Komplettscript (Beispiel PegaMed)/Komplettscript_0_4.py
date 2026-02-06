import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
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

# --- KONFIGURATION ---
SERVER_URL = "http://192.168.10.175:8000/transcribe" 
SAMPLE_RATE = 16000
CHUNK_DURATION = 30 
OPENWEBUI_URL = "http://192.168.10.175:3000/api/chat/completions"
OPENWEBUI_API_KEY = "HIER Der API Key von OpenWebUI"

# Modelle
MODEL_AMBIENT = "Modellname ScribeModell aus OpenwebUI"
MODEL_DIKTAT = "Modellname Diktiermodell aus OpenwebUI"

STANDARD_FINDINGS = {
    "Herz": "Cor: Herztöne rein, regelmäßig, rhythmisch.",
    "Lunge": "Pulmo: Vesikuläratmen bds., keine Rasselgeräusche.",
    "Abdomen": "Abdomen: Bauchdecke weich, kein Druckschmerz.",
    "Rachen": "Rachen: Schleimhaut feucht, rosig, reizlos.",
    "Ohren": "Otoscopie: Trommelfelle intakt, Lichtreflex erhalten.",
    "Wirbelsäule": "WS: Lotgerecht, kein Klopfschmerz.",
    "Niere": "Nierenlager beidseits indolent.",
    "Lymphknoten": "LK: Zervikal/axillär nicht vergrößert.",
    "Beine": "Extremitäten: Keine Ödeme, Pulse tastbar.",
    "Neuro": "Neuro: Isokor, Stand/Gang sicher.",
    "Haut": "Haut: Warm, Turgor normal.",
    "Schilddrüse": "Schilddrüse: Schluckverschieblich.",
    "Psyche": "Psych/AZ: Wach, orientiert, AZ gut."
}

class ModernRecorder:
    def __init__(self, root):
        self.root = root
        self.root.title("Asklaion v1 PRO - Dr. Rasche")
        self.root.geometry("500x920")
        self.root.configure(bg="#f5f7f9")
        
        self.is_recording = False
        self.is_paused = False
        self.audio_buffer = []
        self.full_transcription = []
        
        # Listen für Buttons zur Statussteuerung
        self.finding_buttons_amb = []
        self.control_buttons_amb = []
        self.control_buttons_diktat = []

        self._setup_ui()

    def _setup_ui(self):
        # Header (Statusanzeige)
        header = tk.Frame(self.root, bg="#f5f7f9")
        header.pack(fill="x", padx=20, pady=(10, 0))
        self.status_dot = tk.Label(header, text="●", fg="#bdc3c7", bg="#f5f7f9", font=("Arial", 14))
        self.status_dot.pack(side="left")
        self.status_label = tk.Label(header, text="Bereit", font=("Segoe UI", 9), bg="#f5f7f9", fg="#7f8c8d")
        self.status_label.pack(side="left", padx=5)

        # Notebook / Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        self.tab_ambient = tk.Frame(self.notebook, bg="#f5f7f9")
        self.tab_diktat = tk.Frame(self.notebook, bg="#f5f7f9")

        self.notebook.add(self.tab_ambient, text="  Gespräch (Ambient)  ")
        self.notebook.add(self.tab_diktat, text="  Diktat  ")

        # Inhalten aufbauen
        self._build_ambient_tab()
        self._build_diktat_tab()

    def _build_ambient_tab(self):
        # Steuerung
        ctrl = tk.Frame(self.tab_ambient, bg="white", highlightthickness=1, highlightbackground="#e0e6ed")
        ctrl.pack(fill="x", padx=10, pady=10)
        btn_f = tk.Frame(ctrl, bg="white")
        btn_f.pack(pady=10)

        self.amb_start = tk.Button(btn_f, text="Start", bg="#2ecc71", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", width=10, pady=6, command=self.start_recording)
        self.amb_pause = tk.Button(btn_f, text="Pause", bg="#f39c12", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", width=10, pady=6, state="disabled", command=self.toggle_pause)
        self.amb_stop = tk.Button(btn_f, text="Analyse", bg="#e74c3c", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", width=10, pady=6, state="disabled", command=self.stop_recording)
        
        for b in [self.amb_start, self.amb_pause, self.amb_stop]: 
            b.pack(side="left", padx=3)
            self.control_buttons_amb.append(b)

        # Manuelle Notizen (Nur Ambient)
        tk.Label(self.tab_ambient, text="MANUELLE NOTIZEN (FÜR KI-ANALYSE)", font=("Segoe UI", 7, "bold"), bg="#f5f7f9", fg="#95a5a6").pack(anchor="w", padx=10, pady=(5,0))
        self.note_ambient = tk.Text(self.tab_ambient, height=4, font=("Segoe UI", 10), bd=1, relief="solid")
        self.note_ambient.pack(fill="x", padx=10, pady=5)

        # Normbefunde (Nur Ambient)
        tk.Label(self.tab_ambient, text="NORMBEFUNDE SCHNELLEINFÜGUNG", font=("Segoe UI", 7, "bold"), bg="#f5f7f9", fg="#95a5a6").pack(anchor="w", padx=10)
        grid = tk.Frame(self.tab_ambient, bg="white", bd=1, relief="solid")
        grid.pack(fill="both", expand=True, padx=10, pady=5)

        for i, (name, text) in enumerate(STANDARD_FINDINGS.items()):
            btn = tk.Button(grid, text=name, command=lambda t=text, n=name: self.insert_finding(t, n),
                            bg="#ffffff", fg="#34495e", font=("Segoe UI", 8), relief="flat", bd=0, highlightthickness=1, highlightbackground="#f0f2f5", state="disabled")
            btn.grid(row=i // 2, column=i % 2, padx=2, pady=2, sticky="nsew")
            grid.grid_columnconfigure(i % 2, weight=1)
            self.finding_buttons_amb.append(btn)

        # Log
        self.log_ambient = scrolledtext.ScrolledText(self.tab_ambient, height=5, bg="#1e272e", fg="#ecf0f1", font=("Consolas", 8), borderwidth=0)
        self.log_ambient.pack(fill="x", padx=10, pady=10)

    def _build_diktat_tab(self):
        # Steuerung
        ctrl = tk.Frame(self.tab_diktat, bg="white", highlightthickness=1, highlightbackground="#e0e6ed")
        ctrl.pack(fill="x", padx=10, pady=10)
        btn_f = tk.Frame(ctrl, bg="white")
        btn_f.pack(pady=10)

        self.dik_start = tk.Button(btn_f, text="Start", bg="#2ecc71", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", width=10, pady=6, command=self.start_recording)
        self.dik_pause = tk.Button(btn_f, text="Pause", bg="#f39c12", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", width=10, pady=6, state="disabled", command=self.toggle_pause)
        self.dik_stop = tk.Button(btn_f, text="Analyse", bg="#e74c3c", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", width=10, pady=6, state="disabled", command=self.stop_recording)
        
        for b in [self.dik_start, self.dik_pause, self.dik_stop]: 
            b.pack(side="left", padx=3)
            self.control_buttons_diktat.append(b)

        # Live-Transkript (Viel Platz im Diktat-Modus)
        tk.Label(self.tab_diktat, text="LIVE-TRANSKRIPT (WHISPER VORSCHAU)", font=("Segoe UI", 7, "bold"), bg="#f5f7f9", fg="#95a5a6").pack(anchor="w", padx=10, pady=(5,0))
        self.live_text = scrolledtext.ScrolledText(self.tab_diktat, height=22, font=("Segoe UI", 11), bg="white", bd=1, relief="solid", padx=10, pady=10)
        self.live_text.pack(fill="both", expand=True, padx=10, pady=5)

        # Log
        self.log_diktat = scrolledtext.ScrolledText(self.tab_diktat, height=5, bg="#1e272e", fg="#ecf0f1", font=("Consolas", 8), borderwidth=0)
        self.log_diktat.pack(fill="x", padx=10, pady=10)

    def log(self, message):
        ts = datetime.now().strftime('%H:%M:%S')
        for logger in [self.log_ambient, self.log_diktat]:
            logger.insert(tk.END, f"[{ts}] {message}\n")
            logger.see(tk.END)

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        status = "PAUSIERT" if self.is_paused else "AKTIV"
        color = "#f39c12" if self.is_paused else "#e74c3c"
        self.status_label.config(text=status, fg=color)
        self.status_dot.config(fg=color)
        btn_text = "Weiter" if self.is_paused else "Pause"
        self.amb_pause.config(text=btn_text)
        self.dik_pause.config(text=btn_text)
        self.log(f"Aufnahme {status.lower()}.")

    def insert_finding(self, text, name):
        self.full_transcription.append(f"\n[BEFUND {name.upper()}: {text}]\n")
        self.log(f"-> {name} zugefügt.")

    def audio_callback(self, indata, frames, time, status):
        if self.is_recording and not self.is_paused:
            self.audio_buffer.append(indata.copy())

    def process_audio_thread(self):
        last_chunk_time = time.time()
        while self.is_recording:
            time.sleep(1)
            if not self.is_paused and time.time() - last_chunk_time >= CHUNK_DURATION:
                self.send_chunk()
                last_chunk_time = time.time()

    def send_chunk(self, is_final=False):
        if not self.audio_buffer and not is_final: return
        if self.audio_buffer:
            chunk_data = np.concatenate(self.audio_buffer, axis=0)
            if not is_final: self.audio_buffer = [] 
            wav_io = io.BytesIO()
            wav.write(wav_io, SAMPLE_RATE, chunk_data)
            wav_io.seek(0)
            threading.Thread(target=self._upload_task, args=(wav_io, is_final), daemon=True).start()
        elif is_final:
            self.finalize_transcription()

    def _upload_task(self, wav_file, is_final):
        try:
            files = {'file': ('chunk.wav', wav_file, 'audio/wav')}
            response = requests.post(SERVER_URL, files=files, timeout=15)
            if response.status_code == 200:
                text = response.json().get("text", "")
                if text:
                    self.full_transcription.append(text + " ")
                    # Live-Update nur im Diktat-Tab anzeigen
                    if self.notebook.index(self.notebook.select()) == 1:
                        self.root.after(0, lambda t=text: self.live_text.insert(tk.END, t + " "))
                        self.root.after(0, lambda: self.live_text.see(tk.END))
        except Exception as e:
            self.log(f"Server-Fehler: {e}")
        if is_final: self.root.after(0, self.finalize_transcription)

    def start_recording(self):
        self.is_recording, self.is_paused = True, False
        self.audio_buffer, self.full_transcription = [], []
        self.live_text.delete("1.0", tk.END)
        
        # UI-States
        for b in [self.amb_start, self.dik_start]: b.config(state="disabled", bg="#bdc3c7")
        for b in [self.amb_pause, self.dik_pause, self.amb_stop, self.dik_stop]: b.config(state="normal")
        for b in self.finding_buttons_amb: b.config(state="normal")
        
        self.status_dot.config(fg="#e74c3c")
        self.status_label.config(text="AKTIV", fg="#e74c3c")
        
        self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, callback=self.audio_callback)
        self.stream.start()
        threading.Thread(target=self.process_audio_thread, daemon=True).start()
        self.log("Aufnahme gestartet.")

    def stop_recording(self):
        # Autom. Notizen nur im Ambient-Modus auslesen
        current_tab = self.notebook.index(self.notebook.select())
        if current_tab == 0: # Ambient
            manual_text = self.note_ambient.get("1.0", tk.END).strip()
            if manual_text:
                self.full_transcription.append(f"\n[MANUELLE NOTIZ: {manual_text}]\n")
                self.note_ambient.delete("1.0", tk.END)

        self.is_recording = False
        self.stream.stop()
        self.stream.close()
        
        for b in [self.amb_start, self.dik_start]: b.config(state="normal", bg="#2ecc71")
        for b in [self.amb_pause, self.dik_pause, self.amb_stop, self.dik_stop]: b.config(state="disabled")
        
        self.status_label.config(text="VERARBEITE...", fg="#3498db")
        self.send_chunk(is_final=True)

    def finalize_transcription(self):
        raw_text = "".join(self.full_transcription)
        current_tab = self.notebook.index(self.notebook.select())
        model = MODEL_DIKTAT if current_tab == 1 else MODEL_AMBIENT
        
        output_dir = "Transkripte_Raw"
        if not os.path.exists(output_dir): os.makedirs(output_dir)
        with open(os.path.join(output_dir, f"raw_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"), "w", encoding="utf-8") as f:
            f.write(raw_text)
        
        self.log(f"KI-Analyse läuft ({model})...")
        threading.Thread(target=self.process_with_llm, args=(raw_text, model), daemon=True).start()

    def process_with_llm(self, text, model):
        headers = {"Authorization": f"Bearer {OPENWEBUI_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": model, "messages": [{"role": "user", "content": text}]}
        try:
            response = requests.post(OPENWEBUI_URL, headers=headers, json=payload, timeout=120)
            if response.status_code == 200:
                res = response.json()['choices'][0]['message']['content']
                self.root.after(0, lambda: self.show_editable_result(res))
            else:
                self.log(f"KI-Fehler: {response.status_code}")
        except Exception as e:
            self.log(f"Fehler: {e}")

    def show_editable_result(self, text):
        self.status_label.config(text="BEREIT", fg="#7f8c8d")
        clean_text = text.replace("**", "").replace("##", "").replace("#", "")
        clean_text = clean_text.replace('\r\n', '\n').replace('\n', '\r\n')
        
        pyperclip.copy(clean_text)
        
        res_win = tk.Toplevel(self.root)
        res_win.title("Ergebnis (Editierbar)")
        res_win.geometry("500x650")
        res_win.configure(bg="#f5f7f9")
        res_win.attributes("-topmost", True)

        tk.Label(res_win, text="Generierter Befund (Korrektur möglich):", font=("Segoe UI", 9, "bold"), bg="#f5f7f9", fg="#2c3e50").pack(pady=10)
        
        txt_area = scrolledtext.ScrolledText(res_win, wrap=tk.WORD, font=("Segoe UI", 11), padx=10, pady=10, bg="white", bd=0)
        txt_area.pack(fill="both", expand=True, padx=15, pady=5)
        txt_area.insert(tk.END, clean_text)

        def finalize_and_copy():
            final_text = txt_area.get("1.0", tk.END).strip()
            pyperclip.copy(final_text)
            res_win.destroy()

        btn_close = tk.Button(res_win, text="In Zwischenablage & Schließen", command=finalize_and_copy, 
                              bg="#34495e", fg="white", font=("Segoe UI", 10, "bold"), relief="flat", pady=10)
        btn_close.pack(side="bottom", fill="x", padx=15, pady=15)

if __name__ == "__main__":
    root = tk.Tk()
    s = ttk.Style()
    s.configure('TNotebook.Tab', padding=[15, 5], font=('Segoe UI', 9))
    app = ModernRecorder(root)
    root.mainloop()