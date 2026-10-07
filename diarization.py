"""
diarization.py – Sprechertrennung (Diarisierung) und Sprecher-Anlernen
auf Basis von sherpa-onnx (läuft auf der CPU, kein PyTorch, kein HF-Token).

Ablauf im Server:
  * Für jeden hochgeladenen Audio-Chunk wird im Hintergrund (CPU) die
    Sprechersegmentierung (pyannote-segmentation-3.0) ausgeführt und pro
    Sprechabschnitt ein Stimm-Embedding (WeSpeaker ResNet34) berechnet.
  * Beim Abschluss der Sitzung werden alle Embeddings global geclustert.
    Das dauert nur Millisekunden – die Wartezeit am Ende bleibt minimal.
  * Angelernte Stimmen (z. B. die des Behandlers) werden per Cosinus-Ähnlichkeit
    erkannt und mit ihrem Namen (z. B. "ARZT") beschriftet.

Modelle werden beim ersten Start automatisch nach ./models/ geladen
(GitHub-Releases von k2-fsa/sherpa-onnx, zusammen ca. 33 MB).

Benötigt: pip install sherpa-onnx numpy requests
"""

import json
import os
import tarfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np

try:
    import sherpa_onnx
    HAS_SHERPA = True
except ImportError:  # pragma: no cover
    HAS_SHERPA = False

SAMPLE_RATE = 16000

_RELEASE_BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SEGMENTATION_TARBALL = "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
SEGMENTATION_DIR = "sherpa-onnx-pyannote-segmentation-3-0"
EMBEDDING_MODEL = "wespeaker_en_voxceleb_resnet34_LM.onnx"

SEGMENTATION_URL = f"{_RELEASE_BASE}/speaker-segmentation-models/{SEGMENTATION_TARBALL}"
EMBEDDING_URL = f"{_RELEASE_BASE}/speaker-recongition-models/{EMBEDDING_MODEL}"


# ---------------------------------------------------------------------------
# Modell-Download
# ---------------------------------------------------------------------------

def _download(url: str, dest: Path):
    import requests
    print(f"[DIAR] Lade Modell: {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r[DIAR]   {done / 1e6:6.1f} / {total / 1e6:6.1f} MB", end="")
    print()
    tmp.replace(dest)


def ensure_models(models_dir: str) -> tuple:
    """Stellt sicher, dass Segmentierungs- und Embedding-Modell vorhanden sind."""
    d = Path(models_dir)
    d.mkdir(parents=True, exist_ok=True)
    seg_model = d / SEGMENTATION_DIR / "model.onnx"
    emb_model = d / EMBEDDING_MODEL
    if not seg_model.exists():
        tarball = d / SEGMENTATION_TARBALL
        _download(SEGMENTATION_URL, tarball)
        with tarfile.open(tarball, "r:bz2") as tf:
            tf.extractall(d)
        tarball.unlink(missing_ok=True)
    if not emb_model.exists():
        _download(EMBEDDING_URL, emb_model)
    return str(seg_model), str(emb_model)


# ---------------------------------------------------------------------------
# Datenstrukturen
# ---------------------------------------------------------------------------

@dataclass
class Turn:
    start: float                  # absolute Sekunden seit Aufnahmestart
    end: float
    embedding: Optional[np.ndarray] = None
    cluster: int = -1
    label: str = ""


@dataclass
class DiarizationResult:
    turns: List[Turn] = field(default_factory=list)
    speakers: List[str] = field(default_factory=list)   # Labels in Reihenfolge des ersten Auftretens
    matched: dict = field(default_factory=dict)         # label -> angelernter Name


def _normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def _agglomerative(X: np.ndarray, distance_threshold: float, n_clusters: int = -1) -> list:
    """
    Average-Linkage-Clustering auf Cosinus-Distanz (1 - Ähnlichkeit).
    distance_threshold: zwei Sprecher gelten als verschieden, wenn ihre mittlere
    Distanz größer ist (0.3 = Ähnlichkeit < 0.7). n_clusters > 0 erzwingt die Anzahl.
    """
    n = len(X)
    if n == 0:
        return []
    if n == 1:
        return [0]
    from scipy.cluster.hierarchy import fcluster, linkage
    Z = linkage(X, method="average", metric="cosine")
    if n_clusters > 0:
        labels = fcluster(Z, t=max(1, min(n_clusters, n)), criterion="maxclust")
    else:
        labels = fcluster(Z, t=float(distance_threshold), criterion="distance")
    # Labels nach erstem Auftreten neu nummerieren (0, 1, 2, ...)
    remap, out = {}, []
    for lab in labels:
        if lab not in remap:
            remap[lab] = len(remap)
        out.append(remap[lab])
    return out


# ---------------------------------------------------------------------------
# Sprecher-Anlernen (Enrollment)
# ---------------------------------------------------------------------------

class EnrollmentStore:
    """Speichert Stimm-Embeddings angelernter Personen als .npy unter ./enrollments/"""

    def __init__(self, directory: str):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _safe(self, name: str) -> str:
        return "".join(c for c in name.strip() if c.isalnum() or c in "-_ ").strip() or "unbekannt"

    def save(self, name: str, embedding: np.ndarray, seconds: float):
        name = self._safe(name)
        with self._lock:
            np.save(self.dir / f"{name}.npy", _normalize(embedding.astype(np.float32)))
            meta = self.dir / f"{name}.json"
            meta.write_text(json.dumps({
                "name": name, "seconds": round(seconds, 1),
                "created": time.strftime("%Y-%m-%d %H:%M:%S")
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        return name

    def delete(self, name: str) -> bool:
        name = self._safe(name)
        ok = False
        with self._lock:
            for p in (self.dir / f"{name}.npy", self.dir / f"{name}.json"):
                if p.exists():
                    p.unlink()
                    ok = True
        return ok

    def list(self) -> list:
        out = []
        for p in sorted(self.dir.glob("*.json")):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                out.append({"name": p.stem})
        return out

    def load_all(self) -> dict:
        embs = {}
        for p in self.dir.glob("*.npy"):
            try:
                embs[p.stem] = _normalize(np.load(p).astype(np.float32))
            except Exception as e:
                print(f"[DIAR] Enrollment {p} unlesbar: {e}")
        return embs


# ---------------------------------------------------------------------------
# Diarizer
# ---------------------------------------------------------------------------

class Diarizer:
    """
    Kapselt sherpa-onnx. Alle Aufrufe sind über einen Lock serialisiert
    (die zugrunde liegenden ONNX-Sessions sind nicht thread-sicher).
    """

    MIN_EMBED_SECONDS = 0.4     # kürzere Abschnitte erben das Label des Nachbarn
    MAX_EMBED_SECONDS = 20.0    # längere Abschnitte werden für das Embedding gekappt

    def __init__(self, models_dir: str, threads: int = 4, cluster_threshold: float = 0.3,
                 provider: str = "cpu"):
        if not HAS_SHERPA:
            raise RuntimeError("sherpa-onnx ist nicht installiert (pip install sherpa-onnx)")
        seg_model, emb_model = ensure_models(models_dir)
        self.threads = max(1, int(threads))
        self.cluster_threshold = float(cluster_threshold)   # Cosinus-Distanz, siehe _agglomerative
        self._lock = threading.Lock()

        self._seg_config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=seg_model),
                num_threads=self.threads, provider=provider,
            ),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=emb_model, num_threads=self.threads, provider=provider),
            # Lokales Clustering innerhalb eines Chunks liefert nur die Sprechabschnitte;
            # die globale Sprecherzuordnung erfolgt in cluster() über alle Chunks.
            clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=0.5),
            min_duration_on=0.3,
            min_duration_off=0.5,
        )
        if not self._seg_config.validate():
            raise RuntimeError("sherpa-onnx Diarisierungs-Konfiguration ungültig (Modelle fehlen?)")
        self._sd = sherpa_onnx.OfflineSpeakerDiarization(self._seg_config)
        self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(
            sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=emb_model, num_threads=self.threads,
                                                        provider=provider))
        self.dim = self._extractor.dim
        print(f"[DIAR] Sprechertrennung bereit (CPU, {self.threads} Threads, Embedding-Dim {self.dim})")

    # -- Embeddings -----------------------------------------------------------

    def _embed_locked(self, audio: np.ndarray) -> Optional[np.ndarray]:
        if len(audio) < int(self.MIN_EMBED_SECONDS * SAMPLE_RATE):
            return None
        audio = audio[: int(self.MAX_EMBED_SECONDS * SAMPLE_RATE)]
        s = self._extractor.create_stream()
        s.accept_waveform(SAMPLE_RATE, audio)
        s.input_finished()
        if not self._extractor.is_ready(s):
            return None
        return _normalize(np.asarray(self._extractor.compute(s), dtype=np.float32))

    def embed(self, audio: np.ndarray) -> Optional[np.ndarray]:
        with self._lock:
            return self._embed_locked(audio)

    def enrollment_embedding(self, audio: np.ndarray, window: float = 3.0, hop: float = 1.5):
        """
        Mittelt Embeddings über gleitende Fenster einer Anlern-Aufnahme.
        Stille Fenster (RMS sehr klein) werden übersprungen.
        """
        audio = np.asarray(audio, dtype=np.float32)
        win, step = int(window * SAMPLE_RATE), int(hop * SAMPLE_RATE)
        embs = []
        with self._lock:
            for start in range(0, max(1, len(audio) - win + 1), step):
                seg = audio[start:start + win]
                if len(seg) < int(1.0 * SAMPLE_RATE):
                    continue
                if float(np.sqrt(np.mean(seg ** 2))) < 0.004:
                    continue
                e = self._embed_locked(seg)
                if e is not None:
                    embs.append(e)
            if not embs:
                e = self._embed_locked(audio)
                if e is not None:
                    embs.append(e)
        if not embs:
            return None
        return _normalize(np.mean(np.stack(embs), axis=0))

    # -- Segmentierung eines Chunks -------------------------------------------

    def segment_chunk(self, audio: np.ndarray, offset: float) -> List[Turn]:
        """
        Zerlegt einen Audio-Chunk (float32, 16 kHz) in Sprechabschnitte und
        berechnet je Abschnitt ein Embedding. offset = Startzeit des Chunks
        in Sekunden seit Aufnahmestart.
        """
        audio = np.ascontiguousarray(np.asarray(audio, dtype=np.float32))
        if len(audio) < int(0.5 * SAMPLE_RATE):
            return []
        turns: List[Turn] = []
        with self._lock:
            try:
                result = self._sd.process(audio).sort_by_start_time()
            except Exception as e:
                print(f"[DIAR] Segmentierung fehlgeschlagen: {e}")
                return []
            for r in result:
                s, e = float(r.start), float(r.end)
                seg = audio[int(s * SAMPLE_RATE): int(e * SAMPLE_RATE)]
                emb = self._embed_locked(seg)
                turns.append(Turn(start=offset + s, end=offset + e, embedding=emb))
        return turns

    # -- Globales Clustering ---------------------------------------------------

    def cluster(self, turns: List[Turn], expected_speakers: Optional[int] = None,
                enrolled: Optional[dict] = None, match_threshold: float = 0.45,
                unknown_label_scheme: str = "auto") -> DiarizationResult:
        """
        Clustert alle Turns einer Sitzung, beschriftet die Sprecher und
        erkennt angelernte Stimmen.

        unknown_label_scheme:
          "auto"  -> gibt es genau einen angelernten Treffer und genau einen
                     unbekannten Sprecher, heißt dieser "PATIENT"; sonst
                     "SPRECHER 1", "SPRECHER 2", ...
        """
        res = DiarizationResult()
        turns = sorted(turns, key=lambda t: t.start)
        if not turns:
            return res

        with_emb = [t for t in turns if t.embedding is not None]
        if not with_emb:
            for t in turns:
                t.cluster, t.label = 0, "SPRECHER 1"
            res.turns, res.speakers = turns, ["SPRECHER 1"]
            return res

        X = np.stack([t.embedding for t in with_emb]).astype(np.float32)
        n_clusters = int(expected_speakers) if expected_speakers and expected_speakers > 0 else -1
        if n_clusters > len(with_emb):
            n_clusters = len(with_emb)
        labels = _agglomerative(X, self.cluster_threshold, n_clusters)

        for t, lab in zip(with_emb, labels):
            t.cluster = int(lab)

        # Mini-Cluster (Fehlzuordnungen) in den ähnlichsten großen Cluster mergen
        labels = self._merge_tiny_clusters(with_emb, min_share=0.04, min_seconds=6.0,
                                           keep_min=n_clusters if n_clusters > 0 else 1)

        # Turns ohne Embedding erben das Label des zeitlich nächsten Turns
        for t in turns:
            if t.embedding is None:
                nearest = min(with_emb, key=lambda o: min(abs(o.start - t.start), abs(o.end - t.end)))
                t.cluster = nearest.cluster

        # Zentroide je Cluster
        centroids = {}
        for c in sorted(set(t.cluster for t in with_emb)):
            centroids[c] = _normalize(np.mean(np.stack([t.embedding for t in with_emb if t.cluster == c]), axis=0))

        # Angelernte Stimmen zuordnen (jeder Name maximal einmal, beste Ähnlichkeit gewinnt)
        assigned = {}
        if enrolled:
            pairs = []
            for c, cen in centroids.items():
                for name, emb in enrolled.items():
                    pairs.append((float(np.dot(cen, emb)), c, name))
            pairs.sort(reverse=True)
            used_names = set()
            for sim, c, name in pairs:
                if sim < match_threshold or c in assigned or name in used_names:
                    continue
                assigned[c] = name.upper()
                used_names.add(name)
                res.matched[name.upper()] = round(sim, 3)

        # Unbekannte Sprecher beschriften (Reihenfolge des ersten Auftretens)
        order = []
        for t in turns:
            if t.cluster not in order:
                order.append(t.cluster)
        unknown = [c for c in order if c not in assigned]
        label_map = dict(assigned)
        if unknown_label_scheme == "auto" and len(assigned) == 1 and len(unknown) == 1:
            label_map[unknown[0]] = "PATIENT"
        else:
            for i, c in enumerate(unknown, start=1):
                label_map[c] = f"SPRECHER {i}"

        for t in turns:
            t.label = label_map.get(t.cluster, "SPRECHER ?")
        res.turns = turns
        res.speakers = [label_map[c] for c in order]
        return res

    @staticmethod
    def _merge_tiny_clusters(turns: List[Turn], min_share: float, min_seconds: float, keep_min: int):
        def durations():
            d = {}
            for t in turns:
                d[t.cluster] = d.get(t.cluster, 0.0) + (t.end - t.start)
            return d
        for _ in range(10):
            d = durations()
            if len(d) <= max(1, keep_min):
                break
            total = sum(d.values()) or 1.0
            tiny = [c for c, s in d.items() if s < min_seconds and s / total < min_share]
            if not tiny:
                break
            c = min(tiny, key=lambda k: d[k])
            big = [k for k in d if k != c]
            cen_c = _normalize(np.mean(np.stack([t.embedding for t in turns if t.cluster == c]), axis=0))
            best = max(big, key=lambda k: float(np.dot(
                cen_c, _normalize(np.mean(np.stack([t.embedding for t in turns if t.cluster == k]), axis=0)))))
            for t in turns:
                if t.cluster == c:
                    t.cluster = best
        return [t.cluster for t in turns]


# ---------------------------------------------------------------------------
# Wörter -> Sprecher zuordnen
# ---------------------------------------------------------------------------

def assign_words(words: list, turns: List[Turn], max_gap: float = 1.0) -> list:
    """
    Ordnet jedem Wort (dict mit start/end) das Sprecherlabel des Turns zu,
    der die Wortmitte enthält; sonst des nächstgelegenen Turns (bis max_gap s);
    sonst des vorherigen Wortes.
    Gibt eine Liste von Sprecherblöcken zurück: [{"speaker", "start", "end", "text"}]
    """
    if not words:
        return []
    turns = sorted(turns, key=lambda t: t.start)
    blocks = []
    prev_label = turns[0].label if turns else "SPRECHER 1"
    for w in words:
        mid = (w["start"] + w["end"]) / 2.0
        label = None
        best_gap = None
        for t in turns:
            if t.start <= mid <= t.end:
                label = t.label
                break
            gap = min(abs(t.start - mid), abs(t.end - mid))
            if best_gap is None or gap < best_gap:
                best_gap, best_label = gap, t.label
        if label is None:
            label = best_label if (best_gap is not None and best_gap <= max_gap) else prev_label
        prev_label = label
        if blocks and blocks[-1]["speaker"] == label:
            blocks[-1]["text"] += " " + w["word"]
            blocks[-1]["end"] = w["end"]
        else:
            blocks.append({"speaker": label, "start": w["start"], "end": w["end"], "text": w["word"]})
    for b in blocks:
        b["text"] = b["text"].strip()
    return blocks


def blocks_to_text(blocks: list) -> str:
    return "\n".join(f"{b['speaker']}: {b['text']}" for b in blocks if b["text"])
