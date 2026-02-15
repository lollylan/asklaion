# Askl-AI-on | Transkription via Whisper

Dieses Modul ermöglicht die Echtzeit-Transkription von Patientengesprächen direkt in der Praxis. Durch den Einsatz von `faster-whisper` erreichen wir eine extrem hohe Genauigkeit bei gleichzeitig geringer Latenz – vollkommen lokal.

---

## 📋 Funktionsweise

Das System besteht aus zwei Komponenten:

1. **Server (`ServerFasterWhisper.py`):** Läuft auf einem leistungsstarken Rechner (mit NVIDIA GPU) und verarbeitet die Audio-Daten.
2. **Client (`client_par_Normbefunde.py`):** Läuft auf dem PC im Sprechzimmer. Er nimmt den Ton auf, sendet ihn an den Server und zeigt den Text sowie vorgefertigte **Normalbefunde** an.

---

## 🛠️ Voraussetzungen

### Hardware-Empfehlung

* **Server:** PC mit einer NVIDIA-Grafikkarte (mind. 8GB VRAM für das "large"-Modell empfohlen).
* **Client:** Beliebiger Praxis-PC mit Mikrofon (Headset oder Tischmikrofon).

### Software-Basis

Auf beiden Systemen muss **Python (Version 3.10 oder neuer)** installiert sein. Sie finden den Download unter [python.org](https://www.python.org/downloads/).

---

## 💾 Installation der Abhängigkeiten

Öffnen Sie jeweils ein Terminal (Eingabeaufforderung/PowerShell) und installieren Sie die benötigten Bibliotheken.

### Auf dem Server

```bash
pip install flask numpy faster-whisper waitress

```

### Auf dem Client

```bash
pip install tkinter sounddevice numpy requests pyperclip

```

*(Hinweis: `tkinter` ist unter Windows meist vorinstalliert. Unter Linux nutzen Sie `sudo apt-get install python3-tk`).*

---

## ⚙️ Konfiguration

Damit Client und Server miteinander kommunizieren können, müssen Sie die IP-Adresse anpassen:

1. **Server-IP ermitteln:** Öffnen Sie am Server die Eingabeaufforderung, geben Sie `ipconfig` ein und notieren Sie die IPv4-Adresse (z. B. `192.168.10.177`).
2. **Client-Script anpassen:**
* Öffnen Sie `client_par_0_0_5_Normbefunde.py` in einem Texteditor.
* Suchen Sie die Zeile:
`SERVER_URL = "http://192.168.10.177:6000/transcribe"`
* Ersetzen Sie die IP durch die Adresse Ihres Servers.
* **Wichtig:** Stellen Sie sicher, dass der Port (im Script `6000`) mit dem Port im Server-Script übereinstimmt (im bereitgestellten Server-Script ist `5000` voreingestellt – passen Sie dies an, damit beide identisch sind).



---

## 🚀 Nutzung

### 1. Server starten

Starten Sie das Server-Script auf dem Rechner mit der Grafikkarte:

```bash
python ServerFasterWhisper.py

```

Der Server lädt beim ersten Start das "large"-Whisper-Modell herunter (ca. 3 GB) und wartet dann auf Anfragen.

### 2. Client starten

Starten Sie das Client-Script am Behandlungsplatz:

```bash
python client_par_0_0_5_Normbefunde.py

```

**Features im Client:**

* **Start with Clipboard:** Übernimmt Patientendaten direkt aus der Zwischenablage Ihres PVS.
* **Normalbefunde:** Klicken Sie auf "Lunge", "Abdomen" etc., um vordefinierte, blande Befundtexte sofort in das Dokument einzufügen.
* **Auto-Save:** Nach dem Stoppen wird das Transkript im Ordner `/Transkripte` gespeichert und automatisch in die Zwischenablage kopiert. Dieses Speichern dient dem Schutz von Verlust des Transkriptes, falls man versehentlich etwas anderes kopiert und damit die Zwischenablage überschreibt. Löschen Sie den Inhalt des Ordners Transkripte regelmäßig, am besten täglich, z.B. durch eine zeitlich getriggerte Automatisierung.

---

## 🛡️ Datenschutzhinweis

Da der Client die Audiodaten über das lokale Netzwerk (HTTP) an den Server sendet, sollte dieser Workflow **nur in einem gesicherten Praxis-Netzwerk** betrieben werden. Die Daten verlassen zu keinem Zeitpunkt das Gebäude.