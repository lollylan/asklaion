import sys
import os
# Sicherstellen, dass der Ordner des Scripts im Python-Pfad liegt
# (damit security_utils.py gefunden wird, egal von wo gestartet)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
import json
import queue
from security_utils import encrypt_value, decrypt_value, is_encrypted, open_ca_for_system_install, get_base_dir

_BASE = get_base_dir()

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
CONFIG_FILE = os.path.join(_BASE, "config.json")
DEFAULT_PROMPT_AMBIENT = (
    "Du bist eine professionelle Assistenz-KI für medizinische Dokumentation. "
    "Deine Aufgabe ist es, ein Transkript eines Arzt-Patienten-Gespräches zu analysieren "
    "und in einer strukturierten Zusammenfassung wiederzugeben. Eventuelle Verständnisfehler "
    "der verarbeitenden KI sollen nach bestem Wissen korrigiert werden.\n\n"
    "Die Zusammenfassung muss im folgenden Format erstellt werden:\n\n\n"
    "AN\n"
    "[Anamnese: Beschreibungen des Patienten zu Symptomen, Beschwerden und Krankengeschichte "
    "in einer Zeile; bei mehreren Punkten durch Semicolon getrennt. Falls nötig, Absätze für "
    "thematisch unterschiedliche Inhalte.]\n\n\n"
    "BE\n"
    "[Befund: Ergebnisse der körperlichen Untersuchung, diagnostische Werte oder andere erhobene "
    "Befunde in einer Zeile; bei mehreren Punkten durch Semicolon getrennt. Falls nötig, Absätze "
    "für thematisch unterschiedliche Inhalte.]\n\n\n"
    "LD\n"
    "[Laufende Diagnosen oder im Gespräch erwähnte Verdachtsdiagnosen als ICD-10-Code. "
    "Verwende die Wissensdatenbank (RAG) NUR zur Verifikation eines Codes — trage ihn NUR ein, "
    "wenn du ihn dort eindeutig gefunden hast. Falls kein eindeutiger Treffer in der Wissensdatenbank: "
    "Schreibe die Diagnose im Klartext mit dem Vermerk [ICD?], z.B. \"Hypertonie [ICD?]\". "
    "Keine Benennung der Erkrankung wenn ein Code vorhanden. Bei mehreren Erkrankungen je Code "
    "eine eigene Zeile. Immer nur den Code mit der Endung A, Z, G, oder V, also z.B. \"J06.9G\" "
    "und dann die nächste Zeile. Füge KEINE ICD-10-Codes in AN, BE oder TH ein.]\n\n\n"
    "TH\n"
    "[Therapie und Empfehlungen: Besprochene Maßnahmen, Therapiepläne, Medikamente oder "
    "Empfehlungen in einer Zeile; bei mehreren Punkten durch Semikolon getrennt.]\n\n\n"
    "Weitere Anforderungen:\n\n\n"
    "Sprache: Die Antwort erfolgt immer auf Deutsch. Versuche so geschlechtsneutral wie möglich "
    "zu formulieren, benutze z.B. \"Pat.\" statt \"Patient/Patientin\".\n"
    "Prägnanz: Die zusammengefassten Informationen sollen prägnant, aber vollständig sein.\n"
    "Klarheit: Wenn Informationen fehlen oder unklar sind, notiere dies explizit mit \"[unklar]\" "
    "oder \"[nicht erwähnt]\".\n"
    "Format: Nach den Überschriften AN, BE, LD und TH folgt kein Doppelpunkt oder Leerzeichen. "
    "Der Text beginnt direkt in der nächsten Zeile. Achte unbedingt auf die Formatsvorgabe!"
)

DEFAULT_PROMPT_DIKTAT = (
    "Rolle: Du bist ein hochqualifizierter Editor für medizinische und fachliche Transkripte "
    "mit Fokus auf die deutsche Sprache.\n\n"
    "Aufgabe: Korrigiere und optimiere das folgende Whisper-Transkript eines Gesprächs. "
    "Das Ziel ist eine Version, die so authentisch wie möglich am realen Wortlaut bleibt, "
    "aber typische KI-Transkriptionsfehler eliminiert.\n\n"
    "Leitlinien für die Bearbeitung:\n\n"
    "Authentizität: Verändere nicht den Sprechstil oder die Satzstruktur, es sei denn, sie ist "
    "durch Transkriptionsfehler völlig unverständlich. Behalte den natürlichen Fluss des Gesprächs bei.\n\n"
    "Medikamenten-Check: Dies ist der wichtigste Punkt. Analysiere alle genannten Medikamentennamen. "
    "Falls Whisper ein Wort phonetisch falsch erfasst hat (z. B. \"Metopolol\" statt \"Metoprolol\" "
    "oder \"Amlodipin\" statt \"Amlo-Dippin\"), korrigiere es auf die medizinisch korrekte Schreibweise. "
    "Falls ein Medikament erfunden klingt, leite aus dem Kontext ab, welches reale Präparat gemeint sein könnte.\n\n"
    "Interpunktion & Grammatik: Setze Satzzeichen (Kommas, Punkte, Fragezeichen) so, dass der "
    "Sinnzusammenhang klar wird. Korrigiere offensichtliche Grammatikfehler, die durch die "
    "Audio-Erkennung entstanden sind (z. B. falsche Artikel oder Endungen).\n\n"
    "Fachterminologie: Achte auf medizinische Fachbegriffe und schreibe diese korrekt aus.\n\n"
    "Output: Gib nur den korrigierten Text aus, ohne einleitende Kommentare. Falls du bei einem "
    "Medikament unsicher bist, markiere es in eckigen Klammern, z. B. [Meinte der Sprecher: Marcumar?].\n\n"
    "Wissensnutzung (RAG): Die angebundene Wissensdatenbank kann Medikamentennamen und ICD-10-Codes "
    "enthalten. Benutze dieses Wissen AUSSCHLIESSLICH zur Überprüfung und Korrektur von Medikamenten- "
    "und Fachbegriffen im Transkript. Füge KEINE ICD-10-Codes in den Text ein. Verändere NICHT die "
    "inhaltliche Bedeutung von Diagnosen oder Aussagen des Sprechers."
)

DEFAULT_PROMPT_ARZTBRIEF = (
    "Analysiere den angehängten PDF-Arztbrief und erstelle eine medizinische Zusammenfassung "
    "für die Hausarztakte. Extrahiere ausschließlich die klinisch relevantesten Informationen: "
    "neue Diagnosen, Änderungen der Medikation sowie konkrete Therapieempfehlungen oder anstehende "
    "Untersuchungen. Priorisiere die Vollständigkeit der medizinischen Fakten vor der Kürze, "
    "versuche jedoch, dich auf etwa 2-3 prägnante Sätze zu beschränken. Die Ausgabe muss zwingend "
    "als ein einziger, zusammenhängender Fließtext in einer einzigen Zeile erfolgen - ohne "
    "Zeilenumbrüche, Aufzählungszeichen oder sonstige Formatierungen. Dein Output darf ausschließlich "
    "die Zusammenfassung enthalten, keinerlei einleitende oder abschließende Sätze. Antworte auf Deutsch."
)

DEFAULT_CONFIG = {
    "server_url": "https://192.168.10.51:8000/transcribe",
    "llm_api_url": "http://localhost:11434/v1/chat/completions",
    "api_key": "",
    "ca_cert_path": "",
    "model_ambient": "llama3.1:8b",
    "model_diktat": "llama3.1:8b",
    "model_arena_a": "llama3.1:8b",
    "model_arena_b": "qwen2.5:14b",
    "model_arztbrief": "llama3.1:8b",
    "prompt_ambient": DEFAULT_PROMPT_AMBIENT,
    "prompt_diktat": DEFAULT_PROMPT_DIKTAT,
    "prompt_arena_a": DEFAULT_PROMPT_AMBIENT,
    "prompt_arena_b": DEFAULT_PROMPT_AMBIENT,
    "prompt_arztbrief": DEFAULT_PROMPT_ARZTBRIEF,
    "input_device": None, # ID or Name
    "loopback_device": None, # ID or Name for System Audio
    "chunk_duration": 30,
    "mix_system_audio": False,
    "auto_delete_days": 1
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            # Migration: openwebui_url → llm_api_url
            if "openwebui_url" in loaded and "llm_api_url" not in loaded:
                loaded["llm_api_url"] = loaded.pop("openwebui_url")
            elif "openwebui_url" in loaded:
                loaded.pop("openwebui_url")
            # Neue Keys aus DEFAULT_CONFIG ergänzen (Abwärtskompatibilität)
            for key, value in DEFAULT_CONFIG.items():
                if key not in loaded:
                    loaded[key] = value
            # API-Key im Arbeitsspeicher immer im Klartext halten
            if is_encrypted(loaded.get("api_key", "")):
                loaded["api_key"] = decrypt_value(loaded["api_key"])
            return loaded
    except:
        return DEFAULT_CONFIG.copy()

def save_config(cfg):
    to_save = cfg.copy()
    # API-Key vor dem Schreiben verschlüsseln (nur wenn ein Wert vorhanden)
    raw_key = to_save.get("api_key", "")
    if raw_key and not is_encrypted(raw_key):
        to_save["api_key"] = encrypt_value(raw_key)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=4)

def _tls_verify():
    """Gibt den Pfad zum CA-Zertifikat zurück, False für localhost, oder True (System-CA-Store)."""
    server_url = config.get("server_url", "")
    # Für localhost kein TLS-Verify nötig
    if "localhost" in server_url or "127.0.0.1" in server_url:
        return False
    ca = config.get("ca_cert_path", "")
    if ca and os.path.exists(ca):
        return ca
    return True

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
        self._arena_raw_text = ""  # Rohtext für Arena-Follow-Up
        self.chat_session = {
            "messages": [],      # [{role, content}, ...] voller Chat-Verlauf
            "model": None,       # Ollama-Modell für Follow-Ups
            "window": None,      # Toplevel-Referenz
            "result_text": None, # ScrolledText Widget
            "input_entry": None, # Entry Widget
            "btn_frame": None,   # Frame mit Action-Buttons
        }

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
                windnd.hook_dropfiles(self.root, func=self._on_drop_files, force_unicode=True)
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
        
        filepath = file_list[0]
        if isinstance(filepath, bytes):
            try:
                filepath = filepath.decode("utf-8")
            except UnicodeDecodeError:
                filepath = filepath.decode("cp1252", errors="replace")
        
        filepath = str(filepath).strip('\x00').strip()
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
        """Sendet PDF-Text direkt an Ollama LLM mit System-Prompt"""
        model = config.get("model_arztbrief", "llama3.1:8b")
        system_prompt = config.get("prompt_arztbrief", "")
        headers = self._build_llm_headers()
        payload = {
            "model": model,
            "messages": self._build_messages(system_prompt, text)
        }
        try:
            self.log(f"Sende an LLM ({model})...")
            r = requests.post(config["llm_api_url"], headers=headers, json=payload, timeout=180, verify=_tls_verify())
            if r.status_code == 200:
                result = r.json()['choices'][0]['message']['content']
                self.log(f"Arztbrief-Zusammenfassung erhalten ({len(result)} Zeichen)")
                self.root.after(0, lambda: self._show_arztbrief_done(result, filename, model, system_prompt, text))
            else:
                self.log(f"LLM Fehler: {r.status_code} - {r.text}")
                self.root.after(0, lambda: self._arztbrief_error())
        except Exception as e:
            self.log(f"LLM Exception: {e}")
            self.root.after(0, lambda: self._arztbrief_error())

    def _show_arztbrief_done(self, result, filename, model=None, system_prompt=None, user_text=None):
        """Zeigt Ergebnis an und aktiviert Button wieder"""
        self.arztbrief_status.config(text=f"✅ {filename} analysiert", fg="#27ae60")
        self.status_label.config(text="FERTIG", fg="#2ecc71")
        self.status_dot.config(fg="#2ecc71")
        self.btn_pdf.config(state="normal", bg="#3498db")
        self._show_result(result, model, system_prompt, user_text)

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
        folder = os.path.join(_BASE, "Transkripte_Raw")
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
        win.geometry("620x800")
        win.transient(self.root)
        win.grab_set()

        # Sticky Save Button at the TOP
        top_frame = tk.Frame(win, bg="#ecf0f1")
        top_frame.pack(side="top", fill="x")
        btn_top_save = tk.Button(top_frame, text="💾 Änderungen Speichern", bg="#2ecc71", fg="white", font=("Segoe UI", 9, "bold"), pady=5)
        btn_top_save.pack(side="right", padx=10, pady=5)
        tk.Label(top_frame, text="Einstellungen", font=("Segoe UI", 12, "bold"), bg="#ecf0f1").pack(side="left", padx=10)

        # Scrollbar and Canvas
        canvas = tk.Canvas(win, borderwidth=0, highlightthickness=0)
        scroll = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scroll.set)

        content = tk.Frame(canvas)
        content_window = canvas.create_window((0, 0), window=content, anchor="nw")
        
        def configure_canvas(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(content_window, width=canvas.winfo_width())
        content.bind("<Configure>", configure_canvas)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(content_window, width=e.width))

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        win.bind_all("<MouseWheel>", on_mousewheel)

        def add_entry(name, key):
            tk.Label(content, text=name, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10,0))
            e = tk.Entry(content, width=50)
            e.insert(0, config.get(key, ""))
            e.pack(padx=10, fill="x")
            return e

        e_server = add_entry("Whisper Server URL", "server_url")
        e_webui = add_entry("LLM API URL (Ollama: http://localhost:11434/v1/chat/completions)", "llm_api_url")
        e_key = add_entry("API Key (optional, Ollama braucht keinen)", "api_key")

        # CA-Zertifikat-Auswahl
        tk.Label(content, text="CA-Zertifikat (ca.crt vom Server)", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10,0))
        ca_frame = tk.Frame(content)
        ca_frame.pack(padx=10, fill="x")
        e_ca = tk.Entry(ca_frame, width=38)
        e_ca.insert(0, config.get("ca_cert_path", ""))
        e_ca.pack(side="left", fill="x", expand=True)
        def browse_ca():
            path = filedialog.askopenfilename(title="CA-Zertifikat auswählen", filetypes=[("Zertifikat", "*.crt *.pem"), ("Alle Dateien", "*.*")])
            if path:
                e_ca.delete(0, tk.END)
                e_ca.insert(0, path)
        tk.Button(ca_frame, text="📂", command=browse_ca, relief="flat", bg="#ecf0f1").pack(side="left", padx=4)
        def install_ca_browser():
            path = e_ca.get().strip()
            if not path or not os.path.exists(path):
                messagebox.showerror("Fehler", "Bitte zuerst eine gültige ca.crt Datei auswählen.")
                return
            open_ca_for_system_install(path)
            messagebox.showinfo("Hinweis", "Windows-Zertifikat-Assistent geöffnet.\nBitte 'Lokaler Computer' → 'Vertrauenswürdige Stammzertifizierungsstellen' wählen.")
        tk.Button(content, text="🌐 Im Browser/System vertrauen (einmalig)", command=install_ca_browser,
                  bg="#3498db", fg="white", font=("Segoe UI", 8), relief="flat").pack(anchor="w", padx=10, pady=(2,0))
        # Ollama-Modelle abfragen (versucht localhost:11434 und die konfigurierte URL)
        ollama_models = []
        ollama_urls_to_try = ["http://localhost:11434"]
        configured_url = config.get("llm_api_url", "")
        if configured_url:
            # Basis-URL extrahieren (alles vor /v1/ oder /api/)
            for cut in ["/v1/chat/completions", "/v1/", "/api/chat/completions", "/api/"]:
                if cut in configured_url:
                    base = configured_url.split(cut)[0].rstrip("/")
                    if base not in ollama_urls_to_try:
                        ollama_urls_to_try.insert(0, base)
                    break
        for base_url in ollama_urls_to_try:
            try:
                r_models = requests.get(f"{base_url}/api/tags", timeout=3)
                if r_models.status_code == 200:
                    ollama_models = sorted([m["name"] for m in r_models.json().get("models", [])])
                    break
            except:
                continue

        def add_model_dropdown(label_text, config_key):
            tk.Label(content, text=label_text, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10,0))
            cb = ttk.Combobox(content, values=ollama_models, width=48)
            current_val = config.get(config_key, "")
            cb.set(current_val)
            cb.pack(padx=10, fill="x")
            return cb

        e_model_amb = add_model_dropdown("Gespräch — Modell", "model_ambient")
        e_model_dik = add_model_dropdown("Diktat — Modell", "model_diktat")
        e_model_arena_a = add_model_dropdown("Arena — Modell A", "model_arena_a")
        e_model_arena_b = add_model_dropdown("Arena — Modell B", "model_arena_b")
        e_model_brief = add_model_dropdown("Arztbrief — Modell", "model_arztbrief")
        e_auto_delete = add_entry("Auto-Löschung Transkripte (Tage, 0=aus)", "auto_delete_days")

        # --- System-Prompts ---
        def add_prompt_field(label_text, config_key):
            tk.Label(content, text=label_text, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10,0))
            st = scrolledtext.ScrolledText(content, width=55, height=6, wrap="word", font=("Segoe UI", 8))
            st.insert("1.0", config.get(config_key, ""))
            st.pack(padx=10, fill="x")
            return st

        tk.Label(content, text="─── System-Prompts ───", font=("Segoe UI", 10, "bold"),
                 fg="#2c3e50").pack(anchor="w", padx=10, pady=(15,0))
        tk.Label(content, text="Hier die Anweisungen für jedes LLM pro Modus festlegen:",
                 font=("Segoe UI", 8), fg="#7f8c8d").pack(anchor="w", padx=10)

        st_prompt_amb = add_prompt_field("Gespräch — System-Prompt", "prompt_ambient")
        st_prompt_dik = add_prompt_field("Diktat — System-Prompt", "prompt_diktat")
        st_prompt_arena_a = add_prompt_field("Arena Modell A — System-Prompt", "prompt_arena_a")
        st_prompt_arena_b = add_prompt_field("Arena Modell B — System-Prompt", "prompt_arena_b")
        st_prompt_brief = add_prompt_field("Arztbrief — System-Prompt", "prompt_arztbrief")

        # Audio Devices
        devices = sd.query_devices()
        input_devs = [f"{i}: {d['name']}" for i, d in enumerate(devices) if d['max_input_channels'] > 0]
        wasapi_devs = [f"{i}: {d['name']}" for i, d in enumerate(devices) if d['hostapi'] == sd.default.hostapi]

        tk.Label(content, text="Mikrofon", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10,0))
        cb_mic = ttk.Combobox(content, values=input_devs)
        if config["input_device"] is not None:
             match = [d for d in input_devs if d.startswith(str(config["input_device"]) + ":")]
             if match: cb_mic.set(match[0])
        else:
            cb_mic.set(input_devs[0] if input_devs else "")
        cb_mic.pack(padx=10, fill="x")

        tk.Label(content, text="System-Audio (Loopback) - Optional für Video-Calls", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10,0))
        cb_loop = ttk.Combobox(content, values=wasapi_devs)
        if config["loopback_device"] is not None:
             match = [d for d in wasapi_devs if d.startswith(str(config["loopback_device"]) + ":")]
             if match: cb_loop.set(match[0])
        cb_loop.pack(padx=10, fill="x")
        
        var_mix = tk.BooleanVar(value=config.get("mix_system_audio", False))
        tk.Checkbutton(content, text="System-Audio Aufnehmen (Mix)", variable=var_mix).pack(anchor="w", padx=10, pady=10)

        def save():
            config["server_url"] = e_server.get()
            config["llm_api_url"] = e_webui.get()
            config["api_key"] = e_key.get()
            config["ca_cert_path"] = e_ca.get().strip()
            config["model_ambient"] = e_model_amb.get()
            config["model_diktat"] = e_model_dik.get()
            config["model_arena_a"] = e_model_arena_a.get()
            config["model_arena_b"] = e_model_arena_b.get()
            config["model_arztbrief"] = e_model_brief.get()
            # System-Prompts speichern
            config["prompt_ambient"] = st_prompt_amb.get("1.0", "end-1c")
            config["prompt_diktat"] = st_prompt_dik.get("1.0", "end-1c")
            config["prompt_arena_a"] = st_prompt_arena_a.get("1.0", "end-1c")
            config["prompt_arena_b"] = st_prompt_arena_b.get("1.0", "end-1c")
            config["prompt_arztbrief"] = st_prompt_brief.get("1.0", "end-1c")
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
            
            # Unbind wheel to prevent errors after window destroy
            win.unbind_all("<MouseWheel>")
            win.destroy()
            self.log("Einstellungen gespeichert.")

        btn_top_save.config(command=save)
        tk.Button(content, text="Speichern", command=save, bg="#2ecc71", fg="white", pady=5).pack(fill="x", padx=20, pady=20)

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
            response = requests.post(config["server_url"], files=files, timeout=30, verify=_tls_verify())
            if response.status_code == 200:
                text = response.json().get("text", "")
                if text:
                    self.transcription_parts[idx] = text
                    self._update_live_transcription()
                self.root.after(0, lambda: self.conn_warn.config(text=""))
            else:
                self.log(f"Server Error {response.status_code}")
        except Exception as e:
            err_msg = f"Verbindungsfehler: {str(e)[:30]}..."
            self.log(err_msg)
            self.root.after(0, lambda m=err_msg: self.conn_warn.config(text=m))
        
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

        # UI Updates sofort auf dem Main-Thread (leichtgewichtig)
        for b in [self.amb_start, self.dik_start, self.arena_start]: b.config(state="normal", bg="#2ecc71")
        for b in [self.amb_pause, self.dik_pause, self.amb_stop, self.dik_stop, self.arena_pause, self.arena_stop]: b.config(state="disabled")
        for b in self.finding_buttons: b.config(state="disabled")
        self.status_label.config(text="FINALISIERE...", fg="#3498db")
        self.status_dot.config(fg="#3498db")

        # Manuelle Notiz (braucht Main-Thread für tk.Text-Zugriff)
        note = ""
        if self.notebook.index(self.notebook.select()) == 0:
            note = self.note_ambient.get("1.0", tk.END).strip()
            if note:
                self.note_ambient.delete("1.0", tk.END)

        # Schwere Arbeit (recorder.stop = np.concatenate großer Buffer)
        # in Hintergrund-Thread verschieben, damit GUI nicht einfriert
        def _stop_worker():
            data = self.recorder.stop()

            if note:
                self.chunk_counter += 1
                self.transcription_parts[self.chunk_counter] = f" [NOTIZ: {note}] "

            if data is not None and len(data) > 0:
                self.chunk_counter += 1
                self.upload_queue.put((self.chunk_counter, data, True))
            else:
                self.root.after(0, self.finalize_transcription)

        threading.Thread(target=_stop_worker, daemon=True).start()

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
        
        _raw_dir = os.path.join(_BASE, "Transkripte_Raw")
        if not os.path.exists(_raw_dir): os.makedirs(_raw_dir)
        with open(os.path.join(_raw_dir, f"raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"), "w", encoding="utf-8") as f:
            f.write(raw_text)

        current_tab_idx = self.notebook.index(self.notebook.select())
        
        if current_tab_idx == 2:  # Arena mode
            model_a = config["model_arena_a"]
            model_b = config["model_arena_b"]
            prompt_a = config.get("prompt_arena_a", "")
            prompt_b = config.get("prompt_arena_b", "")
            self.log(f"Arena: Starte LLM A ({model_a}) und LLM B ({model_b})...")
            self.arena_results = {}
            self._arena_raw_text = raw_text
            threading.Thread(target=self._run_llm_arena, args=(raw_text, model_a, "A", prompt_a), daemon=True).start()
            threading.Thread(target=self._run_llm_arena, args=(raw_text, model_b, "B", prompt_b), daemon=True).start()
        else:
            if current_tab_idx == 1:
                model = config["model_diktat"]
                sys_prompt = config.get("prompt_diktat", "")
            else:
                model = config["model_ambient"]
                sys_prompt = config.get("prompt_ambient", "")
            self.log(f"Starte LLM ({model})...")
            threading.Thread(target=self._run_llm, args=(raw_text, model, sys_prompt), daemon=True).start()

    def _build_llm_headers(self):
        """Erstellt Headers für LLM-API. API-Key nur wenn gesetzt (Ollama braucht keinen)."""
        headers = {"Content-Type": "application/json"}
        api_key = config.get("api_key", "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _build_messages(self, system_prompt, user_text):
        """Erstellt messages-Array mit optionalem System-Prompt."""
        messages = []
        if system_prompt and system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_text})
        return messages

    def _run_llm(self, text, model, system_prompt=""):
        headers = self._build_llm_headers()
        payload = {
            "model": model,
            "messages": self._build_messages(system_prompt, text)
        }
        try:
            r = requests.post(config["llm_api_url"], headers=headers, json=payload, timeout=120, verify=_tls_verify())
            if r.status_code == 200:
                res = r.json()['choices'][0]['message']['content']
                self.root.after(0, lambda: self._show_result(res, model, system_prompt, text))
            else:
                self.log(f"LLM Fehler: {r.status_code} - {r.text}")
                self.root.after(0, lambda: self.status_label.config(text="FEHLER", fg="red"))
        except Exception as e:
            self.log(f"LLM Exception: {e}")

    def _run_llm_arena(self, text, model, label, system_prompt=""):
        headers = self._build_llm_headers()
        payload = {
            "model": model,
            "messages": self._build_messages(system_prompt, text)
        }
        result = None
        try:
            r = requests.post(config["llm_api_url"], headers=headers, json=payload, timeout=120, verify=_tls_verify())
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
                m_a = config.get("model_arena_a", "")
                m_b = config.get("model_arena_b", "")
                p_a = config.get("prompt_arena_a", "")
                p_b = config.get("prompt_arena_b", "")
                raw = self._arena_raw_text
                self.root.after(0, lambda: self._show_arena_result(
                    res_a, res_b, raw, m_a, p_a, m_b, p_b))

    # --- Follow-Up Chat ---

    def _reset_chat_session(self):
        """Setzt den Chat-Verlauf zurück."""
        self.chat_session = {
            "messages": [], "model": None, "window": None,
            "result_text": None, "input_entry": None, "btn_frame": None,
        }

    def _send_followup(self, instruction):
        """Sendet eine Follow-Up-Nachricht an das LLM mit vollem Chat-Verlauf."""
        if not instruction or not instruction.strip():
            return
        self.chat_session["messages"].append({"role": "user", "content": instruction.strip()})
        # UI sperren
        if self.chat_session["btn_frame"]:
            for w in self.chat_session["btn_frame"].winfo_children():
                try: w.config(state="disabled")
                except: pass
        if self.chat_session["input_entry"]:
            self.chat_session["input_entry"].config(state="disabled")
        self.status_label.config(text="FOLLOW-UP...", fg="#f39c12")
        self.status_dot.config(fg="#f39c12")
        threading.Thread(target=self._run_followup_llm, daemon=True).start()

    def _send_regenerate(self):
        """Generiert die letzte Antwort neu (gleicher Prompt, frische Antwort)."""
        if self.chat_session["messages"] and self.chat_session["messages"][-1]["role"] == "assistant":
            self.chat_session["messages"].pop()
        # UI sperren
        if self.chat_session["btn_frame"]:
            for w in self.chat_session["btn_frame"].winfo_children():
                try: w.config(state="disabled")
                except: pass
        if self.chat_session["input_entry"]:
            self.chat_session["input_entry"].config(state="disabled")
        self.status_label.config(text="NEU GENERIEREN...", fg="#f39c12")
        self.status_dot.config(fg="#f39c12")
        threading.Thread(target=self._run_followup_llm, daemon=True).start()

    def _run_followup_llm(self):
        """Background-Thread: Sendet vollen Chat-Verlauf an Ollama."""
        headers = self._build_llm_headers()
        payload = {
            "model": self.chat_session["model"],
            "messages": list(self.chat_session["messages"])
        }
        try:
            r = requests.post(config["llm_api_url"], headers=headers, json=payload, timeout=180, verify=_tls_verify())
            if r.status_code == 200:
                res = r.json()['choices'][0]['message']['content']
                self.chat_session["messages"].append({"role": "assistant", "content": res})
                self.root.after(0, lambda: self._update_chat_result(res))
            else:
                self.log(f"Follow-Up LLM Fehler: {r.status_code} - {r.text}")
                self.root.after(0, lambda: self._followup_done_enable())
        except Exception as e:
            self.log(f"Follow-Up LLM Exception: {e}")
            self.root.after(0, lambda: self._followup_done_enable())

    def _update_chat_result(self, new_text):
        """Aktualisiert das Ergebnis-Fenster mit der neuen LLM-Antwort."""
        win = self.chat_session.get("window")
        if not win or not win.winfo_exists():
            self._reset_chat_session()
            return
        clean_text = new_text.replace("**", "").replace("##", "")
        windows_text = clean_text.replace("\r\n", "\n").replace("\n", "\r\n")
        pyperclip.copy(windows_text)
        t = self.chat_session["result_text"]
        t.config(state="normal")
        t.delete("1.0", tk.END)
        t.insert(tk.END, clean_text)
        self.status_label.config(text="FERTIG", fg="#2ecc71")
        self.status_dot.config(fg="#2ecc71")
        self._followup_done_enable()

    def _followup_done_enable(self):
        """Aktiviert Buttons und Eingabefeld nach Follow-Up."""
        if self.chat_session["btn_frame"] and self.chat_session["btn_frame"].winfo_exists():
            for w in self.chat_session["btn_frame"].winfo_children():
                try: w.config(state="normal")
                except: pass
        if self.chat_session["input_entry"] and self.chat_session["input_entry"].winfo_exists():
            self.chat_session["input_entry"].config(state="normal")
            self.chat_session["input_entry"].delete(0, tk.END)
        self.status_label.config(text="FERTIG", fg="#2ecc71")
        self.status_dot.config(fg="#2ecc71")

    def _show_result(self, text, model=None, system_prompt=None, user_text=None):
        self.status_label.config(text="FERTIG", fg="#2ecc71")
        self.status_dot.config(fg="#2ecc71")

        # Altes Chat-Fenster schließen falls noch offen
        old_win = self.chat_session.get("window")
        if old_win and old_win.winfo_exists():
            old_win.destroy()
        self._reset_chat_session()

        clean_text = text.replace("**", "").replace("##", "")
        windows_text = clean_text.replace("\r\n", "\n").replace("\n", "\r\n")
        pyperclip.copy(windows_text)

        win = tk.Toplevel(self.root)
        win.title("Ergebnis")
        win.geometry("600x800")
        win.transient(self.root)
        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 600) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 800) // 2
        win.geometry(f"600x800+{x}+{y}")

        # Ergebnis-Textfeld
        t = scrolledtext.ScrolledText(win, font=("Segoe UI", 11), wrap=tk.WORD)
        t.pack(fill="both", expand=True, padx=10, pady=(10, 5))
        t.insert(tk.END, clean_text)

        # Chat-Session initialisieren
        if model and user_text is not None:
            messages = []
            if system_prompt and system_prompt.strip():
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_text})
            messages.append({"role": "assistant", "content": text})
            self.chat_session["messages"] = messages
            self.chat_session["model"] = model
            self.chat_session["window"] = win
            self.chat_session["result_text"] = t

            # Quick-Action Buttons
            btn_frame = tk.Frame(win, bg="#f5f7f9")
            btn_frame.pack(fill="x", padx=10, pady=(0, 3))
            self.chat_session["btn_frame"] = btn_frame

            tk.Button(btn_frame, text="Neu generieren", command=self._send_regenerate,
                      bg="#e67e22", fg="white", font=("Segoe UI", 9), relief="flat", padx=8, pady=4
                      ).pack(side="left", padx=(0, 4))
            tk.Button(btn_frame, text="Kürzer", command=lambda: self._send_followup("Fasse die Antwort kürzer zusammen."),
                      bg="#3498db", fg="white", font=("Segoe UI", 9), relief="flat", padx=8, pady=4
                      ).pack(side="left", padx=(0, 4))
            tk.Button(btn_frame, text="Länger", command=lambda: self._send_followup("Führe die Antwort ausführlicher aus."),
                      bg="#3498db", fg="white", font=("Segoe UI", 9), relief="flat", padx=8, pady=4
                      ).pack(side="left")

            # Freitext-Eingabe
            input_frame = tk.Frame(win, bg="#f5f7f9")
            input_frame.pack(fill="x", padx=10, pady=(0, 5))

            entry = tk.Entry(input_frame, font=("Segoe UI", 10))
            entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
            self.chat_session["input_entry"] = entry

            def send_custom(event=None):
                txt = entry.get().strip()
                if txt:
                    self._send_followup(txt)

            tk.Button(input_frame, text="Senden", command=send_custom,
                      bg="#27ae60", fg="white", font=("Segoe UI", 9), relief="flat", padx=8, pady=4
                      ).pack(side="right")
            entry.bind("<Return>", send_custom)

        # Kopieren & Schließen
        def close():
            final_text = t.get("1.0", tk.END).strip()
            final_text = final_text.replace("\r\n", "\n").replace("\n", "\r\n")
            pyperclip.copy(final_text)
            self._reset_chat_session()
            win.destroy()

        tk.Button(win, text="Kopieren & Schließen", command=close, bg="#34495e", fg="white", pady=10).pack(fill="x")
        win.protocol("WM_DELETE_WINDOW", close)

    def _show_arena_result(self, result_a, result_b, raw_text="", model_a="", prompt_a="", model_b="", prompt_b=""):
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

        def choose(text_widget, label, chosen_model, chosen_prompt):
            chosen_text = text_widget.get("1.0", tk.END).strip()
            original_result = result_a if label == "A" else result_b
            self.log(f"Arena: Modell {label} gewählt.")
            win.destroy()
            self._show_result(original_result or chosen_text, chosen_model, chosen_prompt, raw_text)

        tk.Button(btn_frame, text=f"✔ Modell A wählen", command=lambda: choose(text_a, "A", model_a, prompt_a),
                  bg="#27ae60", fg="white", font=("Segoe UI", 10, "bold"), pady=8).pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(btn_frame, text=f"✔ Modell B wählen", command=lambda: choose(text_b, "B", model_b, prompt_b),
                  bg="#2980b9", fg="white", font=("Segoe UI", 10, "bold"), pady=8).pack(side="right", fill="x", expand=True, padx=(5, 0))

if __name__ == "__main__":
    root = tk.Tk()
    s = ttk.Style()
    s.configure('TNotebook.Tab', padding=[15, 5], font=('Segoe UI', 9))
    app = ModernRecorder(root)
    root.mainloop()
