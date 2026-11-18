# Mögliche Erweiterungen und Priorisierung

Diese Übersicht bewertet den Nutzen, die Umsetzbarkeit und die tatsächliche
Datenbasis der möglichen Erweiterungen. Vorrang haben Funktionen, die sich aus
den bereits archivierten Ergebnissen nachvollziehbar berechnen lassen. Fehlende
Werte und kleine Stichproben müssen weiterhin sichtbar bleiben.

Interaktive HTML-Mockups zu allen acht Erweiterungen sind über
[die Mockup-Übersicht](mockups/erweiterungen.html) aufrufbar. Die Entwürfe
verwenden fiktive, aber zur vorhandenen Datenlage passende Beispielwerte.

## Kurzbewertung

| Rang | Erweiterung | Nutzen | Umsetzbarkeit | Empfehlung |
|---:|---|---:|---:|---|
| 1 | Konstanz messen | hoch | hoch | Als Nächstes auf der Entwicklungsseite ergänzen |
| 2 | Rundenschwächen identifizieren | hoch | hoch | Aggregierte Weiterkommensanalyse ergänzen |
| 3 | Leistungsprofil je Tanz | hoch | mittel-hoch | Bestehende Tanzseite gezielt ausbauen |
| 4 | Datenqualität überwachen | mittel-hoch | mittel-hoch | Qualitätslogik ausbauen und Probleme sichtbar machen |
| 5 | Richterpanel verstehen | mittel | mittel | Auf ausgewählte, gut belegte Vergleiche begrenzen |
| 6 | Aufstieg planen | hoch | mittel | Mit den dokumentierten Grenzen nachvollziehbar umsetzen |
| 7 | Turnierorte vergleichen | mittel-hoch | mittel | Ortsübersicht umsetzen |
| 8 | Vereine und Begegnungen vergleichen | mittel-hoch | mittel | Vereinsübersicht mit Paar-Detailansicht umsetzen |
| — | Platzierungsprognosen | zunächst zurückstellen | niedrig | Nicht Teil der aktuellen Erweiterungsplanung |

Die Bewertungen beziehen sich auf den derzeitigen Archivbestand, nicht auf alle
historisch verfügbaren Turniere. Im geprüften Archiv lagen 85 Quellseiten, 559
Ranglisteneinträge, 1.193 Rundenergebnisse und 3.620 Richterwertungen. Für das
primär ausgewertete Paar ergaben sich 13 Turniere, davon 12 mit normierter
Endplatzierung, 28 Runden, 43 Tanzplatzierungen und 13 Punkteeinträge. Es gab
15 bekannte Qualifikationsentscheidungen bei 16 relevanten Vorrunden; eine
Kreuzgrenze war für 6 dieser 16 Runden berechenbar.

Das Archiv enthält Daten zu weiteren Paaren und Vereinen, ist aber kein
vollständiger Saisonbestand für alle Paare. Das Dashboard importiert gezielt
Turniere des ausgewählten Paares. Andere Paare sind daher nur für die
Turniere sichtbar, an denen sie gemeinsam mit dem ausgewählten Paar erfasst
wurden.

## 1. Konstanz messen

**Nutzen: hoch · Umsetzbarkeit: hoch · Priorität: sofort**

Die Entwicklungsseite zeigt bereits den normierten Platz im Zeitverlauf und
den Durchschnitt. Mit den vorhandenen Einzelergebnissen können ergänzend
berechnet werden:

- Median, bester und schwächster normierter Platz
- Streuung oder Interquartilsabstand als Maß der Ergebnisschwankung
- Anteil der Turniere mit Finalteilnahme
- Anteil der bekannten Vorrunden, die überstanden wurden
- Vergleich der letzten drei Starts mit dem gesamten ausgewählten Zeitraum

Die Werte sollen jeweils mit der Stichprobengröße angezeigt werden. Bei wenigen
Turnieren sollte das Dashboard keine belastbar klingende Einstufung wie
„konstant“ oder „instabil“ vornehmen. Die Kennzahlen gehören zunächst auf die
bestehende Seite „Entwicklung“; eine eigene Seite ist nicht erforderlich.

## 2. Rundenschwächen identifizieren

**Nutzen: hoch · Umsetzbarkeit: hoch · Priorität: sofort**

Das Archiv enthält bereits Runde, Kreuzrate, Qualifikationsstatus und – wenn
vollständig berechenbar – Kreuzgrenze und Abstand. Die Einzelturnieransicht
zeigt diese Daten bereits. Die Erweiterung fasst sie über den gewählten
Zeitraum zusammen:

- Trichter von Starts über Vorrunde und Zwischenrunde bis zum Finale
- Teilnahmen, bekannte Weiterkommen, Ausscheiden und unbekannte Fälle je Runde
- Weiterkommensquote mit ausgewiesener Stichprobengröße
- durchschnittliche Kreuzrate je Rundentyp
- Grenzabstand und Zahl der Runden, für die eine Grenze tatsächlich berechnet
  werden konnte

Eine Runde gilt nur dann als knapp, wenn die zugehörige Grenze bekannt ist.
Da im geprüften Bestand erst 6 von 16 relevanten Runden eine berechenbare
Kreuzgrenze hatten, muss diese Abdeckung direkt neben der Auswertung stehen.
Unbekannte Qualifikationen und Grenzen dürfen weder als Ausscheiden noch als
Weiterkommen gezählt werden.

## 3. Leistungsprofil je Tanz

**Nutzen: hoch · Umsetzbarkeit: mittel-hoch · Priorität: danach**

Die vorhandene Tanzseite bietet bereits feldgrößen-normalisierte Platzierungen,
Startklassenvergleiche, Stichprobenumfänge, Zeitverläufe und Kreuzraten nach
Runde. Mit 43 Tanzplatzierungen im geprüften Paarbestand besteht eine
brauchbare, aber weiterhin begrenzte Grundlage.

Sinnvolle Ergänzungen:

- Median und Streuung je Tanz
- Heatmap je Tanz und Turnier
- Entwicklung je Tanz in älteren und neueren Saisonabschnitten
- Unterschied zwischen Vor-/Zwischenrunde und späteren Runden, sofern die
  Werte vergleichbar und ausreichend vollständig sind
- Kennzeichnung von Stärke, durchschnittlichem Bereich, schwächeren Ergebnissen
  und unzureichender Datenmenge – zunächst beschreibend, nicht als
  Trainingsdiagnose

Alle Vergleiche brauchen Stichprobengrößen und sollten Startklasse, Disziplin
und Runde nicht unbemerkt vermischen. Automatische Trainingsanweisungen sind
nicht vorgesehen.

## 4. Datenqualität überwachen

**Nutzen: mittel-hoch · Umsetzbarkeit: mittel-hoch · Priorität: begleitend**

Die Analyse meldet bereits bestimmte Qualitätsprobleme, etwa widersprüchliche
Kreuzsummen. Eine umfassendere Übersicht könnte je Turnier prüfen:

- fehlendes Datum oder fehlender Ort
- fehlende Endplatzierung oder Feldgröße
- fehlende Rundendaten oder unbekannte Stimmenzahl
- unbekannter Qualifikationsstatus oder nicht berechenbare Kreuzgrenze
- fehlende Richterliste oder Einzelwertungen
- veraltete Parserfassung
- Quellen, die für aktuellere oder vollständigere Ergebnisse erneut eingelesen
  werden sollten

Die Ansicht sollte Problemzahl, betroffene Turniere, Quellenlink und einen
konkreten nächsten Schritt anzeigen. „Nicht verfügbar“ ist dabei nicht immer
ein Fehler: Die Übersicht muss zwischen nachweislich fehlerhaften,
unvollständigen und aus der Quelle schlicht nicht gelieferten Daten
unterscheiden. Die Datenqualitätslogik sollte bereits bei den anderen
Erweiterungen mitentwickelt werden.

## 5. Richterpanel verstehen

**Nutzen: mittel · Umsetzbarkeit: mittel · Priorität: gezielte Vertiefung**

Die Richterseite vergleicht bereits feldgrößen- beziehungsweise
rundennormalisierte Wertungen mit dem übrigen Panel und zeigt Belege sowie
Stichprobengrößen. Im geprüften Bestand gab es 295 verwendbare Vergleiche,
verteilt auf 38 Richter. Die Gesamtmenge klingt groß, verteilt sich jedoch auf
viele einzelne Richter und Kontexte.

Sinnvolle, begrenzte Ergänzungen:

- zeitlicher Verlauf eines ausgewählten Richters
- Aufteilung nach Tanz und Runde
- Streuung der Abweichung und Zahl der gemeinsamen Panels
- deutliche Kennzeichnung kleiner Stichproben

Auf umfassende Richterrankings oder Aussagen zu Bevorzugung sollte verzichtet
werden. Angezeigt werden relative Abweichungen und Übereinstimmung mit dem
Panel, keine Motive oder kausalen Erklärungen.

## 6. Aufstieg planen

**Nutzen: hoch · Umsetzbarkeit: mittel · Priorität: nach Regelklärung**

Das Archiv enthält bereits erkannte Punkte und Platzierungsangaben; die
Punkteseite summiert gespeicherte Werte nach Startgruppe, Disziplin und
Punktart. Im geprüften Bestand lagen 13 Punkteinträge vor. Die vom Nutzer in
[`punkte_und_platzierungen.md`](punkte_und_platzierungen.md) dokumentierten
Grenzen sind:

| Aufstieg in | Punkte | Erforderliche Platzierungen |
|---|---:|---|
| C | 100 | 7 Platzierungen auf Rang 1–6 |
| B | 100 | 7 Platzierungen auf Rang 1–5 |
| A | 150 | 7 Platzierungen auf Rang 1–3 |
| S | 200 | 10 Platzierungen auf Rang 1–3 |

Punkte und Platzierungen sind getrennte Voraussetzungen; beide müssen für
einen belegten Aufstieg erfüllt sein. Platzierungen außerhalb des jeweiligen
Rangbereichs zählen nicht. Die Anwendung soll die dokumentierten Werte
verwenden und ihre Datenquelle sowie den Regelstand sichtbar machen. Ein
offizieller Verband, Gültigkeitszeitraum und eine Quellen-URL sind in der
Regeldatei nicht angegeben und dürfen nicht hinzuerfunden werden.

Erste Ausbaustufe:

- gespeicherte Punkte nach Punktart und Platzierungen nach Disziplin
- Fortschrittsleiter ab D über chronologische Standard-Turniere, unabhängig
  von der Startklasse des jeweiligen Turniers; LM und OT zusammenfassen
- Zielwerte aus den dokumentierten Aufstiegsgrenzen
- sichtbarer Fortschritt und Liste der je Stufe zugerechneten Turniere
- Kennzeichnung unvollständiger oder nicht eindeutig zuordenbarer Einträge

Das Dashboard unterscheidet zwischen „belegt erreicht“, „nicht erreicht“ und
„nicht beurteilbar“. Unvollständig zugeordnete Punkte oder Platzierungen
bleiben ungeklärt und werden nicht geschätzt. Solange Verband und
Gültigkeitszeitraum nicht belegt sind, muss die Ansicht darauf hinweisen, dass
die dargestellten Grenzen dem dokumentierten Regelstand entsprechen.

## 7. Turnierorte vergleichen

**Nutzen: mittel-hoch · Umsetzbarkeit: mittel · Priorität: nach den
paarbezogenen Auswertungen**

Eine Ortsübersicht soll beantworten: „Wie waren unsere Ergebnisse in
Norderstedt, wie in Hannover?“ Pro Ort können zusammengefasst werden:

- Zahl der Turniere und Starts
- durchschnittlicher normierter Platz und Streuung
- beste Ergebnisse und erreichte Runden
- Weiterkommensquoten, jeweils mit Datenumfang
- Zeitraum der berücksichtigten Ergebnisse

Der Turnierort ist im Archiv bereits als Turniermetadatum vorhanden. Die
Auswertung ist daher technisch relativ direkt umsetzbar. Sie beschreibt die
bisherigen Ergebnisse an diesen Orten; sie belegt nicht, dass der Ort selbst
die Ursache eines Leistungsunterschieds ist. Startklasse, Disziplin,
Feldgröße und kleine Stichproben müssen bei Vergleichen sichtbar bleiben.

## 8. Vereine und Begegnungen vergleichen

Die Ranglisten enthalten Paar- und Vereinsnamen. Im geprüften Archiv waren
45 verschiedene Vereinsnamen vorhanden. Eine Vereinsauswertung soll unabhängig
vom Turnierort funktionieren: Sie benötigt weder eine Vereins-zu-Ort-Zuordnung
noch einen Regionsfilter. Die Übersicht zeigt pro erfasstem Verein die Zahl
der angetroffenen Paare und gemeinsamen Turniere sowie die Bilanz der
vergleichbaren Begegnungen. Paar- und Begegnungszahlen bleiben sichtbar,
damit mehrere Paare eines Vereins nicht als eine einzelne Begegnung
missverstanden werden.

Beim Klick auf einen Verein öffnet sich dessen Detailansicht mit den Paaren
dieses Vereins, denen das ausgewählte Paar bereits begegnet ist. Pro Paar
werden die gemeinsamen Turniere und die direkte Bilanz angezeigt:

- Begegnungen, bei denen das ausgewählte Paar besser platziert war
- Begegnungen, bei denen das Vereinspaar besser platziert war
- Gleichstände und nicht vergleichbare beziehungsweise unbekannte Ergebnisse
- letzte gemeinsame Begegnung und nachvollziehbare Turnierergebnisse

Einzelne Paare können innerhalb der Detailansicht ausgewählt werden, um ihre
Begegnungen und Bilanz über den erfassten Zeitraum zu prüfen. Verglichen
werden nur belegte gemeinsame Turniere in derselben Startklasse und
Disziplin. Überlappende Platzbereiche und fehlende Werte bleiben unbekannt;
Gleichstände werden separat gezählt. Die Vereinsbilanz fasst diese
Paarbegegnungen zusammen und ist kein allgemeines Vereinsranking.

Da das Archiv nur Turniere des ausgewählten Paares gezielt erfasst, bildet
diese Auswertung nicht die vollständige Saisonleistung aller Vereine ab.
Ausgewiesene Nenner und Datenabdeckung sind daher zwingend. Ortsstatistiken
und Vereinsbegegnungen sind getrennte Features und dürfen nicht voneinander
abhängen.

## Zurückgestellt: Platzierungsprognosen

Platzierungsprognosen werden vorerst nicht umgesetzt. Sie bräuchten eine
größere und vollständigere Datenbasis sowie ein transparentes, überprüfbares
Modell. Die bestehenden historischen Vergleiche sind keine Prognose für das
nächste Turnier.

## Empfohlene Reihenfolge

1. Konstanzkennzahlen auf der vorhandenen Entwicklungsseite ergänzen.
2. Rundentrichter, Quoten und bekannte Grenzabstände über den Zeitraum
   zusammenfassen.
3. Datenqualitätsprüfungen und Stichprobenhinweise für diese Auswertungen
   mitführen.
4. Tanzprofil um Streuung, Heatmap und zeitliche Vergleiche erweitern.
5. Richteranalyse nur um gut belegte Aufteilungen und Verläufe ergänzen.
6. Die dokumentierten Aufstiegsgrenzen mit sichtbarer Regelherkunft abbilden.
7. Ortsübersicht erstellen.
8. Vereinsübersicht und anklickbare Paar-Detailbilanzen ergänzen.

Für neue Kennzahlen gelten weiterhin die bestehenden Grundsätze: Rohbelege
und Quellen sollen nachvollziehbar sein, Stichproben müssen sichtbar sein, und
fehlende oder widersprüchliche Werte werden nicht geschätzt.

## Implementierungspläne

Die Mockups geben Aufbau und Interaktionen vor, nicht die Kennzahlen oder
Schwellenwerte. Jeder Plan ist als eigenes Änderungspaket umsetzbar: zuerst
Berechnung und Belege, dann Streamlit-Ansicht und Abnahme.

**Umsetzungsstand:** Eine erste Implementierungsstufe für alle acht Features
ist in den Dashboard-Seiten verfügbar. Die Aufstiegsseite zeigt Fortschritt
gegen die dokumentierten Grenzwerte nur als Orientierung: Startgruppen- und
Punktartzuordnung, Saisonbezug, Mehrfachstarts, Verband und Gültigkeitszeitraum
sind nicht belegt; daher stellt sie keinen Aufstiegsstatus fest. Datenqualität
meldet nur anhand der archivierten Felder nachweisbare Lücken und
Widersprüche; ein vergleichbarer Parserstand ist im Archiv nicht gespeichert.

### Gemeinsame Grundlage

- Den bestehenden Analysekontext in [`etl/common.py`](../etl/common.py)
  verwenden: Paar, Startgruppe, Disziplin und Zeitraum gelten für alle
  neuen Ansichten. Zusätzliche Auswahlen (z. B. Verein oder Tanz) bleiben
  lokal auf der Seite. Aggregationen beziehen sich auf dieselbe gefilterte
  Menge wie ihre Detailtabellen.
- Fachlogik ohne Streamlit in [`etl/data.py`](../etl/data.py) oder in kleinen
  zugehörigen Analysemodulen halten; Normalisierung, Rundenbegriffe und
  Platzierungsvergleich aus [`etl/domain.py`](../etl/domain.py) wiederverwenden.
  Detailzeilen über die bestehende Event-ID verbinden, nicht über
  Turniertitel oder Ort. Ein Event bezeichnet hier einen Start in einer
  Turnierkonkurrenz; mehrere importierte Quellseiten sind kein zweiter Start.
- Pro Kennzahl auswertbare Beobachtungen und Gesamtnenner unterscheiden.
  Fehlendes nicht als null Treffer behandeln, bei Nenner null keine Quote
  anzeigen. Belege mit Datum, Turnier, Kontext und vorhandenen Quellen
  angeben. Für die erste Ausbaustufe keine Archivmigration einplanen.
- Berechnungen mit Fixtures in
  [`tests/test_dashboard_data.py`](../tests/test_dashboard_data.py) bzw.
  [`tests/test_turnier_domain.py`](../tests/test_turnier_domain.py) absichern.
  Neue Navigation und zentrale Interaktionen mit Streamlit-AppTests in
  [`tests/test_dashboard_navigation.py`](../tests/test_dashboard_navigation.py)
  prüfen. Vor Abschluss der Implementierung die bestehende Suite mit
  `uv run --locked python -m unittest discover -s tests -v` ausführen.

### Plan 1 – Konstanz

[Mockup](mockups/erweiterung_01_konstanz.html) ·
Zielseite: [Entwicklung](../dashboard_pages/overview.py).

1. Aus `normalized_place` Median, Quartile, Interquartilsabstand (Q3 − Q1)
   sowie bestes und schwächstes Ergebnis berechnen. Für die Form den Median
   der letzten drei **datierten Starts** dem Median des gefilterten
   Zeitraums gegenüberstellen; fehlende Werte innerhalb dieser drei Starts
   nicht durch ältere Starts ersetzen.
2. Kennzahlen und Quartilsband in den bestehenden Verlauf integrieren.
   Finalquote aus belegten Finalteilnahmen bzw. belegtem Ausscheiden
   berechnen; unbekannte Verläufe separat ausweisen. Die Weiterkommensquote
   der Vorrunde aus Plan 2 übernehmen, sobald sie verfügbar ist.
3. Belegtabelle um Abweichung vom Median ergänzen. Unvollständige letzte
   drei Starts und kleine Stichproben kennzeichnen; keine automatische
   Einstufung als „konstant“ oder „instabil“.

**Abnahme:** Ein Start ohne normierten Platz verändert den Median nicht,
bleibt aber im Startnenner sichtbar. Drei letzte Starts mit einem fehlenden
Wert ergeben im Formvergleich `2/3` auswertbare Starts. Undatierte Starts
fließen nicht in die Auswahl der letzten drei ein.

### Plan 2 – Rundenschwächen

[Mockup](mockups/erweiterung_02_runden.html) ·
Zielseite: [Entwicklung](../dashboard_pages/overview.py), Belege im
[Turnierarchiv](../dashboard_pages/tournament_archive.py).

1. `rounds_by_event` nach Rundentyp zusammenfassen. Der Trichter zählt
   Events je belegter Stufe, die Rundentabelle tatsächlich erfasste Runden.
   Direkte Finalstarts und Lücken in der Rundenfolge sichtbar machen, statt
   fehlende Zwischenstufen zu ergänzen.
2. Weiter, ausgeschieden und unbekannt getrennt zählen. Quote =
   weiter / (weiter + ausgeschieden); Finale nicht als
   Qualifikationsentscheidung zählen. Kreuzraten nur mit bekanntem Nenner
   mitteln. Bekannte Kreuzgrenzen als `auswertbar / relevante Runden`
   ausweisen. „Knapp“ entspricht im ersten Schritt einem absoluten Abstand
   von höchstens zwei Kreuzen bei belegter, widerspruchsfreier Grenze.
3. Trichter, Rundentabelle und Belege für knappe Fälle einbauen. Quoten mit
   dem jeweiligen Nenner zeigen, kleine Stichproben nicht als gesicherten
   Engpass ausgeben.

**Abnahme:** Bei zwölf Weiterkommen, drei ausgeschiedenen und einer
unbekannten Runde lautet die Quote `12/15`, nicht `12/16`. Zwei
Zwischenrunden eines Starts zählen im Trichter einmal und in der
Rundentabelle zweimal. Ohne bekannte Grenze gibt es keinen knappen Fall.

### Plan 3 – Leistungsprofil je Tanz

[Mockup](mockups/erweiterung_03_tanzprofil.html) ·
Zielseite: [Tänze](../dashboard_pages/dance.py).

1. Die vorhandenen `dance_history_rows` für Median, Quartile und Stichprobe
   je Tanz nutzen. Anzahlen von Beobachtungen und Starts getrennt halten;
   Startklasse, Disziplin und Rundentyp im Analysekontext sichtbar halten.
2. Heatmap mit Event pro Zeile und Tanz pro Spalte bauen. Je Vergleich
   einen Rundentyp auswählen oder Runden getrennt abbilden, damit mehrere
   Beobachtungen pro Zelle nicht stillschweigend gemittelt werden. Fehlende
   Beobachtungen neutral markieren; Zellauswahl zeigt Ergebnis, Feldgröße
   und Quelle.
3. Frühere und spätere Abschnitte mit sichtbaren Zeitgrenzen und
   Stichproben vergleichen. Kreuzraten und normierte Platzierungen
   getrennt darstellen; Hinweise nur beschreibend, ohne Trainingsdiagnose.

**Abnahme:** Ein fehlender Tanz erscheint nicht als schlechtestes Ergebnis.
Zwei Wertungen desselben Tanzes in unterschiedlichen Runden bleiben
unterscheidbar. Die ausgewählte Zelle öffnet den passenden Beleg.

### Plan 4 – Datenqualität

[Mockup](mockups/erweiterung_04_datenqualitaet.html) ·
Zielseite: [Turnierarchiv](../dashboard_pages/tournament_archive.py).

1. Bestehende `quality_issues` um stabile Prüfcodes, Stufe, Event-ID,
   Beleg und empfohlenen nächsten Schritt erweitern. Zuerst fehlendes Datum
   oder Ort, Platzierung oder Feldgröße sowie widersprüchliche Kreuzdaten
   erfassen. Anschließend Runden-, Richter- und Parserabdeckung ergänzen.
   Einen alten Parserstand nur melden, wenn ein gespeicherter Stand mit
   `PARSER_VERSION` vergleichbar ist; sonst „Stand unbekannt“ anzeigen.
2. Widersprüche, unvollständige Angaben und nicht gelieferte Daten trennen.
   Abdeckungsquoten pro Datenart mit passendem Nenner berechnen; eine
   Kreuzgrenze ist beispielsweise nicht bei jedem Turnier sinnvoll
   erwartbar. Mehrere betroffene Quellseiten nicht als mehrere Turniere
   zählen.
3. Übersicht und priorisierte Prüfliste anzeigen. Jede Zeile führt zum
   Turnierbeleg oder zur Quelle und nennt eine passende Aktion, etwa
   Quellenprüfung oder erneutes Einlesen über den vorhandenen Erfassungsweg.
   Beim Öffnen der Übersicht wird nichts automatisch erneut importiert.

**Abnahme:** Platzierung fehlt, Kreuzsummen widersprechen sich und Quelle
liefert kein Richterpanel ergeben unterscheidbare Hinweise. Mehrere Hinweise
eines Events ändern die Zahl der betroffenen Events nicht.

### Plan 5 – Richterpanel

[Mockup](mockups/erweiterung_05_richterpanel.html) ·
Zielseite: [Wertungsrichter](../dashboard_pages/judges.py).

1. Auf `judge_evidence` aufsetzen. Die bestehende Referenz, den Median
   der **übrigen** Richter, unverändert lassen. Datum und Startkontext über
   `event_id` ergänzen. Abweichungen in Prozentpunkten ausgeben.
2. Für den gewählten Richter Verlauf, Aufteilung nach Tanz und Runde,
   Streuung und Zahl der Vergleiche bzw. Turniere anzeigen. Tanzplatzierung
   und Rundenkreuzrate getrennt auswerten. Als Startwert aus dem Mockup
   Gruppen mit weniger als drei Vergleichen nur als kleine Stichprobe
   kennzeichnen und nicht im Gruppenvergleich einordnen.
3. Quellenbelege beibehalten; keine pauschalen Richterrankings oder
   Aussagen über Absichten ableiten.

**Abnahme:** Ein Richter ohne vergleichbare übrige Panelwerte erzeugt
keinen Vergleich. Zwei Vergleiche reichen nicht für eine Gruppeneinordnung.
Ein Filterwechsel aktualisiert Verlauf, Nenner und Belege gemeinsam.

### Plan 6 – Aufstieg

[Mockup](mockups/erweiterung_06_aufstieg.html) ·
Zielseite: [Punkte & Plätze](../dashboard_pages/points.py).

1. Die Standard-Grenzen aus
   [`punkte_und_platzierungen.md`](punkte_und_platzierungen.md) als
   typisierte, nach Zielklasse adressierbare Regeln hinterlegen. Die
   Fortschrittsleiter beginnt in D und verarbeitet Standard-Turniere
   chronologisch, unabhängig von der gespeicherten Startklasse; LM- und
   OT-Wertungen werden gemeinsam berücksichtigt. Beim Erreichen beider
   Grenzen beginnt die nächste Klasse mit dem folgenden Turnier. Mangels
   Aufstiegshistorie ist dies eine Fortschrittsberechnung, kein offizieller
   Aufstiegsstatus.
2. Punkte aus `point_records` und Platzierungsnachweise aus den eindeutig
   zugeordneten Events getrennt ermitteln. Eine Platzierung je
   qualifizierendem Start zählen, nicht pro Quellseite. Vollständig innerhalb
   der Ranggrenze liegende Platzbereiche zählen, vollständig außerhalb
   liegende nicht; ein die Grenze überschneidender Bereich bleibt ungeklärt.
3. Bestehende Punktetabelle beibehalten und um Fortschrittsanzeigen,
   Regelquelle und Belege (zählt / zählt nicht / ungeklärt) ergänzen.
   „Belegt erreicht“ nur bei beiden nachweislich erfüllten Bedingungen
   und geklärter Regelzuordnung. Unterhalb einer Grenze nur dann „nicht
   erreicht“, wenn die Daten hierfür vollständig genug sind; sonst
   „nicht beurteilbar“. Keinen Verband oder Gültigkeitszeitraum annehmen.

**Abnahme:** Für Zielklasse C zählt Rang 6, Rang 7 nicht und Rang 6–7
bleibt ungeklärt. 100 Punkte und nur sechs von sieben erforderlichen
Platzierungen genügen nicht. Fehlende Zuordnung verhindert eine
Aufstiegsaussage; für B, A und S wird jeweils die eigene Regel verwendet.

### Plan 7 – Turnierorte

[Mockup](mockups/erweiterung_07_turnierorte.html) ·
Neue Seite „Turnierorte“, registriert in [`app.py`](../app.py).

1. Gefilterte Events anhand von `city` gruppieren. Leerzeichen und
   Groß-/Kleinschreibung vereinheitlichen, nicht belegte Ortsaliasse nicht
   zusammenführen. Fehlende Orte separat als „Ort unbekannt“ ausweisen
   und vom Vergleich benannter Orte ausschließen.
2. Pro Ort Starts, Zeitraum, Mittelwert und Spannweite des normierten
   Endplatzes, bestes Ergebnis, Feldgrößen, erreichte Runden und bekannte
   Weiterkommensquoten zusammenfassen. Die Rundendefinitionen aus Plan 2
   wiederverwenden, nicht neu berechnen. Starts und auswertbare Ergebnisse
   mit getrennten Nennern anzeigen.
3. Ortsübersicht mit Punkt/Spannweiten-Diagramm und auswählbarem
   Zwei-Orte-Vergleich erstellen. Klassen, Disziplin, Feldgrößen und
   Stichprobe sichtbar machen; bei einem Start keine Streuung oder
   belastbare Ortsrangfolge suggerieren.

**Abnahme:** Fehlender Ort wird separat gezählt, fehlender Endplatz
verändert den Mittelwert nicht. Ort A und Ort B lassen sich vergleichen,
ohne dass Vereinsdaten vorhanden sein müssen.

### Plan 8 – Vereine und Begegnungen

[Mockup](mockups/erweiterung_08_vereine.html) ·
Neue Seite „Vereine“, registriert in [`app.py`](../app.py).

1. Auf den einzelnen `opponent_evidence`-Zeilen der
   [Gegnerbilanz](../dashboard_pages/opponents.py) aufbauen und die dort
   noch fehlende `event_id` ergänzen. Pro Event und Gegnerpaar nur eine
   Begegnung zählen. Verein aus dem jeweiligen Starteintrag übernehmen,
   nicht aus der zusammengefassten Liste aller früheren Vereine eines Paars.
   Vereinsnamen vorsichtig vereinheitlichen; fehlende Zugehörigkeit
   gesondert ausweisen. Keine Turnierort- oder Regionszuordnung verwenden.
2. Nur gemeinsame Starts in derselben belegten Konkurrenz (Startklasse und
   Disziplin) vergleichen. `compare_places` wiederverwenden: identische
   Platzbereiche gelten als gleich; nicht identische überlappende oder
   fehlende Bereiche als unbekannt. Pro Verein eindeutige Paare,
   gemeinsame Events und Paarbegegnungen getrennt zählen, ebenso „ihr
   besser“, „Gegner besser“, „gleich“ und „unbekannt“.
3. Einzelne Vereinszeile in der Tabelle auswählbar machen. Darunter die
   erfassten Paare des Vereins mit direkter Bilanz und letzter Begegnung
   zeigen. Eine Paarzeile öffnet die gemeinsamen Starts mit beiden
   Platzbereichen, Vergleichsergebnis und Quellen. Auswahl beim
   Filterwechsel zurücksetzen, falls der Verein oder das Paar nicht mehr
   in der gefilterten Ansicht vorkommt.

**Abnahme:** Zwei Paare desselben Vereins in einer Konkurrenz ergeben
einen gemeinsamen Event und zwei Begegnungen. Ein Vereinswechsel ordnet
jede Begegnung dem damals erfassten Verein zu. Klick auf einen Verein zeigt
nur seine Paare und deren Bilanz; fehlende Ortsangaben beeinflussen weder
die Tabelle noch die Details.
