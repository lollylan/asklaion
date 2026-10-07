"""
asr_engine.py – Whisper-Transkription (faster-whisper / CTranslate2)

Verbesserungen gegenüber v1.0:
  * BatchedInferencePipeline: Chunks werden in Batches durch das Modell
    geschoben – auf einer RTX 4090 ca. 10x schneller als zuvor.
  * Silero-VAD: Stille wird vor der Transkription entfernt. Das ist der
    wichtigste Hebel gegen Halluzinationen ("Untertitel der Amara.org-Community").
  * Hotwords: Praxisvokabular + Kontextbegriffe der Sitzung (z. B. Medikationsplan)
    werden dem Modell als Hinweis mitgegeben.
  * Wort-Zeitstempel für die Sprecherzuordnung.
  * Halluzinations-Filter (bekannte Phrasen, Wiederholungsschleifen, unsichere Segmente).

Standardmodell: large-v3-turbo (deutlich schneller, in unseren Tests bei
Medikamentennamen sogar treffsicherer als large-v3). Für maximale Genauigkeit
kann in server_config.json "large-v3" gesetzt werden.
"""

import importlib.util
import os
import re
import sys
import threading
import time
from typing import List, Optional

import numpy as np


def _fix_windows_cuda_dlls():
    """cuBLAS/cuDNN aus den pip-Paketen (nvidia-*-cu12) auffindbar machen."""
    if os.name != "nt" or getattr(sys, "frozen", False):
        return
    for pkg in ("nvidia.cublas", "nvidia.cudnn"):
        spec = importlib.util.find_spec(pkg)
        if spec and spec.submodule_search_locations:
            bin_path = os.path.abspath(os.path.join(spec.submodule_search_locations[0], "bin"))
            if os.path.exists(bin_path):
                os.add_dll_directory(bin_path)
                os.environ["PATH"] = bin_path + os.pathsep + os.environ["PATH"]


_fix_windows_cuda_dlls()

from faster_whisper import BatchedInferencePipeline, WhisperModel  # noqa: E402

SAMPLE_RATE = 16000

# Typische Whisper-Halluzinationen bei Stille / Rauschen (deutsch)
HALLUCINATION_PATTERNS = [
    r"untertitel", r"amara\.org", r"im auftrag des zdf", r"\bzdf\b", r"\bswr\b", r"\bwdr\b",
    r"\bndr\b", r"vielen dank f[üu]rs? (zuschauen|zuhören)", r"danke f[üu]rs? (zuschauen|zuhören)",
    r"bis zum n[äa]chsten (mal|video)", r"copyright", r"www\.", r"\.com\b", r"\.de\b",
    r"abonnier", r"like[nd]? und", r"kanal", r"untertitelung",
]
_HALLU_RE = re.compile("|".join(HALLUCINATION_PATTERNS), re.IGNORECASE)


def _looks_like_hallucination(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if _HALLU_RE.search(t):
        return True
    # Wiederholungsschleife: gleiches Wort/Phrase sehr oft hintereinander
    words = t.lower().split()
    if len(words) >= 8:
        for n in (1, 2, 3):
            grams = [" ".join(words[i:i + n]) for i in range(0, len(words) - n + 1)]
            if grams:
                most = max(set(grams), key=grams.count)
                if grams.count(most) >= max(4, len(grams) // 2):
                    return True
    return False


def _detect_device(device: str, compute_type: str):
    import ctranslate2
    if device == "auto":
        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"
    return device, compute_type


class ASREngine:
    def __init__(self, model: str = "large-v3-turbo", device: str = "auto", compute_type: str = "auto",
                 batch_size: int = 16, beam_size: int = 5, language: str = "de",
                 cpu_threads: int = 0, vad_min_silence_ms: int = 400):
        self.device, self.compute_type = _detect_device(device, compute_type)
        self.model_name = model
        self.batch_size = int(batch_size)
        self.beam_size = int(beam_size)
        self.language = language
        self.vad_parameters = {
            "min_silence_duration_ms": int(vad_min_silence_ms),
            "speech_pad_ms": 300,
            "threshold": 0.5,
        }
        self._lock = threading.Lock()   # GPU-Zugriff serialisieren
        t0 = time.time()
        print(f"[ASR] Lade Whisper '{model}' auf {self.device} ({self.compute_type}) ...")
        self.model = WhisperModel(model, device=self.device, compute_type=self.compute_type,
                                  cpu_threads=cpu_threads)
        self.pipeline = BatchedInferencePipeline(model=self.model)
        print(f"[ASR] Modell geladen in {time.time() - t0:.1f}s")

    # ------------------------------------------------------------------
    def warmup(self):
        """Encoder und Decoder einmal durchlaufen lassen (cuDNN-Autotuning, Kernel-Caches),
        damit der erste echte Chunk nicht mehrere Sekunden braucht."""
        t0 = time.time()
        try:
            rng = np.random.default_rng(0)
            noise = (rng.normal(0, 0.05, SAMPLE_RATE * 8)).astype(np.float32)
            with self._lock:
                segs, _ = self.pipeline.transcribe(noise, language=self.language, beam_size=self.beam_size,
                                                   batch_size=self.batch_size, vad_filter=False,
                                                   word_timestamps=True, condition_on_previous_text=False)
                list(segs)
            self.transcribe(np.zeros(SAMPLE_RATE * 2, dtype=np.float32))
            print(f"[ASR] Warmup fertig ({time.time() - t0:.1f}s)")
        except Exception as e:  # pragma: no cover
            print(f"[ASR] Warmup-Fehler (ignoriert): {e}")

    # ------------------------------------------------------------------
    def transcribe(self, audio: np.ndarray, hotwords: Optional[str] = None,
                   word_timestamps: bool = True) -> dict:
        """
        audio: float32 mono 16 kHz.
        Rückgabe: {"text": str, "words": [{"word","start","end","prob"}], "segments": [...],
                   "duration": s, "elapsed": s}
        """
        audio = np.ascontiguousarray(np.asarray(audio, dtype=np.float32))
        duration = len(audio) / SAMPLE_RATE
        t0 = time.time()
        words: List[dict] = []
        seg_out: List[dict] = []
        if duration < 0.3:
            return {"text": "", "words": [], "segments": [], "duration": duration, "elapsed": 0.0}

        with self._lock:
            segments, _info = self.pipeline.transcribe(
                audio,
                language=self.language,
                beam_size=self.beam_size,
                batch_size=self.batch_size,
                vad_filter=True,
                vad_parameters=self.vad_parameters,
                word_timestamps=word_timestamps,
                condition_on_previous_text=False,
                hotwords=hotwords or None,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.6,
                compression_ratio_threshold=2.4,
            )
            segments = list(segments)   # Generator hier ausführen (innerhalb des Locks)

        for s in segments:
            text = (s.text or "").strip()
            if not text:
                continue
            nsp = getattr(s, "no_speech_prob", None) or 0.0
            alp = getattr(s, "avg_logprob", None)
            if nsp > 0.85 and alp is not None and alp < -0.8:
                continue
            if _looks_like_hallucination(text):
                print(f"[ASR] Halluzination verworfen: {text[:80]!r}")
                continue
            seg_out.append({"start": float(s.start), "end": float(s.end), "text": text})
            if word_timestamps and s.words:
                for w in s.words:
                    wt = (w.word or "").strip()
                    if wt:
                        words.append({"word": wt, "start": float(w.start), "end": float(w.end),
                                      "prob": float(getattr(w, "probability", 0.0) or 0.0)})
            elif word_timestamps:
                # Fallback ohne Wortzeiten: ganzes Segment als ein "Wort"
                words.append({"word": text, "start": float(s.start), "end": float(s.end), "prob": 0.0})

        text = " ".join(seg["text"] for seg in seg_out).strip()
        return {"text": text, "words": words, "segments": seg_out,
                "duration": duration, "elapsed": time.time() - t0}
