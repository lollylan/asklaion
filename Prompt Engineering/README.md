# Wie man den perfekten Prompt für medizinische SOAP-Berichte schreibt

Die Automatisierung medizinischer Dokumentation durch KI ist einer der nützlichsten Anwendungsfälle für Sprachmodelle (LLMs). Um aus einem rohen Transkript einer Arzt-Patienten-Interaktion einen strukturierten, klinisch präzisen Bericht nach dem **SOAP-Schema** zu generieren, benötigt man jedoch mehr als eine einfache Bitte.

Dieser Artikel erklärt, wie man einen robusten Prompt („Prompt Engineering“) für diesen Zweck entwickelt.

---

## 1. Das Ziel verstehen: Das SOAP-Schema

Bevor wir den Prompt schreiben, müssen wir definieren, was das Modell tun soll. Das SOAP-Schema ist der Goldstandard:

* **S – Subjektiv:** Was der Patient sagt (Symptome, Anamnese, Schmerzen).
* **O – Objektiv:** Was der Arzt misst oder sieht (Vitalparameter, Untersuchungsbefunde, Laborwerte).
* **A – Assessment (Beurteilung):** Die Diagnose oder klinische Einschätzung des Zustands.
* **P – Plan:** Weiteres Vorgehen, Medikamente, Überweisungen, Therapie.

**Die Herausforderung:** In einem Gespräch fließen diese Informationen durcheinander. Der Prompt muss das Modell anweisen, diese Informationen zu *extrahieren*, zu *sortieren* und in *Fachsprache* zu übersetzen.

---

## 2. Anatomie eines guten Medical-Prompts

Ein effektiver Prompt besteht aus vier Komponenten: **Rolle**, **Kontext/Aufgabe**, **Regeln** und **Output-Format**.

### A. Rolle (Persona)

Geben Sie der KI eine Identität. Das aktiviert den richtigen Wortschatz.

> *"Du bist ein erfahrener Facharzt für Innere Medizin und Experte für medizinische Dokumentation. Dein Ton ist professionell, objektiv und präzise."*

### B. Kontext & Aufgabe

Erklären Sie genau, was zu tun ist.

> *"Deine Aufgabe ist es, das folgende Transkript einer Arzt-Patienten-Interaktion zu analysieren und einen strukturierten klinischen Bericht nach dem SOAP-Schema zu erstellen."*

### C. Regeln (Constraints)

Hier verhindern Sie Halluzinationen und stellen Qualität sicher.

* **Keine Erfindungen:** *"Nutze ausschließlich Informationen aus dem Transkript. Wenn Informationen fehlen (z.B. keine Vitalwerte), erfinde nichts dazu."*
* **Sprache:** *"Verwende medizinische Fachterminologie (z.B. 'Dyspnoe' statt 'Atemnot'), wo angebracht."*
* **Stil:** *"Stichpunktartig und prägnant."*

### D. Output-Format

Strukturieren Sie das Ergebnis vor.

> *"Gib das Ergebnis im folgenden Markdown-Format aus:"* (gefolgt von einem Template).

---

## 3. Der "Master-Prompt" (Vorlage)

Hier ist ein Template, das Sie kopieren und anpassen können.

```text
### ROLLE
Du bist ein KI-Assistent für medizinische Dokumentation. Du agierst wie ein erfahrener Arzt. Du bist präzise, sachlich und verlässlich.

### AUFGABE
Erstelle basierend auf dem untenstehenden Transkript einen SOAP-Bericht.

### ANLEITUNG ZU DEN SEKTIONEN
1. **SUBJEKTIV (S):** Fasse die aktuellen Beschwerden, die Krankengeschichte und die Aussagen des Patienten zusammen. Zitiere wörtlich, wenn es um spezifische Schmerzbeschreibungen geht.
2. **OBJEKTIV (O):** Liste alle objektiven Befunde auf, die im Gespräch erwähnt wurden (Vitalparameter, Ergebnisse der körperlichen Untersuchung, Beobachtungen des Arztes). Wenn keine Werte genannt wurden, lasse diesen Bereich leer oder schreibe "Nicht erwähnt".
3. **ASSESSMENT (A):** Nenne die Diagnose(n) oder Verdachtsdiagnosen, die der Arzt im Gespräch geäußert hat.
4. **PLAN (P):** Liste alle vereinbarten Maßnahmen auf (Medikation mit Dosierung, Überweisungen, Wiedervorstellungstermine, Verhaltenshinweise).

### REGELN
- Verwende professionelle medizinische Fachsprache.
- Füge KEINE Informationen hinzu, die nicht im Text stehen.
- Wenn eine Information unklar ist, ignoriere sie lieber als zu raten.
- Anonymisiere Namen (nutze "Patient" und "Arzt").

### INPUT TRANSKRIPT
"""
{{HIER TRANSKRIPT EINFÜGEN}}
"""

### GEWÜNSCHTES FORMAT
**S - Subjektiv:**
- ...

**O - Objektiv:**
- ...

**A - Assessment:**
- ...

**P - Plan:**
- ...
```

---

## 4. Beispiel aus der Praxis

**Input (Transkript-Ausschnitt):**

> *Arzt: "Guten Tag, was führt Sie her?"*
> *Patient: "Ich habe seit drei Tagen so ein Brennen beim Wasserlassen und muss ständig zur Toilette."*
> *Arzt: "Haben Sie Fieber?"*
> *Patient: "Nein, nicht gemessen, aber ich fühle mich nicht heiß."*
> *Arzt: "Okay, ich klopfe mal die Nierenlager ab... Tut das weh?"*
> *Patient: "Nein."*
> *Arzt: "Gut, die Nierenlager sind frei. Ich verschreibe Ihnen Fosfomycin, das ist ein Einmal-Antibiotikum. Trinken Sie das heute Abend. Wenn es in 2 Tagen nicht besser ist, kommen Sie wieder."*

**Output (durch den Prompt generiert):**

**S - Subjektiv:**

- Patient berichtet über Dysurie ("Brennen beim Wasserlassen") und Pollakisurie ("ständig zur Toilette") seit 3 Tagen.
- Verneint subjektives Fieber.

**O - Objektiv:**

- Nierenlager klopfschmerzfrei (NL frei).

**A - Assessment:**

- Verdacht auf unkomplizierte Zystitis (Harnwegsinfekt).

**P - Plan:**

- Medikamentös: Fosfomycin (Einmalgabe) verordnet.
- Wiedervorstellung bei Persistenz der Beschwerden in 2 Tagen.

---

## 5. Wichtige Hinweise zum Datenschutz

Beim Umgang mit echten Patientendaten und LLMs (wie ChatGPT oder Claude) ist äußerste Vorsicht geboten:

1. **PII Entfernung:** Entfernen Sie **vor** dem Einfügen in den Prompt alle direkt identifizierenden Daten (Namen, Geburtsdaten, Telefonnummern).
2. **Lokale LLMs:** Für den klinischen Einsatz empfiehlt sich die Nutzung lokaler Modelle oder DSGVO-konformer Enterprise-Lösungen, um sicherzustellen, dass keine Patientendaten zum Training der KI verwendet werden.
