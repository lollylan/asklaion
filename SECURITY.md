# Sicherheitsrichtlinie & Datenschutz

## Unsere Philosophie: Local-First

Die Sicherheit von Patientendaten hat bei **Askl-AI-on** oberste Priorität. Um dies zu gewährleisten, verfolgen alle in diesem Repository enthaltenen Lösungen und Skripte das "Local-First"-Prinzip:

1.  **Keine Cloud-Übertragung:** Sensible Audio- und Textdaten werden niemals an uns oder Dritte (z.B. OpenAI, Anthropic, Google) gesendet, es sei denn, Sie konfigurieren dies explizit anders (nicht empfohlen für Patientendaten).
2.  **On-Premise:** Die Verarbeitung findet ausschließlich auf Ihrer lokalen Hardware (in Ihrer Praxis) statt.
3.  **Transparenz:** Der gesamte Code ist Open Source und kann jederzeit überprüft werden.

## Meldung von Sicherheitslücken

Sollten Sie eine Sicherheitslücke oder ein Datenschutzproblem entdecken, bitten wir Sie dringend, dies **nicht** öffentlich als Issue zu melden, sondern uns direkt zu kontaktieren, um eine vertrauliche Behebung zu ermöglichen (Responsible Disclosure).

Da dieses Projekt derzeit von einer Einzelperson betreut wird:
- Senden Sie bitte eine E-Mail an [florian.rasche@googlemail.com].
- Beschreiben Sie das Problem so detailliert wie möglich.

## Haftungsausschluss

**WICHTIG:** Dieses Repository stellt **kein Medizinprodukt** dar.
- Die Nutzung erfolgt auf eigene Gefahr.
- Sie sind als Anwender selbst dafür verantwortlich, die Einhaltung der geltenden Datenschutzgesetze (DSGVO, ärztliche Schweigepflicht) sicherzustellen.
- Überprüfen Sie regelmäßig, ob Ihre lokalen KI-Modelle keine Daten ungewollt speichern oder trainieren (bei Ollama/OpenWebUI sind dies Standardeinstellungen, die Sicherheit bieten, aber verifiziert werden sollten).
- Führen Sie regelmäßige Sicherheitsupdates Ihrer Host-Systeme durch.
