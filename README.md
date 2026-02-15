# Askl-AI-on

**Lokale KI-Lösungen für die moderne Hausarztpraxis – Sicher, Open-Source und On-Premise.**

Willkommen bei **Askl-AI-on**. Dieses Projekt ist eine kuratierte Sammlung von Anleitungen, Skripten und Workflows, die darauf abzielen, den administrativen Alltag in der Hausarztpraxis durch den Einsatz künstlicher Intelligenz zu entlasten – ohne dabei sensible Patientendaten in die Cloud zu schicken.

---

## Überblick

In der täglichen Praxis stehen Mediziner vor einer wachsenden Flut an Dokumentationspflichten, Arztbriefen und bürokratischen Prozessen. Herkömmliche KI-Lösungen scheitern oft an der **ärztlichen Schweigepflicht** und den strengen Vorgaben der **DSGVO**, da sie Daten auf externen Servern verarbeiten.

**Askl-AI-on** löst dieses Problem durch:

* **Strikte Lokalität:** Alle Anwendungen laufen auf eigener Hardware in der Praxis.
* **Open-Source:** Volle Transparenz über den verwendeten Code und die Datenverarbeitung.
* **Kostenfreiheit:** Nutzung bewährter Open-Source-Tools statt teurer Abo-Modelle.
* **Modularität:** Eine Sammlung aus Empfehlungen, Drittprogrammen und maßgeschneiderten Skripten.


**Wichtig: Askl-AI-on versteht sich nicht als endgültige Lösung sondern dient nur als Beispiel und Informationsquelle dafür, dass quasi alle aktuell cloud-basierten KI-Lösungen auch wunderbar lokal laufen können, um den Schutz der Patientendaten zu verbessern. Es handelt sich um reine Anleitungen, wie Probleme theoretisch lösbar wären, die finale Implementierung obliegt natürlich den PVS-Herstellern und kommerziellen Anbietern.**

---

## Hauptkomponenten & Module

Das Repository ist in verschiedene Unterordner unterteilt, die jeweils spezifische Lösungen enthalten:

| Modul | Beschreibung | Technologie |
| --- | --- | --- |
| **Ambientscribe** | Automatische Transkription und Zusammenfassung von Patientengesprächen. | Ollama, Docker, Whisper, OpenWebUI |
| **Automatisierung** | Automatisierung von Routineaufgaben (z. B. Fax-Umbenennung, Brief-Zusammenfassung). | n8n, Docker |
| **Prompts** | Optimierte System-Prompts für medizinische Kontexte. | Markdown |

---

## Voraussetzungen

Um die hier angebotenen Lösungen zu nutzen, benötigen Sie in der Regel:

1. **Hardware:** Einen dedizierten Rechner (Server oder leistungsstarker PC) mit einer NVIDIA-Grafikkarte (empfohlen für lokale LLMs), ein Konferenz-Mikrophon (für die Ambient scribe Funktionalität)
2. **Infrastruktur:** Ein stabiles lokales Netzwerk in der Praxis.

*Detaillierte Hardware-Empfehlungen finden Sie in den jeweiligen Modul-Ordnern.*

---

## ⚙️ Installation & Nutzung

Jedes Modul verfügt über eine eigene Dokumentation. Grundsätzlich folgt der Prozess diesem Muster:

1. **Unterordner wählen:** Navigieren Sie in das gewünschte Modul (z. B. `/ambientscribe`).
2. **Anleitung folgen:** Nutzen Sie die dort hinterlegte `README.md` für die spezifische Konfiguration.

---

## ⚖️ Lizenz & Haftungsausschluss

### MIT Lizenz

Dieses Projekt ist unter der **MIT-Lizenz** veröffentlicht. Das bedeutet:

* Sie dürfen die Inhalte für private und kommerzielle Zwecke nutzen, kopieren und verändern.
* Der Quellcode muss offenbleiben oder auf die ursprüngliche Quelle verweisen.
* Die Lizenz von Drittsoftware entspricht der Lizenz des jeweiligen Anbieters.

### Wichtiger Hinweis zur Verantwortlichkeit

> **Achtung:** Die Nutzung der hier bereitgestellten Werkzeuge erfolgt auf eigene Verantwortung. Der Betreiber dieses Repositories übernimmt keine Haftung für Fehlbehandlungen, Datenverlust oder Verstöße gegen die DSGVO, die durch unsachgemäße Konfiguration oder Fehlinterpretationen der KI-Ergebnisse entstehen könnten. KI-generierte medizinische Zusammenfassungen müssen **immer** durch qualifiziertes medizinisches Personal überprüft werden.

---

## 🤝 Mitwirken

Beiträge aus der Community sind herzlich willkommen! Ob Bug-Fixes, neue Workflows oder verbesserte Prompts – öffnen Sie gerne einen *Pull Request* oder erstellen Sie ein *Issue*.