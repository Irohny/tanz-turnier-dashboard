# Anforderungen und Umsetzungsplanung

## 1. Turnierergebnisse dauerhaft speichern

**Anforderung:** Ergebnisse sollen gespeichert und später wieder angesehen werden können.

**Plan:**
- Eine SQLite-Datenbank als dauerhaftes Archiv einführen.
- Turnier, Klasse/Disziplin, Paare, Runden, Wertungen und Quellenlink strukturiert speichern.
- Importe desselben Links wiedererkennbar machen, damit erneutes Einlesen keine Duplikate erzeugt.
- Vorhandene JSON-Ergebnisse können importiert werden; fehlende historische Daten müssen durch erneutes Crawlen ergänzt werden.

**Ergebnis:** Frühere Turniere bleiben nach einem Neustart verfügbar und sind einzeln aufrufbar.

## 2. Richtertendenzen auswerten

**Anforderung:** Erkennen, welche Wertungsrichter tendenziell besser oder schlechter werten.

**Plan:**
- Richterwertungen für alle Paare, Runden und Tänze erfassen.
- Wertungen innerhalb derselben Runde und desselben Tanzes mit dem Panel vergleichen und über Turniere zusammenfassen.
- Richternamen unabhängig von den turnierabhängigen Listenbuchstaben zuordnen; den Buchstaben nicht als Teil der Personenidentität behandeln.
- Anzahl der berücksichtigten Wertungen anzeigen und bei wenigen Daten auf geringe Aussagekraft hinweisen.

**Ergebnis:** Eine relative Tendenz je Richter, ohne daraus eine unbelegte Bevorzugung abzuleiten.

## 3. Tanzleistungen und Trainingsschwerpunkte erkennen

**Anforderung:** Sehen, in welchen Tänzen das Paar tendenziell besser oder schlechter abschneidet.

**Plan:**
- Tanzbezogene Platzierungen und Wertungen pro Runde speichern.
- Ergebnisse über Feldgrößen normalisieren, damit Turniere mit verschieden großen Feldern vergleichbar sind.
- Tanztrends über einen gewählten Zeitraum darstellen und die zugrunde liegenden Turniere/Wertungen anzeigen.

**Ergebnis:** Ein vergleichbarer Überblick zur Leistung je Tanz; er dient als Orientierung und ersetzt keine technische Trainingsanalyse.

## 4. Bisherige Gegner vergleichen

**Anforderung:** Sehen, welche Paare wie oft geschlagen wurden bzw. vor dem eigenen Paar lagen.

**Plan:**
- Paare über die Namen der Tänzer identifizieren; Startnummern gelten nur innerhalb eines Turniers.
- Vereinsnamen separat vom Paarnamen speichern und nicht zur Paaridentität zählen; Vereine in der Gegnerübersicht anzeigen.
- Pro Turnier und Klasse die Endplatzierung des eigenen Paares mit den anderen Paaren vergleichen.
- Siege, Niederlagen und Gleichstände getrennt zählen; Partnerwechsel und Namensvarianten berücksichtigen.
- Für Einschätzungen die Anzahl und Aktualität der Begegnungen mit anzeigen.

**Ergebnis:** Eine historische Gegnerbilanz als Orientierung, keine sichere Vorhersage des nächsten Turniers.

## 5. Aufstiegspunkte und Platzierungen verfolgen

**Anforderung:** Sehen, wie viele Wertungspunkte und Platzierungen in der Klasse erreicht wurden und wie weit der Aufstieg entfernt ist.

**Plan:**
- Die vorhandenen Aufstiegspunkte und Platzierungsangaben aus den TopTurnier-Ergebnisseiten erfassen. Dafür ist insbesondere für `tabges.htm` ein eigener Parser nötig, da die Paare dort als Spalten dargestellt werden.
- Punkte und relevante Platzierungen je Paar, Klasse und Disziplin über Turniere aufsummieren.
- Vor der Berechnung die geltenden Aufstiegsregeln für Verband, Klasse und Disziplin bestätigen und dokumentieren.
- Fehlende oder nicht eindeutig aus der Quelle lesbare Werte als unbekannt kennzeichnen, nicht schätzen.

**Ergebnis:** Fortschritt und noch fehlende Punkte/Platzierungen werden nachvollziehbar angezeigt, sobald die gültigen Regeln feststehen.

## 6. Daten mit möglichst wenig manueller Eingabe erfassen

**Anforderung:** Für den Import soll möglichst nur der Link zu den Turnierergebnissen und das auszuwertende Paar nötig sein.

**Plan:**
- In einem ersten Schritt TopTurnier-Links unterstützen und den vorhandenen Crawler für Frames und Ergebnis-Unterseiten weiterverwenden.
- Alle Paare und relevanten Tabellen automatisch erfassen und dem Turnier, der Klasse und der Disziplin zuordnen.
- Verständliche Fehlermeldungen für nicht unterstützte Links, unvollständige Seiten und nicht erkannte Tabellen anzeigen.
- Beim Import das auszuwertende Paar angeben und nur Turniere archivieren, an denen dieses Paar teilgenommen hat.
- Innerhalb der ausgewählten Turniere weiterhin die Ranglisten und Wertungen aller Paare archivieren, damit Gegnervergleiche möglich bleiben.
- Gleichseitige TopTurnier-Fallback-Links außerhalb des Startpfads (z. B. `/wp-external/turnier/`) gezielt erkennen, ohne beliebige seitenfremde Pfade zu crawlen.

**Ergebnis:** Der Import speichert nur passende Turniere, behält aber alle benötigten Vergleichsdaten der Paare in diesen Turnieren.

## 7. Auswertungen im Streamlit-Dashboard ansehen

**Anforderung:** Einzelne Turniere und Zeiträume visuell auswerten.

**Plan:**
- Streamlit ergänzen und als Oberfläche an die Datenbank und Auswertungsfunktionen anbinden.
- Filter für Paar, Klasse/Disziplin, Turnier und Zeitraum anbieten.
- Ansichten für Turnierergebnisse, Tanz- und Richtertrends, Gegnerbilanz sowie Aufstiegsfortschritt bereitstellen.
- Feldgröße im Turnierarchiv vorrangig aus der Starterliste bestimmen; falls diese fehlt, auf Rangliste und verfügbare Rundendaten zurückgreifen.
- Richtertrends als Tabelle mit Turnieranzahl, Gesamtzahl der Wertungen und farbiger Tendenz (negativ rot, positiv blau) darstellen.
- Richtertendenzen aus feldnormalisierten Finalwertungen und runden-normalisierten Vor-/Zwischenrunden-Kreuzraten berechnen; unbekannte Nenner nicht schätzen.
- In der Tanzanalyse Vor-, Zwischen-, Viertel- und Halbfinalrunden mit bekannter Stimmenzahl als separate, rundenbezogene Kreuzrate samt Stichprobenzahl ausweisen; nicht mit tanzbezogenen Platzierungen vermischen.
- In der normierten Tanzplatzierungsanalyse Startklassen per Mehrfachauswahl filtern und bei Klassenvergleichen die Balken je Tanz farblich gruppiert nebeneinander zeigen.
- Einen Tanzbalken anklicken können, um darunter den zeitlichen Verlauf der feldgrößen-normalisierten Einzelplatzierungen dieses Tanzes zu sehen; die Startklassenauswahl gilt auch für den Verlauf.
- Auf Zeitachsen Datum und Turnierort als Zeitpunkt anzeigen.
- Zeitpunkte vor dem Plotten chronologisch sortieren und Linien in dieser Reihenfolge verbinden.
- Richternamen quellenübergreifend als „Vorname Nachname“ kanonisieren; Listenkürzel getrennt halten und die Schreibweise „Nachname, Vorname“ umstellen.
- Für die Navigation Streamlits `st.navigation`/`st.Page` nutzen und die einzelnen Seiten im Ordner `dashboard_pages/` organisieren. Der reservierte Name `pages/` würde beim direkten Erstaufruf einer Unterseite die alte Navigation aktivieren und den gemeinsamen Einstiegspunkt umgehen.
- Den Turnierort in der Übersichtstabelle und neben dem Turniernamen in der Rundendetail-Auswahl anzeigen, sofern er aus der übergeordneten Turnierseite erkennbar ist.
- Die Rundentabelle eines Einzelturniers um verfügbare Feldgrößen, Platzierungen und feldgrößen-normalisierte Plätze ergänzen; Stimmenzahlen nur aus vollständigen und widerspruchsfreien Richterkreuzen ableiten, eine Qualifikation nur aus einer belegten Folgerunde erschließen und leere Rundeneinträge auslassen.
- Einzelwertungen im Tab der Einzelturnieransicht rundenweise als Matrix darstellen: Wertungsrichter in den Zeilen, Tänze in den Spalten und die vergebenen Plätze in den Zellen; bessere und schlechtere Plätze farblich unterscheiden.
- Zu jeder Kennzahl die Anzahl der Datenpunkte und die zugrunde liegenden Ergebnisse einsehbar machen.

**Ergebnis:** Einzelturniere und längerfristige Entwicklungen können im Browser gefiltert und verglichen werden.

## 8. Kreuzwertungen aus Vor- und Zwischenrunden auswerten

**Anforderung:** Kreuzwertungen aus Vorrunden und Zwischenrunden sollen neben den Endrundenergebnissen erfasst und sinnvoll verglichen werden.

**Plan:**
- `tabges.htm`-Matrixdaten je Paar und Runde parsen, einschließlich Gesamtkreuzen, Richter-Kreuzsummen und Qualifikationsstatus.
- Die mögliche Stimmenzahl nur berechnen, wenn die Richterzahl und die Tanzanzahl aus der zugehörigen Ergebniswertung eindeutig vorliegen.
- Rundencode und Rundentitel vereinheitlichen und die Feldgröße pro Runde speichern.
- Rundencode, mögliche Stimmenzahl, Qualifikationsstatus und Zielrunde dauerhaft im Archiv speichern; Richter-Kreuzsummen je Paar bleiben ebenfalls nachvollziehbar.
- Eine Weiterkommensgrenze und den Abstand des Paares nur aus vollständigen Paarergebnissen mit erfassten Qualifikationsentscheidungen berechnen.
- Rundendetails in CLI-Auswertung und Dashboard um Kreuzrate, Qualifikationsstatus, Grenzabstand und Richter-Kreuzsummen ergänzen.
- Bei der Aktualisierung vorhandener Quellen deren URLs, Start-URLs und erkannte Städte erhalten und die Ergebnisse idempotent aktualisieren.

**Ergebnis:** Vor- und Zwischenrunden sind nachvollziehbar, ohne bei unvollständigen Daten Stimmenzahlen oder Qualifikationsgrenzen zu schätzen.

## Empfohlene Reihenfolge

1. Datenmodell, Paaridentität und Aufstiegsregeln festlegen.
2. Crawler um die benötigten Tabellen und `tabges.htm` erweitern.
3. SQLite-Archiv und idempotenten Import implementieren.
4. Richter-, Tanz- und Gegnerauswertungen auf den gespeicherten Daten aufbauen.
5. Aufstiegsfortschritt berechnen und testen.
6. Streamlit-Dashboard ergänzen und vorhandene Turniere nachimportieren.

Zu jeder Stufe gehören Parser-Fixtures und Tests mit vollständigen sowie unvollständigen Ergebnisdaten. Bereits vorhandene JSON-Dateien bleiben lesbar; fehlende Gegner- oder Rundendaten können nur durch erneutes Crawlen der ursprünglichen Turnierlinks ergänzt werden.

## Umsetzungsstand

- **Erledigt:** SQLite-Archiv mit Paar-, Runden-, Platzierungs- und Richterwertungsdaten.
- **Erledigt:** Wiederholte Importe derselben Ergebnisseiten-URL sind idempotent; geänderte Inhalte aktualisieren den gespeicherten Stand.
- **Erledigt:** Crawler kann direkt ins Archiv schreiben; ein bestehendes Crawler-JSON kann importiert werden.
- **Erledigt:** Die Kommandozeilen-Auswertung kann Ergebnisse aus dem Archiv laden.
- **Erledigt:** Streamlit-Dashboard mit Paarübersicht, feldgrößen-normalisiertem Verlauf, Tanz- und Richteransicht, Gegnerbilanz und Turnierdetails; fehlende Werte werden als nicht verfügbar angezeigt.
- **Erledigt:** Native Streamlit-Navigation mit `st.navigation`/`st.Page` und separaten Seiten im Ordner `dashboard_pages/`; auch direkte Unterseiten-Aufrufe starten über den gemeinsamen Einstiegspunkt.
- **Erledigt:** Importseite fragt das auszuwertende Paar ab und archiviert nur Turniere mit diesem Paar; innerhalb dieser Turniere bleiben die Daten aller Paare für Vergleiche erhalten.
- **Erledigt:** Der Crawler verfolgt gleichseitige TopTurnier-Fallback-Links unter `/wp-external/turnier/`, darunter die Ergebnisseinbettung der ATSV-GLM-2026-Seite.
- **Erledigt:** Turnierarchiv-Tabelle und Rundendetail-Auswahl zeigen den Ort an, wenn er auf einer übergeordneten Turnier-Indexseite erkennbar ist. Bei älteren Archivinhalten ohne Ortsangabe wird „—“ bzw. „Ort unbekannt“ angezeigt; erneutes Crawlen ergänzt verfügbare Ortsdaten.
- **Erledigt:** Die Feldgröße im Turnierarchiv wird aus der Starterliste ermittelt, damit Paare ohne erfasste Ergebniszeile nicht fehlen; ohne Starterliste dient die Rangliste als Fallback.
- **Erledigt:** Richtertendenzen werden über Turniere anhand kanonischer Richternamen aggregiert; Listenkürzel bleiben getrennte Metadaten und „Nachname, Vorname“ wird beim Import und in vorhandenen Archivdaten vereinheitlicht.
- **Erledigt:** Paarnamen und Vereine werden separat gespeichert; die Gegnerbilanz fasst Paare unabhängig vom Verein zusammen und zeigt die erfassten Vereine an.
- **Erledigt:** Richtertendenzen werden in der Übersicht als Tabelle mit Turnieranzahl, Wertungsanzahl und rot/blau markierter Abweichung dargestellt.
- **Erledigt:** Richtertendenzen berücksichtigen feldnormalisierte Platzierungen und Vor-/Zwischenrunden-Kreuzraten; Kreuzraten ohne bekannten Nenner bleiben unberücksichtigt.
- **Erledigt:** `tabges.htm`-Matrixparser für paarbezogene Aufstiegspunkte, Platzierungen, Vor-/Zwischenrunden-Kreuze, Richter-Kreuzsummen und Qualifikationsmarkierungen. Eine Aufstiegsprognose ist vorerst ausdrücklich nicht Teil des Dashboards.
- **Erledigt:** Kreuzraten, Qualifikationsstatus und Weiterkommensgrenzen werden in CLI-Auswertung und Dashboard dargestellt; Grenzen werden nur mit vollständigen Paarergebnissen berechnet.
- **Erledigt:** Die Tanzanalyse ergänzt die getrennten Tanzplatzierungen um durchschnittliche, nach Runde gruppierte Kreuzraten aus Vor- und Zwischenrunden; nur Runden mit gültigem Nenner zählen als Stichprobe.
- **Erledigt:** Die normierte Tanzplatzierungsanalyse kann Startklassen per Segmentauswahl zusammenfassen oder einzeln/mehrfach vergleichen; Klassenbalken werden je Tanz nebeneinander dargestellt.
- **Erledigt:** Ein Klick auf einen Tanzbalken zeigt darunter den chronologischen Verlauf der einzelnen Tanzplatzierungen; Klassenfilter und Startklassenfarben bleiben erhalten.
- **Erledigt:** Die Zeitdiagramme beschriften Zeitpunkte mit Datum und Turnierort; Startklasse, Disziplin und Runde ergänzen die Achsenbeschriftung bei Bedarf.
- **Erledigt:** Zeitpunkte und Linienverläufe werden in beiden Zeitdiagrammen chronologisch sortiert.
- **Erledigt:** Die Rundentabelle im Einzelturnier ergänzt verfügbare Feldgrößen, Platzierungen und normierte Plätze; vollständige Richterkreuze können fehlende Gesamtstimmen sicher rekonstruieren, eine belegte spätere Runde eine fehlende positive Qualifikation ableiten. Unbekannte Werte werden nicht geschätzt, leere Rundeneinträge ausgeblendet und die Endrunde als nicht grenzpflichtig gekennzeichnet.
- **Erledigt:** Der Einzelwertungs-Tab der Einzelturnieransicht zeigt die Richter-Einzelwertungen als rundenweise Matrix mit Wertungsrichtern in den Zeilen, Tänzen in den Spalten und den vergebenen Plätzen in den Feldern; Grün kennzeichnet bessere und Rot schlechtere Plätze.
- **Erledigt:** Die Rundendetails verwenden Tabs statt Expandern für Richterkreuze und Einzelwertungen; der Turnierort steht in der Auswahlliste neben dem Turniernamen und als „Ort“ in der Übersichtstabelle.
- **Erledigt:** Archiv-Schema v4 speichert Rundencode, mögliche Stimmenzahl und Qualifikationsdaten sowie die letzte Importherkunft getrennt von der ursprünglichen Start-URL. Parser v4 erfasst seine Version; bekannte Städte werden bei partiellen Reimports nicht gelöscht.
- **Erledigt:** Gemeinsame Fachlogik für URL-basierte Turnieridentität, exakte Paaridentität, nummerierte Runden, explizite Platzbereiche und vollständige Qualifikationsbelege; CLI und Dashboard verwenden dieselben Regeln.
- **Erledigt:** Gleichstände und unbekannte Gegnerbilanzen sind getrennt. Ungültige Platzierungen, fehlende Richterzellen und widersprüchliche Kreuzsummen erzeugen keine belastbar wirkenden Kennzahlen.
- **Erledigt:** Quellbelege für Platzierungen, Tanzwertungen, Richtervergleiche und Gegnerbegegnungen; aggregierte Richterkreuze im Einzelturnier; Warnung bei kleinen Vergleichsstichproben.
- **Erledigt:** Revisionsbasierte Caches einschließlich externer Imports und SQLite-WAL, günstiger Paarkatalog und Aufbau nur des aktiven Übersichtstabs. Erfolgreiche Imports aktualisieren den gemeinsamen Kontext.
- **Betriebsschritt nach Abnahme:** Bestehende Daten bleiben unverändert. Ein neues, leeres Archiv wird separat aus den Originalquellen aufgebaut; Bestandsreparatur und automatische Namensalias-Verwaltung sind nicht Teil dieser Optimierung.
