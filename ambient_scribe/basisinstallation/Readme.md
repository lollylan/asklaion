# Askl-AI-on | Ambient-Scribe: Basis-Setup

Bevor spezifische Funktionen wie die automatisierte Transkription oder die Generierung von Arztbriefen genutzt werden können, muss eine stabile Infrastruktur für lokale KI-Modelle geschaffen werden. Diese Anleitung führt Sie durch die Installation von **Ollama** als lokalem LLM-Backend.

> **Hinweis:** Dies ist die zwingende Voraussetzung, um KI-Modelle ohne Cloud-Anbindung direkt auf Ihrer Praxis-Hardware zu betreiben.

---

## 🧠 1. Ollama: Das KI-Triebwerk

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

## 📋 2. Modelle für Ambient Scribe herunterladen

Laden Sie die Modelle herunter, die das Komplettscript standardmäßig nutzt:

```bash
ollama pull llama3.1:8b
ollama pull qwen2.5:14b
```

> **Tipp:** Weitere Modelle finden Sie unter [ollama.com/library](https://ollama.com/library). In den Einstellungen der App können Sie die Modellzuordnung jederzeit ändern.

---

## 📊 Zusammenfassung

| Komponente | Aufgabe | Status-Check |
| --- | --- | --- |
| **Ollama** | Modell-Hosting & LLM-API | Befehl `ollama list` zeigt installierte Modelle |

---

## 💡 Nächste Schritte

Sobald diese drei Komponenten laufen, ist Ihre Praxis bereit für den Einsatz von **Ambient-Scribe**.
