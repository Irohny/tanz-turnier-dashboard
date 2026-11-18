# TopTurnier-Ergebnis-Crawler

Liest TopTurnier-Ergebnisseiten aus und speichert erkannte Paare, Wertungsrichter
und Ergebnisse als JSON.

## Installation

Voraussetzung ist Python 3.12 oder neuer. Mit [uv](https://docs.astral.sh/uv/)
werden die passende Python-Umgebung und Abhängigkeiten aus `uv.lock` eingerichtet:

```sh
uv sync
```

Das Dashboard benötigt Streamlit ab Version 1.67. Die CI prüft Python 3.12
und 3.14 mit den gesperrten Abhängigkeiten.

## Aufruf

```sh
uv run python -m etl.crawler \
  https://www.1scn.de/turnierergebnisse_tanzen_2026/index.htm \
  --paar "Mustermann Musterfrau" \
  --alle-paare \
  --out ergebnis.json
```

`--alle-paare` speichert die Wertungszeilen aller Paare einschließlich Feldgröße
und erkannten Richterzellen. Das ist nötig, um die Fortschritte der Gegner über
aufeinanderfolgende Runden auszuwerten. Ohne diese Option bleibt das bisherige
Verhalten erhalten: Im JSON stehen Detailwertungen nur für das mit `--paar`
ausgewählte Paar. Mit `--alle-paare` kann `--paar` weiterhin zum Filtern der
Konsolenausgabe und CSV verwendet werden; die JSON-Datei enthält trotzdem alle
Paare.

Der Crawler folgt auch den Frames der Wettbewerbsseiten, in denen TopTurnier die
Ergebnislinks bereitstellt. Eingebettete TopTurnier-Indexseiten auf derselben
Website werden auch dann verfolgt, wenn sie in einem anderen Jahresordner oder
auf der `www`-Variante der Domain liegen. Bei einem Netzwerk- oder URL-Problem
wird eine Fehlermeldung ausgegeben und der Prozess endet mit einem Fehlerstatus,
statt eine scheinbar erfolgreiche leere JSON-Datei zu schreiben.
Auch erfolgreich geladene HTML-Seiten ohne erkennbare Ergebnisdaten gelten als
Fehler. JSON wird atomar ersetzt; ein abgebrochener Export überschreibt die
vorherige Datei nicht. Seitenlimits und teilweise fehlgeschlagene Abrufe werden
ausdrücklich gemeldet.

`--debug` zeigt erkannte Tabellen und Spaltenköpfe. Mit `--cache ORDNER` werden
abgerufene HTML-Seiten zusätzlich lokal gespeichert.

## SQLite-Archiv

Mit `--db` werden die Ergebnisse zusätzlich dauerhaft in einem SQLite-Archiv
gespeichert. Dabei werden automatisch Wertungen aller Paare erfasst; erneut
importierte, unveränderte Seiten erzeugen keine Duplikate. Geänderte Inhalte
einer bereits bekannten Ergebnisseiten-URL ersetzen deren bisherigen Stand.
Die ursprüngliche Start-URL und bereits bekannte Städte bleiben bei
unvollständigen Reimports erhalten. Schema v4 hält die Herkunft der letzten
Importausführung separat fest. Parser v6 kennzeichnet die Erfassungsversion.
Das reine Laden eines Archivs öffnet SQLite schreibgeschützt und migriert
keine Bestandsdaten.

```sh
uv run python -m etl.crawler \
  https://www.1scn.de/turnierergebnisse_tanzen_2026/index.htm \
  --db turniere.sqlite
```

Eine vorhandene JSON-Datei lässt sich einmalig ins Archiv übernehmen:

```sh
uv run python -m etl.archiv --datei ergebnis.json --db turniere.sqlite
```

Die JSON-Datei wird weiterhin geschrieben. Für die Auswertung kann stattdessen
das Archiv verwendet werden:

```sh
uv run python -m etl.auswertung \
  --db turniere.sqlite \
  --paar "Christoph Struth / Luzie Böckermann"
```

## Streamlit-Dashboard

Das Dashboard verwendet die archivierten SQLite-Daten und bietet eine
Paarübersicht sowie eigene Bereiche für Tänze, Wertungsrichter, Gegnerbilanz,
Turniere und Punkte. Paar, Startgruppe, Disziplin und Zeitraum werden gemeinsam
unter „Filter & Paar ändern“ in der Seitenleiste ausgewählt. Ein
Startklassenvergleich erscheint in der Tanzanalyse nur bei mehreren Klassen.
Richtertendenzen werden nach Namen statt nach
den turnierabhängigen Listenbuchstaben zusammengefasst. Paarnamen und Vereine
werden getrennt gespeichert; die Gegnerbilanz fasst Paare vereinsunabhängig
zusammen und zeigt die erfassten Vereine an. Im Turnierarchiv sind die gespeicherten
Rundenwerte und Einzelwertungen einsehbar; eine Turnierauswahl ersetzt die
doppelte Übersichtsliste. Turnierort und Datum stehen bei der Auswahl und in
den Details, sofern sie ermittelt werden konnten. Bei älteren Importen ergänzt
ein erneuter Crawl verfügbare Ortsangaben. Gespeicherte Punkte werden getrennt
nach Startgruppe, Disziplin und Punktart summiert; unvollständig zugeordnete
Einträge bleiben einzeln sichtbar.
Ein Klick auf eine Zelle der Richter- oder Gegnertabelle zeigt die zugehörigen
Turniere unterhalb der Tabelle; die gemeinsamen Filter gelten auch für diese Liste.

```sh
uv run streamlit run app.py
```

Vor dem Start müssen in den Streamlit Secrets einfache Zugangsdaten hinterlegt
werden. Lokal kann dafür eine nicht versionierte `.streamlit/secrets.toml`
verwendet werden; beim Deployment werden dieselben Werte in den App-Secrets
eingetragen:

```toml
[auth]
user = "mein-benutzer"
password = "ein-langes-passwort"
```

Ohne diese beiden Werte bleibt das Dashboard gesperrt. Nach erfolgreicher
Anmeldung gilt der Zugang für die aktuelle Browser-Sitzung und kann über
„Abmelden“ in der Seitenleiste beendet werden.

Das Dashboard bietet ein abgestimmtes helles und dunkles Farbschema. Im
Streamlit-Menü oben rechts lässt sich unter „Theme“ zwischen „System“,
„Light“ und „Dark“ wechseln; „System“ folgt der Einstellung des Geräts.

Die Seitennavigation verwendet Streamlits `st.navigation`/`st.Page`.
Die einzelnen Seiten liegen im Verzeichnis `dashboard_pages/`. Der reservierte
Name `pages/` wird vermieden, damit Streamlit direkte Unterseiten-Aufrufe beim
Serverstart nicht als alte, vom gemeinsamen Einstiegspunkt getrennte Navigation
behandelt.

Unter „Archiv & JSON-Import“ in der Seitenleiste lässt sich der Pfad des
Archivs ändern oder eine bestehende Crawler-JSON-Datei importieren. Alternativ kann das Archiv vor dem Start
vorbereitet werden:

```sh
uv run python -m etl.archiv --datei ergebnis.json --db turniere.sqlite
```

Über die Dashboard-Seite „Turnier erfassen“ kann eine Ergebnisseite eingegeben
werden. Dabei wird auch das auszuwertende Paar angegeben. Der Crawler folgt den
verlinkten HTML-Ergebnisseiten und archiviert nur Turniere, in denen dieses Paar
vorkommt. Innerhalb dieser Turniere bleiben die Ranglisten und Wertungen aller
Paare erhalten, damit Gegnervergleiche möglich sind. Bereits vorhandene
Archivinhalte werden nicht gelöscht.
Gleichseitige TopTurnier-Fallback-Links unter `/wp-external/turnier/` werden
ebenfalls verfolgt, zum Beispiel die Ergebnisseinbettung auf der ATSV-Seite.

Das Dashboard zeigt nur aus den Quellen gelesene Werte. Der `tabges.htm`-Parser
erfasst paarbezogene Aufstiegspunkte und Platzangaben sowie Kreuzsummen,
Richter-Kreuzsummen und Qualifikationsmarkierungen aus Vor- und Zwischenrunden.
Die mögliche Stimmenzahl ergibt sich aus der Richterzahl der Runde und der
Tanzanzahl aus den zugehörigen Ergebnislisten; dabei wird dieselbe Tanzanzahl
für die Vorrunden angenommen. Bei widersprüchlichen Tanzzahlen oder Richterkreuzen
oberhalb dieser Anzahl bleibt der Nenner unbekannt. Für bereits importierte
Turniere muss die Ergebnisseite erneut abgerufen werden, damit der neue Parser
die Stimmenzahl ergänzt. Eine Aufstiegsprognose ist nicht enthalten.

### Nachvollziehbarkeit und Aktualisierung

- Turniere werden über Ursprung und vollständiges URL-Verzeichnis unterschieden,
  nicht über wechselnde Seitentitel. Verschiedene Spiegel-Domains werden nicht
  automatisch vereinigt.
- Geteilte Plätze zählen als Gleichstand. Fehlende oder überlappende, nicht
  identische Platzbereiche werden als unbekannt ausgewiesen, nicht aus der
  Reihenfolge der Paare abgeleitet.
- Fehlende Richterzellen sind keine negativen Stimmen. Unvollständige oder
  widersprüchliche Kreuzsummen liefern keine scheinbar vollständige Kreuzrate.
  Qualifikationsgrenzen setzen vollständige und widerspruchsfreie Belege voraus.
  Endrundenzellen können zusätzlich Kreuze früherer Runden enthalten; diese
  werden weder in CLI noch Dashboard als Endrunden-Kreuzrate interpretiert.
- Ausklappbare Belege zeigen Rohwerte, Feldgrößen und Quell-URLs.
  Aggregierte Richterkreuze erscheinen auch ohne Einzelzellen als Kreuztabelle
  nach Runde und Wertungsrichter. Die Farbe zeigt den Anteil an möglichen
  Kreuzen; ohne bekannte mögliche Kreuzzahl bleibt das Feld ungefärbt.
- Richtertabellen unterscheiden verwendbare Vergleiche von Rohwertungen.
  Der Hinweis bei weniger als fünf Vergleichen ist eine Orientierung für kleine
  Stichproben, keine statistische Signifikanzgrenze.
- Seiten, Paarkatalog und Analysen werden nach Archivpfad und Dateirevision
  zwischengespeichert. Imports, externe Änderungen und Dateiaustausch einschließlich
  SQLite-WAL invalidieren die Caches. Eine Änderung der Analyse-Datenstruktur
  erfordert eine neue Analyse-Cacheversion. Nur der aktive Übersichtstab wird aufgebaut.
  Nach einem Import wird der gemeinsame Seitenkontext unmittelbar neu geladen.

### Einmaliger Neuaufbau nach der Optimierung

Die bisherige Datenbank wird weder korrigiert noch automatisch überschrieben.
Für einen bereinigten Bestand ein **neues** Archiv wählen und die ursprünglichen
Turnierseiten erneut abrufen; alte JSON-Dateien können historische Parserfehler
enthalten.

```sh
TURNIER_DATABASE=turniere_neu.sqlite uv run streamlit run app.py
```

Auf „Turniere erfassen“ Paar und ursprüngliche Übersichts-URL angeben und die
benötigten Turniere nacheinander importieren. Danach Quellen, Turnieranzahl und
Rundendetails prüfen und erst anschließend auf das neue Archiv umstellen.
Der Neuaufbau ist ein separater Betriebsschritt. Anders als der selektive
Dashboard-Import archiviert die CLI mit `--db` weiterhin alle erkannten Turniere;
`--paar` filtert dort nur die Auswertung.

Für bereits importierte TopTurnier-Ergebnisse mit fehlenden Platzierungen oder
Gegnern die ursprüngliche Ergebnisseite erneut abrufen. Der Reimport ersetzt
die betroffenen Quellseiten im Archiv durch die aktualisierten Parserdaten.

## Paar-Auswertung

Nach dem Crawl fasst dieses Skript die im JSON gespeicherten Runden, Tanzwertungen,
Kreuze, Platzierungen, Wertungsrichter und Vergleichspaare zusammen. Neben
Rohwerten berechnet es feldgrößen-normalisierte Platzierungen, Kreuzraten und die
Abweichung eines Richters vom Median der übrigen Richter. Wenn vollständige
Rundendaten mit Qualifikationsmarkierungen vorliegen, zeigt es zusätzlich den
Status, Richter-Kreuzsummen und den Abstand zur Weiterkommensgrenze:

```sh
uv run python -m etl.auswertung \
  --datei ergebnis.json \
  --paar "Christoph Struth / Luzie Böckermann"
```

Für die normalisierte Gegnerauswertung den Crawler mit `--alle-paare` starten.
Fehlende Runden oder Richterwertungen werden nicht geschätzt. Die
Gegner-Vorleistung ist ein deskriptiver Vergleich, kein Elo- oder
Erwartungswertmodell; eine Kreuzgrenze wird nur aus vollständigen Paarergebnissen
mit erfassten Qualifikationsentscheidungen berechnet.

## Entwicklung und Prüfung

```sh
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
uv run --locked ruff check .
uv run --locked black --check .
```

Alternativ führen `just test` und `just lint` die vorhandenen
Prüfungen aus. Schreibende Tests verwenden ausschließlich temporäre Archive.