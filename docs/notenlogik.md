# Notenlogik

Der fachliche Kern. Ein Fehler hier fällt nicht auf, bis eine falsche Note im
Zeugnis steht — deshalb liegt die Berechnung in einem eigenen Modul ohne
Kenntnis von Web und Datenbank und ist ohne laufende Anwendung testbar.

| | |
|---|---|
| Werte und Rundung | `app/grading/notenwert.py` |
| Berechnung | `app/grading/berechnung.py` |
| Anbindung an das ORM | `app/services/calculation.py` |
| Tests | `tests/test_notenwert.py`, `tests/test_berechnung.py`, `tests/test_calculation.py` |

## Die sechzehn Werte

Jede Note ist ein `Decimal`, nie ein `float`.

| Note | Wert | Note | Wert | Note | Wert |
|---|---|---|---|---|---|
| 1+ | 0,7 | 3+ | 2,7 | 5+ | 4,7 |
| 1 | 1,0 | 3 | 3,0 | 5 | 5,0 |
| 1− | 1,3 | 3− | 3,3 | 5− | 5,3 |
| 2+ | 1,7 | 4+ | 3,7 | 6 | 6,0 |
| 2 | 2,0 | 4 | 4,0 | | |
| 2− | 2,3 | 4− | 4,3 | | |

Tendenzen gibt es von 1+ bis 5−, die 6 hat keine. **0,7 wird als „1+"
angezeigt, nie als „0,7"** — der Wert ist eine Rechengröße, keine Note.

Eine Rückumrechnung berechneter Durchschnitte auf Tendenznoten gibt es nicht.
Ergebnisse erscheinen als Dezimalzahl *und* als ganze Notenstufe.

## Die drei Status

| Status | Wirkung |
|---|---|
| `gewertet` | geht mit seinem Wert ein |
| `nicht_gewertet` | wird angezeigt, fällt aus jeder Berechnung heraus |
| `nicht_erbracht` | geht als 6,0 ein |

**Ein fehlender Wert wird nie implizit als 0 oder 6 behandelt.** Bei
`nicht_erbracht` bleibt `note.notenwert` in der Datenbank NULL; die 6,0
entsteht in `berechnung.beitrag()`. Würde sie gespeichert, wäre eine spätere
Statusänderung nicht mehr von einer echten 6 zu unterscheiden.

## Halbjahresnote — einstufig

```
Halbjahresnote = Σ(notenwert × gruppengewicht × leistungsgewicht)
                 ─────────────────────────────────────────────────
                 Σ(gruppengewicht × leistungsgewicht)
```

**Abweichung von Spezifikation 4.4, vom Betreiber entschieden.** Die
Spezifikation beschrieb zwei Stufen: erst ein Mittel je Notengruppe, dann ein
Mittel dieser Gruppenmittel. Damit hinge die Wirkung einer Gruppe nicht davon
ab, wie viele Noten sie enthält. Gewünscht ist das Gegenteil — vier Tests
sollen bei gleichem Gruppengewicht mehr wiegen als eine einzelne
Klassenarbeit.

Gruppengewichte behalten ihre Wirkung: Eine Note in einer mit 70 gewichteten
Gruppe zählt mehr als eine in einer mit 30 gewichteten.

Nebenbei trifft die einstufige Rechnung den in Testfall T-1 geforderten
Erwartungswert 2,00 exakt — die zweistufige tut das nicht.

**Das Gruppengewicht ist ein Faktor je Note, kein Budget der Gruppe.** Jede
Klassenarbeit geht mit `70 × 1,0` ein, die dritte wie die erste; wer vier
schreibt, hat 280 aus Klassenarbeiten statt 210. Daraus folgt die Vorgabe
`Mitarbeit 3` für neue Kurse (Spezifikation 3.1): Mitarbeitsnoten entstehen
einzeln über das Halbjahr, und ein Gewicht in der Größenordnung der anderen
Gruppen machte sie zur schwersten Position im Zeugnis. Nachgerechnet in
`tests/test_mitarbeitsnote.py`.

**Eine leere Notengruppe hat kein Gewicht.** Sie taucht weder im Zähler noch
im Nenner auf; die in der Spezifikation beschriebene Normalisierung braucht
dafür keinen eigenen Code.

**Folge fürs Nachrechnen:** Es gibt kein Gruppenmittel. Weder Kursübersicht
noch Export weisen eines aus — eine Spalte, die zum Nachrechnen einlädt und
dabei nicht aufgeht, richtet mehr Schaden an als Nutzen. Die
Gruppen*gewichtung* bleibt sichtbar.

## Rundung

Zwei Schritte, beide explizit:

1. Der berechnete Wert wird auf **eine** Nachkommastelle gerundet.
2. Daraus entsteht die **ganze Notenstufe**.

Bei Gleichstand wird zur **besseren** Note gerundet (`ROUND_HALF_DOWN`), nicht
kaufmännisch: 2,50 wird zur 2. Das gilt überall.

> **Die tatsächliche Notengrenze liegt nicht bei 2,50.** Weil die ganze Note
> aus dem bereits gerundeten Wert entsteht, wird 2,54 zu 2,5 und damit zur 2;
> erst 2,56 wird zu 2,6 und damit zur 3. Wer die Grenze bei 2,50 vermutet,
> rechnet falsch nach.

## Jahresnote

Gewichtetes Mittel der beiden **Halbjahresnoten**, nicht der Rohdurchschnitte.
Die Gewichte stehen pro Kurs in `kurs.gewicht_halbjahr_1` und `_2`, Vorgabe
50/50 (`VORGABE_GEWICHT_HALBJAHR` in `app/db/models.py`).

Maßgeblich ist je Halbjahr die **festgesetzte** Note; ist keine gesetzt, zählt
die berechnete.

**Ohne beide Halbjahre keine Jahresnote.** Der praktische Fall ist der Januar:
Halbjahr 2 ist leer, also wird nichts angezeigt — kein Rückfall auf das
einzelne Halbjahr.

### Der rechtliche Hinweis, der nicht verloren gehen darf

Die Schulordnung RLP verlangt für die Jahresnote eine „stärkere
Berücksichtigung der Leistungen im letzten Schulhalbjahr". **Ein Mittel 50/50
bildet das nicht ab.** Die Vorgabe ist trotzdem 50/50, weil der berechnete
Wert nur ein Vorschlag ist: Verbindlich ist die festgesetzte Note, und dort
wird diese Anforderung erfüllt.

Zweiter Punkt: § 53 SchulO kennt nur ganze Notenstufen. Tendenzen sind für
Einzelleistungen und Zwischenstände zulässig, eine **Überschreibung ist immer
eine ganze Stufe 1 bis 6**.

## Festsetzung (Überschreibung)

Die Endnote ist eine pädagogische Entscheidung, keine Rechenoperation. Die
Tabelle `notenueberschreibung` wird nur angehängt, nie geändert; gültig ist
der jüngste Eintrag je (Schüler, Kurs, Bezugszeitraum). Damit gibt es die
Historie einer Zeugnisnote ohne Zusatzaufwand.

Der berechnete Wert wird **nie überschrieben, nur überlagert** — beide stehen
in der Anzeige nebeneinander: „2 (berechnet 2,6)".

## Notenspiegel

Je Leistung ein Durchschnitt und die Verteilung auf die Stufen 1 bis 6:

- Tendenznoten zählen zu ihrer ganzen Stufe — 2+ und 2− stehen beide in
  Spalte 2.
- `nicht erbracht` zählt als 6, in Durchschnitt **und** Verteilung.
- `nicht gewertet` fällt aus beidem heraus und bekommt eine eigene Spalte.
  Sonst sähe eine Klassenarbeit mit vielen Entschuldigten besser aus, als sie
  war.

Der Durchschnitt ist ein schlichtes Mittel über die Teilnehmer. Das
Leistungsgewicht wirkt nur innerhalb der Note eines einzelnen Schülers, nicht
zwischen Schülern.

## Verbindliche Testfälle

Aus Spezifikation 4.6, umgesetzt in `tests/test_berechnung.py`. **Diese Tests
sind die Abnahme der Rechenlogik** — wer die Berechnung ändert, ändert sie
gegen diese Fälle.

| Nr. | Prüft |
|---|---|
| T-1 | Grundfall zweier Gruppen |
| T-2 | leere Gruppe ändert nichts |
| T-3 | `nicht_gewertet` ändert nichts |
| T-4 | `nicht_erbracht` geht als 6,0 ein |
| T-7 | Kurs ohne Note: keine Division durch null, leere Anzeige |
| T-8 | Jahresnote bei Gewichtung 40/60 |
| T-9 | Festsetzung schlägt Berechnung, beide sichtbar |

T-5, T-6 und T-10 der Spezifikation prüften Punkteeingabe und Notenschlüssel
und entfallen ersatzlos — beides gibt es nicht.

```bash
.venv/bin/pytest tests/test_berechnung.py tests/test_notenwert.py
```

## Was es bewusst nicht gibt

**Keine Punkteeingabe, keinen Notenschlüssel.** Noten werden direkt als Stufe
mit Tendenz eingetragen; die Umrechnung von Punkten geschieht außerhalb dieser
Anwendung. Entscheidung des Betreibers zum offenen Punkt O-1.

Eine spätere Rückkehr dazu ist möglich, kostet aber eine Migration
(`punkte`, `max_punkte`, `eingabeart`, Entität *Notenschlüssel*) und den
Nachbau der Eingabemaske.
