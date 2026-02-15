# Askl-AI-on | Fax-Umbenennung & OCR

Dieses Modul automatisiert die Sortierung und Benennung von eingehenden Dokumenten (z. B. Fax-Eingängen oder Scans). Es nutzt eine Kombination aus lokaler Texterkennung (OCR) und einer lokalen KI (Ollama), um Dokumente zu klassifizieren und sinnvoll zu benennen.

---

## 📋 Funktionsweise

Der Workflow überwacht einen lokalen Ordner und führt bei jedem neuen PDF folgende Schritte aus:

1. **Textextraktion:** Zuerst wird versucht, den Text direkt aus der PDF-Datei zu lesen.
2. **OCR-Fallback (Tesseract):** Falls das Dokument ein reiner Scan ohne Textebene ist (oder der Text zu kurz ist), wird automatisch die **Tesseract OCR** gestartet, um das Bild in Text umzuwandeln.
3. **KI-Analyse (Ollama):** Der extrahierte Text wird an ein lokales Sprachmodell (z.B. **gemma3:27b**) gesendet. Dieses erkennt:
* Den Dokumententyp (Arztbrief, Rezept, Werbung, Kontakt, Sonstiges).
* Den Absender (Fachrichtung und Name des Arztes) bei Arztbriefen.
* Eine kurze Inhaltsangabe bei anderen Dokumenten.


4. **Intelligente Bereinigung:** Das System ist so konfiguriert, dass es den Praxisinhaber (z. B. Dr. Florian Rasche) als Empfänger ignoriert und gezielt nach dem externen Absender sucht.
5. **Automatisches Umbenennen:** Die Datei wird nach dem Schema `FachrichtungName_Index.pdf` oder `Typ_Inhalt_Index.pdf` in einen Zielordner verschoben.

---

## 🛠️ Voraussetzungen & Zusätzliche Nodes

Neben einer Standard-Installation von n8n benötigst du zwei zusätzliche Komponenten:

### 1. Tesseract OCR Node (Community Node)

Da n8n standardmäßig kein OCR mitbringt, nutzt dieser Workflow die Tesseract-Integration.

* **Installation:**
1. Gehe in n8n auf **Settings** -> **Community Nodes**.
2. Klicke auf **Install a community node**.
3. Gib `n8n-nodes-tesseractjs` ein und klicke auf **Install**.
4. Bestätige die Installation und starte n8n ggf. neu, falls die Node nicht sofort erscheint.



### 2. Ollama & Modell

Der Workflow benötigt eine laufende Ollama-Instanz (lokal auf demselben Rechner oder im Netzwerk).

* **Modell:** Das Skript ist auf `gemma3:27b` eingestellt. Du kannst dies in der Node "Ollama Chat Model" auf ein kleineres Modell (z. B. `llama3` oder `mistral`) ändern, falls deine Hardware weniger Leistung hat.

---

## 📥 Import des Workflows

1. Lade die Datei `FaxumbenennungOCR.json` aus diesem Ordner herunter.
2. Öffnen dein n8n-Interface.
3. Drücke `Strg + O` oder wähle oben rechts im Menü **"Import from File"**.
4. Wähle die JSON-Datei aus.

---

## ⚙️ Konfiguration

Nach dem Import müssen einige Pfade an deine lokale Praxis-Umgebung angepasst werden:

### Pfade anpassen (WICHTIG)

Klicke nacheinander auf folgende Nodes und ändere die Verzeichnisse unter **Path**:

* **Local File Trigger:** Der Ordner, in dem neue Faxe/Scans landen.
* **Read/Write Files from Disk:** Hier muss der identische Pfad wie im Trigger hinterlegt sein (z. B. `C:\Scans\Eingang\*.pdf`).
* **Create new File Name (Code Node):** Suche im Code die Zeile `const newPath = ...` und trage dort dein Zielverzeichnis für die umbenannten Dateien ein.

### Ollama Verbindung

1. Klicke auf die Node **Ollama Chat Model**.
2. Wähle unter **Credentials** dein lokales Ollama-Konto aus oder erstelle ein neues (meist `http://localhost:11434` oder `http://host.docker.internal:11434`).

---

## 📝 Beispiel der Logik

| Eingangsdatei | KI-Analyse | Neuer Dateiname (Beispiel) |
| --- | --- | --- |
| `fax_12345.pdf` | Typ: Arztbrief, Fach: Kardiologie, Name: Weber | `KardiologieWeber_0.pdf` |
| `scan_abc.pdf` | Typ: Rezept, Inhalt: Bestellung Schmidt | `Rezept_BestellungSchmidt_1.pdf` |
| `flyer.pdf` | Typ: Werbung, Inhalt: CuraMed | `Werbung_CuraMed_2.pdf` |

---

> **Pro-Tipp:** Wenn du den Namen deiner Praxis oder den Namen des Inhabers ändern möchtest, öffne die Node **"Basic LLM Chain"** und passe im System-Prompt den Bereich "SEHR WICHTIGE REGEL" an. So verhinderst du, dass die KI deine eigenen Daten als Absender extrahiert.
