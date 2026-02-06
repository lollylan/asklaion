# Askl-AI-on | Ambient-Scribe: Vollautomatisierung (PegaMed-Edition)

Dieses Modul bietet eine "One-Click"-Lösung für die Dokumentation. Es verknüpft die lokale Audioaufnahme, die KI-Transkription und die Zusammenfassung durch ein lokales Sprachmodell (LLM) zu einem nahtlosen Workflow.

---

## 📋 Funktionsweise

1. **Audioaufnahme:** Der Client nimmt das Gespräch am Behandlungsplatz auf.
2. **CPU-Optimierte Transkription:** Die Audiodaten werden an einen Server gesendet, der mit `faster-whisper` den Text extrahiert. In diesem Beispiel findet die Transkription auf der CPU statt, um in der GPU mehr Platz für ein größeres LLM zu haben. Das Script nutzt Whisper Medium.
3. **Alternative: GPU-Transkription mit NVIDIA-Grafikkarte:** Falls der Transkriptionsserver eine ausreichende Grafikleistung aufweißt, kann man auch das deutlich schnellere und genauere Serverscript ausführen, das NVIDIA CUDA Toolkit (muss seperat installiert werden) nutzt. Dieses Nutzt Whisper Large-V3, das stärkste Whisper-Modell, um eine bestmögliche Transkriptionsqualität zu erreichen.
4. **LLM-Verarbeitung:** Der Text wird an **OpenWebUI** gesendet, wo ein spezialisiertes Modell (`asklaion-v1`) die medizinische Zusammenfassung erstellt.
5. **PegaMed-Optimierung:** Das Skript bereinigt den Text von Markdown-Symbolen (wie `**` oder `##`) und konvertiert Zeilenumbrüche so, dass sie in PegaMed mit `Strg + V` korrekt eingefügt werden können.

---

## 🛠️ Voraussetzungen

### 1. Python-Installation

Beide Systeme (Server und Client) benötigen **Python 3.10+**.

### 2. Abhängigkeiten installieren

Führen Sie in Ihrem Terminal folgende Befehle aus:

**Auf dem Server:**

```bash
pip install fastapi uvicorn faster-whisper

```

**Auf dem Client (Praxis-PC):**

```bash
pip install sounddevice numpy requests scipy pyperclip

```

*(Hinweis: `tkinter` ist unter Windows standardmäßig enthalten.)*

---

## ⚙️ Konfiguration

Damit die Automatisierung funktioniert, müssen Sie die Dateien `server_Gemini_CPU.py` und `Komplettscript2.py` anpassen:

### A. Server-Setup (`server_Gemini_CPU.py`)

Dieses Skript läuft auf einem Server im Praxisnetzwerk. Es nutzt das Modell "medium" auf der CPU, was keine teure Grafikkarte erfordert.

* Standard-Port: `8000`.

### B. OpenWebUI-Vorbereitung

1. **Modell erstellen:** Erstellen Sie in Ihrer OpenWebUI-Instanz ein neues Modell mit dem Namen `asklaion-v1`.
2. **System-Prompt:** Hinterlegen Sie Ihren gewünschten medizinischen System-Prompt direkt in den Einstellungen dieses Modells in OpenWebUI.
3. **API-Key:** Generieren Sie in Ihrem OpenWebUI-Profil einen API-Key.

### C. Client-Setup (`Komplettscript2.py`)

Passen Sie die Variablen im Bereich `CONFIGURATION` an:

* `SERVER_URL`: Die IP Ihres Whisper-Servers (z. B. `http://192.168.10.177:8000/transcribe`).
* `OPENWEBUI_URL`: Die Adresse Ihrer OpenWebUI-Instanz.
* `OPENWEBUI_API_KEY`: Ihr persönlicher API-Key aus OpenWebUI.

---

## 🚀 Nutzung im Praxisalltag

1. **Server starten:** Führen Sie `python server_Gemini_CPU.py` auf Ihrem Server aus.
2. **Client starten:** Starten Sie `python Komplettscript2.py` auf Ihrem Praxis-PC.
3. **Dokumentieren:**
* Klicken Sie auf **Aufnahme Starten**.
* Nutzen Sie während des Gesprächs die Buttons für **Normbefunde** (z. B. "Lunge", "Abdomen"), um Standard-Untersuchungsergebnisse per Klick einzufügen.
* Klicken Sie auf **Stop & LLM-Verarbeitung**.


4. **Einfügen:** Sobald das Fenster "Fertig!" anzeigt, wechseln Sie in **PegaMed** in das entsprechende Feld und drücken Sie **Strg + V**.

---

## 🩺 Spezielle Features für Mediziner

* **PegaMed-Formatierung:** Das Skript entfernt automatisch Fettdruck-Sterne (`**`) und Rauten (`##`), die in PegaMed oft kryptisch dargestellt werden.
* **Windows-Compatibility:** Zeilenumbrüche werden in das Format `\r\n` gewandelt, damit sie in der Praxis-Software sauber untereinander stehen.
* **Normbefunde:** Häufige Befunde wie "Herz: rein, regelmäßig" können zeitsparend per Knopfdruck ergänzt werden, ohne sie diktieren zu müssen.