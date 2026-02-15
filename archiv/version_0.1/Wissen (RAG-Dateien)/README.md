# Wissen den LLMs hinzufügen

RAG ist eine Methode, Wissen einem LLM ohne großen Aufwand hinzuzufügen. Dies können z.B. Handelsnamen wichtiger Medikamente sein oder auch der ICD-10-Code

## Erstellen einer json-Datei für RAG mit dem ICD-10-Code

Aus Lizenzgründen kann kein direkter Download des ICD-10-Codes im für die Anwendung mittels RAG notwendigen Format bereit gestellt werden, man kann sich mit folgender Anleitung aber ganz leicht selbst diese Datei erstellen (lassen). Wichtig: Nur selbst benutzen, nicht weitergeben.

[![Thumbnail](https://img.youtube.com/vi/DSL214j0Pl4/maxresdefault.jpg)](https://youtu.be/DSL214j0Pl4)

```
Wandle die folgenden ICD-10-Daten um:
Jede Zeile enthält einen ICD-10-Code und die zugehörige Beschreibung, getrennt durch ein Semikolon.
Erstelle eine JSON-Ausgabe im Array-Format, in der jedes Objekt zwei Felder hat:

Code: enthält den ICD-10-Code.
Krankheit: enthält die Beschreibung des Codes.
Beispielinput:


A00;Cholera
A00.0;Cholera durch Vibrio cholerae O:1, Biovar cholerae
Erwartete JSON-Ausgabe:

json
  {
    "Code": "A00",
    "Krankheit": "Cholera"
  },
  {
    "Code": "A00.0",
    "Krankheit": "Cholera durch Vibrio cholerae O:1, Biovar cholerae"
  }

Verarbeite alle Daten aus der Datei entsprechend diesem Muster
```