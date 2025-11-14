# Analyse von eingehenden Dokumenten

Wer kennt es nicht? Das PVS hat einen Faxeingangsordner, alle Faxe heißen genau gleich und ein/e MFA muss händisch jedes Fax umbenennen, um ein bisschen Ordnung zu schaffen? Die eingehenden KIM-Nachrichten heißen nur Arztbrief.pdf oder tragen irgend einen Phantasienamen und lassen sich im Nachhinein in der Patientenakte realistisch nicht wieder finden. Die Lösung? Analyse durch ein LLM und Vergabe eines sinnvollen Namens - und das voll automatisiert.

## Kurzanleitung: Lokale KI-Automatisierung mit n8n, Ollama & Tesseract unter Windows

Diese Anleitung führt Sie durch die Installation und Konfiguration von n8n, Ollama (für lokale KI-Modelle) und Tesseract (für OCR/Texterkennung) auf einem Windows-PC. Das Ziel ist es, einen bestehenden n8n-Workflow so einzurichten, dass er automatisch Dateien (z. B. eingehende Faxe) aus einem Ordner liest, verarbeitet und umbenannt in einem anderen Ordner speichert.

---

### 1. Benötigte Software installieren

Für diesen Workflow benötigen wir zwei Hauptprogramme: **n8n Desktop** (zur Workflow-Automatisierung) und **Ollama** (zur Ausführung lokaler Sprachmodelle).

#### n8n Desktop

n8n Desktop ist der einfachste Weg, n8n auf einem Windows-Rechner zu betreiben.

Besuchen Sie die [offizielle n8n-Website](https://n8n.io/) und laden Sie die **n8n Desktop App** für Windows herunter. Es gibt verschiedene Varianten, n8n zu installieren, der Einfachheit halber empfehle ich, zunächst die Software Node.js zu installieren und dann mit dem Befehl in der Kommandozeile (Im Startmenü von Windows einfach nach "cmd" suchen und denn Text hinein zu kopieren und Enter zu drücken)
   >npm install -g n8n

n8n zu installieren. Man Startet dann n8n wenn es fertig installiert ist indem man einfach nur
>n8n

eingibt und dann wenn man aufgefordert wir "o" drückt.

#### Ollama
Ollama ermöglicht es, leistungsstarke KI-Modelle (LLMs) direkt auf Ihrem eigenen Computer auszuführen.

1.  Besuchen Sie die [offizielle Ollama-Website](https://ollama.com/) und laden Sie den Installer für Windows herunter.
2.  Führen Sie die Installationsdatei aus. Ollama wird als Hintergrunddienst eingerichtet.
3.  Um zu prüfen, ob Ollama läuft, öffnen Sie die **Eingabeaufforderung (CMD)** oder **PowerShell** und geben Sie `ollama --version` ein.

---

### 2. Modelle und Nodes vorbereiten

#### Ollama-Modell herunterladen
Bevor n8n ein Modell nutzen kann, muss Ollama es herunterladen.

1.  Öffnen Sie die Eingabeaufforderung (CMD) oder PowerShell.
2.  Geben Sie den `pull`-Befehl für das gewünschte Modell ein. Für allgemeine Textaufgaben (wie das Verarbeiten von Fax-Inhalten) eignet sich z. B. `granite`.
    > ollama run granite4:3b
3.  Warten Sie, bis der Download abgeschlossen ist. Das Modell ist nun lokal verfügbar.

#### Tesseract Community Node installieren
Damit n8n Text aus Bildern oder gescannten PDFs (wie Faxen) lesen kann, benötigen wir die Tesseract OCR Node.

1.  Öffnen Sie Ihre n8n Desktop App.
2.  Klicken Sie oben rechts auf das **Zahnrad-Symbol** (Einstellungen).
3.  Wählen Sie im Menü links **Community Nodes**.
4.  Geben Sie in das Suchfeld `n8n-nodes-tesseract-ocr` ein.
5.  Klicken Sie auf **Install**.
6.  **Wichtig:** Starten Sie n8n Desktop nach der Installation der Node neu, damit sie geladen wird.

---

### 3. n8n-Workflow einrichten

#### Schritt 1: Workflow importieren
Sie benötigen die Workflow-Datei (meist eine `.json`-Datei) oder den kopierten JSON-Code.

1.  Klicken Sie in n8n auf **Import from File** (oder **Import from Clipboard**).
2.  Wählen Sie Ihre `.json`-Datei aus oder fügen Sie den Code ein, um den Workflow in Ihren Editor zu laden.

#### Schritt 2: Credentials eingeben (Ollama)
Der Workflow muss wissen, wie er mit Ollama sprechen kann.

1.  Klicken Sie im Hauptmenü links auf **Credentials**.
2.  Klicken Sie auf **Add Credential**.
3.  Suchen Sie nach **Ollama** und wählen Sie es aus.
4.  Geben Sie als **Base URL** die Standardadresse von Ollama ein:
    > `http://localhost:11434`
5.  Klicken Sie auf **Save**, um die Verbindung zu speichern.
6.  Gehen Sie zurück zu Ihrem Workflow und wählen Sie in der Ollama-Node (falls vorhanden) die soeben erstellten Credentials aus.

#### Schritt 3: Eingabe-Ordner (Fax-Eingang) festlegen
Konfigurieren Sie die erste Node, die Ihre Fax-Dateien abholt.

1.  Klicken Sie auf die erste Node im Workflow (z. B. "Read Binary File" oder die von Ihnen genannte "Read/write file from Disk").
2.  Suchen Sie das Feld **File Path** (Dateipfad).
3.  Geben Sie hier den **vollständigen Pfad** zu Ihrem Fax-Eingangsordner ein.

> **Beispiel für einen Windows-Pfad:**
> `C:\Users\IhrName\Desktop\Fax-Eingang\`
> *Achten Sie darauf, dass der Pfad korrekt ist und n8n die nötigen Leserechte hat.*

#### Schritt 4: Ausgabe-Ordner (Ziel-Ordner) festlegen
Konfigurieren Sie die letzte Node, die Ihre umbenannte Datei speichert.

1.  Klicken Sie auf die letzte Node im Workflow (z. B. "Write File" oder "Write Binary File").
2.  Suchen Sie das Feld **File Path** (Dateipfad).
3.  Geben Sie hier den **vollständigen Pfad** zu dem Ordner ein, in dem die verarbeiteten Dateien gespeichert werden sollen.
4.  Das Feld **File Name** (Dateiname) enthält wahrscheinlich bereits einen Ausdruck (z. B. `{{ $json.neuerName }}.pdf`), um die Datei dynamisch umzubenennen. Ändern Sie hier nur den **Ordnerpfad**.

> **Beispiel für einen Windows-Pfad:**
> `C:\Archiv\Importierte-Faxe\`

---

### 4. Workflow aktivieren

Wenn alle Nodes konfiguriert und keine Fehlermeldungen sichtbar sind, können Sie den Workflow starten.

1.  Klicken Sie auf den **Schieberegler** oben rechts von **Inactive** auf **Active**.
2.  Der Workflow läuft nun und wartet (je nach Konfiguration des Start-Triggers) auf neue Dateien in Ihrem Fax-Eingangsordner.