# Askl-AI-on | n8n-Workflows

Dieses Modul enthält automatisierte Arbeitsabläufe (Workflows) für die Low-Code-Plattform **n8n**. Diese dienen dazu, administrative Prozesse in der Hausarztpraxis zu verknüpfen und zu automatisieren, wobei die volle Datenhoheit lokal gewahrt bleibt.

---

## 📋 Überblick

n8n fungiert in diesem Projekt als die zentrale Logikschicht. Es verbindet Ihre lokalen Dateien (z. B. Fax-Eingänge oder Scans) mit lokalen KI-Modellen (z. B. über Ollama), um Aufgaben ohne manuellen Aufwand zu erledigen.

**Kernvorteile für die Praxis:**

* **Datenschutz:** Alle Daten werden innerhalb Ihres Praxisnetzwerks verarbeitet.
* **Interoperabilität:** Einfache Anbindung von Netzlaufwerken und lokalen APIs.
* **Transparenz:** Jeder Automatisierungsschritt ist im Workflow visuell nachvollziehbar.

---

## 🛠️ Installation

Für den Einsatz in der medizinischen Umgebung ist der Betrieb als **selbstgehostete Instanz (Self-hosted)** zwingend erforderlich, um die DSGVO-Konformität zu gewährleisten.

Detaillierte Installationsanleitungen für verschiedene Betriebssysteme (Docker, Windows, Linux) finden Sie in der offiziellen Dokumentation:

👉 **[n8n Hosting & Installation Documentation](https://docs.n8n.io/hosting/)**

*Empfehlung: Nutzen Sie n8n idealerweise in einer Docker-Umgebung auf demselben System, auf dem auch Ihre lokalen KI-Modelle laufen, um Latenzen zu minimieren.*

---

## 📥 Import der Workflows

Die hier angebotenen Automatisierungen werden als vorkonfigurierte `.json`-Dateien bereitgestellt. Sie können diese einfach importieren:

1. Laden Sie die gewünschte Workflow-Datei (`.json`) aus den Unterordnern herunter.
2. Öffnen Sie Ihre n8n-Instanz im Browser.
3. Wählen Sie im Menü (Drei Punkte oben rechts) die Option **"Import from File"** (oder nutzen Sie `Strg + O`).
4. Wählen Sie die Datei aus.
5. **Anpassung:** Nach dem Import müssen Sie lediglich die lokalen Pfade (z. B. den Ordner Ihres Fax-Eingangs) und ggf. Ihre Anmeldedaten in den jeweiligen Modulen (Nodes) hinterlegen.

---

## 📂 Verfügbare Automatisierungen

Je nach gewünschtem Anwendungsfall finden Sie die Dateien und spezifischen Anleitungen in den folgenden Unterordnern:

| Bereich | Beschreibung | Zielsetzung |
| --- | --- | --- |
| **/Faxumbenennung** | Automatische Analyse und Umbenennung von PDF-Dokumenten. | Ordnung im digitalen Posteingang. |
| **/Briefzusammenfassung** | Extraktion relevanter Informationen aus Arztbriefen. | Schnellere Übernahme in das PVS. |

---

> **Sicherheitshinweis:** Überprüfen Sie nach jedem Import eines Workflows, ob die Berechtigungen der Ordnerzugriffe korrekt gesetzt sind. Stellen Sie sicher, dass keine Cloud-Nodes versehentlich aktiviert werden, falls Sie strikt lokal arbeiten möchten.