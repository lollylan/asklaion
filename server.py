"""
server.py – Asklaion Praxisserver v2.0
=======================================
Ein Server im Praxisnetz für alle Behandlungszimmer:

  * Transkription (faster-whisper, GPU oder CPU) mit VAD, Hotwords, Wortzeiten
  * Sprechertrennung (sherpa-onnx, CPU, inkrementell während des Gesprächs)
  * Sitzungsverwaltung: jedes Zimmer/Gespräch hat eine eigene Session-ID,
    Audio und Text werden strikt getrennt gehalten
  * Sprecher anlernen ("ARZT"), damit Transkripte Rollen tragen
  * LLM-Proxy zu Ollama (/llm/...), damit Clients nur eine Server-Adresse brauchen
  * TLS (selbstsignierte CA, siehe security_utils.py), optionaler API-Key

Konfiguration: server_config.json (wird beim ersten Start erzeugt).

Start:  python server.py
Benötigt: pip install -r requirements-server.txt
"""

import io
import json
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import requests
import soundfile as sf
import uvicorn
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from security_utils import ensure_tls_certs, get_base_dir

VERSION = "2.0"
BASE_DIR = get_base_dir()
CONFIG_FILE = os.path.join(BASE_DIR, "server_config.json")
SAMPLE_RATE = 16000

DEFAULT_SERVER_CONFIG = {
    "host": "0.0.0.0",
    "port": 8000,
    "tls": True,
    "api_key": "",                      # leer = keine Authentifizierung (nur Praxis-LAN!)
    "asr": {
        "model": "large-v3-turbo",      # Alternativen: "large-v3" (genauer, langsamer), "medium", "small"
        "device": "auto",               # "cuda" | "cpu" | "auto"
        "compute_type": "auto",         # "float16" (GPU) | "int8" (CPU) | "auto"
        "batch_size": 16,
        "beam_size": 5,
        "language": "de",
        "cpu_threads": 0,
        "vad_min_silence_ms": 400
    },
    "diarization": {
        "enabled": True,
        "threads": 4,
        "cluster_threshold": 0.3,       # Cosinus-Distanz: kleiner = mehr Sprecher, größer = weniger
        "match_threshold": 0.45,        # Mindest-Ähnlichkeit zu angelernter Stimme
        "default_expected_speakers": 0  # 0 = automatisch
    },
    "ollama_url": "http://localhost:11434",
    "session_timeout_minutes": 90,
    "log_transcripts": False            # True = Transkripttext in der Server-Konsole anzeigen
}


def load_server_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SERVER_CONFIG, f, indent=4, ensure_ascii=False)
        print(f"[CONFIG] Standardkonfiguration erstellt: {CONFIG_FILE}")
        return json.loads(json.dumps(DEFAULT_SERVER_CONFIG))
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # fehlende Schlüssel ergänzen
    def merge(dst, src):
        for k, v in src.items():
            if k not in dst:
                dst[k] = v
            elif isinstance(v, dict) and isinstance(dst[k], dict):
                merge(dst[k], v)
    merge(cfg, DEFAULT_SERVER_CONFIG)
    return cfg


CFG = load_server_config()

# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------
from asr_engine import ASREngine                     # noqa: E402
from vocabulary import Vocabulary                    # noqa: E402
from diarization import (Diarizer, EnrollmentStore,  # noqa: E402
                         Turn, assign_words, blocks_to_text)

VOCAB = Vocabulary(BASE_DIR)
ASR = ASREngine(**CFG["asr"])
ASR.warmup()

DIAR: Optional[Diarizer] = None
if CFG["diarization"]["enabled"]:
    try:
        DIAR = Diarizer(models_dir=os.path.join(BASE_DIR, "models"),
                        threads=CFG["diarization"]["threads"],
                        cluster_threshold=CFG["diarization"]["cluster_threshold"])
    except Exception as e:
        print(f"[DIAR] Sprechertrennung deaktiviert: {e}")
ENROLL = EnrollmentStore(os.path.join(BASE_DIR, "enrollments"))
DIAR_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="diar")

# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

@dataclass
class Session:
    id: str
    client: str = ""
    room: str = ""
    context_terms: List[str] = field(default_factory=list)
    expected_speakers: int = 0
    diarize: bool = True
    created: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    chunk_count: int = 0
    audio_seconds: float = 0.0
    words: List[dict] = field(default_factory=list)      # absolute Zeiten
    chunk_texts: Dict[int, str] = field(default_factory=dict)
    turns: List[Turn] = field(default_factory=list)
    diar_futures: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    finalized: bool = False


SESSIONS: Dict[str, Session] = {}
SESSIONS_LOCK = threading.Lock()


def _get_session(session_id: str) -> Session:
    with SESSIONS_LOCK:
        s = SESSIONS.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Sitzung unbekannt oder abgelaufen")
    s.last_seen = time.time()
    return s


def _reaper():
    timeout = max(5, int(CFG.get("session_timeout_minutes", 90))) * 60
    while True:
        time.sleep(60)
        now = time.time()
        with SESSIONS_LOCK:
            stale = [k for k, s in SESSIONS.items() if now - s.last_seen > timeout]
            for k in stale:
                SESSIONS.pop(k, None)
        if stale:
            print(f"[SESSION] {len(stale)} inaktive Sitzung(en) gelöscht")


threading.Thread(target=_reaper, daemon=True).start()

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def decode_audio(data: bytes) -> np.ndarray:
    """WAV/FLAC/OGG-Bytes -> float32 mono 16 kHz (rein im Speicher, keine Temp-Datei)."""
    try:
        audio, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Audio nicht lesbar: {e}")
    audio = audio.mean(axis=1) if audio.shape[1] > 1 else audio[:, 0]
    if sr != SAMPLE_RATE:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(SAMPLE_RATE, sr)
        audio = resample_poly(audio, SAMPLE_RATE // g, sr // g).astype(np.float32)
    return np.ascontiguousarray(audio, dtype=np.float32)


def _parse_terms(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        val = json.loads(raw)
        if isinstance(val, list):
            return [str(x).strip() for x in val if str(x).strip()]
    except Exception:
        pass
    import re
    return [t.strip() for t in re.split(r"[,\n;]+", raw) if t.strip()]


def _correct_words(words: List[dict], extra_terms: List[str]) -> List[dict]:
    for w in words:
        w["word"], _ = VOCAB.correct_word(w["word"], extra_terms)
    return words


def _run_asr(audio: np.ndarray, context_terms: List[str]) -> dict:
    res = ASR.transcribe(audio, hotwords=VOCAB.hotwords(context_terms))
    res["words"] = _correct_words(res["words"], context_terms)
    res["text"] = VOCAB.correct_text(res["text"], context_terms)
    return res


def _finalize_diarization(session: Session) -> dict:
    """Wartet auf ausstehende Segmentierungen, clustert, ordnet Wörter zu."""
    for fut in session.diar_futures:
        try:
            fut.result(timeout=120)
        except Exception as e:
            print(f"[DIAR] Chunk-Segmentierung fehlgeschlagen: {e}")
    session.diar_futures = []
    if not DIAR or not session.diarize or not session.turns:
        return {"speakers": [], "blocks": [], "transcript": "", "matched": {}}
    expected = session.expected_speakers or int(CFG["diarization"].get("default_expected_speakers", 0))
    result = DIAR.cluster(session.turns, expected_speakers=expected or None,
                          enrolled=ENROLL.load_all(),
                          match_threshold=float(CFG["diarization"]["match_threshold"]))
    blocks = assign_words(sorted(session.words, key=lambda w: w["start"]), result.turns)
    return {"speakers": result.speakers, "blocks": blocks,
            "transcript": blocks_to_text(blocks), "matched": result.matched}


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Asklaion Praxisserver", version=VERSION)


def require_key(x_api_key: Optional[str] = Header(default=None)):
    key = (CFG.get("api_key") or "").strip()
    if key and x_api_key != key:
        raise HTTPException(status_code=401, detail="API-Key fehlt oder falsch")


@app.get("/health")
def health():
    with SESSIONS_LOCK:
        n = len(SESSIONS)
    return {
        "status": "ok", "version": VERSION,
        "asr_model": ASR.model_name, "device": ASR.device, "compute_type": ASR.compute_type,
        "diarization": DIAR is not None, "sessions": n,
        "enrolled": [e.get("name") for e in ENROLL.list()],
        "vocabulary_terms": len(VOCAB.terms),
        "auth_required": bool((CFG.get("api_key") or "").strip()),
    }


# -- Sitzungen ---------------------------------------------------------------

@app.post("/session", dependencies=[Depends(require_key)])
def create_session(client: str = Form(""), room: str = Form(""), context_terms: str = Form(""),
                   expected_speakers: int = Form(0), diarize: bool = Form(True)):
    s = Session(id=uuid.uuid4().hex, client=client[:64], room=room[:64],
                context_terms=_parse_terms(context_terms)[:200],
                expected_speakers=max(0, min(int(expected_speakers), 8)), diarize=bool(diarize))
    with SESSIONS_LOCK:
        SESSIONS[s.id] = s
    print(f"[SESSION] Neu: {s.id[:8]} client={s.client!r} room={s.room!r} "
          f"kontext={len(s.context_terms)} Begriffe, diarize={s.diarize}")
    return {"session_id": s.id, "diarization": bool(DIAR) and s.diarize}


@app.post("/session/{session_id}/chunk", dependencies=[Depends(require_key)])
def upload_chunk(session_id: str, file: UploadFile = File(...), offset: float = Form(-1.0),
                 index: int = Form(-1)):
    s = _get_session(session_id)
    if s.finalized:
        raise HTTPException(status_code=409, detail="Sitzung ist bereits abgeschlossen")
    audio = decode_audio(file.file.read())
    dur = len(audio) / SAMPLE_RATE
    with s.lock:
        chunk_offset = float(offset) if offset >= 0 else s.audio_seconds
        s.chunk_count += 1
        idx = int(index) if index >= 0 else s.chunk_count
        s.audio_seconds = max(s.audio_seconds, chunk_offset + dur)

    res = _run_asr(audio, s.context_terms)
    with s.lock:
        for w in res["words"]:
            w["start"] += chunk_offset
            w["end"] += chunk_offset
        s.words.extend(res["words"])
        s.chunk_texts[idx] = res["text"]
        if DIAR and s.diarize and res["words"]:
            fut = DIAR_POOL.submit(_segment_job, s, audio, chunk_offset)
            s.diar_futures.append(fut)

    if CFG.get("log_transcripts"):
        print(f"[{s.id[:8]}] #{idx} ({dur:.1f}s in {res['elapsed']:.2f}s): {res['text'][:120]}")
    else:
        print(f"[{s.id[:8]}] Chunk #{idx}: {dur:.1f}s Audio in {res['elapsed']:.2f}s, "
              f"{len(res['words'])} Wörter")
    return {"index": idx, "text": res["text"], "words": res["words"],
            "elapsed": round(res["elapsed"], 3), "offset": chunk_offset}


def _segment_job(s: Session, audio: np.ndarray, offset: float):
    turns = DIAR.segment_chunk(audio, offset)
    with s.lock:
        s.turns.extend(turns)


@app.post("/session/{session_id}/finalize", dependencies=[Depends(require_key)])
def finalize_session(session_id: str, file: Optional[UploadFile] = File(None),
                     offset: float = Form(-1.0), index: int = Form(-1)):
    """Optional letzten Chunk mitschicken; liefert das vollständige Transkript."""
    s = _get_session(session_id)
    if file is not None:
        upload_chunk(session_id, file=file, offset=offset, index=index)
    t0 = time.time()
    with s.lock:
        s.finalized = True
        ordered = [s.chunk_texts[k] for k in sorted(s.chunk_texts)]
    plain = " ".join(t for t in ordered if t).strip()
    diar = _finalize_diarization(s)
    print(f"[{s.id[:8]}] Abschluss: {s.audio_seconds:.0f}s Audio, {len(s.words)} Wörter, "
          f"Sprecher={diar['speakers']}, Diarisierung {time.time() - t0:.2f}s")
    return {
        "session_id": s.id, "text": plain, "transcript": diar["transcript"] or plain,
        "speakers": diar["speakers"], "blocks": diar["blocks"], "matched": diar["matched"],
        "audio_seconds": round(s.audio_seconds, 1), "words": len(s.words),
    }


@app.delete("/session/{session_id}", dependencies=[Depends(require_key)])
def delete_session(session_id: str):
    with SESSIONS_LOCK:
        s = SESSIONS.pop(session_id, None)
    if s:
        s.words.clear(); s.turns.clear(); s.chunk_texts.clear()
    return {"deleted": bool(s)}


# -- Einzeltranskription (kompatibel zu v1.0-Clients) -----------------------

@app.post("/transcribe", dependencies=[Depends(require_key)])
def transcribe_once(file: UploadFile = File(...), context_terms: str = Form(""),
                    diarize: bool = Form(False), expected_speakers: int = Form(0)):
    audio = decode_audio(file.file.read())
    terms = _parse_terms(context_terms)
    res = _run_asr(audio, terms)
    out = {"text": res["text"], "language": ASR.language, "elapsed": round(res["elapsed"], 3),
           "duration": round(res["duration"], 1), "id": uuid.uuid4().hex}
    if diarize and DIAR and res["words"]:
        turns = DIAR.segment_chunk(audio, 0.0)
        result = DIAR.cluster(turns, expected_speakers=expected_speakers or None,
                              enrolled=ENROLL.load_all(),
                              match_threshold=float(CFG["diarization"]["match_threshold"]))
        blocks = assign_words(res["words"], result.turns)
        out.update({"transcript": blocks_to_text(blocks), "speakers": result.speakers,
                    "blocks": blocks, "matched": result.matched})
    if CFG.get("log_transcripts"):
        print(f"[once] {res['text'][:120]}")
    return out


# -- Sprecher anlernen --------------------------------------------------------

@app.get("/enroll", dependencies=[Depends(require_key)])
def list_enrollments():
    return {"enrolled": ENROLL.list()}


@app.post("/enroll", dependencies=[Depends(require_key)])
def enroll_speaker(name: str = Form(...), file: UploadFile = File(...)):
    if not DIAR:
        raise HTTPException(status_code=503, detail="Sprechertrennung ist auf dem Server deaktiviert")
    audio = decode_audio(file.file.read())
    seconds = len(audio) / SAMPLE_RATE
    if seconds < 8:
        raise HTTPException(status_code=400, detail="Bitte mindestens 8 Sekunden Sprache aufnehmen")
    emb = DIAR.enrollment_embedding(audio)
    if emb is None:
        raise HTTPException(status_code=400, detail="Keine verwertbare Sprache in der Aufnahme")
    saved = ENROLL.save(name, emb, seconds)
    print(f"[ENROLL] Stimme gespeichert: {saved} ({seconds:.0f}s)")
    return {"name": saved, "seconds": round(seconds, 1)}


@app.delete("/enroll/{name}", dependencies=[Depends(require_key)])
def delete_enrollment(name: str):
    return {"deleted": ENROLL.delete(name)}


# -- LLM-Proxy zu Ollama -----------------------------------------------------

def _ollama(path: str) -> str:
    return CFG["ollama_url"].rstrip("/") + path


@app.get("/llm/models", dependencies=[Depends(require_key)])
def llm_models():
    try:
        r = requests.get(_ollama("/api/tags"), timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama nicht erreichbar: {e}")


@app.post("/llm/chat", dependencies=[Depends(require_key)])
async def llm_chat(request: Request):
    """Reicht den JSON-Body 1:1 an Ollama /api/chat weiter (Streaming-fähig)."""
    body = await request.body()
    try:
        payload = json.loads(body or b"{}")
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiges JSON")
    stream = bool(payload.get("stream", False))
    try:
        r = requests.post(_ollama("/api/chat"), json=payload, stream=stream, timeout=600)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama nicht erreichbar: {e}")
    if r.status_code != 200:
        return JSONResponse(status_code=r.status_code, content={"error": r.text[:500]})
    if not stream:
        return JSONResponse(content=r.json())

    def gen():
        try:
            for line in r.iter_lines():
                if line:
                    yield line + b"\n"
        finally:
            r.close()

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(CFG.get("port", 8000))
    host = CFG.get("host", "0.0.0.0")
    if CFG.get("tls", True):
        cert_file, key_file, ca_cert_file, ip = ensure_tls_certs()
        print(f"\n[OK] Asklaion Praxisserver v{VERSION} laeuft auf: https://{ip}:{port}")
        print(f"[INFO] CA-Zertifikat (einmalig auf jeden Client-PC kopieren): {ca_cert_file}")
        print(f"[INFO] Modell: {ASR.model_name} auf {ASR.device} | Sprechertrennung: "
              f"{'an' if DIAR else 'aus'} | Ollama: {CFG['ollama_url']}\n")
        uvicorn.run(app, host=host, port=port, ssl_certfile=cert_file, ssl_keyfile=key_file,
                    log_level="warning")
    else:
        print(f"\n[OK] Asklaion Praxisserver v{VERSION} laeuft auf: http://{host}:{port} (ohne TLS!)\n")
        uvicorn.run(app, host=host, port=port, log_level="warning")
