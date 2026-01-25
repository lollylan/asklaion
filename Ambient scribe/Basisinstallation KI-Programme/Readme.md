# Askl-AI-on | Ambient-Scribe: Basis-Setup

Bevor spezifische Funktionen wie die automatisierte Transkription oder die Generierung von Arztbriefen genutzt werden können, muss eine stabile Infrastruktur für lokale KI-Modelle geschaffen werden. Diese Anleitung führt Sie durch die Installation der drei Grundpfeiler: **Docker**, **Ollama** und **OpenWebUI**.

> **Hinweis:** Dies ist die zwingende Voraussetzung, um KI-Modelle ohne Cloud-Anbindung direkt auf Ihrer Praxis-Hardware zu betreiben.

---

## 🏗️ 1. Docker: Das Fundament

Docker ist eine Plattform, die Anwendungen in isolierten "Containern" ausführt. Dies garantiert, dass die KI-Software unabhängig von Ihrem Betriebssystem stabil läuft.

* **Offizielle Anleitung:** [Docker Get Started](https://docs.docker.com/get-docker/)
* **Kurzzusammenfassung:** * Laden Sie **Docker Desktop** (für Windows/Mac) oder die **Docker Engine** (für Linux) herunter.
* Installieren Sie die Anwendung und stellen Sie sicher, dass sie gestartet ist (ein kleines Wal-Symbol in der Taskleiste zeigt dies an).
* Docker verwaltet im Hintergrund die Ressourcen für OpenWebUI und n8n.



---

## 🧠 2. Ollama: Das KI-Triebwerk

Ollama ist die Software, die die eigentlichen Sprachmodelle (LLMs) lädt und ausführt. Sie fungiert als Schnittstelle zwischen der Hardware (Grafikkarte) und der Anwendung.

* **Offizielle Anleitung:** [Ollama Download & Setup](https://ollama.com/download)
* **Kurzzusammenfassung:**
* Laden Sie den Installer für Ihr Betriebssystem herunter und führen Sie ihn aus.
* Ollama läuft nach der Installation als Hintergrunddienst.
* **Test-Modell laden:** Öffnen Sie Ihr Terminal (CMD oder PowerShell) und geben Sie folgenden Befehl ein, um ein leistungsfähiges, kompaktes Modell für einen ersten Test zu laden:
```bash
ollama run llama3.2

```


* Sobald der Download fertig ist, können Sie direkt im Terminal mit der KI chatten. Geben Sie `/bye` ein, um den Chat zu beenden.



---

## 🖥️ 3. OpenWebUI: Die Benutzeroberfläche

OpenWebUI bietet Ihnen eine grafische Oberfläche für Ihre lokale KI, die optisch und funktional stark an ChatGPT erinnert – jedoch komplett lokal in Ihrem Browser läuft.

* **Offizielle Anleitung:** [OpenWebUI Installation Guide](https://docs.openwebui.com/getting-started/)
* **Kurzzusammenfassung:**
* OpenWebUI wird am einfachsten über Docker installiert.
* Führen Sie folgenden Befehl in Ihrem Terminal aus, um OpenWebUI zu starten (dies verbindet die Oberfläche automatisch mit Ihrem installierten Ollama):
```bash
docker run -d -p 3000:8080 --add-host=host.docker.internal:host-gateway -v open-webui:/app/backend/data --name open-webui ghcr.io/open-webui/open-webui:main

```


* Nach dem Start erreichen Sie Ihre Praxis-KI im Browser unter: `http://localhost:3000`.
* Beim ersten Aufruf müssen Sie ein lokales Administratoren-Konto erstellen (Ihre Daten bleiben nur auf diesem Rechner).



---

## 📊 Zusammenfassung der Infrastruktur

| Komponente | Aufgabe | Status-Check |
| --- | --- | --- |
| **Docker** | System-Umgebung | Wal-Icon in der Taskleiste sichtbar |
| **Ollama** | Modell-Hosting | Befehl `ollama list` zeigt installierte Modelle |
| **OpenWebUI** | Benutzer-Interface | Oberfläche unter Port 3000 im Browser erreichbar |

---

## 💡 Nächste Schritte

Sobald diese drei Komponenten laufen, ist Ihre Praxis bereit für den Einsatz von **Ambient-Scribe**.
