# Askl-AI-on – Ambient Scribe v2.0

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Lokale KI-Dokumentation für die Hausarztpraxis – Open Source, On-Premise, ohne Cloud.**

> **Kein Medizinprodukt.** Alle Transkripte und KI-Texte müssen vor der Übernahme in die Patientenakte ärztlich geprüft werden. Für DSGVO und Schweigepflicht ist der Anwender selbst verantwortlich. Details: [Sicherheitsrichtlinie](SECURITY.md) und Haftungsausschluss am Ende dieser Seite.


Askl-AI-on ist eine "One-Click"-Lösung für die medizinische Dokumentation: Ein **Praxisserver** (ein Rechner mit GPU im Praxisnetz) transkribiert die Gespräche aller Behandlungszimmer, trennt die Sprecher und stellt das lokale Sprachmodell (Ollama) bereit. Auf jedem Behandlungsplatz läuft nur der leichte **Client**, der das Mikrofon aufnimmt und das Ergebnis für das PVS aufbereitet.

```
 Zimmer 1: Komplettscript_2_0  ─┐
 Zimmer 2: Komplettscript_2_0  ─┼── HTTPS (ein Port) ──►  Praxisserver (server.py)
 Zimmer 3: Komplettscript_2_0  ─┘                          ├─ Whisper large-v3-turbo (GPU)
                                                            ├─ Sprechertrennung (CPU)
                                                            └─ Ollama-Proxy (LLM)
```

Jedes Gespräch bekommt auf dem Server eine eigene **Sitzung** – mehrere Zimmer können gleichzeitig aufnehmen, ohne dass sich etwas vermischt.

---

## 🆕 Was ist neu in v2.0

| Bereich | v1.0 | v2.0 |
|---|---|---|
| Transkription | Whisper large-v3, unbatched | large-v3-turbo mit Batch-Pipeline, Silero-VAD, Hotwords, Wortzeitstempeln – **ca. 10x schneller** (20 s Audio in 0,2–0,5 s auf einer RTX 4090) |
| Stille / Halluzinationen | keine Behandlung | VAD entfernt Stille vor der Erkennung, bekannte Whisper-Phantomsätze ("Untertitel …") und Wiederholungsschleifen werden verworfen, stille Chunks werden gar nicht erst gesendet |
| Chunking | harter Schnitt alle 30 s (zerschnittene Wörter) | Schnitt an der nächsten Sprechpause (Standard 20 s + max. 15 s Wartezeit) |
| Sprecher | – | **ARZT / PATIENT / SPRECHER n** – die eigene Stimme kann angelernt werden |
| Medikamente | nur über den LLM-Prompt | Praxisvokabular (`vokabular_medizin.txt`, ~700 Begriffe) als Whisper-Hotwords + automatische Korrektur ähnlich klingender Wörter ("Raemipril" → "Ramipril") + **Kontextfeld** für den Medikationsplan des Patienten |
| Mehrbenutzer | ein Endpunkt, Temp-Dateien | Sitzungen mit eigener ID, Audio nur im Arbeitsspeicher, automatische Bereinigung |
| LLM | OpenAI-kompatibler Endpunkt ohne Kontextlänge (lange Gespräche wurden still abgeschnitten) | Ollama-API mit explizitem `num_ctx` (16k) und Temperatur, Streaming der Antwort, Denkmodus aus, Proxy über den Praxisserver |
| Server | drei Skripte (CPU / GPU / Parallel) | ein `server.py`, Konfiguration in `server_config.json` (Modell, Gerät, Ports, API-Key) |

---

## 📋 Funktionsweise

1. **Aufnahme:** Der Client nimmt am Behandlungsplatz auf. Alle ~20 s wird an der nächsten Sprechpause ein Chunk geschnitten und an den Server geschickt.
2. **Transkription:** Der Server erkennt den Text (Whisper) und zerlegt den Chunk im Hintergrund in Sprechabschnitte mit Stimm-Embeddings (Sprechertrennung).
3. **Live-Transkript:** Der Client zeigt den erkannten Text während des Gesprächs an.
4. **Abschluss ("Analyse"):** Der letzte Rest wird übertragen, die Sprecher werden global zugeordnet, angelernte Stimmen (z. B. `ARZT`) erkannt. Das dauert typischerweise 1–3 s.
5. **LLM-Verarbeitung:** Das Transkript (mit Sprecherlabels, Notizen, Normbefunden und Kontext) geht an **Ollama** – über den Praxisserver, so dass die Clients nur eine Adresse kennen müssen. Die Antwort wird gestreamt angezeigt und liegt am Ende in der Zwischenablage.
6. **PVS-Ausgabe:** Markdown wird entfernt, Zeilenumbrüche werden Windows-kompatibel gesetzt (`Strg + V` in PegaMed, Tomedo, Medistar …). Der Standard-Prompt ist für **PegaMed** (AN/BE/LD/TH) optimiert und in den Einstellungen anpassbar.

---

## 🗂️ Tabs & Funktionen

| Tab | Funktion |
|---|---|
| **Gespräch** | Ambient-Scribe mit Sprechertrennung, Kontextfeld, Notizen, Normbefunden, Live-Transkript |
| **Diktat** | Diktat aufnehmen und durch das LLM stilistisch überarbeiten lassen (ohne Sprechertrennung) |
| **Arena** | Zwei LLM-Modelle gleichzeitig vergleichen |
| **Arztbrief** | PDF-Arztbriefe hochladen und zusammenfassen lassen |

**Follow-Up Chat** (alle Tabs): Im Ergebnisfenster lässt sich das Ergebnis mit *Neu generieren*, *Kürzer*, *Länger* oder einer Freitext-Anweisung verfeinern. *Transkript* zeigt den Rohtext, der an das LLM ging.

**Kontextfeld (Gespräch):** Vor dem Start den aktuellen Medikationsplan / Vorerkrankungen aus dem PVS einfügen. Die Begriffe werden als Whisper-Hotwords genutzt (bessere Erkennung genau dieser Präparate) und dem LLM als verlässlicher Kontext mitgegeben.

---

## 🛠️ Installation

### Server (ein Rechner im Praxisnetz)

Voraussetzungen: Python 3.10–3.14, NVIDIA-GPU mit aktuellem Treiber (empfohlen, ein CUDA-Toolkit ist **nicht** nötig) und [Ollama](https://ollama.com/download).

```bash
pip install -r requirements-server.txt
python server.py
```

Beim ersten Start werden

* das Whisper-Modell (large-v3-turbo, ~1,6 GB) von Hugging Face,
* die Modelle für die Sprechertrennung (~33 MB) von GitHub nach `models/`,
* `server_config.json`, `vokabular_medizin.txt` und die TLS-Zertifikate in `certs/`

angelegt. Die Konsole zeigt die Adresse (`https://<IP>:8000`) und den Pfad zur `ca.crt`, die einmalig auf jeden Client-PC kopiert wird.

Ollama-Modelle laden, z. B.:

```bash
ollama pull gemma4:12b
ollama pull qwen3.5:9b
```

> **VRAM-Budget (24 GB, z. B. RTX 4090):** Whisper large-v3-turbo belegt ~1,6 GB, large-v3 ~3 GB. Der Rest steht Ollama zur Verfügung – ein 12B–27B-Modell in Q4 passt problemlos daneben; 31B-Modelle werden knapp. Damit mehrere Zimmer gleichzeitig zusammenfassen können, in Ollama `OLLAMA_NUM_PARALLEL=2` (oder höher) setzen.

### Client (jeder Behandlungsplatz)

```bash
pip install -r requirements-client.txt
python Komplettscript_2_0.py
```

In den **⚙ Einstellungen**: Server-Adresse (`https://<Server-IP>:8000`), `ca.crt` auswählen, Mikrofon wählen, Modelle aus der Liste wählen (wird vom Server geholt), optional *Eigene Stimme anlernen*.

> Die Server-Adresse als **IP** eintragen, nicht `localhost` – Windows löst `localhost` zuerst auf IPv6 auf, was jede Anfrage um ~2 s verzögert.

### EXE-Build (optional)

`build_all.bat` erzeugt mit PyInstaller `dist\server\server.exe` und `dist\Komplettscript_2_0\Komplettscript_2_0.exe`.

---

## ⚙️ Konfiguration

### Server: `server_config.json`

| Schlüssel | Beschreibung | Standard |
|---|---|---|
| `port`, `tls` | Port und TLS (selbstsignierte CA) | `8000`, `true` |
| `api_key` | Gemeinsamer Schlüssel; Clients senden ihn als `X-Api-Key` | leer (aus) |
| `asr.model` | `large-v3-turbo` (schnell), `large-v3` (max. Genauigkeit), `medium`/`small` (CPU) | `large-v3-turbo` |
| `asr.device` / `asr.compute_type` | `auto` wählt CUDA + float16, sonst CPU + int8 | `auto` |
| `asr.batch_size`, `asr.beam_size` | Batch-Größe der Pipeline, Beam-Search | `16`, `5` |
| `diarization.enabled` | Sprechertrennung | `true` |
| `diarization.cluster_threshold` | Cosinus-Distanz zwischen Sprechern; kleiner = mehr Sprecher, größer = weniger | `0.3` |
| `diarization.match_threshold` | Mindest-Ähnlichkeit zu einer angelernten Stimme | `0.45` |
| `ollama_url` | Ollama-Adresse (vom Server aus) | `http://localhost:11434` |
| `session_timeout_minutes` | Inaktive Sitzungen werden gelöscht | `90` |
| `log_transcripts` | Transkripttext in der Server-Konsole (Standard: nur Statistik) | `false` |

### Client: `config.json` (über die Einstellungs-Oberfläche)

| Schlüssel | Beschreibung | Standard |
|---|---|---|
| `server_url` | Praxisserver | `https://192.168.10.51:8000` |
| `api_key`, `ca_cert_path`, `client_name` | Zugang, Zertifikat, Zimmername | – |
| `llm_via_server` | LLM über den Praxisserver (`/llm/...`) statt direkt zu Ollama | `true` |
| `llm_num_ctx`, `llm_temperature` | Kontextfenster und Temperatur für alle LLM-Aufrufe | `16384`, `0.2` |
| `model_*`, `prompt_*` | Modelle und System-Prompts je Tab | s. App |
| `diarize`, `expected_speakers` | Sprechertrennung, erwartete Sprecheranzahl (0 = automatisch) | `true`, `0` |
| `chunk_duration`, `chunk_max_extra`, `silence_threshold` | Chunk-Länge, max. Wartezeit auf Sprechpause (harte Schnitte mitten im Wort kosten Wortfragmente), Stille-Schwelle (RMS) | `20`, `15`, `0.01` |
| `auto_delete_days` | Transkripte in `Transkripte_Raw/` nach n Tagen löschen (0 = aus) | `1` |

### Vokabular: `vokabular_medizin.txt` (Server)

Ein Begriff pro Zeile, `#` für Kommentare. Die oberen Einträge haben Vorrang für die Whisper-Hotwords (das Prompt-Fenster ist begrenzt); alle Einträge ab 7 Zeichen werden für die automatische Korrektur ähnlich klingender Wörter genutzt. Eigene Präparate, Kollegen, Ortsnamen einfach ergänzen; nach Änderungen den Server neu starten. Zusätzlich wird – falls vorhanden – `Medikamente Handelsnamen.json` neben dem Server-Script eingelesen (Handelsnamen + Wirkstoffe).

---

## 🎤 Eigene Stimme anlernen

Einstellungen → *Eigene Stimme anlernen* → 25 s normal sprechen. Der Server speichert nur ein 256-dimensionales Stimm-Embedding (kein Audio) unter `enrollments/<Name>.npy`. Im Transkript erscheint diese Person dann als `ARZT` (bzw. unter dem gewählten Namen), der übrige Sprecher als `PATIENT`; bei mehr als zwei Personen `SPRECHER 1/2/…`. Ohne Anlernen heißen alle Sprecher `SPRECHER n` – der LLM-Prompt erschließt die Rollen dann aus dem Inhalt. Mehrere Behandler können jeweils ihre Stimme anlernen.

---

## 🌐 Server-API (für eigene Integrationen)

| Methode | Pfad | Zweck |
|---|---|---|
| `GET` | `/health` | Status, Modell, Sprechertrennung, angelernte Stimmen |
| `POST` | `/session` | Sitzung anlegen (`client`, `room`, `context_terms`, `expected_speakers`, `diarize`) |
| `POST` | `/session/{id}/chunk` | WAV-Chunk (`file`, `offset`, `index`) → Text + Wortzeiten |
| `POST` | `/session/{id}/finalize` | optional letzter Chunk; liefert Transkript mit Sprechern |
| `DELETE` | `/session/{id}` | Sitzung löschen |
| `POST` | `/transcribe` | Einzeltranskription (kompatibel zu v1.0), optional `diarize=true` |
| `GET/POST/DELETE` | `/enroll` | Stimmen anlernen / auflisten / löschen |
| `GET` | `/llm/models` | Ollama-Modelle |
| `POST` | `/llm/chat` | Proxy zu Ollama `/api/chat` (Streaming) |

---

## 🔒 Datenschutz

* **Kein Cloud-Dienst:** Audio, Transkript und LLM bleiben im Praxisnetz; Verbindung per TLS.
* **Kein Audio auf der Festplatte:** Der Server verarbeitet Chunks im Arbeitsspeicher und verwirft sie nach der Segmentierung; nur Wortzeiten und Embeddings bleiben bis zum Sitzungsende.
* **Automatische Löschung:** Transkripte im Ordner `Transkripte_Raw/` des Clients werden nach `auto_delete_days` gelöscht; inaktive Server-Sitzungen nach `session_timeout_minutes`.
* **Stimm-Embeddings** angelernter Behandler sind biometrische Daten – nur mit Einwilligung der betreffenden Person anlegen; Patienten werden nicht angelernt.
* Eine schriftliche Einwilligung der Patienten zur Aufzeichnung wird dringend empfohlen.

---

## 🩺 Spezielle Features für Mediziner

* **Normbefunde:** Häufige Befunde per Knopfdruck ergänzen – sie werden dem LLM als verlässliche Arztangaben gekennzeichnet übergeben.
* **Manuelle Notizen:** Werden beim Abschluss an das Transkript angehängt.
* **Kontextfeld:** Medikationsplan/Vorerkrankungen verbessern Erkennung und Zusammenfassung.
* **Drag-and-Drop:** PDF-Arztbriefe direkt auf die Anwendung ziehen.

---

## 🔧 Fehlerbehebung

| Problem | Lösung |
|---|---|
| Client meldet "Praxisserver nicht erreichbar" | Läuft `server.py`? Firewall-Port 8000 freigeben; IP statt `localhost`; `ca.crt` in den Einstellungen gewählt? |
| Jede Anfrage dauert ~2 s | `localhost` durch `127.0.0.1` bzw. die Server-IP ersetzen |
| Server startet auf CPU statt GPU | `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`; NVIDIA-Treiber aktuell? Konsole zeigt "auf cuda" |
| Sprecher werden vertauscht/zusammengelegt | `expected_speakers` auf 2 setzen; Stimme anlernen; `cluster_threshold` anpassen (0.25 = mehr Sprecher, 0.4 = weniger) |
| Halluzinierte Sätze bei Stille | `silence_threshold` erhöhen (z. B. 0.02), Mikrofonpegel prüfen |
| LLM antwortet abgeschnitten | `llm_num_ctx` erhöhen (Modell muss das Kontextfenster unterstützen) |
| Modell mit Denkmodus (qwen3, gpt-oss) antwortet langsam | Der Client sendet `think: false`; alternativ ein Modell ohne Denkmodus wählen |

---

## ⚖️ Regulatorischer Hinweis

Die Funktionen **Patientenanalyse** und **Dokumentenbefragung** bleiben deaktiviert. Sie könnten dazu führen, dass die Software regulatorisch als **Medizinprodukt** (Software as a Medical Device, SaMD) eingestuft wird. Der Funktionsumfang beschränkt sich auf Dokumentations- und Transkriptionshilfen sowie einfache Zusammenfassungen.

> **Entscheidungsgrundlage:** MDR (EU) 2017/745

---

## ⚠️ Disclaimer / Haftungsausschluss

> **Transkription & Dokumentation:** Transkripte, Sprecherzuordnungen und KI-generierte Dokumentationen sind vom behandelnden Arzt/Ärztin auf Vollständigkeit und Richtigkeit zu überprüfen. Dieses Programm dient lediglich als Dokumentationshilfe und darf die ärztliche Behandlung nicht beeinflussen.

> **Arztbrief-Zusammenfassung:** Dient ausschließlich der schnelleren Orientierung und ersetzt nicht das sorgfältige Studium des Originaldokuments.

> **Nutzung auf eigene Gefahr – es wird keine Haftung übernommen.**

---

## 🗄️ Ältere Versionen

Die v1.x-Versionen (inkl. fertiger EXE-Dateien) liegen unter [Releases](https://github.com/lollylan/asklaion/releases); der frühere Repo-Inhalt (Archiv, n8n-Automatisierungen, Prompt-Sammlung) ist in der Git-Historie erhalten.

## 🤝 Mitwirken

Beiträge sind willkommen – siehe [CONTRIBUTING.md](CONTRIBUTING.md).

## 📄 Lizenz

[MIT](LICENSE)
