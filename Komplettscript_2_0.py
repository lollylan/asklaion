"""
Asklaion Komplettscript v2.0 – Client für das Behandlungszimmer
================================================================
Nimmt das Arzt-Patienten-Gespräch auf, schickt es chunkweise an den
Praxisserver (server.py), zeigt das Live-Transkript, holt am Ende das
Transkript mit Sprecherlabels ab und lässt ein lokales LLM (Ollama, über den
Praxisserver) die Dokumentation erstellen.

Neu in v2.0:
  * Sitzungsbasierte Übertragung: jedes Zimmer hat eine eigene Server-Sitzung,
    nichts vermischt sich – auch bei gleichzeitiger Nutzung.
  * Chunks werden an Sprechpausen geschnitten (keine zerschnittenen Wörter),
    stille Chunks werden gar nicht erst hochgeladen.
  * Sprechertrennung (ARZT / PATIENT / SPRECHER n) und Anlernen der eigenen Stimme.
  * Kontextfeld (Medikationsplan, Vorerkrankungen) verbessert Whisper (Hotwords)
    und die LLM-Zusammenfassung.
  * LLM-Antworten werden gestreamt; Kontextfenster und Temperatur werden explizit
    gesetzt (kein stilles Abschneiden langer Gespräche mehr).
  * Globale Tastenkürzel (Start / Pause / Analyse / Kopieren & Schließen), auch per
    Makro auslösbar, und Freihand-Diktat: Taste halten, sprechen, loslassen – der
    Text landet im gerade aktiven Fenster (PVS, Notepad, ...).

Benötigt: pip install -r requirements-client.txt
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import io
import json
import queue
import re
import socket
import threading
import time
from datetime import datetime

import numpy as np
import requests
import sounddevice as sd
import scipy.io.wavfile as wav
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import pyperclip

from security_utils import (encrypt_value, decrypt_value, is_encrypted,
                            open_ca_for_system_install, get_base_dir)
import hotkeys

try:
    import winsound
except ImportError:
    winsound = None

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

_BASE = get_base_dir()
VERSION = "2.0"
SAMPLE_RATE = 16000

try:
    from PyPDF2 import PdfReader
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False
    print("WARNING: PyPDF2 nicht installiert. 'pip install PyPDF2' für Arztbrief-Funktion.")

try:
    import windnd
    HAS_WINDND = True
except ImportError:
    HAS_WINDND = False

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
CONFIG_FILE = os.path.join(_BASE, "config.json")

DEFAULT_PROMPT_AMBIENT = (
    "Du bist eine professionelle Assistenz-KI für medizinische Dokumentation in einer "
    "Hausarztpraxis. Deine Aufgabe ist es, das Transkript eines Arzt-Patienten-Gesprächs zu "
    "analysieren und als strukturierte Dokumentation wiederzugeben.\n\n"
    "Hinweise zum Transkript:\n"
    "- Die Zeilen sind mit Sprecherlabels versehen (ARZT, PATIENT, SPRECHER 1/2, ...). "
    "Sind die Rollen nicht benannt, erschließe sie aus dem Inhalt (wer untersucht, fragt und "
    "verordnet, ist der Arzt). Angehörige oder Begleitpersonen als solche kennzeichnen.\n"
    "- Automatische Spracherkennung kann Wörter verwechseln; korrigiere offensichtliche "
    "Erkennungsfehler nach bestem Wissen, insbesondere bei Medikamentennamen. Ein ggf. "
    "mitgelieferter Kontext (Medikationsplan, Notizen) hat dabei Vorrang.\n"
    "- Abschnitte [NOTIZ: ...] und [BEFUND ...] stammen direkt vom Arzt und sind verlässlich.\n\n"
    "Die Zusammenfassung muss im folgenden Format erstellt werden:\n\n\n"
    "AN\n"
    "[Anamnese: Beschreibungen des Patienten zu Symptomen, Beschwerden und Krankengeschichte "
    "in einer Zeile; bei mehreren Punkten durch Semikolon getrennt. Falls nötig, Absätze für "
    "thematisch unterschiedliche Inhalte.]\n\n\n"
    "BE\n"
    "[Befund: Ergebnisse der körperlichen Untersuchung, diagnostische Werte oder andere erhobene "
    "Befunde in einer Zeile; bei mehreren Punkten durch Semikolon getrennt.]\n\n\n"
    "LD\n"
    "[Laufende Diagnosen oder im Gespräch genannte Verdachtsdiagnosen. Wenn du dir beim ICD-10-Code "
    "sicher bist, nur den Code mit Endung A, Z, G oder V (z. B. \"J06.9G\"), je Code eine Zeile. "
    "Bist du unsicher, schreibe die Diagnose im Klartext mit dem Vermerk [ICD?], z. B. "
    "\"Hypertonie [ICD?]\". Füge KEINE ICD-10-Codes in AN, BE oder TH ein.]\n\n\n"
    "TH\n"
    "[Therapie und Empfehlungen: Besprochene Maßnahmen, Therapiepläne, Medikamente (mit Dosis, "
    "falls genannt) oder Empfehlungen in einer Zeile; bei mehreren Punkten durch Semikolon getrennt.]\n\n\n"
    "Weitere Anforderungen:\n\n"
    "Sprache: Die Antwort erfolgt immer auf Deutsch. Formuliere geschlechtsneutral, z. B. "
    "\"Pat.\" statt \"Patient/Patientin\".\n"
    "Prägnanz: Prägnant, aber vollständig. Keine Erfindungen – nur Inhalte aus dem Transkript "
    "und dem Kontext.\n"
    "Klarheit: Fehlende oder unklare Informationen explizit mit \"[unklar]\" oder "
    "\"[nicht erwähnt]\" kennzeichnen.\n"
    "Format: Nach den Überschriften AN, BE, LD und TH folgt kein Doppelpunkt. Der Text beginnt "
    "direkt in der nächsten Zeile. Keine Markdown-Formatierung, keine Einleitung, kein Schlusssatz."
)

DEFAULT_PROMPT_DIKTAT = (
    "Rolle: Du bist ein hochqualifizierter Editor für medizinische und fachliche Transkripte "
    "mit Fokus auf die deutsche Sprache.\n\n"
    "Aufgabe: Korrigiere und optimiere das folgende automatisch erstellte Transkript eines Diktats. "
    "Das Ziel ist eine Version, die so authentisch wie möglich am realen Wortlaut bleibt, "
    "aber typische Transkriptionsfehler eliminiert.\n\n"
    "Leitlinien:\n"
    "Authentizität: Verändere nicht den Sprechstil oder die Satzstruktur, es sei denn, sie ist "
    "durch Transkriptionsfehler völlig unverständlich.\n"
    "Medikamenten-Check: Analysiere alle genannten Medikamentennamen. Falls ein Wort phonetisch "
    "falsch erfasst wurde (z. B. \"Metopolol\" statt \"Metoprolol\"), korrigiere es auf die "
    "medizinisch korrekte Schreibweise. Ein ggf. mitgelieferter Kontext (Medikationsplan) hat Vorrang.\n"
    "Interpunktion & Grammatik: Setze Satzzeichen so, dass der Sinnzusammenhang klar wird. "
    "Korrigiere offensichtliche Grammatikfehler, die durch die Spracherkennung entstanden sind.\n"
    "Fachterminologie: Schreibe medizinische Fachbegriffe korrekt aus.\n"
    "Diktierte Steuerbefehle wie \"Punkt\", \"Komma\", \"neuer Absatz\" in die entsprechende "
    "Formatierung umsetzen.\n\n"
    "Output: Gib nur den korrigierten Text aus, ohne einleitende Kommentare und ohne Markdown. "
    "Falls du bei einem Medikament unsicher bist, markiere es in eckigen Klammern, z. B. "
    "[Gemeint: Marcumar?]. Füge KEINE ICD-10-Codes ein und verändere NICHT die inhaltliche "
    "Bedeutung von Diagnosen oder Aussagen."
)

DEFAULT_PROMPT_ARZTBRIEF = (
    "Analysiere den angehängten Arztbrief und erstelle eine medizinische Zusammenfassung "
    "für die Hausarztakte. Extrahiere ausschließlich die klinisch relevantesten Informationen: "
    "neue Diagnosen, Änderungen der Medikation sowie konkrete Therapieempfehlungen oder anstehende "
    "Untersuchungen. Priorisiere die Vollständigkeit der medizinischen Fakten vor der Kürze, "
    "versuche jedoch, dich auf etwa 2-3 prägnante Sätze zu beschränken. Die Ausgabe muss zwingend "
    "als ein einziger, zusammenhängender Fließtext in einer einzigen Zeile erfolgen - ohne "
    "Zeilenumbrüche, Aufzählungszeichen oder sonstige Formatierungen. Dein Output darf ausschließlich "
    "die Zusammenfassung enthalten, keinerlei einleitende oder abschließende Sätze. Antworte auf Deutsch."
)

DEFAULT_CONFIG = {
    "server_url": "https://192.168.10.51:8000",
    "api_key": "",
    "ca_cert_path": "",
    "client_name": socket.gethostname(),
    "llm_via_server": True,
    "llm_api_url": "http://localhost:11434",
    "llm_num_ctx": 16384,
    "llm_temperature": 0.2,
    "model_ambient": "gemma4:12b",
    "model_diktat": "gemma4:12b",
    "model_arena_a": "gemma4:12b",
    "model_arena_b": "qwen3.5:9b",
    "model_arztbrief": "gemma4:12b",
    "prompt_ambient": DEFAULT_PROMPT_AMBIENT,
    "prompt_diktat": DEFAULT_PROMPT_DIKTAT,
    "prompt_arena_a": DEFAULT_PROMPT_AMBIENT,
    "prompt_arena_b": DEFAULT_PROMPT_AMBIENT,
    "prompt_arztbrief": DEFAULT_PROMPT_ARZTBRIEF,
    "input_device": None,
    "loopback_device": None,
    "mix_system_audio": False,
    "chunk_duration": 20,
    "chunk_max_extra": 15,
    "silence_threshold": 0.01,
    "diarize": True,
    "expected_speakers": 0,
    "auto_delete_days": 1,
    "save_raw_transcripts": True,
    # Globale Tastenkürzel (leer = aus), Format siehe hotkeys.py
    "hotkey_start": "ctrl+shift+f9",
    "hotkey_pause": "ctrl+shift+f10",
    "hotkey_analyse": "ctrl+shift+f11",
    "hotkey_copy_close": "ctrl+shift+f12",
    # Freihand-Diktat: Taste halten = aufnehmen, loslassen = Text ins aktive Fenster
    "ptt_hotkey": "rctrl",
    "ptt_insert_mode": "paste",    # "paste" (Zwischenablage + Strg+V) oder "type" (Zeichen tippen)
    "ptt_llm": False,              # Text vor dem Einfügen mit dem Diktat-Prompt überarbeiten
    "ptt_beep": True,
}


def _migrate(cfg: dict) -> dict:
    """Alte v1.0-Konfigurationen auf v2.0 heben."""
    if "openwebui_url" in cfg:
        cfg.setdefault("llm_api_url", cfg.pop("openwebui_url"))
    su = cfg.get("server_url", "")
    if su.endswith("/transcribe"):
        cfg["server_url"] = su[: -len("/transcribe")]
    llm = cfg.get("llm_api_url", "")
    for cut in ("/v1/chat/completions", "/api/chat", "/v1/", "/api/"):
        if cut in llm:
            cfg["llm_api_url"] = llm.split(cut)[0].rstrip("/")
            break
    # v1.0-Prompts durch die neuen Standardprompts ersetzen, wenn sie unverändert waren
    old_markers = ("Verwende die Wissensdatenbank (RAG)", "Wissensnutzung (RAG)")
    for key, new in (("prompt_ambient", DEFAULT_PROMPT_AMBIENT), ("prompt_arena_a", DEFAULT_PROMPT_AMBIENT),
                     ("prompt_arena_b", DEFAULT_PROMPT_AMBIENT), ("prompt_diktat", DEFAULT_PROMPT_DIKTAT)):
        if any(m in cfg.get(key, "") for m in old_markers):
            cfg[key] = new
    return cfg


def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        loaded = _migrate(loaded)
        for key, value in DEFAULT_CONFIG.items():
            if key not in loaded:
                loaded[key] = value
        if is_encrypted(loaded.get("api_key", "")):
            loaded["api_key"] = decrypt_value(loaded["api_key"])
        return loaded
    except Exception as e:
        print(f"config.json unlesbar ({e}), nutze Standardwerte")
        return DEFAULT_CONFIG.copy()


def save_config(cfg):
    to_save = cfg.copy()
    raw_key = to_save.get("api_key", "")
    if raw_key and not is_encrypted(raw_key):
        to_save["api_key"] = encrypt_value(raw_key)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=4, ensure_ascii=False)


config = load_config()


def _tls_verify():
    server_url = config.get("server_url", "")
    if "localhost" in server_url or "127.0.0.1" in server_url:
        return False
    ca = config.get("ca_cert_path", "")
    if ca and os.path.exists(ca):
        return ca
    return True


def _server_headers():
    h = {}
    key = (config.get("api_key") or "").strip()
    if key:
        h["X-Api-Key"] = key
    return h


def audio_to_wav_bytes(data: np.ndarray) -> io.BytesIO:
    data = np.asarray(data, dtype=np.float32).reshape(-1)
    pcm = np.clip(data * 32767.0, -32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    wav.write(buf, SAMPLE_RATE, pcm)
    buf.seek(0)
    return buf


_DICTATION_COMMANDS = (
    (re.compile(r"[\s,;:]*\bneue[rn]?\s+absatz\b[\s,.;:]*", re.IGNORECASE), "\n\n"),
    (re.compile(r"[\s,;:]*\bneue\s+zeile\b[\s,.;:]*", re.IGNORECASE), "\n"),
)


def apply_dictation_commands(text: str) -> str:
    """Gesprochene Steuerbefehle ("neue Zeile", "neuer Absatz") in Umbrüche umsetzen."""
    t = (text or "").strip()
    for rx, repl in _DICTATION_COMMANDS:
        t = rx.sub(repl, t)
    return t.strip(" ")


def extract_context_terms(text: str) -> list:
    """Zieht Begriffe (Präparate, Diagnosen) aus dem Kontextfeld für Whisper-Hotwords."""
    terms = []
    seen = set()
    for line in re.split(r"[\n;,]+", text or ""):
        line = line.strip()
        if not line:
            continue
        # Dosisangaben/Zahlen entfernen
        cleaned = re.sub(r"\b\d+([.,]\d+)?\s*(mg|µg|mcg|g|ml|IE|%|x|-)?\b", " ", line, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–:")
        words = cleaned.split()
        cands = []
        if 0 < len(words) <= 3:
            cands.append(cleaned)
        cands += [w.strip(".,()") for w in words if len(w) >= 4 and w[0].isupper()]
        for c in cands:
            if c and c.lower() not in seen:
                seen.add(c.lower())
                terms.append(c)
    return terms[:200]


# ---------------------------------------------------------------------------
# Server-Client
# ---------------------------------------------------------------------------
class ServerClient:
    """HTTP-Zugriff auf den Praxisserver; eine Keep-Alive-Session spart den TLS-Handshake pro Chunk."""

    def __init__(self):
        self._session = requests.Session()
        self._session_lock = threading.Lock()

    @property
    def base(self):
        return config.get("server_url", "").rstrip("/")

    def _http(self):
        with self._session_lock:
            self._session.headers.update(_server_headers())
            self._session.verify = _tls_verify()
            return self._session

    def _post(self, path, timeout=120, **kw):
        return self._http().post(self.base + path, timeout=timeout, **kw)

    def _get(self, path, timeout=10):
        return self._http().get(self.base + path, timeout=timeout)

    def _delete(self, path, timeout=10):
        return self._http().delete(self.base + path, timeout=timeout)

    def health(self):
        r = self._get("/health", timeout=5)
        r.raise_for_status()
        return r.json()

    def create_session(self, context_terms, expected_speakers=0, diarize=True, room=""):
        r = self._post("/session", timeout=15, data={
            "client": config.get("client_name", ""), "room": room,
            "context_terms": json.dumps(context_terms, ensure_ascii=False),
            "expected_speakers": int(expected_speakers or 0),
            "diarize": "true" if diarize else "false"})
        r.raise_for_status()
        return r.json()["session_id"]

    def upload_chunk(self, sid, data, offset, index):
        r = self._post(f"/session/{sid}/chunk", timeout=180,
                       files={"file": ("chunk.wav", audio_to_wav_bytes(data), "audio/wav")},
                       data={"offset": f"{offset:.3f}", "index": str(index)})
        r.raise_for_status()
        return r.json()

    def finalize(self, sid, data=None, offset=0.0, index=-1):
        files = None
        payload = {}
        if data is not None and len(data) > 0:
            files = {"file": ("chunk.wav", audio_to_wav_bytes(data), "audio/wav")}
            payload = {"offset": f"{offset:.3f}", "index": str(index)}
        r = self._post(f"/session/{sid}/finalize", timeout=300, files=files, data=payload)
        r.raise_for_status()
        return r.json()

    def transcribe(self, data, context_terms=None):
        """Einzeltranskription ohne Sitzung/Sprechertrennung (Freihand-Diktat)."""
        r = self._post("/transcribe", timeout=120,
                       files={"file": ("dictation.wav", audio_to_wav_bytes(data), "audio/wav")},
                       data={"context_terms": json.dumps(context_terms or [], ensure_ascii=False),
                             "diarize": "false"})
        r.raise_for_status()
        return r.json()

    def delete_session(self, sid):
        try:
            self._delete(f"/session/{sid}")
        except Exception:
            pass

    def enroll(self, name, data):
        r = self._post("/enroll", timeout=120, data={"name": name},
                       files={"file": ("enroll.wav", audio_to_wav_bytes(data), "audio/wav")})
        if r.status_code != 200:
            raise RuntimeError(r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text)
        return r.json()

    def list_enrolled(self):
        r = self._get("/enroll")
        r.raise_for_status()
        return r.json().get("enrolled", [])

    def delete_enrolled(self, name):
        self._delete(f"/enroll/{name}")


SERVER = ServerClient()


# ---------------------------------------------------------------------------
# LLM-Client (Ollama-API, über Praxisserver oder direkt)
# ---------------------------------------------------------------------------
class LLMClient:
    def _url(self, path):
        if config.get("llm_via_server", True):
            return SERVER.base + "/llm" + path, _tls_verify(), _server_headers()
        base = config.get("llm_api_url", "http://localhost:11434").rstrip("/")
        return base + "/api" + path, False, {}

    def models(self):
        urls = []
        url, verify, headers = self._url("/models" if config.get("llm_via_server", True) else "/tags")
        urls.append((url, verify, headers))
        urls.append(("http://localhost:11434/api/tags", False, {}))
        for url, verify, headers in urls:
            try:
                r = requests.get(url, headers=headers, timeout=4, verify=verify)
                if r.status_code == 200:
                    return sorted(m["name"] for m in r.json().get("models", []))
            except Exception:
                continue
        return []

    def chat(self, model, messages, stream_cb=None, timeout=600):
        """Gibt den vollständigen Antworttext zurück; stream_cb(partial_text) bei Streaming."""
        url, verify, headers = self._url("/chat")
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream_cb is not None,
            "options": {
                "temperature": float(config.get("llm_temperature", 0.2)),
                "num_ctx": int(config.get("llm_num_ctx", 16384)),
            },
            "keep_alive": "30m",
        }
        # Denkmodus (qwen3, deepseek-r1, gpt-oss ...) abschalten – spart Zeit.
        # Modelle ohne Denkmodus lehnen das Feld ggf. ab -> dann ohne Feld erneut senden.
        for attempt in (0, 1):
            p = dict(payload)
            if attempt == 0:
                p["think"] = False
            r = requests.post(url, json=p, headers=headers, timeout=timeout, verify=verify,
                              stream=payload["stream"])
            if r.status_code == 400 and attempt == 0 and "think" in r.text.lower():
                r.close()
                continue
            break
        if r.status_code != 200:
            raise RuntimeError(f"LLM-Fehler {r.status_code}: {r.text[:300]}")
        if not payload["stream"]:
            return r.json()["message"]["content"]
        text = ""
        try:
            for line in r.iter_lines():
                if not line:
                    continue
                d = json.loads(line)
                if "error" in d:
                    raise RuntimeError(d["error"])
                text += d.get("message", {}).get("content", "")
                if stream_cb:
                    stream_cb(text)
                if d.get("done"):
                    break
        finally:
            r.close()
        return text


LLM = LLMClient()


def clean_for_pvs(text: str) -> str:
    """Markdown entfernen; Zeilenumbrüche Windows-kompatibel."""
    t = text.replace("**", "").replace("##", "").replace("# ", "")
    t = re.sub(r"<think>.*?</think>\s*", "", t, flags=re.DOTALL)
    return t.strip()


# ---------------------------------------------------------------------------
# Audio-Aufnahme
# ---------------------------------------------------------------------------
class AudioRecorder:
    def __init__(self, meter_callback_fn):
        self.meter_callback_fn = meter_callback_fn
        self.running = False
        self.paused = False
        self.stream_mic = None
        self.stream_loop = None
        self.queue = queue.Queue()
        self.buffer = []
        self.buffer_lock = threading.Lock()
        self.sample_rate = SAMPLE_RATE
        self.samples_recorded = 0      # Gesamt (ohne Pausen)
        self.buffer_start_sample = 0   # Position des aktuellen Chunk-Anfangs
        self.last_error = ""

    def start(self, mic_id, loop_id=None, use_loopback=False):
        self.running = True
        self.paused = False
        with self.buffer_lock:
            self.buffer = []
            self.samples_recorded = 0
            self.buffer_start_sample = 0

        def mic_callback(indata, frames, t, status):
            if status:
                print(f"Mic Status: {status}")
            if self.running and not self.paused:
                self.queue.put(("mic", indata.copy()))

        try:
            self.stream_mic = sd.InputStream(device=mic_id, samplerate=self.sample_rate, channels=1,
                                             dtype="float32", callback=mic_callback, blocksize=2048)
            self.stream_mic.start()
        except Exception as e:
            print(f"Error starting mic: {e}")
            self.last_error = str(e)
            self.running = False
            return False

        if use_loopback and loop_id is not None:
            def loop_callback(indata, frames, t, status):
                if self.running and not self.paused:
                    self.queue.put(("loop", indata.copy()))
            try:
                self.stream_loop = sd.InputStream(device=loop_id, samplerate=self.sample_rate, channels=1,
                                                  dtype="float32", callback=loop_callback, blocksize=2048)
                self.stream_loop.start()
            except Exception as e:
                print(f"Error starting loopback: {e}")

        threading.Thread(target=self._process_queue, daemon=True).start()
        return True

    def stop(self):
        self.running = False
        for s in (self.stream_mic, self.stream_loop):
            if s:
                try:
                    s.stop(); s.close()
                except Exception:
                    pass
        self.stream_mic = self.stream_loop = None
        time.sleep(0.15)  # Restdaten aus der Queue holen
        self._drain()
        return self.get_and_reset_buffer()

    def _drain(self):
        while True:
            try:
                source, data = self.queue.get_nowait()
            except queue.Empty:
                return
            self._append(data)

    def _append(self, data):
        data = data.reshape(-1).astype(np.float32)
        with self.buffer_lock:
            self.buffer.append(data)
            self.samples_recorded += len(data)

    def _process_queue(self):
        while self.running:
            try:
                source, data = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            rms = float(np.sqrt(np.mean(data ** 2)))
            self.meter_callback_fn(min(rms * 5, 1.0))
            self._append(data)

    def buffer_seconds(self) -> float:
        with self.buffer_lock:
            return (self.samples_recorded - self.buffer_start_sample) / self.sample_rate

    def tail_rms(self, seconds=0.4) -> float:
        n = int(seconds * self.sample_rate)
        with self.buffer_lock:
            got, parts = 0, []
            for a in reversed(self.buffer):
                parts.append(a)
                got += len(a)
                if got >= n:
                    break
        if not parts:
            return 0.0
        tail = np.concatenate(parts[::-1])[-n:]
        return float(np.sqrt(np.mean(tail ** 2))) if len(tail) else 0.0

    def get_and_reset_buffer(self):
        """Gibt (audio, startzeit_in_sekunden) zurück oder (None, start)."""
        with self.buffer_lock:
            start = self.buffer_start_sample / self.sample_rate
            if not self.buffer:
                return None, start
            data = np.concatenate(self.buffer)
            self.buffer = []
            self.buffer_start_sample = self.samples_recorded
        return data, start


# ---------------------------------------------------------------------------
# Hauptanwendung
# ---------------------------------------------------------------------------
STANDARD_FINDINGS = {
    "Herz": "Cor: Herztöne rein, regelmäßig, rhythmisch.",
    "Lunge": "Pulmo: Vesikuläratmen bds., keine Rasselgeräusche.",
    "Abdomen": "Abdomen: Bauchdecke weich, kein Druckschmerz.",
    "Rachen": "Rachen: Schleimhaut feucht, rosig, reizlos.",
    "Ohren": "Otoskopie: Trommelfelle intakt, Lichtreflex erhalten.",
    "Wirbelsäule": "WS: Lotgerecht, kein Klopfschmerz.",
    "Niere": "Nierenlager beidseits indolent.",
    "Lymphknoten": "LK: Zervikal/axillär nicht vergrößert.",
    "Beine": "Extremitäten: Keine Ödeme, Pulse tastbar.",
    "Neuro": "Neuro: Isokor, Stand/Gang sicher.",
    "Haut": "Haut: Warm, Turgor normal.",
    "Schilddrüse": "Schilddrüse: Schluckverschieblich.",
    "Psyche": "Psych/AZ: Wach, orientiert, AZ gut.",
}

DISCLAIMER_TRANSCRIPTION = (
    "⚠ Hinweis: Transkripte und KI-generierte Dokumentationen sind vom behandelnden "
    "Arzt/Ärztin auf Vollständigkeit und Richtigkeit zu überprüfen. Dieses Programm dient "
    "lediglich als Dokumentationshilfe und darf die ärztliche Behandlung nicht beeinflussen. "
    "Nutzung auf eigene Gefahr – es wird keine Haftung übernommen."
)

BG = "#f5f7f9"


class StatusOverlay:
    """Kleiner Hinweis unten in der Bildschirmmitte, immer im Vordergrund, stiehlt nie den Fokus –
    zeigt bei Tastenkürzeln und Freihand-Diktat, was gerade passiert, auch wenn Asklaion im Hintergrund ist.
    Nur aus dem Tk-Haupt-Thread aufrufen."""

    def __init__(self, root):
        self.root = root
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-alpha", 0.94)
        except tk.TclError:
            pass
        self.label = tk.Label(self.win, text="", font=("Segoe UI", 11, "bold"), fg="white", bg="#34495e",
                              padx=18, pady=9)
        self.label.pack()
        # Statt withdraw/deiconify (würde den Fokus holen) wird das Fenster nur verschoben.
        self.win.geometry("+-10000+-10000")
        hotkeys.make_no_activate(self.win)
        self._after = None

    def show(self, text, color="#34495e"):
        if self._after:
            self.root.after_cancel(self._after)
            self._after = None
        self.label.config(text=text, bg=color)
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        x = (self.win.winfo_screenwidth() - w) // 2
        y = self.win.winfo_screenheight() - h - 90
        self.win.attributes("-topmost", True)   # vor geometry(), sonst setzt Tk die alte Position zurück
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def flash(self, text, color="#34495e", ms=1800):
        self.show(text, color)
        self._after = self.root.after(ms, self.hide)

    def hide(self):
        if self._after:
            self.root.after_cancel(self._after)
            self._after = None
        self.win.geometry("+-10000+-10000")


class ModernRecorder:
    TAB_AMBIENT, TAB_DIKTAT, TAB_ARENA, TAB_ARZTBRIEF = 0, 1, 2, 3

    def __init__(self, root):
        self.root = root
        self.root.title(f"Asklaion v{VERSION}")
        self.root.geometry("540x1000")
        self.root.configure(bg=BG)

        self.recorder = AudioRecorder(self.update_meter)
        self.upload_queue = queue.Queue()
        self.transcription_parts = {}   # idx -> text (Live-Ansicht)
        self.notes_parts = []           # Notizen/Befunde in Reihenfolge
        self.chunk_counter = 0
        self.is_recording = False
        self.session_id = None
        self.session_mode = None        # Tab-Index beim Start
        self.session_context = ""
        self.arena_results = {}
        self.arena_lock = threading.Lock()
        self._arena_raw_text = ""
        self.server_ok = False
        self.chat_session = self._empty_chat_session()
        # Tk ist nicht thread-sicher: Hintergrund-Threads legen UI-Aufrufe in diese
        # Queue, der Haupt-Thread arbeitet sie alle 30 ms ab (self._ui(...)).
        self.ui_queue = queue.Queue()
        self._meter_last = 0.0

        # Freihand-Diktat (Push-to-Talk): eigener Recorder, Aufträge werden der Reihe nach
        # transkribiert und eingefügt, damit die Reihenfolge im Zielfenster stimmt.
        self.ptt_recorder = AudioRecorder(self.update_meter)
        self.ptt_events = queue.Queue()
        self.ptt_jobs = queue.Queue()
        self.ptt_active = False
        self.ptt_gen = 0
        self.ptt_started = 0.0
        self.ptt_target = None
        self.ptt_paused_ambient = False
        self.hotkeys = hotkeys.HotkeyManager(on_error=self.log)

        self._setup_ui()
        self.overlay = StatusOverlay(self.root)
        self.root.after(30, self._process_ui_queue)
        self._start_upload_worker()
        threading.Thread(target=self._ptt_control_loop, daemon=True).start()
        threading.Thread(target=self._ptt_worker, daemon=True).start()
        self._cleanup_old_transcripts()
        threading.Thread(target=self._check_server, daemon=True).start()
        self._init_hotkeys()

    # ------------------------------------------------------------------ UI-Queue
    def _ui(self, fn):
        """UI-Aufruf aus beliebigem Thread sicher in den Haupt-Thread übergeben."""
        self.ui_queue.put(fn)

    def _process_ui_queue(self):
        for _ in range(200):
            try:
                fn = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as e:
                print(f"UI-Fehler: {e}")
        self.root.after(30, self._process_ui_queue)

    # ------------------------------------------------------------------ UI
    def _setup_ui(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=(10, 0))
        self.status_dot = tk.Label(header, text="●", fg="#bdc3c7", bg=BG, font=("Arial", 14))
        self.status_dot.pack(side="left")
        self.status_label = tk.Label(header, text="Bereit", font=("Segoe UI", 9), bg=BG, fg="#7f8c8d")
        self.status_label.pack(side="left", padx=5)
        tk.Button(header, text="⚙ Einstellungen", command=self.open_settings, bg="#ecf0f1", fg="#2c3e50",
                  font=("Segoe UI", 8), relief="flat").pack(side="right")

        self.conn_warn = tk.Label(self.root, text="", font=("Segoe UI", 8), bg=BG, fg="#e74c3c", wraplength=500)
        self.conn_warn.pack(pady=(0, 3))

        self.meter_frame = tk.Frame(self.root, bg="#ddd", height=5)
        self.meter_frame.pack(fill="x", padx=20, pady=5)
        self.meter_bar = tk.Frame(self.meter_frame, bg="#2ecc71", height=5, width=0)
        self.meter_bar.pack(side="left", fill="y")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)
        self.tab_ambient = tk.Frame(self.notebook, bg=BG)
        self.tab_diktat = tk.Frame(self.notebook, bg=BG)
        self.tab_arena = tk.Frame(self.notebook, bg=BG)
        self.tab_arztbrief = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.tab_ambient, text=" Gespräch ")
        self.notebook.add(self.tab_diktat, text=" Diktat ")
        self.notebook.add(self.tab_arena, text=" Arena ")
        self.notebook.add(self.tab_arztbrief, text=" Arztbrief ")

        self._build_ambient_tab()
        self._build_diktat_tab()
        self._build_arena_tab()
        self._build_arztbrief_tab()

    def _section(self, parent, text):
        tk.Label(parent, text=text, font=("Segoe UI", 7, "bold"), bg=BG, fg="#95a5a6").pack(anchor="w", padx=10, pady=(5, 0))

    def _controls(self, parent):
        ctrl = tk.Frame(parent, bg="white", highlightthickness=1, highlightbackground="#e0e6ed")
        ctrl.pack(fill="x", padx=10, pady=10)
        btn_f = tk.Frame(ctrl, bg="white")
        btn_f.pack(pady=10)
        start = self._make_btn(btn_f, "Start", "#2ecc71", self.start_recording)
        pause = self._make_btn(btn_f, "Pause", "#f39c12", self.toggle_pause, state="disabled")
        stop = self._make_btn(btn_f, "Analyse", "#e74c3c", self.stop_recording, state="disabled")
        return start, pause, stop

    def _build_ambient_tab(self):
        self.amb_start, self.amb_pause, self.amb_stop = self._controls(self.tab_ambient)

        self._section(self.tab_ambient, "KONTEXT (MEDIKATIONSPLAN, VORERKRANKUNGEN – OPTIONAL, VOR DEM START EINFÜGEN)")
        self.context_ambient = tk.Text(self.tab_ambient, height=4, font=("Segoe UI", 9), bd=1, relief="solid")
        self.context_ambient.pack(fill="x", padx=10, pady=3)

        self._section(self.tab_ambient, "MANUELLE NOTIZEN")
        self.note_ambient = tk.Text(self.tab_ambient, height=3, font=("Segoe UI", 10), bd=1, relief="solid")
        self.note_ambient.pack(fill="x", padx=10, pady=3)

        self._section(self.tab_ambient, "NORMBEFUNDE SCHNELLEINFÜGUNG")
        grid = tk.Frame(self.tab_ambient, bg="white", bd=1, relief="solid")
        grid.pack(fill="x", padx=10, pady=3)
        self.finding_buttons = []
        for i, (name, text) in enumerate(STANDARD_FINDINGS.items()):
            btn = tk.Button(grid, text=name, command=lambda t=text, n=name: self.insert_finding(t, n),
                            bg="#ffffff", fg="#34495e", font=("Segoe UI", 8), relief="flat", bd=0,
                            highlightthickness=1, highlightbackground="#f0f2f5", state="disabled")
            btn.grid(row=i // 3, column=i % 3, padx=2, pady=2, sticky="nsew")
            grid.grid_columnconfigure(i % 3, weight=1)
            self.finding_buttons.append(btn)

        self._section(self.tab_ambient, "LIVE-TRANSKRIPT")
        self.amb_live_text = scrolledtext.ScrolledText(self.tab_ambient, height=8, font=("Segoe UI", 10),
                                                       bg="white", bd=1, relief="solid", padx=8, pady=6)
        self.amb_live_text.pack(fill="both", expand=True, padx=10, pady=3)

        tk.Label(self.tab_ambient, text=DISCLAIMER_TRANSCRIPTION, font=("Segoe UI", 8), bg=BG, fg="#e74c3c",
                 wraplength=500, justify="left").pack(anchor="w", padx=10, pady=(3, 0))
        self.log_ambient = self._make_log(self.tab_ambient)

    def _build_diktat_tab(self):
        self.dik_start, self.dik_pause, self.dik_stop = self._controls(self.tab_diktat)
        self._section(self.tab_diktat, "KONTEXT (OPTIONAL)")
        self.context_diktat = tk.Text(self.tab_diktat, height=2, font=("Segoe UI", 9), bd=1, relief="solid")
        self.context_diktat.pack(fill="x", padx=10, pady=3)
        self._section(self.tab_diktat, "LIVE-TRANSKRIPT (VORSCHAU)")
        self.live_text = scrolledtext.ScrolledText(self.tab_diktat, height=18, font=("Segoe UI", 11), bg="white",
                                                   bd=1, relief="solid", padx=10, pady=10)
        self.live_text.pack(fill="both", expand=True, padx=10, pady=5)
        tk.Label(self.tab_diktat, text=DISCLAIMER_TRANSCRIPTION, font=("Segoe UI", 8), bg=BG, fg="#e74c3c",
                 wraplength=500, justify="left").pack(anchor="w", padx=10, pady=(5, 0))
        self.log_diktat = self._make_log(self.tab_diktat)

    def _build_arena_tab(self):
        self.arena_start, self.arena_pause, self.arena_stop = self._controls(self.tab_arena)
        self._section(self.tab_arena, "KONTEXT (OPTIONAL)")
        self.context_arena = tk.Text(self.tab_arena, height=2, font=("Segoe UI", 9), bd=1, relief="solid")
        self.context_arena.pack(fill="x", padx=10, pady=3)
        self._section(self.tab_arena, "LIVE-TRANSKRIPT (VORSCHAU)")
        self.arena_live_text = scrolledtext.ScrolledText(self.tab_arena, height=18, font=("Segoe UI", 11),
                                                         bg="white", bd=1, relief="solid", padx=10, pady=10)
        self.arena_live_text.pack(fill="both", expand=True, padx=10, pady=5)
        tk.Label(self.tab_arena, text=DISCLAIMER_TRANSCRIPTION, font=("Segoe UI", 8), bg=BG, fg="#e74c3c",
                 wraplength=500, justify="left").pack(anchor="w", padx=10, pady=(5, 0))
        self.log_arena = self._make_log(self.tab_arena)

    def _build_arztbrief_tab(self):
        self.drop_frame = tk.Frame(self.tab_arztbrief, bg="white", highlightthickness=2,
                                   highlightbackground="#3498db", relief="flat")
        self.drop_frame.pack(fill="x", padx=10, pady=10, ipady=30)
        self.drop_label = tk.Label(self.drop_frame, text="📄  PDF hier hineinziehen\noder Button klicken",
                                   font=("Segoe UI", 12), bg="white", fg="#7f8c8d", justify="center")
        self.drop_label.pack(expand=True, pady=10)
        btn_frame = tk.Frame(self.tab_arztbrief, bg=BG)
        btn_frame.pack(fill="x", padx=10)
        self.btn_pdf = tk.Button(btn_frame, text="📁 PDF auswählen", command=self._select_pdf, bg="#3498db",
                                 fg="white", font=("Segoe UI", 10, "bold"), relief="flat", pady=8, cursor="hand2")
        self.btn_pdf.pack(fill="x")
        self.arztbrief_status = tk.Label(self.tab_arztbrief, text="Kein PDF geladen", font=("Segoe UI", 9),
                                         bg=BG, fg="#95a5a6")
        self.arztbrief_status.pack(anchor="w", padx=10, pady=(10, 0))
        self._section(self.tab_arztbrief, "EXTRAHIERTER TEXT (VORSCHAU)")
        self.arztbrief_preview = scrolledtext.ScrolledText(self.tab_arztbrief, height=12, font=("Segoe UI", 10),
                                                           bg="white", bd=1, relief="solid", padx=10, pady=10)
        self.arztbrief_preview.pack(fill="both", expand=True, padx=10, pady=5)
        tk.Label(self.tab_arztbrief, text="⚠ Hinweis: KI-generierte Zusammenfassungen dienen ausschließlich der "
                 "schnelleren Orientierung und ersetzen nicht das sorgfältige Aktenstudium.",
                 font=("Segoe UI", 8), bg=BG, fg="#e74c3c", wraplength=500, justify="left").pack(anchor="w", padx=10, pady=(5, 0))
        self.log_arztbrief = self._make_log(self.tab_arztbrief)
        if HAS_WINDND:
            try:
                windnd.hook_dropfiles(self.root, func=self._on_drop_files, force_unicode=True)
            except Exception as e:
                print(f"Drag-and-Drop Fehler: {e}")

    def _make_btn(self, parent, text, color, cmd, state="normal"):
        b = tk.Button(parent, text=text, bg=color, fg="white", font=("Segoe UI", 9, "bold"), relief="flat",
                      width=10, pady=6, command=cmd, state=state)
        b.pack(side="left", padx=3)
        return b

    def _make_log(self, parent):
        log = scrolledtext.ScrolledText(parent, height=4, bg="#1e272e", fg="#ecf0f1", font=("Consolas", 8), borderwidth=0)
        log.pack(fill="x", padx=10, pady=8)
        return log

    def log(self, message):
        ts = datetime.now().strftime('%H:%M:%S')

        def _do():
            for logger in (self.log_ambient, self.log_diktat, self.log_arena, self.log_arztbrief):
                logger.insert(tk.END, f"[{ts}] {message}\n")
                logger.see(tk.END)
        self._ui(_do)

    def set_status(self, text, color):
        def _do():
            self.status_label.config(text=text, fg=color)
            self.status_dot.config(fg=color)
        self._ui(_do)

    # ------------------------------------------------------------ Server
    def _check_server(self):
        try:
            h = SERVER.health()
            self.server_ok = True
            info = (f"Server OK: {h.get('asr_model')} auf {h.get('device')}, Sprechertrennung "
                    f"{'an' if h.get('diarization') else 'aus'}"
                    f"{', angelernt: ' + ', '.join(h.get('enrolled', [])) if h.get('enrolled') else ''}")
            self.log(info)
            self._ui(lambda: self.conn_warn.config(text="", fg="#27ae60"))
        except Exception as e:
            self.server_ok = False
            msg = f"Praxisserver nicht erreichbar ({config.get('server_url')}): {str(e)[:80]}"
            self.log(msg)
            self._ui(lambda: self.conn_warn.config(text=msg, fg="#e74c3c"))

    # ------------------------------------------------------------ Cleanup
    def _cleanup_old_transcripts(self):
        days = config.get("auto_delete_days", 1)
        if not isinstance(days, int) or days <= 0:
            return
        folder = os.path.join(_BASE, "Transkripte_Raw")
        if not os.path.exists(folder):
            return
        cutoff = time.time() - days * 86400
        deleted = 0
        for fname in os.listdir(folder):
            fpath = os.path.join(folder, fname)
            if os.path.isfile(fpath) and fname.endswith(".txt") and os.path.getmtime(fpath) < cutoff:
                try:
                    os.remove(fpath)
                    deleted += 1
                except Exception as e:
                    print(f"Cleanup-Fehler: {e}")
        if deleted:
            self.log(f"Datenschutz: {deleted} alte Transkript(e) gelöscht (älter als {days} Tag(e)).")

    # ------------------------------------------------------------ Meter
    def update_meter(self, level):
        now = time.time()
        if now - self._meter_last < 0.07:   # max. ~15 Updates/s
            return
        self._meter_last = now
        self._ui(lambda: self._draw_meter(level))

    def _draw_meter(self, level):
        self.meter_bar.config(width=int(self.meter_frame.winfo_width() * level))

    # ------------------------------------------------------------ Aufnahme
    def _current_context_widget(self):
        idx = self.notebook.index(self.notebook.select())
        return {self.TAB_AMBIENT: self.context_ambient, self.TAB_DIKTAT: self.context_diktat,
                self.TAB_ARENA: self.context_arena}.get(idx)

    def start_recording(self):
        if self.is_recording:
            return
        self.session_mode = self.notebook.index(self.notebook.select())
        ctx_widget = self._current_context_widget()
        self.session_context = ctx_widget.get("1.0", tk.END).strip() if ctx_widget else ""
        self.chunk_counter = 0
        self.transcription_parts = {}
        self.notes_parts = []
        self.session_id = None
        for w in (self.live_text, self.arena_live_text, self.amb_live_text):
            w.delete("1.0", tk.END)

        mic_id = config.get("input_device")
        loop_id = config.get("loopback_device")
        use_loop = config.get("mix_system_audio", False)
        if not self.recorder.start(mic_id, loop_id, use_loop):
            messagebox.showerror("Fehler", "Konnte Audio-Gerät nicht starten. Bitte Mikrofon in den Einstellungen prüfen."
                                 f"\n\n{self.recorder.last_error}")
            return
        self.is_recording = True

        for b in (self.amb_start, self.dik_start, self.arena_start):
            b.config(state="disabled", bg="#bdc3c7")
        for b in (self.amb_pause, self.dik_pause, self.amb_stop, self.dik_stop, self.arena_pause, self.arena_stop):
            b.config(state="normal")
        for b in self.finding_buttons:
            b.config(state="normal")
        self.set_status("AUFNAHME", "#e74c3c")

        # Sitzung auf dem Server anlegen (im Hintergrund, noch vor dem ersten Chunk)
        diarize = bool(config.get("diarize", True)) and self.session_mode in (self.TAB_AMBIENT, self.TAB_ARENA)
        terms = extract_context_terms(self.session_context)
        self.upload_queue.put(("session", diarize, terms))
        threading.Thread(target=self.chunk_timer, daemon=True).start()
        self.log("Aufnahme gestartet." + (f" Kontext: {len(terms)} Begriffe." if terms else ""))

    def chunk_timer(self):
        dur = float(config.get("chunk_duration", 20))
        extra = float(config.get("chunk_max_extra", 15))
        thr = float(config.get("silence_threshold", 0.01))
        while self.is_recording:
            time.sleep(0.25)
            if not self.is_recording or self.recorder.paused:
                continue
            elapsed = self.recorder.buffer_seconds()
            if elapsed < dur:
                continue
            # An einer Sprechpause schneiden – notfalls nach dur+extra Sekunden hart.
            # (Harte Schnitte mitten im Wort kosten Wortfragmente an der Chunk-Grenze,
            #  deshalb lieber deutlich länger auf eine Pause warten.)
            if self.recorder.tail_rms(0.3) < thr or elapsed >= dur + extra:
                data, start = self.recorder.get_and_reset_buffer()
                if data is not None:
                    self._enqueue_chunk(data, start, final=False)

    def _enqueue_chunk(self, data, start, final):
        thr = float(config.get("silence_threshold", 0.01))
        rms = float(np.sqrt(np.mean(data ** 2))) if len(data) else 0.0
        if not final and rms < thr * 0.5:
            self.log(f"Stiller Abschnitt ({len(data) / SAMPLE_RATE:.0f}s) übersprungen.")
            return
        self.chunk_counter += 1
        self.upload_queue.put(("final" if final else "chunk", self.chunk_counter, data, start))

    def toggle_pause(self):
        if not self.is_recording:
            return
        self.recorder.paused = not self.recorder.paused
        state = "PAUSIERT" if self.recorder.paused else "AUFNAHME"
        self.set_status(state, "#f39c12" if self.recorder.paused else "#e74c3c")
        btn_text = "Weiter" if self.recorder.paused else "Pause"
        for b in (self.amb_pause, self.dik_pause, self.arena_pause):
            b.config(text=btn_text)

    def insert_finding(self, text, name):
        self.chunk_counter += 1
        entry = f"[BEFUND {name}: {text}]"
        self.transcription_parts[self.chunk_counter] = entry
        self.notes_parts.append(entry)
        self.log(f"Befund {name} eingefügt.")
        self._update_live_transcription()

    def stop_recording(self):
        if not self.is_recording:
            return
        self.is_recording = False
        for b in (self.amb_start, self.dik_start, self.arena_start):
            b.config(state="normal", bg="#2ecc71")
        for b in (self.amb_pause, self.dik_pause, self.amb_stop, self.dik_stop, self.arena_pause, self.arena_stop):
            b.config(state="disabled")
        for b in self.finding_buttons:
            b.config(state="disabled")
        for b in (self.amb_pause, self.dik_pause, self.arena_pause):
            b.config(text="Pause")
        self.set_status("FINALISIERE...", "#3498db")

        note = self.note_ambient.get("1.0", tk.END).strip() if self.session_mode == self.TAB_AMBIENT else ""
        if note:
            self.note_ambient.delete("1.0", tk.END)
            self.chunk_counter += 1
            entry = f"[NOTIZ: {note}]"
            self.transcription_parts[self.chunk_counter] = entry
            self.notes_parts.append(entry)

        def _stop_worker():
            data, start = self.recorder.stop()
            if data is None:
                data = np.zeros(0, dtype=np.float32)
            self._enqueue_chunk(data, start, final=True)

        threading.Thread(target=_stop_worker, daemon=True).start()

    # ------------------------------------------------------------ Upload
    def _start_upload_worker(self):
        threading.Thread(target=self._upload_worker, daemon=True).start()

    def _upload_worker(self):
        while True:
            item = self.upload_queue.get()
            try:
                kind = item[0]
                if kind == "session":
                    self._create_session(item[1], item[2])
                elif kind == "chunk":
                    self._upload_chunk(item[1], item[2], item[3])
                elif kind == "final":
                    self._upload_final(item[1], item[2], item[3])
            except Exception as e:
                self.log(f"Upload-Fehler: {e}")
            finally:
                self.upload_queue.task_done()

    def _create_session(self, diarize, terms):
        for attempt in range(3):
            try:
                self.session_id = SERVER.create_session(terms, config.get("expected_speakers", 0), diarize,
                                                        room=config.get("client_name", ""))
                self._ui(lambda: self.conn_warn.config(text=""))
                return
            except Exception as e:
                msg = f"Sitzung konnte nicht angelegt werden ({str(e)[:60]}) – Versuch {attempt + 1}/3"
                self.log(msg)
                self._ui(lambda m=msg: self.conn_warn.config(text=m, fg="#e74c3c"))
                time.sleep(2)
        self.session_id = None

    def _upload_chunk(self, idx, data, start):
        if self.session_id is None:
            self._create_session(bool(config.get("diarize", True)), extract_context_terms(self.session_context))
        if self.session_id is None:
            self.transcription_parts[idx] = "[Abschnitt nicht transkribiert – Server nicht erreichbar]"
            self._update_live_transcription()
            return
        last_err = None
        for attempt in range(3):
            try:
                res = SERVER.upload_chunk(self.session_id, data, start, idx)
                if res.get("text"):
                    self.transcription_parts[idx] = res["text"]
                    self._update_live_transcription()
                self._ui(lambda: self.conn_warn.config(text=""))
                return
            except Exception as e:
                last_err = e
                time.sleep(1.5)
        msg = f"Verbindungsfehler: {str(last_err)[:60]}"
        self.log(msg)
        self._ui(lambda m=msg: self.conn_warn.config(text=m, fg="#e74c3c"))
        self.transcription_parts[idx] = "[Abschnitt nicht transkribiert – Verbindungsfehler]"

    def _upload_final(self, idx, data, start):
        result = None
        if self.session_id is not None:
            try:
                result = SERVER.finalize(self.session_id, data if len(data) else None, start, idx)
            except Exception as e:
                self.log(f"Abschluss fehlgeschlagen: {str(e)[:80]}")
        if result is None and len(data) > int(0.5 * SAMPLE_RATE) and self.session_id is None:
            self.log("Kein Server – Aufnahme konnte nicht transkribiert werden.")
        sid = self.session_id
        self.session_id = None
        if sid:
            threading.Thread(target=SERVER.delete_session, args=(sid,), daemon=True).start()
        self._ui(lambda: self.finalize_transcription(result))

    def _update_live_transcription(self):
        full_text = " ".join(self.transcription_parts[k] for k in sorted(self.transcription_parts))

        def update():
            for w in (self.live_text, self.arena_live_text, self.amb_live_text):
                w.delete("1.0", tk.END)
                w.insert(tk.END, full_text)
                w.see(tk.END)
        self._ui(update)

    # ------------------------------------------------------------ Abschluss
    def finalize_transcription(self, result):
        if result and result.get("transcript"):
            body = result["transcript"]
            if result.get("speakers"):
                self.log(f"Sprecher erkannt: {', '.join(result['speakers'])}")
        elif result and result.get("text"):
            body = result["text"]
        else:
            body = " ".join(v for k, v in sorted(self.transcription_parts.items()) if not v.startswith("["))

        raw_text = body.strip()
        if self.notes_parts:
            raw_text += "\n\n[NOTIZEN UND BEFUNDE DES ARZTES]\n" + "\n".join(self.notes_parts)
        if self.session_context:
            raw_text += "\n\n[KONTEXT (Medikationsplan/Vorerkrankungen, vom Arzt eingegeben)]\n" + self.session_context

        for w in (self.live_text, self.arena_live_text, self.amb_live_text):
            w.delete("1.0", tk.END)
            w.insert(tk.END, raw_text)

        if config.get("save_raw_transcripts", True):
            raw_dir = os.path.join(_BASE, "Transkripte_Raw")
            os.makedirs(raw_dir, exist_ok=True)
            with open(os.path.join(raw_dir, f"raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"), "w",
                      encoding="utf-8") as f:
                f.write(raw_text)

        if not body.strip():
            self.set_status("KEIN TEXT", "#e74c3c")
            self.log("Kein Transkript erhalten.")
            return

        mode = self.session_mode
        if mode == self.TAB_ARENA:
            model_a, model_b = config["model_arena_a"], config["model_arena_b"]
            prompt_a, prompt_b = config.get("prompt_arena_a", ""), config.get("prompt_arena_b", "")
            self.log(f"Arena: Starte LLM A ({model_a}) und LLM B ({model_b})...")
            self.arena_results = {}
            self._arena_raw_text = raw_text
            self.set_status("ARENA...", "#3498db")
            threading.Thread(target=self._run_llm_arena, args=(raw_text, model_a, "A", prompt_a), daemon=True).start()
            threading.Thread(target=self._run_llm_arena, args=(raw_text, model_b, "B", prompt_b), daemon=True).start()
        else:
            if mode == self.TAB_DIKTAT:
                model, sys_prompt = config["model_diktat"], config.get("prompt_diktat", "")
            else:
                model, sys_prompt = config["model_ambient"], config.get("prompt_ambient", "")
            self.log(f"Starte LLM ({model})...")
            self._start_streaming_result(model, sys_prompt, raw_text)

    # ------------------------------------------------------------ LLM
    @staticmethod
    def _build_messages(system_prompt, user_text):
        messages = []
        if system_prompt and system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_text})
        return messages

    def _start_streaming_result(self, model, system_prompt, user_text):
        """Öffnet das Ergebnisfenster sofort und streamt die LLM-Antwort hinein."""
        self.set_status("LLM...", "#3498db")
        self._open_result_window(model, system_prompt, user_text)
        self.chat_session["messages"] = self._build_messages(system_prompt, user_text)
        threading.Thread(target=self._run_chat_stream, daemon=True).start()

    def _run_chat_stream(self):
        session = self.chat_session
        try:
            def cb(partial):
                self._ui(lambda p=partial: self._stream_update(p))
            text = LLM.chat(session["model"], list(session["messages"]), stream_cb=cb)
            session["messages"].append({"role": "assistant", "content": text})
            self._ui(lambda: self._finish_result(text))
        except Exception as e:
            self.log(f"LLM Fehler: {e}")
            self._ui(lambda: self._finish_result(None))

    def _run_llm_arena(self, text, model, label, system_prompt=""):
        result = None
        try:
            result = LLM.chat(model, self._build_messages(system_prompt, text))
            self.log(f"Arena Modell {label} ({model}) fertig.")
        except Exception as e:
            self.log(f"Arena LLM {label} Fehler: {e}")
        with self.arena_lock:
            self.arena_results[label] = result
            if len(self.arena_results) == 2:
                res_a, res_b = self.arena_results.get("A"), self.arena_results.get("B")
                self._ui(lambda: self._show_arena_result(
                    res_a, res_b, self._arena_raw_text, config.get("model_arena_a", ""), config.get("prompt_arena_a", ""),
                    config.get("model_arena_b", ""), config.get("prompt_arena_b", "")))

    # ------------------------------------------------------------ Ergebnisfenster
    @staticmethod
    def _empty_chat_session():
        return {"messages": [], "model": None, "window": None, "result_text": None,
                "input_entry": None, "btn_frame": None, "user_text": None, "close": None}

    def _reset_chat_session(self):
        self.chat_session = self._empty_chat_session()

    def _set_chat_ui_enabled(self, enabled):
        cs = self.chat_session
        state = "normal" if enabled else "disabled"
        if cs["btn_frame"] and cs["btn_frame"].winfo_exists():
            for w in cs["btn_frame"].winfo_children():
                try:
                    w.config(state=state)
                except Exception:
                    pass
        if cs["input_entry"] and cs["input_entry"].winfo_exists():
            cs["input_entry"].config(state=state)
            if enabled:
                cs["input_entry"].delete(0, tk.END)

    def _open_result_window(self, model, system_prompt, user_text):
        old_win = self.chat_session.get("window")
        if old_win and old_win.winfo_exists():
            old_win.destroy()
        self._reset_chat_session()

        win = tk.Toplevel(self.root)
        win.title("Ergebnis")
        win.transient(self.root)
        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 620) // 2
        y = max(0, self.root.winfo_y() + (self.root.winfo_height() - 820) // 2)
        win.geometry(f"620x820+{x}+{y}")

        t = scrolledtext.ScrolledText(win, font=("Segoe UI", 11), wrap=tk.WORD)
        t.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        cs = self.chat_session
        cs.update({"model": model, "window": win, "result_text": t, "user_text": user_text})

        btn_frame = tk.Frame(win, bg=BG)
        btn_frame.pack(fill="x", padx=10, pady=(0, 3))
        for c in range(4):
            btn_frame.grid_columnconfigure(c, weight=1)
        cs["btn_frame"] = btn_frame
        tk.Button(btn_frame, text="Neu generieren", command=self._send_regenerate, bg="#e67e22", fg="white",
                  font=("Segoe UI", 9, "bold"), relief="flat", pady=6).grid(row=0, column=0, sticky="ew", padx=(0, 2))
        tk.Button(btn_frame, text="Kürzer", command=lambda: self._send_followup("Fasse die Antwort kürzer zusammen."),
                  bg="#3498db", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", pady=6).grid(row=0, column=1, sticky="ew", padx=2)
        tk.Button(btn_frame, text="Länger", command=lambda: self._send_followup("Führe die Antwort ausführlicher aus."),
                  bg="#3498db", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", pady=6).grid(row=0, column=2, sticky="ew", padx=2)
        tk.Button(btn_frame, text="Transkript", command=self._show_transcript_window, bg="#7f8c8d", fg="white",
                  font=("Segoe UI", 9, "bold"), relief="flat", pady=6).grid(row=0, column=3, sticky="ew", padx=(2, 0))

        input_frame = tk.Frame(win, bg=BG)
        input_frame.pack(fill="x", padx=10, pady=(0, 5))
        entry = tk.Entry(input_frame, font=("Segoe UI", 10))
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        cs["input_entry"] = entry

        def send_custom(event=None):
            txt = entry.get().strip()
            if txt:
                self._send_followup(txt)
        tk.Button(input_frame, text="Senden", command=send_custom, bg="#27ae60", fg="white", font=("Segoe UI", 9),
                  relief="flat", padx=8, pady=4).pack(side="right")
        entry.bind("<Return>", send_custom)

        def close():
            final_text = t.get("1.0", tk.END).strip().replace("\r\n", "\n").replace("\n", "\r\n")
            pyperclip.copy(final_text)
            self._reset_chat_session()
            win.destroy()
        tk.Button(win, text="Kopieren & Schließen", command=close, bg="#34495e", fg="white", pady=10).pack(fill="x")
        win.protocol("WM_DELETE_WINDOW", close)
        cs["close"] = close
        self._set_chat_ui_enabled(False)
        t.insert(tk.END, "… LLM arbeitet …")
        return win

    def _stream_update(self, partial):
        t = self.chat_session.get("result_text")
        if not t or not t.winfo_exists():
            return
        t.delete("1.0", tk.END)
        t.insert(tk.END, clean_for_pvs(partial))
        t.see(tk.END)

    def _finish_result(self, text):
        t = self.chat_session.get("result_text")
        if text is None:
            self.set_status("FEHLER", "#e74c3c")
            if t and t.winfo_exists():
                t.delete("1.0", tk.END)
                t.insert(tk.END, "Fehler bei der LLM-Verarbeitung – siehe Log.")
            self._set_chat_ui_enabled(True)
            return
        clean = clean_for_pvs(text)
        pyperclip.copy(clean.replace("\r\n", "\n").replace("\n", "\r\n"))
        if t and t.winfo_exists():
            t.delete("1.0", tk.END)
            t.insert(tk.END, clean)
        self._set_chat_ui_enabled(True)
        self.set_status("FERTIG (in Zwischenablage)", "#2ecc71")

    def _show_result(self, text, model=None, system_prompt=None, user_text=None):
        """Fertiges Ergebnis (z. B. aus der Arena) anzeigen."""
        self._open_result_window(model, system_prompt, user_text)
        if model and user_text is not None:
            self.chat_session["messages"] = self._build_messages(system_prompt, user_text) + \
                [{"role": "assistant", "content": text}]
        self._finish_result(text)

    def _show_transcript_window(self):
        raw = self.chat_session.get("user_text") or ""
        win = tk.Toplevel(self.root)
        win.title("Transkript (Rohtext)")
        win.geometry("600x600")
        t = scrolledtext.ScrolledText(win, font=("Segoe UI", 10), wrap=tk.WORD)
        t.pack(fill="both", expand=True, padx=8, pady=8)
        t.insert(tk.END, raw)

    def _send_followup(self, instruction):
        if not instruction or not instruction.strip() or not self.chat_session.get("model"):
            return
        self.chat_session["messages"].append({"role": "user", "content": instruction.strip()})
        self._set_chat_ui_enabled(False)
        self.set_status("FOLLOW-UP...", "#f39c12")
        threading.Thread(target=self._run_chat_stream, daemon=True).start()

    def _send_regenerate(self):
        original = []
        for msg in self.chat_session["messages"]:
            if msg["role"] == "system":
                original.append(msg)
            elif msg["role"] == "user":
                original.append(msg)
                break
        self.chat_session["messages"] = original
        self._set_chat_ui_enabled(False)
        self.set_status("NEU GENERIEREN...", "#f39c12")
        threading.Thread(target=self._run_chat_stream, daemon=True).start()

    def _show_arena_result(self, result_a, result_b, raw_text="", model_a="", prompt_a="", model_b="", prompt_b=""):
        self.set_status("ARENA FERTIG", "#2ecc71")
        clean_a = clean_for_pvs(result_a or "(Kein Ergebnis)")
        clean_b = clean_for_pvs(result_b or "(Kein Ergebnis)")

        win = tk.Toplevel(self.root)
        win.title("Arena – Ergebnis-Vergleich")
        win.transient(self.root)
        win.update_idletasks()
        x = max(0, self.root.winfo_x() + (self.root.winfo_width() - 1100) // 2)
        y = max(0, self.root.winfo_y() + (self.root.winfo_height() - 700) // 2)
        win.geometry(f"1100x700+{x}+{y}")

        pane = tk.Frame(win, bg=BG)
        pane.pack(fill="both", expand=True, padx=10, pady=10)
        pane.grid_columnconfigure(0, weight=1)
        pane.grid_columnconfigure(1, weight=1)
        pane.grid_rowconfigure(0, weight=1)
        texts = {}
        for col, (label, name, content) in enumerate((("A", model_a, clean_a), ("B", model_b, clean_b))):
            frame = tk.LabelFrame(pane, text=f"  Modell {label}: {name}  ", font=("Segoe UI", 10, "bold"), bg=BG)
            frame.grid(row=0, column=col, sticky="nsew", padx=(0, 5) if col == 0 else (5, 0))
            tw = scrolledtext.ScrolledText(frame, font=("Segoe UI", 10), wrap=tk.WORD)
            tw.pack(fill="both", expand=True, padx=5, pady=5)
            tw.insert(tk.END, content)
            texts[label] = tw

        btn_frame = tk.Frame(win, bg=BG)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        def choose(label, chosen_model, chosen_prompt):
            original = result_a if label == "A" else result_b
            chosen_text = texts[label].get("1.0", tk.END).strip()
            self.log(f"Arena: Modell {label} gewählt.")
            win.destroy()
            self._show_result(original or chosen_text, chosen_model, chosen_prompt, raw_text)

        tk.Button(btn_frame, text="✔ Modell A wählen", command=lambda: choose("A", model_a, prompt_a), bg="#27ae60",
                  fg="white", font=("Segoe UI", 10, "bold"), pady=8).pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(btn_frame, text="✔ Modell B wählen", command=lambda: choose("B", model_b, prompt_b), bg="#2980b9",
                  fg="white", font=("Segoe UI", 10, "bold"), pady=8).pack(side="right", fill="x", expand=True, padx=(5, 0))

    # ------------------------------------------------------------ Arztbrief
    def _select_pdf(self):
        filepath = filedialog.askopenfilename(title="PDF-Arztbrief auswählen",
                                              filetypes=[("PDF-Dateien", "*.pdf"), ("Alle Dateien", "*.*")])
        if filepath:
            self._process_arztbrief(filepath)

    def _on_drop_files(self, file_list):
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
            self.notebook.select(self.tab_arztbrief)
            self.root.after(100, lambda: self._process_arztbrief(filepath))
        else:
            self.log(f"Nur PDF-Dateien werden unterstützt. Erhalten: {os.path.basename(filepath)}")

    def _process_arztbrief(self, filepath):
        filename = os.path.basename(filepath)
        self.arztbrief_status.config(text=f"📄 {filename}", fg="#2c3e50")
        self.log(f"Lade PDF: {filename}")
        if not HAS_PYPDF2:
            self.log("FEHLER: PyPDF2 nicht installiert! 'pip install PyPDF2'")
            self.arztbrief_status.config(text="FEHLER: PyPDF2 fehlt", fg="#e74c3c")
            return
        try:
            reader = PdfReader(filepath)
            text_pages = [p.extract_text() for p in reader.pages if p.extract_text()]
            if not text_pages:
                self.log("FEHLER: Kein Text im PDF gefunden (evtl. gescanntes Bild-PDF).")
                self.arztbrief_status.config(text="FEHLER: Kein Text extrahiert", fg="#e74c3c")
                return
            pdf_text = "\n\n".join(text_pages)
            self.log(f"PDF gelesen: {len(reader.pages)} Seiten, {len(pdf_text)} Zeichen")
            self.arztbrief_preview.delete("1.0", tk.END)
            self.arztbrief_preview.insert(tk.END, pdf_text)
        except Exception as e:
            self.log(f"PDF-Lesefehler: {e}")
            self.arztbrief_status.config(text="FEHLER beim Lesen", fg="#e74c3c")
            return
        self.arztbrief_status.config(text=f"⏳ Analysiere {filename}...", fg="#3498db")
        self.btn_pdf.config(state="disabled", bg="#bdc3c7")
        self.log(f"Sende an LLM ({config.get('model_arztbrief')})...")
        self._start_streaming_result(config.get("model_arztbrief"), config.get("prompt_arztbrief", ""), pdf_text)
        self.root.after(500, self._arztbrief_watch)

    def _arztbrief_watch(self):
        cs = self.chat_session
        if cs.get("input_entry") and cs["input_entry"].winfo_exists() and str(cs["input_entry"].cget("state")) == "disabled":
            self.root.after(500, self._arztbrief_watch)
            return
        self.btn_pdf.config(state="normal", bg="#3498db")
        self.arztbrief_status.config(text="✅ Analyse abgeschlossen", fg="#27ae60")

    # ------------------------------------------------------------ Globale Tastenkürzel
    HOTKEY_ACTIONS = (
        ("hotkey_start", "Start"),
        ("hotkey_pause", "Pause / Weiter"),
        ("hotkey_analyse", "Analyse"),
        ("hotkey_copy_close", "Ergebnis kopieren & schließen"),
    )

    def _init_hotkeys(self):
        if not hotkeys.IS_WINDOWS:
            return
        if not self.hotkeys.start():
            self.log("Globale Tastenkürzel nicht verfügbar.")
            return
        self._apply_hotkeys()

    def _apply_hotkeys(self):
        if not self.hotkeys.running:
            return
        handlers = {"hotkey_start": self._hk_start, "hotkey_pause": self._hk_pause,
                    "hotkey_analyse": self._hk_analyse, "hotkey_copy_close": self._hk_copy_close}
        # Rückrufe kommen aus dem Hotkey-Thread -> Tk-Aufrufe über die UI-Queue
        actions = {label: (config.get(key, ""), lambda h=handlers[key]: self._ui(h))
                   for key, label in self.HOTKEY_ACTIONS}
        ptt = (config.get("ptt_hotkey", ""), lambda: self.ptt_events.put(self._ptt_press),
               lambda: self.ptt_events.put(self._ptt_release), lambda: self.ptt_events.put(self._ptt_cancel))
        for err in self.hotkeys.set_bindings(actions, ptt):
            self.log(f"Tastenkürzel: {err}")
        active = [f"{label} = {hotkeys.format_combo(config.get(key, ''))}"
                  for key, label in self.HOTKEY_ACTIONS if config.get(key)]
        if config.get("ptt_hotkey"):
            active.append(f"Diktat halten = {hotkeys.format_combo(config['ptt_hotkey'])}")
        if active:
            self.log("Tastenkürzel: " + "; ".join(active))

    def _toast(self, text, color, ms=1800):
        if not self.ptt_active:   # den Diktat-Hinweis nicht überdecken
            self.overlay.flash(text, color, ms)

    def _hk_start(self):
        if self.is_recording:
            return
        if self.notebook.index(self.notebook.select()) not in (self.TAB_AMBIENT, self.TAB_DIKTAT, self.TAB_ARENA):
            self.notebook.select(self.tab_ambient)
        self.start_recording()
        if self.is_recording:
            tab = self.notebook.tab(self.notebook.select(), "text").strip()
            self._toast(f"Aufnahme läuft ({tab})", "#c0392b")

    def _hk_pause(self):
        if not self.is_recording:
            return
        self.toggle_pause()
        if self.recorder.paused:
            self._toast("Aufnahme pausiert", "#d35400")
        else:
            self._toast("Aufnahme läuft weiter", "#c0392b")

    def _hk_analyse(self):
        if not self.is_recording:
            return
        self.stop_recording()
        self._toast("Analyse läuft …", "#2980b9")

    def _hk_copy_close(self):
        cs = self.chat_session
        if not cs.get("close"):
            return
        entry = cs.get("input_entry")
        if entry and entry.winfo_exists() and str(entry.cget("state")) == "disabled":
            self._toast("LLM arbeitet noch …", "#7f8c8d")
            return
        cs["close"]()
        self._toast("Ergebnis in der Zwischenablage", "#27ae60")

    # ------------------------------------------------------------ Freihand-Diktat (Push-to-Talk)
    # _ptt_press/_release/_cancel laufen nacheinander in einem eigenen Steuer-Thread (ein
    # hängendes Mikrofon blockiert so nicht die übrigen Kürzel); Transkription und Einfügen
    # erledigt _ptt_worker.
    def _ptt_control_loop(self):
        while True:
            fn = self.ptt_events.get()
            try:
                fn()
            except Exception as e:
                self.log(f"Diktat-Fehler: {e}")

    def _ptt_press(self):
        if self.ptt_active:
            return
        self.ptt_target = hotkeys.foreground_window()
        self.ptt_paused_ambient = self.is_recording and not self.recorder.paused
        if self.ptt_paused_ambient:
            self.recorder.paused = True   # laufendes Gespräch solange anhalten
        if not self.ptt_recorder.start(config.get("input_device")):
            self._ptt_resume_ambient()
            self.log(f"Diktat: Mikrofon konnte nicht gestartet werden – {self.ptt_recorder.last_error}")
            self._ui(lambda: self.overlay.flash("Mikrofon konnte nicht gestartet werden (Details im Log)",
                                                "#c0392b", 3000))
            return
        self.ptt_active = True
        self.ptt_started = time.time()
        self.ptt_gen += 1
        threading.Timer(0.25, self._ptt_feedback, args=(self.ptt_gen,)).start()

    def _ptt_feedback(self, gen):
        # Erst nach kurzem Halten melden: die rechte Strg-Taste wird auch für normale Kürzel
        # (Strg+C) benutzt – dann soll weder Hinweis noch Signalton kommen.
        if not self.ptt_active or gen != self.ptt_gen:
            return
        self._ui(lambda: self.overlay.show("Diktat – sprechen, zum Einfügen loslassen", "#c0392b"))
        if winsound and config.get("ptt_beep", True):
            try:
                winsound.Beep(1100, 60)
            except RuntimeError:
                pass

    def _ptt_resume_ambient(self):
        if self.ptt_paused_ambient and self.is_recording:
            self.recorder.paused = False
        self.ptt_paused_ambient = False

    def _ptt_stop_recorder(self):
        self.ptt_active = False
        data, _ = self.ptt_recorder.stop()
        self._ptt_resume_ambient()
        return data

    def _ptt_release(self):
        if not self.ptt_active:
            return
        held = time.time() - self.ptt_started
        data = self._ptt_stop_recorder()
        if data is None or held < 0.5:   # nur angetippt
            self._ui(self._ptt_overlay_idle)
            return
        self.ptt_jobs.put((data, self.ptt_target))
        self._ui(self._ptt_overlay_idle)

    def _ptt_cancel(self):
        if self.ptt_active:
            self._ptt_stop_recorder()
            self._ui(self._ptt_overlay_idle)

    def _ptt_overlay_idle(self, text=None, color="#7f8c8d"):
        """Overlay nach einem Diktat zurücksetzen (Tk-Thread) – nicht, wenn schon das nächste läuft."""
        if self.ptt_active:
            return
        if self.ptt_jobs.unfinished_tasks:
            self.overlay.show("Diktat wird transkribiert …", "#2980b9")
        elif text:
            self.overlay.flash(text, color, 2500)
        else:
            self.overlay.hide()

    def _ptt_worker(self):
        while True:
            data, target = self.ptt_jobs.get()
            msg = None
            try:
                text = self._ptt_transcribe(data)
                if text:
                    hotkeys.insert_text(text, config.get("ptt_insert_mode", "paste"), target)
                    self.log(f"Diktat eingefügt ({len(text.strip())} Zeichen).")
                else:
                    msg = ("Nichts erkannt", "#7f8c8d")
            except Exception as e:
                self.log(f"Diktat-Fehler: {e}")
                msg = (f"Diktat fehlgeschlagen: {str(e)[:70]}", "#c0392b")
            finally:
                self.ptt_jobs.task_done()
            self._ui(lambda m=msg: self._ptt_overlay_idle(*m) if m else self._ptt_overlay_idle())

    def _ptt_transcribe(self, data):
        thr = float(config.get("silence_threshold", 0.01))
        if not len(data) or float(np.sqrt(np.mean(data ** 2))) < thr * 0.5:
            return ""
        text = apply_dictation_commands(SERVER.transcribe(data).get("text", ""))
        if text and config.get("ptt_llm", False):
            self._ui(lambda: None if self.ptt_active else self.overlay.show("LLM überarbeitet das Diktat …", "#2980b9"))
            reply = LLM.chat(config.get("model_diktat"), self._build_messages(config.get("prompt_diktat", ""), text))
            text = clean_for_pvs(reply)
        if text and not text[-1].isspace():
            text += " "   # mehrere Diktate hintereinander nicht zusammenkleben
        return text

    # ------------------------------------------------------------ Einstellungen
    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Einstellungen")
        win.geometry("660x850")
        win.transient(self.root)
        win.grab_set()

        top_frame = tk.Frame(win, bg="#ecf0f1")
        top_frame.pack(side="top", fill="x")
        btn_top_save = tk.Button(top_frame, text="💾 Änderungen Speichern", bg="#2ecc71", fg="white",
                                 font=("Segoe UI", 9, "bold"), pady=5)
        btn_top_save.pack(side="right", padx=10, pady=5)
        tk.Label(top_frame, text="Einstellungen", font=("Segoe UI", 12, "bold"), bg="#ecf0f1").pack(side="left", padx=10)

        canvas = tk.Canvas(win, borderwidth=0, highlightthickness=0)
        scroll = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        content = tk.Frame(canvas)
        content_window = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda e: (canvas.configure(scrollregion=canvas.bbox("all")),
                                               canvas.itemconfig(content_window, width=canvas.winfo_width())))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(content_window, width=e.width))
        win.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        def heading(text):
            tk.Label(content, text=f"─── {text} ───", font=("Segoe UI", 10, "bold"), fg="#2c3e50").pack(anchor="w", padx=10, pady=(15, 0))

        def add_entry(name, key, show=None):
            tk.Label(content, text=name, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
            e = tk.Entry(content, width=50, show=show)
            e.insert(0, str(config.get(key, "") if config.get(key) is not None else ""))
            e.pack(padx=10, fill="x")
            return e

        heading("Praxisserver")
        e_server = add_entry("Server-Adresse (z. B. https://192.168.10.51:8000)", "server_url")
        e_apikey = add_entry("API-Key (nur wenn auf dem Server gesetzt)", "api_key", show="*")
        e_client = add_entry("Name dieses Arbeitsplatzes (Zimmer)", "client_name")

        tk.Label(content, text="CA-Zertifikat (ca.crt vom Server)", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        ca_frame = tk.Frame(content)
        ca_frame.pack(padx=10, fill="x")
        e_ca = tk.Entry(ca_frame, width=38)
        e_ca.insert(0, config.get("ca_cert_path", ""))
        e_ca.pack(side="left", fill="x", expand=True)

        def browse_ca():
            path = filedialog.askopenfilename(title="CA-Zertifikat auswählen",
                                              filetypes=[("Zertifikat", "*.crt *.pem"), ("Alle Dateien", "*.*")])
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
            messagebox.showinfo("Hinweis", "Windows-Zertifikat-Assistent geöffnet.\nBitte 'Lokaler Computer' → "
                                "'Vertrauenswürdige Stammzertifizierungsstellen' wählen.")
        tk.Button(content, text="🌐 Im Browser/System vertrauen (einmalig)", command=install_ca_browser,
                  bg="#3498db", fg="white", font=("Segoe UI", 8), relief="flat").pack(anchor="w", padx=10, pady=(2, 0))

        heading("Transkription")
        var_diar = tk.BooleanVar(value=config.get("diarize", True))
        tk.Checkbutton(content, text="Sprechertrennung (ARZT / PATIENT) im Gespräch-Modus", variable=var_diar).pack(anchor="w", padx=10, pady=(8, 0))
        e_speakers = add_entry("Erwartete Sprecheranzahl (0 = automatisch, 2 = Arzt + Patient)", "expected_speakers")
        e_chunk = add_entry("Chunk-Dauer in Sekunden (Schnitt an der nächsten Sprechpause)", "chunk_duration")

        # Stimme anlernen
        tk.Label(content, text="Eigene Stimme anlernen (für das Label ARZT)", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        enroll_frame = tk.Frame(content)
        enroll_frame.pack(padx=10, fill="x")
        e_enroll_name = tk.Entry(enroll_frame, width=14)
        e_enroll_name.insert(0, "Arzt")
        e_enroll_name.pack(side="left")
        lbl_enroll = tk.Label(content, text="", font=("Segoe UI", 8), fg="#7f8c8d", wraplength=600, justify="left")

        def refresh_enrolled():
            try:
                names = [f"{e.get('name')} ({e.get('seconds', '?')}s)" for e in SERVER.list_enrolled()]
                lbl_enroll.config(text="Angelernt: " + (", ".join(names) if names else "– keine –"))
            except Exception as ex:
                lbl_enroll.config(text=f"Server nicht erreichbar: {str(ex)[:60]}")

        def do_enroll():
            name = e_enroll_name.get().strip() or "Arzt"
            secs = 25
            if not messagebox.askokcancel("Stimme anlernen",
                                          f"Es werden jetzt {secs} Sekunden aufgenommen.\nBitte normal sprechen "
                                          f"(z. B. einen Befund vorlesen).\n\nAufnahme starten?"):
                return
            btn_enroll.config(state="disabled")

            def worker():
                try:
                    dev = config.get("input_device")
                    for remaining in range(secs, 0, -1):
                        self._ui(lambda r=remaining: lbl_enroll.config(text=f"Aufnahme läuft … noch {r}s"))
                        if remaining == secs:
                            rec = sd.rec(int(secs * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=dev)
                        time.sleep(1)
                    sd.wait()
                    audio = rec.reshape(-1)
                    self._ui(lambda: lbl_enroll.config(text="Übertrage …"))
                    res = SERVER.enroll(name, audio)
                    self.log(f"Stimme angelernt: {res.get('name')} ({res.get('seconds')}s)")
                except Exception as ex:
                    self._ui(lambda: messagebox.showerror("Fehler", f"Anlernen fehlgeschlagen:\n{ex}"))
                finally:
                    self._ui(refresh_enrolled)
                    self._ui(lambda: btn_enroll.config(state="normal"))
            threading.Thread(target=worker, daemon=True).start()

        def do_delete_enrolled():
            name = e_enroll_name.get().strip()
            if name and messagebox.askyesno("Löschen", f"Angelernte Stimme '{name}' auf dem Server löschen?"):
                try:
                    SERVER.delete_enrolled(name)
                except Exception as ex:
                    messagebox.showerror("Fehler", str(ex))
                refresh_enrolled()

        btn_enroll = tk.Button(enroll_frame, text="🎤 Jetzt anlernen (25 s)", command=do_enroll, bg="#8e44ad", fg="white",
                               font=("Segoe UI", 8), relief="flat")
        btn_enroll.pack(side="left", padx=6)
        tk.Button(enroll_frame, text="Löschen", command=do_delete_enrolled, bg="#ecf0f1", font=("Segoe UI", 8),
                  relief="flat").pack(side="left")
        lbl_enroll.pack(anchor="w", padx=10)
        threading.Thread(target=lambda: self._ui(refresh_enrolled), daemon=True).start()

        heading("Tastenkürzel (systemweit, auch per Makro auslösbar)")
        hk_entries = {}
        capture_btn = {"btn": None}

        def finish_capture(entry, btn, combo):
            if combo is not None:
                entry.delete(0, tk.END)
                entry.insert(0, hotkeys.format_combo(combo))
            if btn.winfo_exists():
                btn.config(text="Festlegen", bg="#ecf0f1")
            capture_btn["btn"] = None

        def start_capture(entry, btn):
            if not self.hotkeys.running:
                messagebox.showinfo("Tastenkürzel", "Der Tastaturhook läuft nicht – bitte das Kürzel eintippen, "
                                    "z. B. 'Strg + Umschalt + F9'.", parent=win)
                return
            if capture_btn["btn"] and capture_btn["btn"].winfo_exists():
                capture_btn["btn"].config(text="Festlegen", bg="#ecf0f1")
            capture_btn["btn"] = btn
            btn.config(text="Tasten drücken … (Esc)", bg="#f9e79f")
            self.hotkeys.capture(lambda combo: self._ui(lambda: finish_capture(entry, btn, combo)))

        def hotkey_row(label_text, key):
            tk.Label(content, text=label_text, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(8, 0))
            row = tk.Frame(content)
            row.pack(padx=10, fill="x")
            e = tk.Entry(row, width=30)
            e.insert(0, hotkeys.format_combo(config.get(key, "")))
            e.pack(side="left", fill="x", expand=True)
            b = tk.Button(row, text="Festlegen", bg="#ecf0f1", font=("Segoe UI", 8), relief="flat", width=20)
            b.config(command=lambda: start_capture(e, b))
            b.pack(side="left", padx=4)
            tk.Button(row, text="Leeren", bg="#ecf0f1", font=("Segoe UI", 8), relief="flat",
                      command=lambda: e.delete(0, tk.END)).pack(side="left")
            hk_entries[key] = e

        for key, label in self.HOTKEY_ACTIONS:
            hotkey_row(label, key)
        hotkey_row("Freihand-Diktat (gedrückt halten, z. B. Strg rechts)", "ptt_hotkey")
        tk.Label(content, text="Ins Zielfenster klicken (PVS-Feld, Notepad …), Taste halten, sprechen, loslassen – "
                 "der Text wird an der Cursorposition eingefügt. „neue Zeile“ und „neuer Absatz“ werden umgesetzt. "
                 "Ein leeres Feld schaltet das Kürzel ab.",
                 font=("Segoe UI", 8), fg="#7f8c8d", wraplength=600, justify="left").pack(anchor="w", padx=10, pady=(2, 0))
        var_ptt_mode = tk.StringVar(value=config.get("ptt_insert_mode", "paste"))
        tk.Radiobutton(content, text="Einfügen über die Zwischenablage (Strg+V, schnell; Zwischenablage bleibt erhalten)",
                       variable=var_ptt_mode, value="paste").pack(anchor="w", padx=10, pady=(6, 0))
        tk.Radiobutton(content, text="Zeichen für Zeichen tippen (wenn das Programm Strg+V nicht annimmt)",
                       variable=var_ptt_mode, value="type").pack(anchor="w", padx=10)
        var_ptt_llm = tk.BooleanVar(value=config.get("ptt_llm", False))
        tk.Checkbutton(content, text="Diktat vor dem Einfügen mit dem Diktat-Prompt überarbeiten (LLM, langsamer)",
                       variable=var_ptt_llm).pack(anchor="w", padx=10)
        var_ptt_beep = tk.BooleanVar(value=config.get("ptt_beep", True))
        tk.Checkbutton(content, text="Signalton, sobald die Diktat-Aufnahme läuft", variable=var_ptt_beep).pack(anchor="w", padx=10)
        win.bind("<Destroy>", lambda e: self.hotkeys.cancel_capture() if e.widget is win else None)

        heading("Sprachmodell (LLM)")
        var_via = tk.BooleanVar(value=config.get("llm_via_server", True))
        tk.Checkbutton(content, text="LLM über den Praxisserver ansprechen (empfohlen)", variable=var_via).pack(anchor="w", padx=10, pady=(8, 0))
        e_llm = add_entry("Direkte Ollama-Adresse (nur wenn nicht über Praxisserver)", "llm_api_url")
        e_ctx = add_entry("Kontextfenster (num_ctx, Tokens)", "llm_num_ctx")
        e_temp = add_entry("Temperatur (0.0 – 1.0)", "llm_temperature")

        ollama_models = LLM.models()

        def add_model_dropdown(label_text, config_key):
            tk.Label(content, text=label_text, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
            cb = ttk.Combobox(content, values=ollama_models, width=48)
            cb.set(config.get(config_key, ""))
            cb.pack(padx=10, fill="x")
            return cb

        e_model_amb = add_model_dropdown("Gespräch — Modell", "model_ambient")
        e_model_dik = add_model_dropdown("Diktat — Modell", "model_diktat")
        e_model_arena_a = add_model_dropdown("Arena — Modell A", "model_arena_a")
        e_model_arena_b = add_model_dropdown("Arena — Modell B", "model_arena_b")
        e_model_brief = add_model_dropdown("Arztbrief — Modell", "model_arztbrief")
        e_auto_delete = add_entry("Auto-Löschung Transkripte (Tage, 0 = aus)", "auto_delete_days")

        heading("System-Prompts")

        def add_prompt_field(label_text, config_key):
            tk.Label(content, text=label_text, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
            st = scrolledtext.ScrolledText(content, width=55, height=6, wrap="word", font=("Segoe UI", 8))
            st.insert("1.0", config.get(config_key, ""))
            st.pack(padx=10, fill="x")
            return st

        st_prompt_amb = add_prompt_field("Gespräch — System-Prompt", "prompt_ambient")
        st_prompt_dik = add_prompt_field("Diktat — System-Prompt", "prompt_diktat")
        st_prompt_arena_a = add_prompt_field("Arena Modell A — System-Prompt", "prompt_arena_a")
        st_prompt_arena_b = add_prompt_field("Arena Modell B — System-Prompt", "prompt_arena_b")
        st_prompt_brief = add_prompt_field("Arztbrief — System-Prompt", "prompt_arztbrief")

        heading("Audio")
        devices = sd.query_devices()
        input_devs = [f"{i}: {d['name']}" for i, d in enumerate(devices) if d['max_input_channels'] > 0]
        wasapi_devs = [f"{i}: {d['name']}" for i, d in enumerate(devices) if d['hostapi'] == sd.default.hostapi]

        tk.Label(content, text="Mikrofon", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        cb_mic = ttk.Combobox(content, values=input_devs)
        if config.get("input_device") is not None:
            match = [d for d in input_devs if d.startswith(str(config["input_device"]) + ":")]
            if match:
                cb_mic.set(match[0])
        else:
            cb_mic.set(input_devs[0] if input_devs else "")
        cb_mic.pack(padx=10, fill="x")

        tk.Label(content, text="System-Audio (Loopback) – optional für Video-Sprechstunde", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        cb_loop = ttk.Combobox(content, values=wasapi_devs)
        if config.get("loopback_device") is not None:
            match = [d for d in wasapi_devs if d.startswith(str(config["loopback_device"]) + ":")]
            if match:
                cb_loop.set(match[0])
        cb_loop.pack(padx=10, fill="x")
        var_mix = tk.BooleanVar(value=config.get("mix_system_audio", False))
        tk.Checkbutton(content, text="System-Audio mit aufnehmen (Mix)", variable=var_mix).pack(anchor="w", padx=10, pady=10)

        def to_int(entry, default):
            try:
                return int(float(entry.get()))
            except ValueError:
                return default

        def save():
            new_hotkeys, seen = {}, {}
            labels = dict(self.HOTKEY_ACTIONS, ptt_hotkey="Freihand-Diktat")
            for key, e in hk_entries.items():
                err = hotkeys.validate_combo(e.get())
                combo = hotkeys.normalize_combo(e.get())
                if not err and combo in seen:
                    err = f"schon für '{labels[seen[combo]]}' vergeben"
                if err:
                    messagebox.showerror("Tastenkürzel", f"{labels[key]}: {err}", parent=win)
                    return
                if combo:
                    seen[combo] = key
                new_hotkeys[key] = combo
            config.update(new_hotkeys)
            config["ptt_insert_mode"] = var_ptt_mode.get()
            config["ptt_llm"] = var_ptt_llm.get()
            config["ptt_beep"] = var_ptt_beep.get()
            config["server_url"] = e_server.get().strip().rstrip("/")
            config["api_key"] = e_apikey.get().strip()
            config["client_name"] = e_client.get().strip()
            config["ca_cert_path"] = e_ca.get().strip()
            config["diarize"] = var_diar.get()
            config["expected_speakers"] = to_int(e_speakers, 0)
            config["chunk_duration"] = max(5, to_int(e_chunk, 20))
            config["llm_via_server"] = var_via.get()
            config["llm_api_url"] = e_llm.get().strip().rstrip("/")
            config["llm_num_ctx"] = max(2048, to_int(e_ctx, 16384))
            try:
                config["llm_temperature"] = float(e_temp.get().replace(",", "."))
            except ValueError:
                config["llm_temperature"] = 0.2
            config["model_ambient"] = e_model_amb.get()
            config["model_diktat"] = e_model_dik.get()
            config["model_arena_a"] = e_model_arena_a.get()
            config["model_arena_b"] = e_model_arena_b.get()
            config["model_arztbrief"] = e_model_brief.get()
            config["prompt_ambient"] = st_prompt_amb.get("1.0", "end-1c")
            config["prompt_diktat"] = st_prompt_dik.get("1.0", "end-1c")
            config["prompt_arena_a"] = st_prompt_arena_a.get("1.0", "end-1c")
            config["prompt_arena_b"] = st_prompt_arena_b.get("1.0", "end-1c")
            config["prompt_arztbrief"] = st_prompt_brief.get("1.0", "end-1c")
            config["auto_delete_days"] = to_int(e_auto_delete, 1)
            if cb_mic.get():
                config["input_device"] = int(cb_mic.get().split(":")[0])
            if cb_loop.get():
                config["loopback_device"] = int(cb_loop.get().split(":")[0])
            config["mix_system_audio"] = var_mix.get()
            save_config(config)
            win.unbind_all("<MouseWheel>")
            win.destroy()
            self.log("Einstellungen gespeichert.")
            self._apply_hotkeys()
            threading.Thread(target=self._check_server, daemon=True).start()

        btn_top_save.config(command=save)
        tk.Button(content, text="Speichern", command=save, bg="#2ecc71", fg="white", pady=5).pack(fill="x", padx=20, pady=20)


if __name__ == "__main__":
    root = tk.Tk()
    s = ttk.Style()
    s.configure('TNotebook.Tab', padding=[15, 5], font=('Segoe UI', 9))
    app = ModernRecorder(root)
    root.mainloop()
