# Verbesserungsbericht: Dashboard-Erweiterungen

**Stand: 18. November 2026.** Dieser Bericht dokumentiert die
Review-Verbesserungen für die acht Erweiterungen.

## Kurzfazit

Die im Review reproduzierten Probleme wurden an ihren Datenquellen bzw.
Darstellungen behoben. Die Aufstiegsauswertung läuft chronologisch ab D über
alle Standard-Turniere, unabhängig von der dort gespeicherten Startklasse.
Die separaten Orts- und Vereinsauswertungen bleiben erhalten.

## Behobene Befunde

### Tanzprofil: Heatmap-Auswahl und Belegzuordnung

Streamlit liefert bei der Zellenauswahl den Spaltennamen statt eines
Spaltenindex. Die Heatmap verwendet jetzt die Spaltenbezeichnung direkt und
führt den Zeilenindex auf die Event-ID zurück. Der Beleg wird über Event-ID,
Runde und Tanz ermittelt. Ein AppTest klickt eine Heatmap-Zelle und prüft die
Beleganzeige.

### Aufstieg: Startklasse und dokumentierte Grenzen

Die Fortschrittsberechnung startet in D und verarbeitet Standard-Turniere
chronologisch, auch wenn ein Turnier eine andere Startklasse ausweist. Punkte
und qualifizierende Platzierungen zählen bis zum Erreichen beider Grenzen;
das nächste Turnier wird der nächsten Stufe zugerechnet. LM- und OT-Ergebnisse
werden gemeinsam gezählt. Latein wird nicht für Standard-Grenzen verwendet.
Für S wird keine nicht dokumentierte nächste Grenze angenommen.

### Runden und Konstanz: Finalstatus und Kreuzgrenzen

Finalteilnahme, Ausscheiden und unbekannter Finalstatus werden getrennt
ausgewiesen. Eine Finalqualifikation ohne Finalergebnis zählt nicht als
Finalteilnahme. Widersprüchliche Kreuzdaten unterdrücken auch Grenze und
Abstand. Ein Regressionstest prüft die Finalqualifikation ohne Finalbeleg.

### Vereine: Doppelte Ranglistenzeilen

Gegnerbelege werden pro Event und Paar dedupliziert. Widersprüchliche
Ranglistenzeilen gelten als unbekannt statt willkürlich aufgelöst. Die
Vereinsansicht kann für einen Verein die Begegnungen und Ergebnisse gegen
dessen Paare zeigen.

## Weitere umgesetzte Verbesserungen

| Bereich | Umsetzung |
|---|---|
| Konstanz / Runden | Finalstatus und auswertbare Stichproben für Kreuzraten werden in der Übersicht dargestellt; Runden werden nicht künstlich ergänzt. |
| Tanzprofil | Streuung ist nach Klasse, Disziplin und Runde getrennt; Zeitabschnitte verwenden gemeinsame Datumsgrenzen und zählen Events. |
| Datenqualität | Probleme sind über Event-ID, Prüfcode und Schweregrad zugeordnet. Abdeckung enthält Kreuzgrenzen, Richter und Parserstand; undatierte ausgeblendete Starts werden gezählt. |
| Richterpanel | Zeitverläufe und Auswertungen sind nach Wertungsart, Tanz bzw. Runde getrennt. |
| Turnierorte | Unbekannter Ort hat einen eigenen Schlüssel und wird vom Vergleich ausgeschlossen. Für einen auswertbaren Start wird keine Spannweite ausgegeben. |

## Einschränkungen

Die Archivdaten enthalten keine explizite Aufstiegshistorie. Die angezeigte
chronologische Leiter ist daher eine Berechnung ab D und kein Nachweis eines
offiziellen Aufstiegs. Die dokumentierten Aufstiegsgrenzen liegen nur für
Standard vor; undatierte Starts können nicht chronologisch zugeordnet werden.

**Validierung:** Die vollständige Testsuite, `ruff check` und der
Format-Check aller geänderten Python-Dateien sind erfolgreich.
