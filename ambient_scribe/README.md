# Ambient Scribe – Die intelligente Praxisassistenz

**Ambient Scribe** ist das Herzstück dieses Repositories für den direkten klinischen Einsatz. Das Ziel ist die "umgebende Dokumentation": Die KI hört (lokal!) zu und erstellt daraus strukturierte Einträge für Ihre Patientenakte, ohne dass Sie während des Gesprächs tippen müssen.

---

## ⚠️ Wichtiger erster Schritt: Die Basis

Bevor Sie die Module in diesem Ordner nutzen können, muss die technische Infrastruktur in Ihrer Praxis stehen. Sollten Sie dies noch nicht erledigt haben, folgen Sie bitte zuerst dieser Anleitung:

👉 **[Basisinstallation KI-Programme](basisinstallation/README.md)**
*(Installation von Ollama)*

---

## 📂 Aktuelle Module

Sobald die Basisinstallation läuft, können Sie die folgenden Anwendungen nutzen:

| Modul | Inhalt & Zweck | Fokus |
| --- | --- | --- |
| **[Komplettscript v2.0](komplettscript/)** | **Hauptanwendung:** Praxisserver (Whisper-Transkription, Sprechertrennung ARZT/PATIENT, Ollama-Proxy) + Client für jedes Behandlungszimmer, der Audio aufnimmt und das Ergebnis für das PVS (z.B. PegaMed, Turbomed, etc.) aufbereitet. Mehrere Zimmer gleichzeitig, ein Server. | Vollautomatisierung |
| **Basisinstallation** | Anleitung zur Einrichtung von Ollama als lokalem LLM-Backend. | Infrastruktur |

*(Ältere Versionen finden Sie im Ordner `../archiv`)*

---

## 🔒 Datenschutz & Sicherheit

Wie bei allen Modulen von **Askl-AI-on** gilt:

* **Kein Cloud-Zwang:** Weder das gesprochene Wort noch der Text verlassen den Praxis-Server.
* **Zero-Storage-Policy:** Die verwendeten Modelle (wie Whisper oder Llama) speichern in der Standardkonfiguration keine Daten für das Training.
* **DSGVO-Konform:** Die Verarbeitung findet "On-Premise" statt. Eine schriftliche Einwilligung der Patienten zur Nutzung der Transkription wird dringend empfohlen.

---

## 🛠️ Fehlerbehebung

Sollten Probleme auftreten:
1.  Prüfen Sie, ob **Ollama** läuft (`ollama list`).
2.  Stellen Sie sicher, dass das richtige Mikrofon in den Windows-Einstellungen als Standardgerät gewählt ist.
3.  Kontrollieren Sie die `config.json` im `komplettscript`-Ordner auf korrekte IP-Adressen und Modell-IDs.
4.  Prüfen Sie mit `https://<Server-IP>:8000/health` im Browser, ob der Praxisserver läuft (Modell, GPU, Sprechertrennung).