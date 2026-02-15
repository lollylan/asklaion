# Askl-AI-on

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Lokale KI-Lösungen für die moderne Hausarztpraxis – Sicher, Open-Source und On-Premise.**

Willkommen bei **Askl-AI-on**. Dieses Projekt ist eine kuratierte Sammlung von Anleitungen, Skripten und Workflows, die darauf abzielen, den administrativen Alltag in der Hausarztpraxis durch den Einsatz künstlicher Intelligenz zu entlasten – ohne dabei sensible Patientendaten in die Cloud zu schicken. Die hier vorgestellten Lösungen sollen lediglich als Inspiration und Ausgangspunkt für eigene Entwicklungen dienen und ersetzen keine professionelle Software oder Beratung. Ziel ist es primär, den großen Herstellern und PVS-Anbietern zu zeigen, dass es auch anders geht und eine datenschutzkonforme, lokale KI-Nutzung möglich ist. Es ist kein fertiges Produkt, sondern ein Werkzeugkasten für Ärzte, die bereit sind, sich mit der Technologie auseinanderzusetzen und sie an ihre Bedürfnisse anzupassen.

---

## 🎯 Zielgruppe & Fokus
Dieses Repository richtet sich an **technisch versierte Ärzte und Ärztinnen**, die:
1.  Den administrativen Aufwand ihrer Praxis durch KI reduzieren wollen.
2.  Absolute Kontrolle über ihre Daten behalten möchten (**Local-First**).
3.  Bereit sind, einfache technische Konfigurationen (Docker, Python-Skripte) selbst durchzuführen.

---

## 🚨 Haftungsausschluss & Rechtliches

> **WICHTIGER HINWEIS:**
> Die hier bereitgestellten Werkzeuge und Skripte sind **keine zertifizierten Medizinprodukte**. Sie dienen ausschließlich als assistierende Werkzeuge zur Entlastung bei administrativen Tätigkeiten.
> - **Verantwortung:** Die medizinische Entscheidungsgewalt und Verantwortung liegt **ausschließlich** beim behandelnden Arzt/bei der behandelnden Ärztin.
> - **Überprüfungspflicht:** Alle KI-generierten Texte (Arztbriefe, Transkripte) **müssen** vor der Übernahme in die Patientenakte sorgfältig auf Richtigkeit und Vollständigkeit geprüft werden.
> - **Datenschutz:** Der Anwender ist selbst für die Einhaltung der DSGVO und der ärztlichen Schweigepflicht verantwortlich. Stellen Sie sicher, dass Ihre lokale Hardware sicher konfiguriert ist.

Bitte beachten Sie unsere detaillierte [Sicherheitsrichtlinie](SECURITY.md).

---

## 🔒 Datenschutz-Philosophie

- **100% Lokal:** Keine Daten verlassen Ihre Praxis. Sprachverarbeitung und Textgenerierung finden ausschließlich auf Ihrer eigenen Hardware statt.
- **Transparenz:** Da der Quellcode offen liegt, können Sie jederzeit nachvollziehen, was mit den Daten passiert.
- **Keine Hintertüren:** Wir nutzen etablierte Open-Source-Modelle (wie Llama, Whisper via Ollama), die so konfiguriert sind, dass sie keine Daten nach Hause telefonieren.

---

## 📂 Struktur & Module

Das Repository ist modular aufgebaut, um verschiedene Anwendungsfälle abzudecken:

### 1. **Ambient Scribe (Hauptanwendung)**
*Ordner: [`ambient_scribe`](ambient_scribe/)*
Das Herzstück für den täglichen Einsatz.
- **Funktion:** Automatische Transkription und Zusammenfassung von Patientengesprächen in Echtzeit.
- **Technologie:** Python, Ollama, Whisper (lokal).
- **Setup:** Siehe separate [Dokumentation](ambient_scribe/README.md).

### 2. **Automatisierungen**
*Ordner: [`automatisierungen`](automatisierungen/)*
Skripte für Routineaufgaben im Hintergrund.
- **Beispiele:** Intelligente Umbenennung von gescannten Dokumenten, PDFs sortieren, Fax-Eingang verarbeiten.
- **Technologie:** n8n, Python-Skripte.

### 3. **Prompt Engineering**
*Ordner: [`prompt_engineering`](prompt_engineering/)*
Spezialisiertes Wissen, um KI-Modelle für medizinische Aufgaben zu instruieren.
- **Inhalt:** System-Prompts für Arztbriefe, Anamnese, Befunde.

### 4. **RAG-Wissen**
*Ordner: [`wissensdatenbank_rag`](wissensdatenbank_rag/)*
Dateien, um Ihre lokale KI mit spezifischem Fachwissen (Leitlinien, Praxis-Standards) anzureichern (Retrieval-Augmented Generation).

---

## 🚀 Erste Schritte

Um die Lösungen nutzen zu können, benötigen Sie eine solide Basis-Infrastruktur:

1.  **Hardware:**
    - Ein dedizierter PC/Server in der Praxis (Empfehlung: NVIDIA GPU mit mind. 12GB VRAM für flüssige lokale LLMs).
    - Ein gutes Konferenzmikrofon für die Ambient-Funktion.
2.  **Software-Basis:**
    - Befolgen Sie unseren [Installations-Guide](ambient_scribe/basisinstallation/README.md) zur Einrichtung von Docker & Ollama.
3.  **Starten:**
    - Navigieren Sie in den Ordner [`ambient_scribe`](ambient_scribe/) und starten Sie mit dem Skript im Ordner `komplettscript`.

---

## 🤝 Mitwirken

Beiträge sind herzlich willkommen! Ob Bug-Report oder neuer Workflow – beteiligen Sie sich an der Sicherheit und Effizienz Ihrer Kollegen.
Siehe [CONTRIBUTING.md](CONTRIBUTING.md).

## 📄 Lizenz

Dieses Projekt ist unter der [MIT Lizenz](LICENSE) veröffentlicht. Sie dürfen es frei verwenden, modifizieren und weitergeben – auch kommerziell.