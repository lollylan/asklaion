# Automatische Zusammenfassung von Arztbriefen via n8n & Ollama (PoC)

Dieses Projekt stellt einen n8n-Workflow vor, der als **Proof of Concept (PoC)** für die automatisierte Verarbeitung und Zusammenfassung medizinischer Dokumente dient. Er ist als technische Demonstration konzipiert und nicht als fertiges Produkt für den Produktiveinsatz gedacht.

## 🎥 Video-Anleitung

Eine visuelle Erklärung der Funktionsweise und Einrichtung findest du in diesem Video:

[https://youtu.be/iMlgmlJKctA](https://youtu.be/iMlgmlJKctA)

## 🛠 Funktionsweise des Workflows

Der Workflow automatisiert die Extraktion und Analyse von medizinischen Informationen aus PDF-Dateien:

* **Dateien einlesen:** Der Prozess startet mit dem Einlesen von PDF-Dokumenten aus einem lokalen Verzeichnis (vordefiniert unter `C:\Users\lolly\Desktop\KIM\`).
* **Textextraktion:** Der Inhalt der PDFs wird für die weitere Verarbeitung in Text umgewandelt.
* **KI-Analyse:** Der Text wird an eine lokale **Ollama**-Instanz übermittelt.
* **Modell:** Zum Einsatz kommt in diesem Beispiel `gemma3:27b`.
* **Prompt-Design:** Die KI fasst den Brief präzise (80-120 Wörter) zusammen und extrahiert gezielt Absender, Aufnahmegrund, Diagnosen, Maßnahmen sowie die Medikation.


* **Ergebnisspeicherung:** Die fertige Zusammenfassung wird als neue `.txt`-Datei mit dem Suffix `_zusammenfassung` im Ausgangsverzeichnis gespeichert.

## 📥 Installation & Import

Um den Workflow in n8n zu nutzen, folgen Sie diesen Schritten:

1. Laden Sie die Datei `KIMZusammenfassung001.json` aus diesem Repository herunter.
2. Öffnen Sie Ihre n8n-Instanz im Browser.
3. Erstellen Sie einen neuen Workflow ("Create a workflow").
4. Wählen Sie im Menü oben rechts den Punkt **"Import from File"** und laden Sie die JSON-Datei hoch.
5. **Anpassung:** Öffnen Sie die Knoten "KIM PDFs lesen" sowie "Zusammenfassung speichern" und passen Sie die Dateipfade an Ihre lokale Ordnerstruktur an.

## 📋 Systemvoraussetzungen

* **n8n:** Eine laufende n8n-Instanz (lokal oder Docker).
* **Ollama:** Lokal installiert und erreichbar unter `http://localhost:11434`.
* **KI-Modell:** Das Modell `gemma3:27b` muss in Ollama geladen sein.

---

*Hinweis: Da es sich um medizinische Daten handelt, stellen Sie bei einer Weiterentwicklung sicher, dass alle datenschutzrechtlichen Anforderungen (DSGVO) erfüllt sind.*