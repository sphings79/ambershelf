<div align="center">

# AmberSync

### Einbahn-Plattenabgleich mit Freigabe — gebaut gegen Verschlüsselungstrojaner

**Spiegelt eine Master-Platte auf eine oder mehrere Sicherungsplatten, ohne jemals
hinter deinem Rücken etwas zu löschen oder zu überschreiben.** Selbst gehostet, Docker,
Weboberfläche, exFAT und NTFS — für Foto- und Videoarchive, die auf Platten im Schrank
liegen.

[![Lizenz: AGPL v3](https://img.shields.io/badge/Lizenz-AGPL%20v3-2ea44f?style=flat-square)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](compose.yaml)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](requirements.txt)
[![Selbst gehostet](https://img.shields.io/badge/Selbst%20gehostet-ja-e08b12?style=flat-square)](#schnellstart)
[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-sphings-FFDD00?style=flat-square&logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/sphings)

[English](README.md) · **Deutsch**

**Wenn dir AmberSync nützt, gib dem Repo bitte einen ⭐ Stern** — anders finden Leute mit
demselben Problem es nicht.

<img src="docs/screenshots/overview-dark.png"
     alt="AmberSync Übersicht im dunklen Erscheinungsbild: eine nur lesend eingehängte Master-Platte und zwei Sicherungskopien mit Verzeichnisstand" width="880">

</div>

---

## Das Problem dahinter

Ein Fotoarchiv ändert sich nicht. Es kommen Dateien dazu; geändert wird fast nie etwas,
und gelöscht wird selten und mit Absicht. Trotzdem versteht jedes übliche
Abgleichsprogramm „die Quelle hat sich geändert" als Auftrag, die Kopie mitzuändern —
also genau das, was du **nicht** willst, wenn die Quelle gerade von einem Trojaner
verschlüsselt, von einem defekten Kabel zerschossen oder von einem vertippten Befehl
geleert wurde.

AmberSync dreht das um. Es liest beide Seiten, bildet den Unterschied über Prüfsummen und
**zeigt dir dann, was es tun würde**. Dateien hinzufügen ist Alltag. Eine ersetzen oder
löschen braucht deine Freigabe. Eine Massenänderung löst die Notbremse und hält den Lauf an.

Gebaut für den Umgang, den externe Platten in Wirklichkeit haben: gelegentlich
angesteckt, zwischen Mac und Windows-PC getragen, den Rest der Zeit im Schrank.

## Bildschirmfotos

| Übersicht — hell | Aufteilung auf mehrere Platten |
| --- | --- |
| <img src="docs/screenshots/overview-light.png" alt="AmberSync Übersicht im hellen Erscheinungsbild mit Plattenkarten, Belegungsbalken und Verzeichnisstand" width="420"> | <img src="docs/screenshots/split-light.png" alt="AmberSync Aufteilung: Ordner eines Fotoarchivs werden zwei Sicherungsplatten zugeteilt, mit Belegungsbalken" width="420"> |

**Die Vorschau mit ausgelöster Notbremse** — es wird nichts ausgeführt, bis du entschieden hast:

<img src="docs/screenshots/preview-dark.png" alt="AmberSync Vorschau mit neuen, geänderten, umbenannten und nur auf der Kopie vorhandenen Dateien; die Notbremse sperrt den Lauf, weil 18 Prozent des Bestands ersetzt würden" width="880">

**Hell, dunkel und System, fünf Akzentfarben:**

<img src="docs/screenshots/settings-dark.png" alt="AmberSync Einstellungen mit Umschalter für das Erscheinungsbild, Akzentfarben und den Grenzwerten der Notbremse" width="880">

## Eigenschaften

- **Der Master wird vom Kernel nur lesend eingehängt.** Nicht „das Programm schreibt da
  nicht hin" — das Dateisystem ist `ro` eingehängt, und die Flags werden gegengelesen,
  bevor ein einziges Byte gelesen wird. Auch ein Programmierfehler oder jemand, der den
  Container übernimmt, kommt an dein Original nicht heran.
- **Gegen Verschlüsselungstrojaner gebaut.** Nichts wird ohne deine Freigabe gelöscht oder
  überschrieben, und eine Massenersetzung löst eine einstellbare Notbremse aus — nach
  absoluter Zahl **und** nach Anteil am Bestand.
- **Plattenerkennung, die von innen nicht zu fälschen ist.** Eine Platte wird über
  Dateisystem-UUID und Seriennummer erkannt; die Zuordnung von Platte zu Rolle liegt in
  einer root-eigenen Datei auf dem Host, außerhalb der Reichweite des Containers. Ein
  umbenannter Ordner oder eine geklonte Platte können keine Richtung umdrehen.
- **Vergleich über Prüfsummen (SHA-256).** Nie über Zeitstempel — exFAT speichert die Zeit
  in Lokalzeit mit 10 ms Auflösung, was sich zwischen Rechnern oft genug unterscheidet, um
  als Beweis unbrauchbar zu sein.
- **Umbenennungserkennung.** Eine verschobene Datei behält ihren Platz, statt noch einmal
  kopiert und anschließend als Fremdkörper gemeldet zu werden.
- **Einen großen Master auf mehrere kleinere Platten aufteilen**, Ordner für Ordner, mit
  einer dauerhaften Warnung für alles, was auf keiner Kopie gelandet ist — der stille
  Fehler, der wirklich Daten kostet.
- **Fortsetzbares Einlesen.** Der erste Prüfsummenlauf über ein Terabyte dauert Stunden;
  er lässt sich anhalten, fortsetzen und übersteht einen Neustart des Containers mit
  höchstens einer verlorenen Datei.
- **Normale, durchsuchbare Kopien.** Eine Sicherungsplatte bleibt ein gewöhnlicher
  Ordnerbaum, den du an jedem Rechner ohne AmberSync öffnen kannst — kein eigenes Format.
- **Unprivilegierter Container.** Kein `privileged`, keine Capabilities, kein Gerätezugriff.
- **Deutsche und englische Oberfläche**, helles/dunkles/System-Erscheinungsbild, fünf
  Akzentfarben.

## Aufbau

```
Host                                Container (unprivilegiert)
──────────────────────────────      ────────────────────────────
ambersync-helper (root)             Weboberfläche
  · listet Blockgeräte                · Einlesen und Prüfsummen
  · hängt den Master nur lesend ein   · Vergleich und Vorschau
  · hängt Kopien schreibend ein       · Ordnerzuteilung
  · besitzt /etc/ambersync/disks.conf · SQLite-Verzeichnis
          │                                      │
          └──── Unix-Socket ─────────────────────┘
          └──── /mnt/ambersync (rshared bind) ───┘
```

Der Container kann nur darum **bitten**, einen Satz einzuhängen. Er benennt nie ein Gerät,
nie eine Einhänge-Option und entscheidet nie über eine Rolle — das ist es, was den Master
schützt, selbst wenn der Container vollständig übernommen wird.

Registrieren über den Socket geht **nur hinzufügend**, mit Absicht. Eine Rolle ändern oder
eine Registrierung entfernen verlangt einen bewussten Befehl auf dem Host; sonst wäre
Löschen-und-neu-anlegen ein Weg an der Regel vorbei.

## Schnellstart

Vorausgesetzt: ein Linux-Host mit Docker und systemd, `util-linux` und die Kernel-Treiber
für deine Dateisysteme (`exfat` seit 5.7, `ntfs3` seit 5.15 — beide sind in jeder aktuellen
Distribution dabei). `exfatprogs`, falls du einen unsauber getrennten exFAT-Datenträger
reparieren können willst.

```bash
git clone https://github.com/sphings79/ambersync.git
cd ambersync
sudo docker/install.sh      # Helfer, systemd-Unit, Gruppe, Verzeichnisse
docker compose up -d
```

Die Oberfläche hört auf `127.0.0.1:8088`. Stell sie hinter einen Reverse Proxy und
beschränke sie auf dein eigenes Netz — sie hat bewusst keine eigene Anmeldung, weil jede
Installation dazu ohnehin schon eine Meinung hat. Ein Traefik-Beispiel für den
Datei-Provider liegt in [`docs/traefik-ambersync.yml`](docs/traefik-ambersync.yml).

## Benutzung

1. **Platten** — Platte anstecken, benennen, Rolle wählen, registrieren. Der Master wird
   gelesen, Kopien werden beschrieben.
2. **Übersicht** — Satz einhängen, dann jede Platte einlesen. Der erste Lauf prüfsummt alles.
3. **Aufteilung** (wahlweise) — Ordner den Kopien zuteilen. Der Baum beginnt auf Ordnerebene 2,
   `Fotos/2019` ist also eine Einheit. Alles Unzugeordnete wird als Warnung angezeigt.
4. **Vorschau** — vergleichen und genau ansehen, was passieren würde.

### exFAT und NTFS

Beides geht, auch gemischt innerhalb eines Satzes.

**exFAT** ist das einzige Dateisystem, das macOS und Windows ohne Zusatzsoftware lesen
**und** beschreiben können — deshalb gewinnt es bei Platten, die herumgereicht werden. Es
hat kein Journal, also schreibt AmberSync über eine Temporärdatei und benennt erst um,
wenn die Prüfsumme stimmt, hängt nach jedem Lauf sauber aus und weigert sich, auf einen
Datenträger zu schreiben, dessen Dirty-Flag gesetzt ist.

**NTFS** hat ein Journal und ist robuster, aber macOS kann es nur lesen.

## Im Vergleich

| | AmberSync | rsync | Syncthing | FreeFileSync |
| --- | --- | --- | --- | --- |
| Quelle physisch schreibgeschützt | **ja, `ro`-Mount** | nein | nein | nein |
| Löschungen brauchen Freigabe | **ja** | nein (`--delete` oder gar nicht) | nein | nur Nachfrage |
| Notbremse bei Massenänderung | **ja** | nein | nein | nein |
| Eine Quelle auf mehrere Ziele aufteilen | **ja** | nein | nein | nein |
| Merkt sich deine Entscheidungen | **ja** | nein | entfällt | nein |
| Ziel bleibt ein normaler Ordnerbaum | **ja** | ja | ja | ja |
| Laufend / in beide Richtungen | nein, bewusst | nein | ja | nein |
| Weboberfläche | **ja** | nein | ja | nein |

Wenn du laufenden Abgleich in beide Richtungen zwischen Rechnern willst, nimm Syncthing.
Wenn du einen skriptbaren Einzeiler willst, nimm rsync. AmberSync ist für den Fall, dass
die Kopie der Quelle **nicht** in einen kaputten Zustand folgen darf.

## Häufige Fragen

**Schützt mich das vor Verschlüsselungstrojanern?**
Es schützt die *Kopie* vor einem Master, der bereits beschädigt ist — etwa weil die Platte
an einem befallenen Windows-PC hing. Kopfbyte-Prüfungen, die Freigabe und die Notbremse
verhindern, dass der Schaden weitergetragen wird. Es schützt **nicht** davor, dass jemand
den Host selbst übernimmt. Dein eigentlicher Schutz dagegen ist, dass die Platten die
meiste Zeit nicht angesteckt sind — und AmberSync ist so gebaut, dass es das nicht aufweicht.

**Warum nicht einfach rsync?**
rsync kopiert Dateien gut. Was es nicht hat: einen Freigabe-Ablauf, eine Zustandsdatenbank,
Umbenennungserkennung über Prüfsummen, Aufteilung auf mehrere Ziele oder eine Notbremse.
Das alles um rsync herumzubauen heißt, den Großteil davon ohnehin nachzubauen — mit
weniger Kontrolle über jeden einzelnen Schritt.

**Kann es Dateien auf der Kopie löschen?**
Nur solche, die du freigibst, einzeln oder gesammelt — und erst, wenn AmberSync selbst
einmal auf diese Kopie geschrieben hat. Vorher lässt sich eine gelöschte Datei nicht von
einer unterscheiden, die nie da war. Das sagt es, statt zu raten.

**Wie lange dauert der erste Lauf?**
Er liest und prüfsummt alles. Rechne grob mit 4 bis 8 Stunden je Terabyte über USB 3, je
nach Platte und Dateigrößen. Spätere Läufe prüfen nur, was sich geändert hat. Der Lauf
lässt sich anhalten und fortsetzen.

**Müssen die Platten dauerhaft angesteckt bleiben?**
Nein. Genau darum geht es. Anstecken, laufen lassen, auswerfen.

**Geht das auch ohne Docker?**
Der Webteil ist reines Python mit uvicorn, also im Prinzip ja — aber den Host-Helfer und
die geteilte Mount-Weitergabe richtet dir die Compose-Datei ein.

**Funktioniert es mit einer NAS-Freigabe, SMB oder NFS?**
Derzeit nicht. Es erkennt Platten über Dateisystem-UUID und Seriennummer, und die hat eine
Netzfreigabe nicht.

## Ausbaustand

| Abschnitt | Inhalt | Stand |
| --- | --- | --- |
| 1 | Host-Helfer, Registrierung, Einhängen | ✅ fertig |
| 2 | Einlesen, Prüfsummen, Vergleich, Vorschau | ✅ fertig |
| 3 | Kopieren mit Prüfung, Freigaben, Verlauf | 🚧 als Nächstes |
| 4 | Aufteilung auf mehrere Kopien, Deckungsprüfung | ✅ fertig |
| 5 | Trojaner-Erkennung, Benachrichtigungen | Umbenennungen fertig, Rest geplant |

> **Aktueller Stand: es liest, vergleicht und zeigt. Es schreibt noch nicht auf eine
> Datenplatte.** Abschnitt 3 bringt die schreibende Hälfte.

## Mitmachen

Fehlermeldungen und Pull Requests sind willkommen — besonders Rückmeldungen zu
Dateisystemen und Plattengehäusen, die ich hier nicht testen kann. Kommentare, Namen und
Commit-Nachrichten bitte auf Englisch.

## Das Projekt unterstützen

Wenn dir AmberSync eine Sicherung gerettet hat — oder auch nur einen Abend:

<a href="https://buymeacoffee.com/sphings">
  <img src="https://img.shields.io/badge/Buy%20me%20a%20coffee-sphings-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy me a coffee">
</a>

Und ein ⭐ kostet nichts und hilft sehr.

## Lizenz

[AGPL-3.0-or-later](LICENSE). Benutzen, ändern, weitergeben — wer es anderen über ein Netz
anbietet, veröffentlicht seine Änderungen mit.

---

<sub>**Schlagwörter:** Plattenabgleich · Einbahn-Sync · Sicherungskopie · externe Festplatte
sichern · Schutz vor Verschlüsselungstrojanern · Fotoarchiv sichern · exFAT unter Linux ·
NTFS · selbst gehostet · Docker · rsync-Alternative · FreeFileSync-Alternative ·
schreibgeschützte Quelle · Prüfsummen · SHA-256 · Sicherung auf mehrere Platten aufteilen ·
Kaltlagerung · USB-Platte spiegeln · Freigabe-Ablauf</sub>
