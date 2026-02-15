# Transkription des Arzt-Patienten-Gespräches

Um ein Arzt-Patienten-Gespräch transkribieren zu können ist eines erst einmal essentiell: Die Einverständnis des Patienten, am Besten schriftlich. Wie man das in seinen Praxisalltag einbaut hängt sehr von den jeweiligen Praxisabläufen ab, aber ein Mikrophon im Sprechzimmer ohne die ausdrückliche Einverständnis des Patienten zu starten ist selbstverständlich nicht nur ethisch verwerflich, sondern auch schlicht illegal.

Es gibt mehrere Wege, an ein Transkript zu kommen, zunächst wird die in Open WebUI eingebaute Variante gezeigt, im Verlauf wird ein selbstgeschriebenes Skript veröffentlich, das den Ablauf beschleunigt und einige Vorteile birgt.

## Transkription nativ in Open WebUI

[![Thumbnail](https://img.youtube.com/vi/OCLHo8SxCDU/maxresdefault.jpg)](https://youtu.be/OCLHo8SxCDU)

## Transkription mit Python-Script

In den beiden Unterordnern "Gleiches Gerät" findet sich ein Pythonscript (Python 3.8.x benötigt), das ein Gespräch "in Echtzeit" in 30 Sekunden-Abschnitten transkribiert, sodass ein Teil der Arbeit bereits während des Gespräches passiert, in "Server und Client" finden sich die entsprechenden Scripte, wenn man einen zentralen Server zur Berechnung nutzen will. In letzterem Fall muss man das Server oder das ServerFasterWhisper Script auf dem Server starten und auf dem Client die Client-Datei, nachdem man die IP-Adresse des Servers im Script (einfach mit dem Editor öffnen) bearbeitet hat.