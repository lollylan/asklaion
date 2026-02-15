# Askl-AI-on | Ambient-Scribe

**Ambient-Scribe** ist das Herzstück dieses Repositories für den direkten klinischen Einsatz. Das Ziel ist die "umgebende Dokumentation": Die KI hört (lokal!) zu und erstellt daraus strukturierte Einträge für Ihre Patientenakte, ohne dass Sie während des Gesprächs tippen müssen.

---

## ⚠️ Wichtiger erster Schritt: Die Basis

Bevor Sie die Module in diesem Ordner nutzen können, muss die technische Infrastruktur in Ihrer Praxis stehen. Sollten Sie dies noch nicht erledigt haben, folgen Sie bitte zuerst dieser Anleitung:

👉 **Basisinstallation KI-Programme** *(Installation von Docker, Ollama und OpenWebUI)*

---

## 📂 Modul-Übersicht

Sobald die Basisinstallation läuft, können Sie je nach gewünschtem Automatisierungsgrad die folgenden Unterordner nutzen. Wählen Sie das Modul, das am besten zu Ihrem Workflow passt:

| Modul | Inhalt & Zweck | Fokus |
| --- | --- | --- |
| **Askl-AI-on in OpenwebUI** | Nutzung der Weboberfläche mit spezifischen **System-Prompts** für die Hausarztpraxis. | Manuelle Eingabe / Kopieren |
| **Transkription via Whisper** | Einrichtung von OpenAI Whisper (lokal), um Audioaufnahmen in Text umzuwandeln. | Audio-zu-Text |
| **Komplettscript (Beispiel PegaMed)** | Ein End-to-End Skript, das Audio aufnimmt, transkribiert und für das PVS **PegaMed** aufbereitet. | Vollautomatisierung |


---

## 🔒 Datenschutz

Wie bei allen Modulen von **Askl-AI-on** gilt:

* **Kein Cloud-Zwang:** Weder das gesprochene Wort noch der Text verlassen den Praxis-Server.
* **Zero-Storage-Policy:** Die verwendeten Modelle (wie Whisper oder Llama) speichern in der Standardkonfiguration keine Daten für das Training.
* **DSGVO-Konform:** Da die Verarbeitung "On-Premise" stattfindet, bleibt die ärztliche Schweigepflicht vollständig gewahrt. Die Einverständnis der Patienten/Patientinnen zur Nutzung der Transkription ist zwingend erforderlich, lassen Sie sich dies sicherheitshalber schriftlich bestätigen.