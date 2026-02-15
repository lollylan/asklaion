import sys
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog, filedialog
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
import queue

# PDF-Textextraktion
try:
    from PyPDF2 import PdfReader
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False
    print("WARNING: PyPDF2 nicht installiert. 'pip install PyPDF2' für Arztbrief-Funktion.")

# Drag-and-Drop (optional)
try:
    import windnd
    HAS_WINDND = True
except ImportError:
    HAS_WINDND = False

# --- CONFIGURATION MANAGEMENT ---
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "server_url": "http://192.168.10.44:8000/transcribe",
    "openwebui_url": "http://192.168.10.44:3000/api/chat/completions",
    "api_key": "API-Key von OpenwebUI hier eintragen",
    "model_ambient": "asklaion-v1",
    "model_diktat": "diktiersklavev1",
    "model_arena_a": "asklaion-v1",
    "model_arena_b": "diktiersklavev1",
    "model_arztbrief": "arztbriefzusammenfasser",
    "input_device": None, # ID or Name
    "loopback_device": None, # ID or Name for System Audio
    "chunk_duration": 30,
    "mix_system_audio": False,
    "auto_delete_days": 1
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            # Neue Keys aus DEFAULT_CONFIG ergänzen (Abwärtskompatibilität)
            for key, value in DEFAULT_CONFIG.items():
                if key not in loaded:
                    loaded[key] = value
            return loaded
    except:
        return DEFAULT_CONFIG

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

# --- GLOBAL STATE ---
config = load_config()

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

DISCLAIMER_TRANSCRIPTION = (
    "⚠ Hinweis: Transkripte und KI-generierte Dokumentationen sind vom behandelnden "
    "Arzt/Ärztin auf Vollständigkeit und Richtigkeit zu überprüfen. Dieses Programm dient "
    "lediglich als Dokumentationshilfe und darf die ärztliche Behandlung nicht beeinflussen. "
    "Nutzung auf eigene Gefahr – es wird keine Haftung übernommen."
)

class AudioRecorder:
    def __init__(self, callback_fn, meter_callback_fn):
        self.callback_fn = callback_fn
        self.meter_callback_fn = meter_callback_fn
        self.running = False
        self.paused = False
        self.stream_mic = None
        self.stream_loop = None
        self.queue = queue.Queue()
        self.buffer = []
        self.sample_rate = 16000
        
    def start(self, mic_id, loop_id=None, use_loopback=False):
        self.running = True
        self.paused = False
        self.buffer = []
        
        def mic_callback(indata, frames, time, status):
            if status:
                print(f"Mic Status: {status}")
            if self.running and not self.paused:
                self.queue.put(("mic", indata.copy()))

        # Start Mic Stream
        try:
            self.stream_mic = sd.InputStream(
                device=mic_id, samplerate=self.sample_rate, channels=1, 
                callback=mic_callback, blocksize=4096
            )
            self.stream_mic.start()
        except Exception as e:
            print(f"Error starting mic: {e}")
            return False

        # Start Loopback Stream if requested
        if use_loopback and loop_id is not None:
            def loop_callback(indata, frames, time, status):
                if status:
                    print(f"Loop Status: {status}")
                if self.running and not self.paused:
                    self.queue.put(("loop", indata.copy()))
            
            try:
                self.stream_loop = sd.InputStream(
                    device=loop_id, samplerate=self.sample_rate, channels=1,
                    callback=loop_callback, blocksize=4096
                )
                self.stream_loop.start()
            except Exception as e:
                print(f"Error starting loopback: {e}")

        threading.Thread(target=self._process_queue, daemon=True).start()
        return True

    def stop(self):
        self.running = False
        if self.stream_mic:
            self.stream_mic.stop()
            self.stream_mic.close()
        if self.stream_loop:
            self.stream_loop.stop()
            self.stream_loop.close()
        return np.concatenate(self.buffer, axis=0) if self.buffer else None

    def _process_queue(self):
        while self.running:
            try:
                source, data = self.queue.get(timeout=1) 
                rms = np.sqrt(np.mean(data**2))
                level = min(rms * 5, 1.0)
                self.meter_callback_fn(level)
                self.buffer.append(data)
            except queue.Empty:
                continue

    def get_and_reset_buffer(self):
        if not self.buffer:
            return None
        data = np.concatenate(self.buffer, axis=0)
        self.buffer = []
        return data


class ModernRecorder:
    def __init__(self, root):
        self.root = root
        self.root.title("Asklaion v1.0")
        self.root.geometry("520x980")
        self.root.configure(bg="#f5f7f9")
        
        self.recorder = AudioRecorder(self.audio_data_callback, self.update_meter)
        self.upload_queue = queue.Queue()
        self.transcription_parts = {} # index -> text
        self.chunk_counter = 0
        self.is_recording = False
        self.waiting_for_final = False
        self.arena_results = {}
        self.arena_lock = threading.Lock()
        self.patient_files = []  # Liste der angehängten Dateipfade
        self.doc_chat_files = []  # Dokumentenbefragung Dateipfade
        self.doc_chat_messages = []  # Chat-Verlauf [{role, content}]
        self.doc_chat_text = ""  # Extrahierter Dokumententext

        self._setup_ui()
        self._start_upload_worker()
        self._cleanup_old_transcripts()

    def _setup_ui(self):
        # Header (Status & Settings)
        header = tk.Frame(self.root, bg="#f5f7f9")
        header.pack(fill="x", padx=20, pady=(10, 0))
        
        self.status_dot = tk.Label(header, text="●", fg="#bdc3c7", bg="#f5f7f9", font=("Arial", 14))
        self.status_dot.pack(side="left")
        self.status_label = tk.Label(header, text="Bereit", font=("Segoe UI", 9), bg="#f5f7f9", fg="#7f8c8d")
        self.status_label.pack(side="left", padx=5)

        btn_settings = tk.Button(header, text="⚙ Einstellungen", command=self.open_settings,
                               bg="#ecf0f1", fg="#2c3e50", font=("Segoe UI", 8), relief="flat")
        btn_settings.pack(side="right")

        # Connection Warning Label
        self.conn_warn = tk.Label(self.root, text="", font=("Segoe UI", 8), bg="#f5f7f9", fg="#e74c3c")
        self.conn_warn.pack(pady=(0,5))

        # Audio Meter
        self.meter_frame = tk.Frame(self.root, bg="#ddd", height=5)
        self.meter_frame.pack(fill="x", padx=20, pady=5)
        self.meter_bar = tk.Frame(self.meter_frame, bg="#2ecc71", height=5, width=0)
        self.meter_bar.pack(side="left", fill="y")

        # Notebook / Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)
        self.tab_ambient = tk.Frame(self.notebook, bg="#f5f7f9")
        self.tab_diktat = tk.Frame(self.notebook, bg="#f5f7f9")
        self.tab_arena = tk.Frame(self.notebook, bg="#f5f7f9")
        self.tab_arztbrief = tk.Frame(self.notebook, bg="#f5f7f9")
        self.notebook.add(self.tab_ambient, text=" Gespräch ")
        self.notebook.add(self.tab_diktat, text=" Diktat ")
        self.notebook.add(self.tab_arena, text=" Arena ")
        self.notebook.add(self.tab_arztbrief, text=" Arztbrief ")

        self.control_buttons_amb = []
        self.control_buttons_diktat = []
        self.control_buttons_arena = []
        
        self._build_ambient_tab()
        self._build_diktat_tab()
        self._build_arena_tab()
        self._build_arztbrief_tab()

    def _build_ambient_tab(self):
        ctrl = tk.Frame(self.tab_ambient, bg="white", highlightthickness=1, highlightbackground="#e0e6ed")
        ctrl.pack(fill="x", padx=10, pady=10)
        btn_f = tk.Frame(ctrl, bg="white")
        btn_f.pack(pady=10)

        self.amb_start = self._make_btn(btn_f, "Start", "#2ecc71", self.start_recording)
        self.amb_pause = self._make_btn(btn_f, "Pause", "#f39c12", self.toggle_pause, state="disabled")
        self.amb_stop = self._make_btn(btn_f, "Analyse", "#e74c3c", self.stop_recording, state="disabled")
        self.control_buttons_amb = [self.amb_start, self.amb_pause, self.amb_stop]

        tk.Label(self.tab_ambient, text="MANUELLE NOTIZEN", font=("Segoe UI", 7, "bold"), bg="#f5f7f9", fg="#95a5a6").pack(anchor="w", padx=10, pady=(5,0))
        self.note_ambient = tk.Text(self.tab_ambient, height=4, font=("Segoe UI", 10), bd=1, relief="solid")
        self.note_ambient.pack(fill="x", padx=10, pady=5)

        tk.Label(self.tab_ambient, text="NORMBEFUNDE SCHNELLEINFÜGUNG", font=("Segoe UI", 7, "bold"), bg="#f5f7f9", fg="#95a5a6").pack(anchor="w", padx=10)
        grid = tk.Frame(self.tab_ambient, bg="white", bd=1, relief="solid")
        grid.pack(fill="both", expand=True, padx=10, pady=5)

        self.finding_buttons = []
        for i, (name, text) in enumerate(STANDARD_FINDINGS.items()):
            btn = tk.Button(grid, text=name, command=lambda t=text, n=name: self.insert_finding(t, n),
                            bg="#ffffff", fg="#34495e", font=("Segoe UI", 8), relief="flat", bd=0, highlightthickness=1, highlightbackground="#f0f2f5", state="disabled")
            btn.grid(row=i // 2, column=i % 2, padx=2, pady=2, sticky="nsew")
            grid.grid_columnconfigure(i % 2, weight=1)
            self.finding_buttons.append(btn)

        tk.Label(self.tab_ambient, text=DISCLAIMER_TRANSCRIPTION, font=("Segoe UI", 9),
                 bg="#f5f7f9", fg="#e74c3c", wraplength=480, justify="left").pack(anchor="w", padx=10, pady=(5,0))
        self.log_ambient = self._make_log(self.tab_ambient)

    def _build_diktat_tab(self):
        ctrl = tk.Frame(self.tab_diktat, bg="white", highlightthickness=1, highlightbackground="#e0e6ed")
        ctrl.pack(fill="x", padx=10, pady=10)
        btn_f = tk.Frame(ctrl, bg="white")
        btn_f.pack(pady=10)

        self.dik_start = self._make_btn(btn_f, "Start", "#2ecc71", self.start_recording)
        self.dik_pause = self._make_btn(btn_f, "Pause", "#f39c12", self.toggle_pause, state="disabled")
        self.dik_stop = self._make_btn(btn_f, "Analyse", "#e74c3c", self.stop_recording, state="disabled")
        self.control_buttons_diktat = [self.dik_start, self.dik_pause, self.dik_stop]

        tk.Label(self.tab_diktat, text="LIVE-TRANSKRIPT (VORSCHAU)", font=("Segoe UI", 7, "bold"), bg="#f5f7f9", fg="#95a5a6").pack(anchor="w", padx=10, pady=(5,0))
        self.live_text = scrolledtext.ScrolledText(self.tab_diktat, height=18, font=("Segoe UI", 11), bg="white", bd=1, relief="solid", padx=10, pady=10)
        self.live_text.pack(fill="both", expand=True, padx=10, pady=5)

        tk.Label(self.tab_diktat, text=DISCLAIMER_TRANSCRIPTION, font=("Segoe UI", 9),
                 bg="#f5f7f9", fg="#e74c3c", wraplength=480, justify="left").pack(anchor="w", padx=10, pady=(5,0))
        self.log_diktat = self._make_log(self.tab_diktat)

    def _build_arena_tab(self):
        ctrl = tk.Frame(self.tab_arena, bg="white", highlightthickness=1, highlightbackground="#e0e6ed")
        ctrl.pack(fill="x", padx=10, pady=10)
        btn_f = tk.Frame(ctrl, bg="white")
        btn_f.pack(pady=10)

        self.arena_start = self._make_btn(btn_f, "Start", "#2ecc71", self.start_recording)
        self.arena_pause = self._make_btn(btn_f, "Pause", "#f39c12", self.toggle_pause, state="disabled")
        self.arena_stop = self._make_btn(btn_f, "Analyse", "#e74c3c", self.stop_recording, state="disabled")
        self.control_buttons_arena = [self.arena_start, self.arena_pause, self.arena_stop]

        tk.Label(self.tab_arena, text="LIVE-TRANSKRIPT (VORSCHAU)", font=("Segoe UI", 7, "bold"), bg="#f5f7f9", fg="#95a5a6").pack(anchor="w", padx=10, pady=(5,0))
        self.arena_live_text = scrolledtext.ScrolledText(self.tab_arena, height=18, font=("Segoe UI", 11), bg="white", bd=1, relief="solid", padx=10, pady=10)
        self.arena_live_text.pack(fill="both", expand=True, padx=10, pady=5)

        tk.Label(self.tab_arena, text=DISCLAIMER_TRANSCRIPTION, font=("Segoe UI", 9),
                 bg="#f5f7f9", fg="#e74c3c", wraplength=480, justify="left").pack(anchor="w", padx=10, pady=(5,0))
        self.log_arena = self._make_log(self.tab_arena)

    def _build_arztbrief_tab(self):
        """Baut den Arztbrief-Tab: Drop-Zone, PDF-Button, Status, Log"""
        
        # Drop-Zone / Visueller Bereich
        self.drop_frame = tk.Frame(self.tab_arztbrief, bg="white", highlightthickness=2, 
                                    highlightbackground="#3498db", relief="flat")
        self.drop_frame.pack(fill="x", padx=10, pady=10, ipady=30)
        
        self.drop_label = tk.Label(self.drop_frame, 
                                    text="📄  PDF hier hineinziehen\noder Button klicken",
                                    font=("Segoe UI", 12), bg="white", fg="#7f8c8d", justify="center")
        self.drop_label.pack(expand=True, pady=10)
        
        # PDF auswählen Button
        btn_frame = tk.Frame(self.tab_arztbrief, bg="#f5f7f9")
        btn_frame.pack(fill="x", padx=10)
        
        self.btn_pdf = tk.Button(btn_frame, text="📁 PDF auswählen", 
                                  command=self._select_pdf,
                                  bg="#3498db", fg="white", font=("Segoe UI", 10, "bold"),
                                  relief="flat", pady=8, cursor="hand2")
        self.btn_pdf.pack(fill="x")
        
        # Status Label
        self.arztbrief_status = tk.Label(self.tab_arztbrief, text="Kein PDF geladen", 
                                          font=("Segoe UI", 9), bg="#f5f7f9", fg="#95a5a6")
        self.arztbrief_status.pack(anchor="w", padx=10, pady=(10, 0))
        
        # Vorschau des extrahierten Texts
        tk.Label(self.tab_arztbrief, text="EXTRAHIERTER TEXT (VORSCHAU)", 
                 font=("Segoe UI", 7, "bold"), bg="#f5f7f9", fg="#95a5a6").pack(anchor="w", padx=10, pady=(10,0))
        self.arztbrief_preview = scrolledtext.ScrolledText(self.tab_arztbrief, height=12, 
                                                            font=("Segoe UI", 10), bg="white", 
                                                            bd=1, relief="solid", padx=10, pady=10)
        self.arztbrief_preview.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Log
        disclaimer_text = (
            "⚠ Hinweis: KI-generierte Zusammenfassungen dienen ausschließlich der schnelleren "
            "Orientierung und ersetzen nicht das sorgfältige Aktenstudium."
        )
        tk.Label(self.tab_arztbrief, text=disclaimer_text, font=("Segoe UI", 9),
                 bg="#f5f7f9", fg="#e74c3c", wraplength=480, justify="left").pack(anchor="w", padx=10, pady=(5,0))
        self.log_arztbrief = self._make_log(self.tab_arztbrief)
        
        # Drag-and-Drop aktivieren (wenn windnd verfügbar)
        if HAS_WINDND:
            try:
                windnd.hook_dropfiles(self.drop_frame, func=self._on_drop_files)
                windnd.hook_dropfiles(self.drop_label, func=self._on_drop_files)
            except Exception as e:
                print(f"Drag-and-Drop Fehler: {e}")

    def _select_pdf(self):
        """Öffnet Dateidialog zur PDF-Auswahl"""
        filepath = filedialog.askopenfilename(
            title="PDF-Arztbrief auswählen",
            filetypes=[("PDF-Dateien", "*.pdf"), ("Alle Dateien", "*.*")]
        )
        if filepath:
            self._process_arztbrief(filepath)

    def _on_drop_files(self, file_list):
        """Callback für Drag-and-Drop (windnd)"""
        if not file_list:
            return
        # windnd gibt eine Liste von bytes-Pfaden zurück
        filepath = file_list[0]
        if isinstance(filepath, bytes):
            try:
                filepath = filepath.decode("utf-8")
            except UnicodeDecodeError:
                filepath = filepath.decode("cp1252")
        filepath = filepath.strip()
        if filepath.lower().endswith(".pdf"):
            # Zum Arztbrief-Tab wechseln
            self.notebook.select(self.tab_arztbrief)
            self.root.after(100, lambda: self._process_arztbrief(filepath))
        else:
            self.log(f"Nur PDF-Dateien werden unterstützt. Erhalten: {os.path.basename(filepath)}")

    def _process_arztbrief(self, filepath):
        """Extrahiert Text aus PDF und sendet an LLM"""
        filename = os.path.basename(filepath)
        self.arztbrief_status.config(text=f"📄 {filename}", fg="#2c3e50")
        self.log(f"Lade PDF: {filename}")
        
        if not HAS_PYPDF2:
            self.log("FEHLER: PyPDF2 nicht installiert! 'pip install PyPDF2'")
            self.arztbrief_status.config(text="FEHLER: PyPDF2 fehlt", fg="#e74c3c")
            return
        
        # PDF-Text extrahieren
        try:
            reader = PdfReader(filepath)
            text_pages = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text_pages.append(page_text)
            
            if not text_pages:
                self.log("FEHLER: Kein Text im PDF gefunden (evtl. gescanntes Bild-PDF).")
                self.arztbrief_status.config(text="FEHLER: Kein Text extrahiert", fg="#e74c3c")
                return
            
            pdf_text = "\n\n".join(text_pages)
            self.log(f"PDF gelesen: {len(reader.pages)} Seiten, {len(pdf_text)} Zeichen")
            
            # Vorschau anzeigen
            self.arztbrief_preview.delete("1.0", tk.END)
            self.arztbrief_preview.insert(tk.END, pdf_text)
            
        except Exception as e:
            self.log(f"PDF-Lesefehler: {e}")
            self.arztbrief_status.config(text="FEHLER beim Lesen", fg="#e74c3c")
            return
        
        # An LLM senden
        self.arztbrief_status.config(text=f"⏳ Analysiere {filename}...", fg="#3498db")
        self.status_label.config(text="ARZTBRIEF...", fg="#3498db")
        self.status_dot.config(fg="#3498db")
        self.btn_pdf.config(state="disabled", bg="#bdc3c7")
        
        threading.Thread(target=self._run_llm_arztbrief, args=(pdf_text, filename), daemon=True).start()

    def _run_llm_arztbrief(self, text, filename):
        """Sendet PDF-Text an OpenWebUI Modell 'arztbriefzusammenfasser'"""
        model = config.get("model_arztbrief", "arztbriefzusammenfasser")
        headers = {"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": text}]
        }
        try:
            self.log(f"Sende an LLM ({model})...")
            r = requests.post(config["openwebui_url"], headers=headers, json=payload, timeout=180)
            if r.status_code == 200:
                result = r.json()['choices'][0]['message']['content']
                self.log(f"Arztbrief-Zusammenfassung erhalten ({len(result)} Zeichen)")
                self.root.after(0, lambda: self._show_arztbrief_done(result, filename))
            else:
                self.log(f"LLM Fehler: {r.status_code} - {r.text}")
                self.root.after(0, lambda: self._arztbrief_error())
        except Exception as e:
            self.log(f"LLM Exception: {e}")
            self.root.after(0, lambda: self._arztbrief_error())

    def _show_arztbrief_done(self, result, filename):
        """Zeigt Ergebnis an und aktiviert Button wieder"""
        self.arztbrief_status.config(text=f"✅ {filename} analysiert", fg="#27ae60")
        self.status_label.config(text="FERTIG", fg="#2ecc71")
        self.status_dot.config(fg="#2ecc71")
        self.btn_pdf.config(state="normal", bg="#3498db")
        self._show_result(result)

    def _arztbrief_error(self):
        """Fehlerbehandlung für Arztbrief LLM"""
        self.arztbrief_status.config(text="❌ Fehler bei der Analyse", fg="#e74c3c")
        self.status_label.config(text="FEHLER", fg="#e74c3c")
        self.btn_pdf.config(state="normal", bg="#3498db")

    def _make_btn(self, parent, text, color, cmd, state="normal"):
        b = tk.Button(parent, text=text, bg=color, fg="white", font=("Segoe UI", 9, "bold"), relief="flat", width=10, pady=6, command=cmd, state=state)
        b.pack(side="left", padx=3)
        return b
    
    def _make_log(self, parent):
        log = scrolledtext.ScrolledText(parent, height=5, bg="#1e272e", fg="#ecf0f1", font=("Consolas", 8), borderwidth=0)
        log.pack(fill="x", padx=10, pady=10)
        return log

    def log(self, message):
        ts = datetime.now().strftime('%H:%M:%S')
        for logger in [self.log_ambient, self.log_diktat, self.log_arena, self.log_arztbrief]:
            logger.insert(tk.END, f"[{ts}] {message}\n")
            logger.see(tk.END)

    def _cleanup_old_transcripts(self):
        """Löscht alte Transkripte aus Transkripte_Raw/ nach konfigurierten Tagen"""
        days = config.get("auto_delete_days", 1)
        if not isinstance(days, int) or days <= 0:
            return
        folder = "Transkripte_Raw"
        if not os.path.exists(folder):
            return
        cutoff = time.time() - (days * 86400)
        deleted = 0
        for fname in os.listdir(folder):
            fpath = os.path.join(folder, fname)
            if os.path.isfile(fpath) and fname.endswith(".txt"):
                if os.path.getmtime(fpath) < cutoff:
                    try:
                        os.remove(fpath)
                        deleted += 1
                    except Exception as e:
                        print(f"Cleanup-Fehler: {e}")
        if deleted > 0:
            self.log(f"Datenschutz: {deleted} alte Transkript(e) gelöscht (älter als {days} Tag(e)).")

    # --- SETTINGS ---
    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Einstellungen")
        win.geometry("500x650") 
        win.transient(self.root)
        win.grab_set()

        def add_entry(name, key):
            tk.Label(win, text=name, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10,0))
            e = tk.Entry(win, width=50)
            e.insert(0, config.get(key, ""))
            e.pack(padx=10)
            return e

        e_server = add_entry("Whisper Server URL", "server_url")
        e_webui = add_entry("OpenWebUI URL", "openwebui_url")
        e_key = add_entry("API Key", "api_key")
        e_model_amb = add_entry("Ambient Modell ID", "model_ambient")
        e_model_dik = add_entry("Diktat Modell ID", "model_diktat")
        e_model_arena_a = add_entry("Arena Modell A", "model_arena_a")
        e_model_arena_b = add_entry("Arena Modell B", "model_arena_b")
        e_model_brief = add_entry("Arztbrief Modell ID", "model_arztbrief")
        e_auto_delete = add_entry("Auto-Löschung Transkripte (Tage, 0=aus)", "auto_delete_days")

        # Audio Devices
        devices = sd.query_devices()
        input_devs = [f"{i}: {d['name']}" for i, d in enumerate(devices) if d['max_input_channels'] > 0]
        wasapi_devs = [f"{i}: {d['name']}" for i, d in enumerate(devices) if d['hostapi'] == sd.default.hostapi]

        tk.Label(win, text="Mikrofon", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10,0))
        cb_mic = ttk.Combobox(win, values=input_devs, width=50)
        if config["input_device"] is not None:
             match = [d for d in input_devs if d.startswith(str(config["input_device"]) + ":")]
             if match: cb_mic.set(match[0])
        else:
            cb_mic.set(input_devs[0] if input_devs else "")
        cb_mic.pack(padx=10)

        tk.Label(win, text="System-Audio (Loopback) - Optional für Video-Calls", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10,0))
        cb_loop = ttk.Combobox(win, values=wasapi_devs, width=50)
        if config["loopback_device"] is not None:
             match = [d for d in wasapi_devs if d.startswith(str(config["loopback_device"]) + ":")]
             if match: cb_loop.set(match[0])
        cb_loop.pack(padx=10)
        
        var_mix = tk.BooleanVar(value=config.get("mix_system_audio", False))
        tk.Checkbutton(win, text="System-Audio Aufnehmen (Mix)", variable=var_mix).pack(anchor="w", padx=10, pady=5)

        def save():
            config["server_url"] = e_server.get()
            config["openwebui_url"] = e_webui.get()
            config["api_key"] = e_key.get()
            config["model_ambient"] = e_model_amb.get()
            config["model_diktat"] = e_model_dik.get()
            config["model_arena_a"] = e_model_arena_a.get()
            config["model_arena_b"] = e_model_arena_b.get()
            config["model_arztbrief"] = e_model_brief.get()
            try:
                config["auto_delete_days"] = int(e_auto_delete.get())
            except ValueError:
                config["auto_delete_days"] = 1
            
            if cb_mic.get():
                config["input_device"] = int(cb_mic.get().split(":")[0])
            if cb_loop.get():
                config["loopback_device"] = int(cb_loop.get().split(":")[0])
            config["mix_system_audio"] = var_mix.get()
            
            save_config(config)
            win.destroy()
            self.log("Einstellungen gespeichert.")

        tk.Button(win, text="Speichern", command=save, bg="#2ecc71", fg="white", pady=5).pack(fill="x", padx=20, pady=20)

    # --- LOGIC ---
    def audio_data_callback(self, data):
        pass

    def update_meter(self, level):
        self.root.after(10, lambda: self._draw_meter(level))

    def _draw_meter(self, level):
        width = self.meter_frame.winfo_width()
        bar_width = int(width * level)
        self.meter_bar.config(width=bar_width)

    def chunk_timer(self):
        last_time = time.time()
        while self.is_recording:
            time.sleep(0.5)
            if self.is_recording and not self.recorder.paused and (time.time() - last_time >= config["chunk_duration"]):
                data = self.recorder.get_and_reset_buffer()
                if data is not None:
                    self.chunk_counter += 1
                    self.upload_queue.put((self.chunk_counter, data, False))
                last_time = time.time()

    def _start_upload_worker(self):
        def worker():
            while True:
                idx, data, is_final = self.upload_queue.get()
                self._upload_chunk(idx, data, is_final)
                self.upload_queue.task_done()
        threading.Thread(target=worker, daemon=True).start()

    def _upload_chunk(self, idx, data, is_final):
        wav_io = io.BytesIO()
        wav.write(wav_io, 16000, data)
        wav_io.seek(0)
        
        try:
            files = {'file': ('chunk.wav', wav_io, 'audio/wav')}
            response = requests.post(config["server_url"], files=files, timeout=30)
            if response.status_code == 200:
                text = response.json().get("text", "")
                if text:
                    self.transcription_parts[idx] = text
                    self._update_live_transcription()
                self.root.after(0, lambda: self.conn_warn.config(text=""))
            else:
                self.log(f"Server Error {response.status_code}")
        except Exception as e:
            self.root.after(0, lambda: self.conn_warn.config(text=f"Verbindungsfehler: {str(e)[:30]}..."))
        
        if is_final:
            self.root.after(0, self.finalize_transcription)

    def _update_live_transcription(self):
        sorted_keys = sorted(self.transcription_parts.keys())
        full_text = " ".join([self.transcription_parts[k] for k in sorted_keys])
        
        def update():
            self.live_text.delete("1.0", tk.END)
            self.live_text.insert(tk.END, full_text)
            self.live_text.see(tk.END)
            self.arena_live_text.delete("1.0", tk.END)
            self.arena_live_text.insert(tk.END, full_text)
            self.arena_live_text.see(tk.END)
        self.root.after(0, update)

    def start_recording(self):
        self.is_recording = True
        self.chunk_counter = 0
        self.transcription_parts = {}
        self.live_text.delete("1.0", tk.END)
        
        mic_id = config.get("input_device")
        loop_id = config.get("loopback_device")
        use_loop = config.get("mix_system_audio", False)

        success = self.recorder.start(mic_id, loop_id, use_loop)
        if not success:
            messagebox.showerror("Fehler", "Konnte Audio-Gerät nicht starten.")
            self.is_recording = False
            return

        # UI Updates
        for b in [self.amb_start, self.dik_start, self.arena_start]: b.config(state="disabled", bg="#bdc3c7")
        for b in [self.amb_pause, self.dik_pause, self.amb_stop, self.dik_stop, self.arena_pause, self.arena_stop]: b.config(state="normal")
        for b in self.finding_buttons: b.config(state="normal")
        self.status_dot.config(fg="#e74c3c")
        self.status_label.config(text="AUFNAHME", fg="#e74c3c")

        threading.Thread(target=self.chunk_timer, daemon=True).start()
        self.log("Aufnahme gestartet.")

    def stop_recording(self):
        self.is_recording = False
        data = self.recorder.stop()
        
        # UI Updates
        for b in [self.amb_start, self.dik_start, self.arena_start]: b.config(state="normal", bg="#2ecc71")
        for b in [self.amb_pause, self.dik_pause, self.amb_stop, self.dik_stop, self.arena_pause, self.arena_stop]: b.config(state="disabled")
        for b in self.finding_buttons: b.config(state="disabled")
        self.status_label.config(text="FINALISIERE...", fg="#3498db")
        self.status_dot.config(fg="#3498db")

        # Manuelle Notiz
        if self.notebook.index(self.notebook.select()) == 0:
            note = self.note_ambient.get("1.0", tk.END).strip()
            if note:
                self.chunk_counter += 1
                self.transcription_parts[self.chunk_counter] = f" [NOTIZ: {note}] "
                self.note_ambient.delete("1.0", tk.END)

        if data is not None and len(data) > 0:
            self.chunk_counter += 1
            self.upload_queue.put((self.chunk_counter, data, True))
        else:
            self.finalize_transcription()

    def toggle_pause(self):
        self.recorder.paused = not self.recorder.paused
        state = "PAUSIERT" if self.recorder.paused else "AUFNAHME"
        self.status_label.config(text=state, fg="#f39c12" if self.recorder.paused else "#e74c3c")
        btn_text = "Weiter" if self.recorder.paused else "Pause"
        self.amb_pause.config(text=btn_text)
        self.dik_pause.config(text=btn_text)
        self.arena_pause.config(text=btn_text)

    def insert_finding(self, text, name):
        self.chunk_counter += 1
        self.transcription_parts[self.chunk_counter] = f" [BEFUND {name}: {text}] "
        self.log(f"Befund {name} eingefügt.")
        self._update_live_transcription()

    def finalize_transcription(self):
        sorted_keys = sorted(self.transcription_parts.keys())
        raw_text = " ".join([self.transcription_parts[k] for k in sorted_keys])
        
        if not os.path.exists("Transkripte_Raw"): os.makedirs("Transkripte_Raw")
        with open(f"Transkripte_Raw/raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", "w", encoding="utf-8") as f:
            f.write(raw_text)

        current_tab_idx = self.notebook.index(self.notebook.select())
        
        if current_tab_idx == 2:  # Arena mode
            model_a = config["model_arena_a"]
            model_b = config["model_arena_b"]
            self.log(f"Arena: Starte LLM A ({model_a}) und LLM B ({model_b})...")
            self.arena_results = {}
            threading.Thread(target=self._run_llm_arena, args=(raw_text, model_a, "A"), daemon=True).start()
            threading.Thread(target=self._run_llm_arena, args=(raw_text, model_b, "B"), daemon=True).start()
        else:
            model = config["model_diktat"] if current_tab_idx == 1 else config["model_ambient"]
            self.log(f"Starte LLM ({model})...")
            threading.Thread(target=self._run_llm, args=(raw_text, model), daemon=True).start()

    def _run_llm(self, text, model):
        headers = {"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"}
        payload = {
            "model": model, 
            "messages": [{"role": "user", "content": text}]
        }
        try:
            r = requests.post(config["openwebui_url"], headers=headers, json=payload, timeout=120)
            if r.status_code == 200:
                res = r.json()['choices'][0]['message']['content']
                self.root.after(0, lambda: self._show_result(res))
            else:
                self.log(f"LLM Fehler: {r.status_code} - {r.text}")
                self.root.after(0, lambda: self.status_label.config(text="FEHLER", fg="red"))
        except Exception as e:
            self.log(f"LLM Exception: {e}")

    def _run_llm_arena(self, text, model, label):
        headers = {"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": text}]
        }
        result = None
        try:
            r = requests.post(config["openwebui_url"], headers=headers, json=payload, timeout=120)
            if r.status_code == 200:
                result = r.json()['choices'][0]['message']['content']
                self.log(f"Arena Modell {label} ({model}) fertig.")
            else:
                self.log(f"Arena LLM {label} Fehler: {r.status_code} - {r.text}")
        except Exception as e:
            self.log(f"Arena LLM {label} Exception: {e}")

        with self.arena_lock:
            self.arena_results[label] = result
            if len(self.arena_results) == 2:
                res_a = self.arena_results.get("A")
                res_b = self.arena_results.get("B")
                self.root.after(0, lambda: self._show_arena_result(res_a, res_b))

    def _show_result(self, text):
        self.status_label.config(text="FERTIG", fg="#2ecc71")
        self.status_dot.config(fg="#2ecc71")
        
        clean_text = text.replace("**", "").replace("##", "")
        windows_text = clean_text.replace("\r\n", "\n").replace("\n", "\r\n")
        pyperclip.copy(windows_text)
        
        win = tk.Toplevel(self.root)
        win.title("Ergebnis")
        win.geometry("600x700")
        win.transient(self.root)
        # Über dem Hauptfenster zentrieren
        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 600) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 700) // 2
        win.geometry(f"600x700+{x}+{y}")
        
        t = scrolledtext.ScrolledText(win, font=("Segoe UI", 11), wrap=tk.WORD)
        t.pack(fill="both", expand=True, padx=10, pady=10)
        t.insert(tk.END, clean_text)
        
        def close(): 
            final_text = t.get("1.0", tk.END).strip()
            final_text = final_text.replace("\r\n", "\n").replace("\n", "\r\n")
            pyperclip.copy(final_text)
            win.destroy()
            
        tk.Button(win, text="Kopieren & Schließen", command=close, bg="#34495e", fg="white", pady=10).pack(fill="x")

    def _show_arena_result(self, result_a, result_b):
        self.status_label.config(text="ARENA FERTIG", fg="#2ecc71")
        self.status_dot.config(fg="#2ecc71")

        model_a_name = config.get("model_arena_a", "Modell A")
        model_b_name = config.get("model_arena_b", "Modell B")

        clean_a = (result_a or "(Kein Ergebnis)").replace("**", "").replace("##", "")
        clean_b = (result_b or "(Kein Ergebnis)").replace("**", "").replace("##", "")

        win = tk.Toplevel(self.root)
        win.title("Arena – Ergebnis-Vergleich")
        win.geometry("1100x700")
        win.transient(self.root)
        # Über dem Hauptfenster zentrieren
        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 1100) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 700) // 2
        win.geometry(f"1100x700+{x}+{y}")

        pane = tk.Frame(win, bg="#f5f7f9")
        pane.pack(fill="both", expand=True, padx=10, pady=10)
        pane.grid_columnconfigure(0, weight=1)
        pane.grid_columnconfigure(1, weight=1)
        pane.grid_rowconfigure(0, weight=1)

        frame_a = tk.LabelFrame(pane, text=f"  Modell A: {model_a_name}  ", font=("Segoe UI", 10, "bold"), bg="#f5f7f9")
        frame_a.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        text_a = scrolledtext.ScrolledText(frame_a, font=("Segoe UI", 10), wrap=tk.WORD)
        text_a.pack(fill="both", expand=True, padx=5, pady=5)
        text_a.insert(tk.END, clean_a)

        frame_b = tk.LabelFrame(pane, text=f"  Modell B: {model_b_name}  ", font=("Segoe UI", 10, "bold"), bg="#f5f7f9")
        frame_b.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        text_b = scrolledtext.ScrolledText(frame_b, font=("Segoe UI", 10), wrap=tk.WORD)
        text_b.pack(fill="both", expand=True, padx=5, pady=5)
        text_b.insert(tk.END, clean_b)

        btn_frame = tk.Frame(win, bg="#f5f7f9")
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        def choose(text_widget, label):
            final_text = text_widget.get("1.0", tk.END).strip()
            final_text = final_text.replace("\r\n", "\n").replace("\n", "\r\n")
            pyperclip.copy(final_text)
            self.log(f"Arena: Modell {label} gewählt und kopiert.")
            win.destroy()

        tk.Button(btn_frame, text=f"✔ Modell A wählen & kopieren", command=lambda: choose(text_a, "A"),
                  bg="#27ae60", fg="white", font=("Segoe UI", 10, "bold"), pady=8).pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(btn_frame, text=f"✔ Modell B wählen & kopieren", command=lambda: choose(text_b, "B"),
                  bg="#2980b9", fg="white", font=("Segoe UI", 10, "bold"), pady=8).pack(side="right", fill="x", expand=True, padx=(5, 0))

if __name__ == "__main__":
    root = tk.Tk()
    s = ttk.Style()
    s.configure('TNotebook.Tab', padding=[15, 5], font=('Segoe UI', 9))
    app = ModernRecorder(root)
    root.mainloop()
