# Askl-AI-on | Ambient-Scribe v1.0: Vollautomatisierung

Dieses Modul bietet eine "One-Click"-Lösung für die medizinische Dokumentation. Es verknüpft die lokale Audioaufnahme, die KI-Transkription und die Zusammenfassung durch ein lokales Sprachmodell (LLM) zu einem nahtlosen Workflow — inklusive Arztbriefzusammenfassung, Patientenanalyse und interaktive Dokumentenbefragung.

---

## 📋 Funktionsweise

1. **Audioaufnahme:** Der Client nimmt das Gespräch am Behandlungsplatz auf.
2. **CPU-Optimierte Transkription:** Die Audiodaten werden an einen Server gesendet, der mit `faster-whisper` den Text extrahiert. In diesem Beispiel findet die Transkription auf der CPU statt, um in der GPU mehr Platz für ein größeres LLM zu haben. Das Script nutzt Whisper Medium.
3. **Alternative: GPU-Transkription mit NVIDIA-Grafikkarte:** Falls der Transkriptionsserver eine ausreichende Grafikleistung aufweist, kann man auch das deutlich schnellere und genauere Serverscript ausführen, das NVIDIA CUDA Toolkit (muss separat installiert werden) nutzt. Dieses nutzt Whisper Large-V3, das stärkste Whisper-Modell, um eine bestmögliche Transkriptionsqualität zu erreichen. Wenn mehrere Behandler gleichzeitig die KI-Transkription nutzen wollen, bitte das Script `server_GPU_Cuda_Parallel.py` nutzen, damit die Diktate nicht "vermischt" werden.
4. **LLM-Verarbeitung:** Der Text wird an **OpenWebUI** gesendet, wo ein spezialisiertes Modell die medizinische Zusammenfassung erstellt oder das Diktat verbessert.
5. **PVS-kompatible Ausgabe:** Das Skript bereinigt den Text von Markdown-Symbolen (wie `**` oder `##`) und konvertiert Zeilenumbrüche so, dass sie in gängigen PVS (z.B. PegaMed, Tomedo, Medistar) mit `Strg + V` korrekt eingefügt werden können. Der mitgelieferte `asklaion-v1` System-Prompt ist so gestaltet, dass das Ausgabeformat sich leicht in **PegaMed** einfügen lässt. Andere PVS-Systeme sind selbstverständlich ebenfalls nutzbar — der System-Prompt muss lediglich an das gewünschte Ausgabeformat angepasst werden.

---

## 🗂️ Tabs & Funktionen

Das Programm bietet sechs Tabs:

| Tab | Funktion | OpenWebUI-Modell |
|---|---|---|
| **Gespräch** | Ambient-Scribe: Arzt-Patienten-Gespräch aufnehmen und zusammenfassen | `asklaion-v1` |
| **Diktat** | Diktiertes Transkript durch LLM stilistisch überarbeiten | `diktiersklavev1` |
| **Arena** | Zwei LLM-Modelle gleichzeitig vergleichen | `asklaion-v1` / `diktiersklavev1` |
| **Arztbrief** | PDF-Arztbriefe hochladen und zusammenfassen lassen | `arztbriefzusammenfasser` |

### 🆕 Neue Funktionen (v1.0)

- **PVS-agnostisches Design:** Nicht mehr an PegaMed gebunden — das Ausgabeformat lässt sich durch Anpassung des System-Prompts in OpenWebUI an jedes PVS anpassen.
- **Automatische Transkript-Löschung (Datenschutz):** Transkripte im Ordner `Transkripte_Raw/` werden beim Programmstart automatisch gelöscht, wenn sie älter als die konfigurierte Anzahl Tage sind (Standard: 1 Tag, konfigurierbar über Einstellungen, 0 = deaktiviert).

---

## 🛠️ Voraussetzungen

### 1. Python-Installation

Beide Systeme (Server und Client) benötigen **Python 3.10+**.

### 2. Abhängigkeiten installieren

Führen Sie in Ihrem Terminal folgende Befehle aus:

**Auf dem Server (Transkription):**

```bash
pip install fastapi uvicorn faster-whisper
```

**Auf dem Client (Praxis-PC):**

```bash
pip install sounddevice numpy requests scipy pyperclip PyPDF2 windnd
```

| Paket | Zweck |
|---|---|
| `sounddevice` | Audioaufnahme |
| `numpy` | Audio-Datenverarbeitung |
| `requests` | HTTP-Kommunikation mit Server & OpenWebUI |
| `scipy` | WAV-Export |
| `pyperclip` | Kopieren in Zwischenablage |
| `PyPDF2` | PDF-Textextraktion (Arztbrief) |
| `windnd` | Drag-and-Drop Unterstützung (optional, nur Windows) |

> **Hinweis:** `tkinter` ist unter Windows standardmäßig mit Python enthalten und muss nicht separat installiert werden.

---

## ⚙️ Konfiguration

Die Konfiguration erfolgt über die integrierte **Einstellungs-Oberfläche** (⚙️ Button in der App) oder direkt in der Datei `config.json`, die beim ersten Start automatisch erzeugt wird.

### Konfigurationsoptionen

| Schlüssel | Beschreibung | Standard |
|---|---|---|
| `server_url` | URL des Whisper-Transkriptionsservers | `http://192.168.10.44:8000/transcribe` |
| `openwebui_url` | URL der OpenWebUI API | `http://192.168.10.44:3000/api/chat/completions` |
| `api_key` | API-Key aus OpenWebUI | — |
| `model_ambient` | Modell für Gesprächszusammenfassung | `asklaion-v1` |
| `model_diktat` | Modell für Diktat-Überarbeitung | `diktiersklavev1` |
| `model_arena_a` / `model_arena_b` | Arena-Vergleichsmodelle | `asklaion-v1` / `diktiersklavev1` |
| `model_arztbrief` | Modell für Arztbriefzusammenfassung | `arztbriefzusammenfasser` |
| `auto_delete_days` | Tage nach denen Transkripte gelöscht werden (0 = aus) | `1` |
| `input_device` | Mikrofon-Eingang (ID oder Name) | Systemstandard |
| `loopback_device` | System-Audio Eingang | — |
| `chunk_duration` | Aufnahme-Chunk-Dauer in Sekunden | `30` |
| `mix_system_audio` | System-Audio mitmischen | `false` |

### OpenWebUI-Vorbereitung

1. **Modelle erstellen:** Erstellen Sie in Ihrer OpenWebUI-Instanz die benötigten Modelle (siehe Tabelle oben).
2. **System-Prompts:** Hinterlegen Sie Ihren gewünschten System-Prompt direkt in den Einstellungen der jeweiligen Modelle (Beispiele siehe Prompt-Dateien im Repository). Der `asklaion-v1` Prompt ist standardmäßig für PegaMed optimiert. Für andere PVS passen Sie den Prompt an das gewünschte Ausgabeformat an.
3. **API-Key:** Generieren Sie in Ihrem OpenWebUI-Profil einen API-Key.

### Server-Setup

Starten Sie das Transkriptions-Skript auf dem Server:

```bash
# CPU-Transkription (kein CUDA nötig)
python server_CPU.py

# GPU-Transkription (NVIDIA CUDA erforderlich)
python server_GPU_CUDA.py

# GPU mit Parallelverarbeitung für mehrere Behandler
python server_GPU_CUDA_Parallel.py
```

---

## 🚀 Nutzung im Praxisalltag

1. **Server starten:** Transkriptionsserver wie oben beschrieben starten.
2. **Client starten:** `python Komplettscript_1_0.py` auf dem Praxis-PC ausführen.
3. **Dokumentieren:**
   * **Gespräch-Tab:** Aufnahme starten → Gespräch führen → Stop & LLM-Verarbeitung.
   * **Diktat-Tab:** Diktierte Notizen aufnehmen und durch LLM verbessern lassen.
   * **Arena-Tab:** Zwei Modelle gleichzeitig vergleichen.
   * **Arztbrief-Tab:** PDF hochladen → Zusammenfassung generieren.
4. **Einfügen:** Sobald "Fertig!" angezeigt wird, im PVS mit **Strg + V** einfügen.

---

## 🔒 Datenschutz

* **Automatische Löschung:** Transkripte im Ordner `Transkripte_Raw/` werden beim Start automatisch gelöscht, wenn sie älter als die konfigurierte Anzahl Tage sind (Standard: 1 Tag).
* **Konfiguration:** Über `auto_delete_days` in den Einstellungen steuerbar. Setzen Sie den Wert auf `0`, um die automatische Löschung zu deaktivieren.
* **Lokale Verarbeitung:** Alle Daten werden lokal verarbeitet — kein Cloud-Dienst nötig.

---

## 🩺 Spezielle Features für Mediziner

* **PVS-kompatible Formatierung:** Das Skript entfernt automatisch Fettdruck-Sterne (`**`) und Rauten (`##`), die in PVS-Systemen oft kryptisch dargestellt werden. Die Zeilenumbrüche werden Windows-kompatibel (`\r\n`) formatiert.
* **Flexibles Ausgabeformat:** Der System-Prompt in OpenWebUI bestimmt die Ausgabestruktur. Der mitgelieferte `asklaion-v1` Prompt ist für PegaMed optimiert — für andere PVS einfach den Prompt anpassen.
* **Normbefunde:** Häufige Befunde wie "Herz: rein, regelmäßig" können zeitsparend per Knopfdruck ergänzt werden.
* **Drag-and-Drop:** PDF-Arztbriefe können direkt auf die Anwendung gezogen werden.

---

## ⚖️ Regulatorischer Hinweis

Die Funktionen **Patientenanalyse** und **Dokumentenbefragung** wurden in dieser Version deaktiviert. Obwohl technisch problemlos machbar, könnten diese Funktionen dazu führen, dass die Software regulatorisch als **Medizinprodukt** (Software as a Medical Device, SaMD) eingestuft wird. Um rechtliche Risiken für dieses Open-Source-Projekt zu vermeiden, konzentriert sich der Funktionsumfang auf reine Dokumentations- und Transkriptionshilfen sowie einfache Zusammenfassungen.

> **Entscheidungsgrundlage:** MDR (EU) 2017/745

---

## ⚠️ Disclaimer / Haftungsausschluss

> **Transkription & Dokumentation:** Transkripte und KI-generierte Dokumentationen sind vom behandelnden Arzt/Ärztin auf Vollständigkeit und Richtigkeit zu überprüfen. Dieses Programm dient lediglich als Dokumentationshilfe und darf die ärztliche Behandlung nicht beeinflussen.

> **Arztbrief-Zusammenfassung:** Dient ausschließlich der schnelleren Orientierung und ersetzt nicht das sorgfältige Studium des Originaldokuments.

> **Nutzung auf eigene Gefahr – es wird keine Haftung übernommen.**
