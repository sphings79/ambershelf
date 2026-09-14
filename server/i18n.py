# AmberShelf - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Two languages, one dictionary. Missing keys fall back to the key itself,
which is ugly enough to be noticed during testing."""
from __future__ import annotations

LANGUAGES = {"de": "Deutsch", "en": "English"}

STRINGS: dict[str, dict[str, str]] = {
    "de": {
        "app.name": "AmberShelf",
        "app.tagline": "Plattenabgleich mit Freigabe",

        "nav.overview": "Übersicht",
        "nav.disks": "Platten",
        "nav.assign": "Sync-Art",
        "nav.plan": "Vorschau",
        "nav.events": "Verlauf",
        "nav.settings": "Einstellungen",

        "common.yes": "Ja",
        "common.no": "Nein",
        "common.save": "Speichern",
        "common.cancel": "Abbrechen",
        "common.close": "Schließen",
        "common.files": "Dateien",
        "common.size": "Größe",
        "common.path": "Pfad",
        "common.disk": "Platte",
        "common.role": "Rolle",
        "common.set": "Satz",
        "common.state": "Zustand",
        "common.none": "keine",
        "common.unknown": "unbekannt",
        "common.back": "Zurück",
        "common.of": "von",
        "common.free": "frei",
        "common.total": "gesamt",
        "common.never": "nie",

        "role.master": "Master",
        "role.slave": "Kopie",

        "helper.missing.title": "Der Host-Helfer antwortet nicht",
        "helper.missing.body": "Ohne ihn kann keine Platte eingehängt werden. "
                               "Prüfe auf dem Host: systemctl status ambershelf-helper",

        "overview.title": "Übersicht",
        "overview.no_sets": "Noch kein Satz eingerichtet. Registriere zuerst eine Platte.",
        "overview.connected": "angeschlossen",
        "overview.not_connected": "nicht angeschlossen",
        "overview.mounted": "eingehängt",
        "overview.not_mounted": "nicht eingehängt",
        "overview.readonly": "nur lesend",
        "overview.writable": "schreibend",
        "overview.mount": "Einhängen",
        "overview.umount": "Sicher trennen",
        "overview.scan": "Einlesen",
        "overview.compare": "Vergleichen",
        "overview.last_scan": "Letztes Einlesen",
        "overview.indexed": "erfasst",
        "overview.unhashed": "ohne Prüfsumme",
        "overview.index_complete": "Verzeichnis vollständig",
        "overview.index_incomplete": "Verzeichnis unvollständig",
        "overview.dirty.title": "Diese Platte wurde nicht sauber getrennt",
        "overview.dirty.body": "exFAT hat kein Journal. Prüfe die Platte, bevor "
                               "darauf geschrieben wird: sudo fsck.exfat /dev/…",

        "disks.title": "Platten",
        "disks.connected": "Angeschlossen",
        "disks.registered": "Registriert",
        "disks.register": "Registrieren",
        "disks.none_connected": "Keine Platte mit einem erkannten Dateisystem gefunden.",
        "disks.none_registered": "Noch keine Platte registriert.",
        "disks.label": "Bezeichnung",
        "disks.serial": "Seriennummer",
        "disks.fstype": "Dateisystem",
        "disks.uuid": "UUID",
        "disks.display_name": "Anzeigename",
        "disks.set_name": "Satz",
        "disks.already": "bereits registriert",
        "disks.role_locked": "Rollen lassen sich nicht umschreiben",
        "disks.role_locked_help":
            "Hinzufügen und Vergessen kannst du hier. Eine bestehende Rolle "
            "umschreiben nicht — dafür gibt es keinen Weg, weder hier noch sonstwo. "
            "Einen Master gibst du stattdessen ganz auf (\u201eMaster aufgeben\u201c), danach "
            "ist die Platte unbekannt und du kannst sie neu registrieren, in welcher "
            "Rolle du willst.",
        "plan.show_all": "Auswahl aufheben, alle zeigen",
        "accent.amber": "Bernstein",
        "accent.violet": "Violett",
        "accent.blue": "Blau",
        "accent.emerald": "Smaragd",
        "accent.rose": "Rosé",
        "disks.state": "Zustand",
        "disks.connected": "angeschlossen",
        "disks.not_connected": "nicht angeschlossen",
        "disks.mounted_ro": "eingehängt, nur lesend",
        "disks.mounted_rw": "eingehängt, schreibend",
        "disks.not_mounted": "nicht eingehängt",
        "disks.safe_to_unplug": "Kann abgezogen werden",
        "disks.eject": "Satz {name} auswerfen",
        "disks.eject_help":
            "Hängt alle Platten dieses Satzes aus. Erst danach dürfen sie abgezogen werden.",
        "disks.pick_role": "Rolle wählen …",
        "disks.no_role": "Bitte erst eine Rolle wählen.",
        "claim.look_first":
            "Auf dieser Platte liegen schon Daten. Sieh nach, bevor du sie als Kopie einträgst.",
        "claim.title": "{name} ist nicht leer",
        "claim.body":
            "Als Kopie von „{set}\u201c wird diese Platte schreibend eingehängt, und beim "
            "Abgleich landet der Bestand des Masters darauf. Was hier liegt und nicht zum "
            "Master gehört, meldet AmberShelf zwar, aber verlassen solltest du dich darauf "
            "nicht — trage eine Platte nur dann als Kopie ein, wenn du weißt, was darauf ist.",
        "claim.contents": "Darauf liegen {count} Einträge, unter anderem:",
        "claim.understood":
            "Ich weiß, was auf dieser Platte liegt, und will sie als Kopie verwenden.",
        "claim.do": "Trotzdem als Kopie eintragen",
        "disks.register_help":
            "Der Master wird immer nur lesend eingehängt. Prüfe die Rolle, bevor "
            "du registrierst — ändern lässt sie sich danach nur noch am Host.",

        "assign.title": "Sync-Art",
        "assign.sub": "Legt fest, was auf den Kopien landet.",
        "mode.title": "Wie soll gesynct werden?",
        "mode.active": "aktiv",
        "mode.choose": "Diese Art verwenden",
        "mode.mirror": "Jede Kopie trägt alles",
        "mode.mirror.body":
            "Jede Kopie bekommt den kompletten Bestand des Masters. "
            "Zwei Kopien heißt zweimal derselbe Inhalt \u2013 also zweimal Sicherheit. "
            "Jede einzelne Kopie muss dafür so groß sein wie der belegte Platz auf dem Master.",
        "mode.mirror.example": "Beispiel: Master 4 TB mit 1,5 TB Daten \u2192 jede Kopie braucht 1,5 TB.",
        "mode.mirror.note":
            "In dieser Sync-Art gibt es nichts einzustellen: Jede Kopie bekommt jeden Ordner.",
        "mode.pool": "Kopien teilen sich den Bestand",
        "mode.pool.body":
            "Mehrere kleinere Platten ergeben zusammen ein Ziel. Jeder Ordner des Masters "
            "geht auf genau eine Kopie, zusammen decken sie alles ab. Das spart Platz, "
            "aber jeder Ordner liegt nur einmal \u2013 f\u00e4llt eine Kopie aus, fehlt ihr Teil.",
        "mode.pool.example":
            "Beispiel: Master 4 TB, Kopien 2 TB + 2 TB \u2192 zusammen ein Ziel f\u00fcr 4 TB.",
        "assign.depth": "Ordnerebene",
        "assign.rebuild": "Ordnerbaum neu berechnen",
        "assign.suggest": "Vorschlag berechnen",
        "assign.apply_suggestion": "Vorschlag übernehmen",
        "assign.uncovered": "Nicht zugeordnet",
        "assign.uncovered_warning":
            "Diese Ordner liegen auf keiner Kopie. Sie sind nicht gesichert.",
        "assign.covered": "zugeordnet",
        "assign.inherited": "geerbt",
        "assign.mixed": "geteilt",
        "assign.over_capacity": "passt nicht auf die Platte",
        "assign.no_tree": "Der Master wurde noch nicht eingelesen.",
        "assign.unassign": "nicht zuordnen",
        "assign.capacity": "Belegung",

        "plan.title": "Vorschau",
        "plan.none": "Noch keine Vorschau berechnet.",
        "plan.build": "Vorschau berechnen",
        "plan.not_ready": "Vergleich noch nicht möglich",
        "plan.nothing": "Keine Unterschiede gefunden.",
        "plan.readonly_notice":
            "In diesem Ausbaustand wird noch nichts geschrieben. Die Vorschau zeigt, "
            "was passieren würde.",
        "plan.kind.new": "Neu",
        "plan.kind.changed": "Geändert",
        "plan.kind.renamed": "Umbenannt",
        "plan.kind.slave_only": "Nur auf der Kopie",
        "plan.kind.out_of_scope": "Gehört woanders hin",
        "plan.kind.unreadable": "Nicht lesbar",
        "plan.kind.new.help": "Liegt auf dem Master, fehlt auf der Kopie. Würde kopiert.",
        "plan.kind.changed.help":
            "Auf beiden Seiten vorhanden, Inhalt unterschiedlich. Braucht deine Freigabe.",
        "plan.kind.renamed.help":
            "Gleicher Inhalt unter anderem Namen. Braucht deine Freigabe.",
        "plan.kind.slave_only.help":
            "Liegt nur auf der Kopie und war nie auf dem Master. Wird nur gemeldet.",
        "plan.kind.out_of_scope.help":
            "Liegt auf dem Master, ist aber einer anderen Kopie zugeteilt.",
        "plan.kind.unreadable.help":
            "Beim Einlesen nicht lesbar. Prüfe die Platte.",
        "plan.brake.title": "Notbremse ausgelöst",
        "plan.brake.body": "Es wird nichts ausgeführt, bis du entschieden hast.",
        "plan.needed": "benötigt",
        "plan.fits": "passt",
        "plan.does_not_fit": "passt nicht",
        "plan.deletions_note":
            "Löschungen erscheinen erst, wenn AmberShelf selbst einmal geschrieben hat. "
            "Vorher ist nicht unterscheidbar, ob eine Datei gelöscht wurde oder nie da war.",

        "job.running": "läuft",
        "job.queued": "wartet",
        "job.paused": "angehalten",
        "job.done": "fertig",
        "job.failed": "fehlgeschlagen",
        "job.cancelled": "abgebrochen",
        "job.pause": "Pause",
        "job.resume": "Weiter",
        "job.cancel": "Abbrechen",
        "job.phase.walk": "Ordner durchgehen",
        "job.phase.hash": "Prüfsummen berechnen",
        "job.phase.scope": "Zuordnung auflösen",
        "job.phase.compare": "Vergleichen",
        "job.none": "Nichts läuft gerade.",
        "job.remaining": "verbleibend",

        "events.title": "Verlauf",
        "events.none": "Noch nichts passiert.",

        "settings.title": "Einstellungen",
        "settings.brake": "Notbremse",
        "settings.brake_replace_absolute": "Höchstzahl zu ersetzender Dateien",
        "settings.brake_replace_percent": "Höchstanteil zu ersetzender Dateien (%)",
        "settings.brake_delete_absolute": "Höchstzahl zu löschender Dateien",
        "settings.brake_delete_percent": "Höchstanteil zu löschender Dateien (%)",
        "settings.slave_free_space_gb": "Mindestens freier Platz auf der Kopie (GB)",
        "settings.behaviour": "Verhalten",
        "settings.detect_renames": "Umbenennungen erkennen",
        "settings.verify_after_copy": "Kopien nach dem Schreiben prüfen",
        "settings.assignment_depth": "Ordnerebene für die Aufteilung",
        "settings.language": "Sprache",
        "settings.saved": "Gespeichert.",
        "plan.index_now": "Jetzt alle Platten einlesen",
        "plan.index_hint":
            "Der erste Lauf prüfsummt alles und dauert bei einem großen Archiv "
            "Stunden. Er lässt sich anhalten.",
        "overview.scan_all": "Alle einlesen",
        "overview.compare.needs_index": "Erst einlesen, dann vergleichen",
        "scan.started": "Einlesen gestartet.",
        "scan.none_ready": "Keine Platte bereit — erst den Satz einhängen.",
        "format.help": "Diese Platte formatieren",
        "format.do": "Jetzt löschen und formatieren",
        "format.done": "Formatiert.",
        "format.unsupported":
            "Formatieren geht nur in der Docker-Fassung. Nimm dafür das Werkzeug "
            "deines Systems.",
        "format.not_understood": "Setz das Häkchen — bewusst.",
        "format.device_wrong": "Gerätename stimmt nicht. Es wurde nichts angefasst.",
        "format.warning.title": "{device} wird vollständig gelöscht",
        "format.warning.body":
            "Alles auf dieser Platte ist danach weg. Das lässt sich nicht "
            "rückgängig machen, und AmberShelf hat davon keine Kopie.",
        "format.contents": "Darauf liegen gerade {count} Einträge:",
        "format.contents_unreadable": "Der Inhalt ließ sich nicht lesen.",
        "format.contents_empty": "Auf der Platte ist kein lesbares Dateisystem.",
        "format.filesystem": "Dateisystem",
        "format.label": "Bezeichnung",
        "format.exfat_hint": "Mac und Windows, lesen und schreiben",
        "format.ntfs_hint": "robuster, Mac nur lesend",
        "format.understood": "Mir ist klar, dass alle Daten auf dieser Platte verloren gehen.",
        "format.type_device": "Zum Bestätigen {device} eintippen",
        "disks.reason.no_filesystem": "kein Dateisystem — erst formatieren",
        "disks.reason.unsupported_filesystem": "Dateisystem wird nicht unterstützt",
        "disks.unusable_note":
            "Platten ohne brauchbares Dateisystem stehen mit dem Grund dabei, "
            "statt einfach zu fehlen. Formatiere sie als exFAT, wenn sie auch am "
            "Mac und unter Windows lesbar sein sollen.",
        "exclude.title": "Dauerhaft ausgeschlossen",
        "exclude.help": "Diese Platte dauerhaft ausschließen",
        "exclude.hidden": "{count} ausgeschlossen",
        "exclude.undo": "Wieder zulassen",
        "exclude.done": "Ausgeschlossen. AmberShelf fasst die Platte nicht mehr an.",
        "exclude.undone": "Nicht mehr ausgeschlossen.",
        "exclude.note":
            "Diese Platten erscheinen nirgends mehr und lassen sich weder "
            "registrieren noch einhängen — auch nicht versehentlich. Auf ihnen "
            "wird nichts angefasst.",
        "disks.system_hidden": "{count} Systempartitionen ausgeblendet",
        "disks.show_all": "Auch {count} feste Platten zeigen",
        "disks.only_removable": "Nur Wechseldatenträger",
        "disks.not_removable": "fest eingebaut",
        "disks.show_all_warning":
            "Feste Platten lassen sich nicht abziehen und liegen im selben Gehäuse "
            "wie der Rechner. Als Sicherungskopie taugen sie nur, wenn du weißt, "
            "warum. Systempartitionen werden gar nicht erst angeboten.",
        "forget.help": "Diese Platte vergessen",
        "forget.confirm": "Zum Bestätigen {name} eintippen:",
        "forget.set": "Satz {name} auflösen",
        "forget.set_confirm": "Zum Auflösen {name} eintippen:",
        "forget.do": "Vergessen",
        "forget.done": "Vergessen. Auf der Platte wurde nichts angefasst.",
        "forget.name_wrong": "Name stimmt nicht — es wurde nichts geändert.",
        "forget.unknown": "Diese Platte ist nicht registriert.",
        "forget.busy": "Erst warten, bis der laufende Vorgang fertig ist.",
        "forget.note":
            "Vergessen löscht nur, was AmberShelf über die Platte weiß — "
            "Verzeichnis, Zuteilungen, Verlauf. Auf der Platte selbst wird nichts "
            "angefasst. Eine Platte, die einmal Master war, lässt sich danach nur "
            "wieder als Master registrieren.",
        "disks.demote_off":
            "Hinzufügen und Vergessen kannst du hier. Eine bestehende Rolle "
            "umschreiben nicht. Einen Master aufzugeben ist auf diesem Host "
            "abgeschaltet — das geht nur am Rechner selbst: sudo ambershelf-helper "
            "--admin remove <uuid>, danach --admin forget <uuid>. Wieder "
            "einschalten mit \"allow_demote\": true in /etc/ambershelf/disks.conf.",
        "demote.switched_off":
            "Master aufgeben ist auf diesem Host abgeschaltet.",
        "smart.column": "Zustand (SMART)",
        "smart.check_all": "Plattenzustand prüfen",
        "smart.note":
            "Wird auch bei jedem Einhängen automatisch geholt. Schlafende Platten "
            "werden dafür nicht aufgeweckt.",
        "smart.never": "noch nicht geprüft",
        "smart.unavailable": "keine Auskunft",
        "smart.level.ok": "unauffällig",
        "smart.level.warn": "auffällig",
        "smart.level.danger": "kritisch",
        "smart.level.unknown": "keine Auskunft",
        "smart.hours": "{hours} Betriebsstunden",
        "smart.found_ok": "Alle Platten melden unauffällige Werte.",
        "smart.found_warn": "Mindestens eine Platte meldet auffällige Werte — siehe Platten.",
        "smart.found_danger": "Mindestens eine Platte meldet kritische Werte — siehe Platten.",
        "smart.no_binary":
            "smartctl ist nicht installiert. Auf dem Docker-Host: "
            "sudo apt install smartmontools. Am Mac: brew install smartmontools.",
        "smart.unsupported":
            "Diese Platte gibt ihre SMART-Werte nicht heraus. Bei USB-Gehäusen ist "
            "das häufig — der Chip im Gehäuse reicht die Abfrage nicht durch.",
        "smart.unreadable": "Die Antwort der Platte war nicht lesbar.",
        "smart.timeout": "Die Platte hat nicht geantwortet.",
        "smart.not_connected": "Die Platte ist nicht angeschlossen.",
        "smart.alarm.failed":
            "Die Platte selbst meldet sich als defekt. Sofort ersetzen.",
        "smart.alarm.pending":
            "Sektoren, die die Platte gerade nicht lesen kann. Das ist der ernsteste "
            "Wert überhaupt — sichere, was noch geht, und ersetze die Platte",
        "smart.alarm.uncorrectable":
            "Sektoren, die endgültig nicht mehr lesbar waren — dort liegende Daten "
            "sind verloren",
        "smart.alarm.reallocated":
            "Sektoren, die die Platte aufgegeben und ersetzt hat. Einzelne sind "
            "normal, eine wachsende Zahl nicht",
        "smart.alarm.crc_errors":
            "Übertragungsfehler auf dem Weg zur Platte. Das ist nicht die Platte, "
            "sondern Kabel, Gehäuse oder Stromversorgung",
        "smart.alarm.hot": "Die Platte ist zu warm (°C)",
        "smart.alarm.spare": "Die Reserveblöcke der SSD gehen zur Neige (%)",
        "demote.button": "Master aufgeben",
        "demote.help": "Diese Platte ist dann kein Master mehr",
        "demote.title": "{name} als Master aufgeben",
        "demote.what":
            "Danach kennt AmberShelf diese Platte nicht mehr und du kannst sie neu "
            "registrieren — auch als Kopie, und die wird beschrieben.",
        "demote.effect_registration": "Die Registrierung von {name} wird entfernt.",
        "demote.effect_index":
            "Verzeichnis, Vergleiche, Zuteilungen und Verlauf dieser Platte werden "
            "gelöscht. Nach einer Neuregistrierung muss neu eingelesen werden.",
        "demote.effect_writable":
            "Der Schreibschutz gilt nur für Master. Registrierst du die Platte "
            "danach als Kopie, hängt AmberShelf sie schreibbar ein und kann Dateien "
            "darauf anlegen, ändern und löschen.",
        "demote.effect_data":
            "Auf der Platte selbst wird jetzt nichts angefasst — keine einzige Datei.",
        "demote.understood":
            "Ich weiß, dass diese Platte danach beschreibbar werden kann.",
        "demote.type_name": "Zum Bestätigen den Namen eintippen",
        "demote.password": "Passwort",
        "demote.do": "Master aufgeben",
        "demote.done":
            "Master aufgegeben. Die Platte ist jetzt unbekannt und kann neu "
            "registriert werden. Auf der Platte wurde nichts angefasst.",
        "demote.not_master": "Diese Platte ist kein Master.",
        "demote.not_understood": "Erst den Hinweis bestätigen.",
        "demote.password_wrong": "Passwort falsch — es wurde nichts geändert.",
        "demote.no_password":
            "Für diese Installation ist kein Passwort gesetzt, deshalb wird hier "
            "keins abgefragt.",
        "first.title": "Passwort festlegen",
        "first.body":
            "Du hast dich mit dem erzeugten Passwort angemeldet. Leg jetzt ein "
            "eigenes fest — bis dahin geht nichts anderes.",
        "first.submit": "Festlegen und weiter",
        "first.hint":
            "Mindestens acht Zeichen. Danach ist das erzeugte Passwort ungültig "
            "und alle anderen Sitzungen sind beendet.",
        "password.chosen": "Passwort festgelegt.",
        "login.title": "Anmelden",
        "login.password": "Passwort",
        "login.submit": "Anmelden",
        "login.logout": "Abmelden",
        "login.wrong": "Falsches Passwort.",
        "login.locked": "Zu viele Fehlversuche. Warte kurz.",
        "login.hint":
            "AmberShelf hat einen einzigen Zugang. Beim ersten Start steht das "
            "erzeugte Passwort im Protokoll des Containers - danach legst du "
            "ein eigenes fest.",
        "settings.account": "Zugang",
        "settings.account.help":
            "Ein Passwort für die ganze Anwendung. Beim Ändern werden alle anderen "
            "Sitzungen beendet.",
        "settings.password.current": "Bisheriges Passwort",
        "settings.password.new": "Neues Passwort",
        "settings.password.confirm": "Neues Passwort wiederholen",
        "settings.password.change": "Passwort ändern",
        "settings.sessions": "Angemeldete Geräte",
        "settings.sessions.address": "Adresse",
        "settings.sessions.agent": "Programm",
        "settings.sessions.last_seen": "Zuletzt gesehen",
        "settings.sessions.this_one": "dieses hier",
        "settings.sessions.revoke": "Alle anderen abmelden",
        "sessions.revoked": "Andere Sitzungen beendet.",
        "password.changed": "Passwort geändert, andere Sitzungen beendet.",
        "password.wrong_current": "Das bisherige Passwort stimmt nicht.",
        "password.mismatch": "Die beiden neuen Passwörter sind verschieden.",
        "password.too_short": "Mindestens acht Zeichen.",
        "settings.connection": "Verbindung",
        "settings.connection.help":
            "Diese App kann das Rechenwerk selbst betreiben oder ein Fenster auf "
            "ein AmberShelf sein, das anderswo läuft — etwa die Docker-Fassung auf "
            "einem Linux-Rechner.",
        "settings.connection.restart":
            "Wirkt beim nächsten Start. Sollte die Adresse nicht antworten, "
            "startet die App wieder örtlich. Mit dem Schalter --local kommst du "
            "immer zurück.",
        "settings.desktop_mode": "Betriebsart",
        "settings.desktop_mode.local": "Auf diesem Rechner",
        "settings.desktop_mode.remote": "Entfernter Server",
        "settings.desktop_remote_url": "Adresse des entfernten Servers",
        "nav.findings": "Befunde",
        "findings.title": "Befunde",
        "findings.sub": "Was der Integritätsprüfung aufgefallen ist",
        "findings.none": "Nichts zu beanstanden.",
        "findings.clear": "Alle als gesehen abhaken",
        "findings.cleared": "Abgehakt.",
        "findings.kind": "Art",
        "findings.found_at": "Gefunden",
        "findings.warning.title": "{count} Befunde",
        "findings.warning.body":
            "Solange hier etwas offen ist, bleibt die Notbremse eingelegt. Sieh "
            "dir die Dateien an und hake sie ab, wenn sie in Ordnung sind.",
        "findings.kind.header_mismatch": "Kopf passt nicht",
        "findings.kind.text_garbled": "Text unlesbar",
        "findings.kind.empty": "Leer",
        "findings.kind.unreadable": "Nicht lesbar",
        "findings.kind.ransom_note": "Erpresserbrief",
        "findings.kind.double_extension": "Zweite Endung",
        "findings.kind.burst": "Massenänderung",
        "findings.kinds.help":
            "Kopf passt nicht: Der Inhalt beginnt nicht so, wie die Endung es "
            "verspricht — genau das passiert bei Verschlüsselung. Massenänderung: "
            "Sehr viele Dateien wurden fast gleichzeitig geändert.",
        "brake.integrity": "{count} Befunde der Integritätsprüfung sind offen",
        "scan.damaged": "{count} beschädigt",
        "scan.suspicious": "{count} auffällige Namen",
        "job.phase.check": "Dateien prüfen",
        "settings.integrity_check": "Dateien beim Einlesen auf Beschädigung prüfen",
        "settings.notify": "Benachrichtigung",
        "settings.notify.help":
            "AmberShelf schickt bei Ereignissen ein kleines JSON an eine Adresse "
            "deiner Wahl — Home Assistant, ntfy, Gotify oder ein eigenes Skript.",
        "settings.notify_url": "Adresse (Webhook)",
        "settings.notify_level": "Wann melden",
        "settings.notify_level.off": "gar nicht",
        "settings.notify_level.errors": "nur Fehler",
        "settings.notify_level.warnings": "Fehler und Warnungen",
        "settings.notify_level.all": "alles",
        "settings.notify_headers": "Zusätzliche Kopfzeilen (JSON, optional)",
        "settings.notify.test": "Testnachricht senden",
        "notify.sent": "Testnachricht verschickt.",
        "notify.no_url": "Erst eine Adresse eintragen.",
        "apply.refused.gone": "Diesen Plan gibt es nicht mehr.",
        "apply.refused.stale": "Es gibt einen neueren Vergleich — sieh dir den an.",
        "apply.refused.blocked": "Die Notbremse ist eingelegt.",
        "apply.refused.applied": "Dieser Plan wurde bereits ausgeführt.",
        "apply.refused.no_master": "Dieser Satz hat keinen Master.",
        "apply.refused.nothing": "Nichts ausgewählt — gib zuerst etwas frei.",
        "plan.kind.deleted": "Gelöscht",
        "plan.kind.deleted.help":
            "Von AmberShelf hierher kopiert, auf dem Master nicht mehr vorhanden. "
            "Braucht deine Freigabe.",
        "plan.state.applied": "ausgeführt",
        "plan.copy_modified": "Die Kopie selbst wurde verändert, nicht der Master",
        "plan.pending": "{count} ohne Entscheidung",
        "plan.apply": "{count} ausführen",
        "plan.apply.help":
            "{count} Vorgänge sind freigegeben. Neue Dateien werden kopiert; "
            "ersetzte und gelöschte landen unter .ambershelf-trash auf der Kopie.",
        "plan.decide": "Entscheidung",
        "plan.decide.all": "Alle in dieser Liste:",
        "plan.decide.approve": "Freigeben",
        "plan.decide.skip_once": "Diesmal übergehen",
        "plan.decide.skip_forever": "Nie wieder fragen",
        "plan.brake.confirm": "Zum Lösen die Zahl {number} eintippen",
        "plan.brake.release": "Notbremse lösen",
        "brake.wrong_number": "Falsche Zahl — die Notbremse bleibt.",
        "brake.released": "Notbremse gelöst.",
        "brake.delete_absolute": "{count} Dateien würden gelöscht, erlaubt sind {limit}",
        "brake.delete_percent":
            "{percent} % des Bestands würden gelöscht, erlaubt sind {limit} %",
        "apply.started": "Ausführung gestartet.",
        "run.title": "Lauf",
        "run.items": "Vorgänge",
        "run.all": "Alle",
        "run.copied": "Kopiert",
        "run.replaced": "Ersetzt",
        "run.renamed": "Umbenannt",
        "run.deleted": "Gelöscht",
        "run.failed": "Fehlgeschlagen",
        "run.written": "Geschrieben",
        "run.state.running": "läuft",
        "run.state.done": "fertig",
        "run.state.done_with_errors": "mit Fehlern beendet",
        "run.state.failed": "fehlgeschlagen",
        "run.state.cancelled": "abgebrochen",
        "run.state.interrupted": "unterbrochen",
        "events.runs": "Läufe",
        "events.no_runs": "Noch nichts ausgeführt.",
        "job.phase.apply": "Ausführen",
        "settings.delete_mode": "Gelöschte und ersetzte Dateien",
        "settings.delete_mode.trash": "nach .ambershelf-trash verschieben",
        "settings.delete_mode.remove": "endgültig löschen",
        "settings.keep_mtime": "Änderungsdatum mitkopieren",
        "overview.unprotected": "nicht schreibgeschützt",
        "unprotected.title": "Der Master ist auf diesem System nicht schreibgeschützt",
        "unprotected.body":
            "AmberShelf schreibt nie auf ihn — aber jedes andere Programm auf diesem "
            "Rechner kann es. Den vom Kernel erzwungenen Schutz gibt es nur in der "
            "Docker-Fassung auf einem Linux-Rechner.",
        "unprotected.registry":
            "Auch die Zuordnung von Platte zu Rolle liegt hier in einer Datei, die dir "
            "gehört, und ist damit änderbar.",
        "support.star": "Stern auf GitHub",
        "support.coffee": "Kaffee spendieren",
        "nav.section.main": "Betrieb",
        "nav.section.system": "System",
        "overview.sub": "Platten, Zustand und letzte Läufe",
        "overview.connected_count": "{connected} von {total} angeschlossen",
        "overview.empty": "leer",
        "overview.rehash": "Neu prüfen",
        "overview.rehash.help": "Alle Prüfsummen verwerfen, beim nächsten Einlesen neu berechnen",
        "common.used": "belegt",
        "disks.sub": "Erkennen, registrieren, Rollen ansehen",
        "assign.folders": "Ordner",
        "plan.result": "Ergebnis",
        "events.log": "Meldungen",
        "events.scans": "Einlesevorgänge",
        "settings.appearance": "Darstellung",
        "settings.theme": "Erscheinungsbild",
        "settings.theme.light": "Hell",
        "settings.theme.dark": "Dunkel",
        "settings.theme.system": "System",
        "settings.accent": "Akzentfarbe",
        "settings.brake.help":
            "Wird eine Grenze überschritten, wird der Lauf angehalten und "
            "nichts ausgeführt.",
        "plan.state.building": "wird berechnet",
        "plan.state.ready": "bereit",
        "plan.state.blocked": "gesperrt",
        "plan.state.cancelled": "abgebrochen",

        "scan.summary": "{files} Dateien · {size} · {hashed} neu geprüft",
        "scan.removed": "{count} seit dem letzten Lauf verschwunden",
        "scan.vanished": "{count} während des Lesens verschwunden",
        "scan.errors": "{count} Lesefehler",
        "brake.replace_absolute": "{count} Dateien würden ersetzt, erlaubt sind {limit}",
        "brake.replace_percent":
            "{percent} % des Bestands würden ersetzt, erlaubt sind "
            "{limit} %",
        "brake.unreadable": "{count} Dateien waren beim Einlesen nicht lesbar",
        "brake.free_space": "Auf {disk} blieben danach weniger als {limit} GB frei",
        "ready.no_master": "Dieser Satz hat keinen Master",
        "ready.no_slave": "Dieser Satz hat keine Kopie",
        "ready.not_indexed": "{disk} wurde noch nicht eingelesen",
        "ready.unhashed": "{disk} hat noch {count} Dateien ohne Prüfsumme",
        "events.technical":
            "Technisches Protokoll — bewusst auf Englisch, damit "
            "Meldungen suchbar bleiben.",
    },
    "en": {
        "app.name": "AmberShelf",
        "app.tagline": "Disk mirroring with an approval step",

        "nav.overview": "Overview",
        "nav.disks": "Disks",
        "nav.assign": "Sync mode",
        "nav.plan": "Preview",
        "nav.events": "History",
        "nav.settings": "Settings",

        "common.yes": "Yes",
        "common.no": "No",
        "common.save": "Save",
        "common.cancel": "Cancel",
        "common.close": "Close",
        "common.files": "files",
        "common.size": "size",
        "common.path": "path",
        "common.disk": "disk",
        "common.role": "role",
        "common.set": "set",
        "common.state": "state",
        "common.none": "none",
        "common.unknown": "unknown",
        "common.back": "Back",
        "common.of": "of",
        "common.free": "free",
        "common.total": "total",
        "common.never": "never",

        "role.master": "Master",
        "role.slave": "Copy",

        "helper.missing.title": "The host helper is not answering",
        "helper.missing.body": "Without it nothing can be mounted. On the host check: "
                               "systemctl status ambershelf-helper",

        "overview.title": "Overview",
        "overview.no_sets": "No set yet. Register a disk first.",
        "overview.connected": "connected",
        "overview.not_connected": "not connected",
        "overview.mounted": "mounted",
        "overview.not_mounted": "not mounted",
        "overview.readonly": "read-only",
        "overview.writable": "writable",
        "overview.mount": "Mount",
        "overview.umount": "Eject safely",
        "overview.scan": "Index",
        "overview.compare": "Compare",
        "overview.last_scan": "Last index run",
        "overview.indexed": "indexed",
        "overview.unhashed": "without a hash",
        "overview.index_complete": "index complete",
        "overview.index_incomplete": "index incomplete",
        "overview.dirty.title": "This disk was not unmounted cleanly",
        "overview.dirty.body": "exFAT has no journal. Check the disk before writing "
                               "to it: sudo fsck.exfat /dev/…",

        "disks.title": "Disks",
        "disks.connected": "Connected",
        "disks.registered": "Registered",
        "disks.register": "Register",
        "disks.none_connected": "No disk with a recognised filesystem found.",
        "disks.none_registered": "No disk registered yet.",
        "disks.label": "Label",
        "disks.serial": "Serial",
        "disks.fstype": "Filesystem",
        "disks.uuid": "UUID",
        "disks.display_name": "Name",
        "disks.set_name": "Set",
        "disks.already": "already registered",
        "disks.role_locked": "Roles are never rewritten",
        "disks.role_locked_help":
            "Adding and forgetting happen here. Rewriting the role of a registered "
            "disk does not - there is no path for it anywhere. Instead you give a "
            "master up entirely (\u201cGive up master\u201d); the disk is then unknown "
            "and you can register it again in whatever role you want.",
        "plan.show_all": "Clear the selection, show everything",
        "accent.amber": "Amber",
        "accent.violet": "Violet",
        "accent.blue": "Blue",
        "accent.emerald": "Emerald",
        "accent.rose": "Rose",
        "disks.state": "State",
        "disks.connected": "connected",
        "disks.not_connected": "not connected",
        "disks.mounted_ro": "mounted, read-only",
        "disks.mounted_rw": "mounted, writable",
        "disks.not_mounted": "not mounted",
        "disks.safe_to_unplug": "Safe to unplug",
        "disks.eject": "Eject set {name}",
        "disks.eject_help":
            "Unmounts every disk of this set. Only then may they be unplugged.",
        "disks.pick_role": "Choose a role \u2026",
        "disks.no_role": "Choose a role first.",
        "claim.look_first":
            "There is already something on this disk. Have a look before registering it "
            "as a copy.",
        "claim.title": "{name} is not empty",
        "claim.body":
            "As a copy of \u201c{set}\u201d this disk is mounted writable, and a sync puts "
            "the master's archive on it. AmberShelf reports what is here and does not "
            "belong to the master, but do not lean on that - only register a disk as a "
            "copy when you know what is on it.",
        "claim.contents": "It holds {count} entries, among them:",
        "claim.understood": "I know what is on this disk and want to use it as a copy.",
        "claim.do": "Register as a copy anyway",
        "disks.register_help":
            "A master is always mounted read-only. Check the role before registering - "
            "afterwards it can only be changed on the host.",

        "assign.title": "Sync mode",
        "assign.sub": "Decides what ends up on the copies.",
        "mode.title": "How should this set be synced?",
        "mode.active": "active",
        "mode.choose": "Use this mode",
        "mode.mirror": "Every copy carries everything",
        "mode.mirror.body":
            "Each copy receives the master's complete archive. Two copies mean the same "
            "content twice \u2013 two chances to survive a failure. In return, every single "
            "copy has to be as large as the used space on the master.",
        "mode.mirror.example": "Example: a 4 TB master holding 1.5 TB \u2192 every copy needs 1.5 TB.",
        "mode.mirror.note": "There is nothing to configure in this mode: every copy gets every folder.",
        "mode.pool": "Copies share the archive",
        "mode.pool.body":
            "Several smaller disks act as one target. Every folder of the master goes to "
            "exactly one copy, and together they cover all of it. That saves space, but each "
            "folder exists only once \u2013 lose a copy and you lose its share.",
        "mode.pool.example":
            "Example: a 4 TB master with 2 TB + 2 TB copies \u2192 one 4 TB target.",
        "assign.depth": "Folder level",
        "assign.rebuild": "Rebuild the folder tree",
        "assign.suggest": "Calculate a proposal",
        "assign.apply_suggestion": "Apply the proposal",
        "assign.uncovered": "Not assigned",
        "assign.uncovered_warning":
            "These folders are on no copy at all. They are not backed up.",
        "assign.covered": "assigned",
        "assign.inherited": "inherited",
        "assign.mixed": "split",
        "assign.over_capacity": "does not fit on the disk",
        "assign.no_tree": "The master has not been indexed yet.",
        "assign.unassign": "unassign",
        "assign.capacity": "Usage",

        "plan.title": "Preview",
        "plan.none": "No preview calculated yet.",
        "plan.build": "Calculate preview",
        "plan.not_ready": "Cannot compare yet",
        "plan.nothing": "No differences found.",
        "plan.readonly_notice":
            "At this stage nothing is written yet. The preview shows what would happen.",
        "plan.kind.new": "New",
        "plan.kind.changed": "Changed",
        "plan.kind.renamed": "Renamed",
        "plan.kind.slave_only": "Only on the copy",
        "plan.kind.out_of_scope": "Belongs elsewhere",
        "plan.kind.unreadable": "Unreadable",
        "plan.kind.new.help": "On the master, missing on the copy. Would be copied.",
        "plan.kind.changed.help":
            "Present on both sides with different contents. Needs your approval.",
        "plan.kind.renamed.help":
            "Same contents under a different name. Needs your approval.",
        "plan.kind.slave_only.help":
            "Only on the copy and never on the master. Reported only.",
        "plan.kind.out_of_scope.help":
            "On the master, but assigned to a different copy.",
        "plan.kind.unreadable.help":
            "Could not be read while indexing. Check the disk.",
        "plan.brake.title": "The brake tripped",
        "plan.brake.body": "Nothing runs until you have decided.",
        "plan.needed": "needed",
        "plan.fits": "fits",
        "plan.does_not_fit": "does not fit",
        "plan.deletions_note":
            "Deletions only appear once AmberShelf has written to a copy itself. "
            "Before that there is no way to tell a deleted file from one that was "
            "never there.",

        "job.running": "running",
        "job.queued": "queued",
        "job.paused": "paused",
        "job.done": "done",
        "job.failed": "failed",
        "job.cancelled": "cancelled",
        "job.pause": "Pause",
        "job.resume": "Resume",
        "job.cancel": "Cancel",
        "job.phase.walk": "Walking folders",
        "job.phase.hash": "Hashing",
        "job.phase.scope": "Resolving assignments",
        "job.phase.compare": "Comparing",
        "job.none": "Nothing is running.",
        "job.remaining": "remaining",

        "events.title": "History",
        "events.none": "Nothing has happened yet.",

        "settings.title": "Settings",
        "settings.brake": "Brake",
        "settings.brake_replace_absolute": "Maximum files to replace",
        "settings.brake_replace_percent": "Maximum share of files to replace (%)",
        "settings.brake_delete_absolute": "Maximum files to delete",
        "settings.brake_delete_percent": "Maximum share of files to delete (%)",
        "settings.slave_free_space_gb": "Minimum free space left on a copy (GB)",
        "settings.behaviour": "Behaviour",
        "settings.detect_renames": "Detect renames",
        "settings.verify_after_copy": "Verify copies after writing",
        "settings.assignment_depth": "Folder level used for splitting",
        "settings.language": "Language",
        "settings.saved": "Saved.",
        "plan.index_now": "Index every disk now",
        "plan.index_hint":
            "The first run hashes everything and takes hours for a large archive. "
            "It can be paused.",
        "overview.scan_all": "Index all",
        "overview.compare.needs_index": "Index first, then compare",
        "scan.started": "Indexing started.",
        "scan.none_ready": "No disk is ready - mount the set first.",
        "format.help": "Format this disk",
        "format.do": "Erase and format now",
        "format.done": "Formatted.",
        "format.unsupported":
            "Formatting is only available in the Docker edition. Use your system's "
            "own tool for it.",
        "format.not_understood": "Tick the box - deliberately.",
        "format.device_wrong": "The device name does not match. Nothing was touched.",
        "format.warning.title": "{device} will be erased completely",
        "format.warning.body":
            "Everything on this disk is gone afterwards. It cannot be undone, and "
            "AmberShelf has no copy of it.",
        "format.contents": "It currently holds {count} entries:",
        "format.contents_unreadable": "The contents could not be read.",
        "format.contents_empty": "There is no readable filesystem on this disk.",
        "format.filesystem": "Filesystem",
        "format.label": "Label",
        "format.exfat_hint": "macOS and Windows, read and write",
        "format.ntfs_hint": "more robust, macOS read-only",
        "format.understood": "I understand that all data on this disk will be lost.",
        "format.type_device": "Type {device} to confirm",
        "disks.reason.no_filesystem": "no filesystem - format it first",
        "disks.reason.unsupported_filesystem": "filesystem is not supported",
        "disks.unusable_note":
            "A disk with nothing readable on it is listed with the reason rather "
            "than simply missing. Format it as exFAT if it also has to work on "
            "macOS and Windows.",
        "exclude.title": "Excluded for good",
        "exclude.help": "Exclude this disk for good",
        "exclude.hidden": "{count} excluded",
        "exclude.undo": "Allow again",
        "exclude.done": "Excluded. AmberShelf will not touch that disk.",
        "exclude.undone": "No longer excluded.",
        "exclude.note":
            "These disks appear nowhere and can neither be registered nor mounted, "
            "not even by accident. Nothing on them is touched.",
        "disks.system_hidden": "{count} system partitions hidden",
        "disks.show_all": "Also show {count} fixed disks",
        "disks.only_removable": "Removable only",
        "disks.not_removable": "built in",
        "disks.show_all_warning":
            "A fixed disk cannot be unplugged and sits in the same box as the "
            "computer. It makes a backup copy only if you know why. System "
            "partitions are not offered at all.",
        "forget.help": "Forget this disk",
        "forget.confirm": "Type {name} to confirm:",
        "forget.set": "Dissolve set {name}",
        "forget.set_confirm": "Type {name} to dissolve it:",
        "forget.do": "Forget",
        "forget.done": "Forgotten. Nothing on the disk was touched.",
        "forget.name_wrong": "The name does not match - nothing was changed.",
        "forget.unknown": "This disk is not registered.",
        "forget.busy": "Wait until the running job has finished.",
        "forget.note":
            "Forgetting removes only what AmberShelf knows about the disk - the "
            "index, the assignments, the history. Nothing on the disk itself is "
            "touched. A disk that has been a master can afterwards only be "
            "registered as a master again.",
        "disks.demote_off":
            "Adding and forgetting happen here. Rewriting the role of a registered "
            "disk does not. Giving a master up is switched off on this host - it "
            "can only be done at the machine itself: sudo ambershelf-helper --admin "
            "remove <uuid>, then --admin forget <uuid>. Switch it back on with "
            "\"allow_demote\": true in /etc/ambershelf/disks.conf.",
        "demote.switched_off": "Giving a master up is switched off on this host.",
        "smart.column": "Health (SMART)",
        "smart.check_all": "Check disk health",
        "smart.note":
            "Also fetched automatically whenever a set is mounted. Sleeping disks "
            "are not woken up for it.",
        "smart.never": "not checked yet",
        "smart.unavailable": "no answer",
        "smart.level.ok": "nothing to report",
        "smart.level.warn": "worth a look",
        "smart.level.danger": "serious",
        "smart.level.unknown": "no answer",
        "smart.hours": "{hours} hours powered on",
        "smart.found_ok": "Every disk reports normal values.",
        "smart.found_warn": "At least one disk reports something worth a look - see Disks.",
        "smart.found_danger": "At least one disk reports something serious - see Disks.",
        "smart.no_binary":
            "smartctl is not installed. On the Docker host: sudo apt install "
            "smartmontools. On a Mac: brew install smartmontools.",
        "smart.unsupported":
            "This disk does not hand out its SMART values. That is common with USB "
            "enclosures - the chip inside does not pass the question through.",
        "smart.unreadable": "The answer from the disk could not be read.",
        "smart.timeout": "The disk did not answer.",
        "smart.not_connected": "The disk is not connected.",
        "smart.alarm.failed": "The disk reports itself as failing. Replace it now.",
        "smart.alarm.pending":
            "Sectors the disk currently cannot read. This is the most serious value "
            "there is - rescue what you can and replace the disk",
        "smart.alarm.uncorrectable":
            "Sectors that could not be read and could not be recovered - whatever "
            "was there is gone",
        "smart.alarm.reallocated":
            "Sectors the disk has given up on and replaced. A few are normal, a "
            "growing number is not",
        "smart.alarm.crc_errors":
            "Transfers that arrived damaged. This is not the disk itself but the "
            "cable, the enclosure or the power supply",
        "smart.alarm.hot": "The disk is running too warm (°C)",
        "smart.alarm.spare": "The SSD is running out of spare blocks (%)",
        "demote.button": "Give up master",
        "demote.help": "This disk stops being a master",
        "demote.title": "Give up {name} as a master",
        "demote.what":
            "Afterwards AmberShelf does not know this disk any more and you can "
            "register it again - as a copy too, and a copy is written to.",
        "demote.effect_registration": "The registration of {name} is removed.",
        "demote.effect_index":
            "The index, comparisons, assignments and history of this disk are "
            "deleted. After registering it again it has to be indexed from scratch.",
        "demote.effect_writable":
            "Write protection applies to masters only. Register the disk as a copy "
            "afterwards and AmberShelf mounts it writable and may create, change "
            "and delete files on it.",
        "demote.effect_data":
            "Nothing on the disk itself is touched right now - not a single file.",
        "demote.understood": "I know this disk can become writable afterwards.",
        "demote.type_name": "Type the name to confirm",
        "demote.password": "Password",
        "demote.do": "Give up master",
        "demote.done":
            "Master given up. The disk is unknown now and can be registered again. "
            "Nothing on the disk was touched.",
        "demote.not_master": "This disk is not a master.",
        "demote.not_understood": "Acknowledge the warning first.",
        "demote.password_wrong": "Wrong password - nothing was changed.",
        "demote.no_password":
            "This installation has no password set, so none is asked for here.",
        "first.title": "Choose a password",
        "first.body":
            "You signed in with the generated password. Choose your own now - "
            "nothing else works until you do.",
        "first.submit": "Set it and continue",
        "first.hint":
            "At least eight characters. Afterwards the generated password stops "
            "working and every other session is ended.",
        "password.chosen": "Password set.",
        "login.title": "Sign in",
        "login.password": "Password",
        "login.submit": "Sign in",
        "login.logout": "Sign out",
        "login.wrong": "Wrong password.",
        "login.locked": "Too many attempts. Wait a moment.",
        "login.hint":
            "AmberShelf has a single way in. On first start the generated password "
            "is in the container's log - you then choose your own.",
        "settings.account": "Account",
        "settings.account.help":
            "One password for the whole application. Changing it ends every other "
            "session.",
        "settings.password.current": "Current password",
        "settings.password.new": "New password",
        "settings.password.confirm": "Repeat the new password",
        "settings.password.change": "Change the password",
        "settings.sessions": "Signed-in devices",
        "settings.sessions.address": "Address",
        "settings.sessions.agent": "Program",
        "settings.sessions.last_seen": "Last seen",
        "settings.sessions.this_one": "this one",
        "settings.sessions.revoke": "Sign out everything else",
        "sessions.revoked": "Other sessions ended.",
        "password.changed": "Password changed, other sessions ended.",
        "password.wrong_current": "The current password is wrong.",
        "password.mismatch": "The two new passwords differ.",
        "password.too_short": "At least eight characters.",
        "settings.connection": "Connection",
        "settings.connection.help":
            "This application can run the engine itself, or be a window onto an "
            "AmberShelf running somewhere else - the Docker one on a Linux machine, "
            "for instance.",
        "settings.connection.restart":
            "Takes effect at the next start. If the address does not answer, the "
            "application starts locally again. The --local switch always gets you "
            "back.",
        "settings.desktop_mode": "Mode",
        "settings.desktop_mode.local": "On this computer",
        "settings.desktop_mode.remote": "Remote server",
        "settings.desktop_remote_url": "Address of the remote server",
        "nav.findings": "Findings",
        "findings.title": "Findings",
        "findings.sub": "What the integrity check objected to",
        "findings.none": "Nothing to report.",
        "findings.clear": "Acknowledge all",
        "findings.cleared": "Acknowledged.",
        "findings.kind": "Kind",
        "findings.found_at": "Found",
        "findings.warning.title": "{count} findings",
        "findings.warning.body":
            "While anything here is open the brake stays engaged. Look at the "
            "files and acknowledge them if they are fine.",
        "findings.kind.header_mismatch": "Header mismatch",
        "findings.kind.text_garbled": "Text unreadable",
        "findings.kind.empty": "Empty",
        "findings.kind.unreadable": "Unreadable",
        "findings.kind.ransom_note": "Ransom note",
        "findings.kind.double_extension": "Second extension",
        "findings.kind.burst": "Mass change",
        "findings.kinds.help":
            "Header mismatch: the content does not begin the way the extension "
            "promises - which is exactly what encryption does. Mass change: a "
            "great many files changed at almost the same moment.",
        "brake.integrity": "{count} findings from the integrity check are open",
        "scan.damaged": "{count} damaged",
        "scan.suspicious": "{count} suspicious names",
        "job.phase.check": "Checking files",
        "settings.integrity_check": "Check files for damage while indexing",
        "settings.notify": "Notification",
        "settings.notify.help":
            "AmberShelf posts a small JSON object to an address of your choice when "
            "something happens - Home Assistant, ntfy, Gotify or a script of your "
            "own.",
        "settings.notify_url": "Address (webhook)",
        "settings.notify_level": "When to send",
        "settings.notify_level.off": "never",
        "settings.notify_level.errors": "errors only",
        "settings.notify_level.warnings": "errors and warnings",
        "settings.notify_level.all": "everything",
        "settings.notify_headers": "Extra headers (JSON, optional)",
        "settings.notify.test": "Send a test",
        "notify.sent": "Test notification sent.",
        "notify.no_url": "Enter an address first.",
        "apply.refused.gone": "This plan no longer exists.",
        "apply.refused.stale": "A newer comparison exists - look at that one.",
        "apply.refused.blocked": "The brake is engaged.",
        "apply.refused.applied": "This plan has already been carried out.",
        "apply.refused.no_master": "This set has no master.",
        "apply.refused.nothing": "Nothing selected - approve something first.",
        "plan.kind.deleted": "Deleted",
        "plan.kind.deleted.help":
            "Copied here by AmberShelf, gone from the master. Needs your approval.",
        "plan.state.applied": "carried out",
        "plan.copy_modified": "The copy itself was altered, not the master",
        "plan.pending": "{count} undecided",
        "plan.apply": "Carry out {count}",
        "plan.apply.help":
            "{count} operations are approved. New files are copied; replaced and "
            "deleted ones are parked under .ambershelf-trash on the copy.",
        "plan.decide": "Decision",
        "plan.decide.all": "Everything in this list:",
        "plan.decide.approve": "Approve",
        "plan.decide.skip_once": "Skip this time",
        "plan.decide.skip_forever": "Never ask again",
        "plan.brake.confirm": "Type {number} to release",
        "plan.brake.release": "Release the brake",
        "brake.wrong_number": "Wrong number - the brake stays on.",
        "brake.released": "The brake was released.",
        "brake.delete_absolute": "{count} files would be deleted, the limit is {limit}",
        "brake.delete_percent":
            "{percent}% of the archive would be deleted, the limit is {limit}%",
        "apply.started": "The run has started.",
        "run.title": "Run",
        "run.items": "Operations",
        "run.all": "All",
        "run.copied": "Copied",
        "run.replaced": "Replaced",
        "run.renamed": "Renamed",
        "run.deleted": "Deleted",
        "run.failed": "Failed",
        "run.written": "Written",
        "run.state.running": "running",
        "run.state.done": "done",
        "run.state.done_with_errors": "finished with errors",
        "run.state.failed": "failed",
        "run.state.cancelled": "cancelled",
        "run.state.interrupted": "interrupted",
        "events.runs": "Runs",
        "events.no_runs": "Nothing has been carried out yet.",
        "job.phase.apply": "Carrying out",
        "settings.delete_mode": "Deleted and replaced files",
        "settings.delete_mode.trash": "move to .ambershelf-trash",
        "settings.delete_mode.remove": "delete for good",
        "settings.keep_mtime": "Copy the modification date too",
        "overview.unprotected": "not write-protected",
        "unprotected.title": "The master is not write-protected on this system",
        "unprotected.body":
            "AmberShelf never writes to it - but any other program on this computer "
            "can. Protection the kernel actually enforces only exists in the Docker "
            "edition on a Linux machine.",
        "unprotected.registry":
            "The mapping from disk to role also lives in a file you own here, so it "
            "can be changed.",
        "support.star": "Star on GitHub",
        "support.coffee": "Buy me a coffee",
        "nav.section.main": "Operation",
        "nav.section.system": "System",
        "overview.sub": "Disks, state and recent runs",
        "overview.connected_count": "{connected} of {total} connected",
        "overview.empty": "empty",
        "overview.rehash": "Rehash",
        "overview.rehash.help": "Drop every stored hash and recompute on the next index run",
        "common.used": "used",
        "disks.sub": "Detect, register, review roles",
        "assign.folders": "Folders",
        "plan.result": "Result",
        "events.log": "Messages",
        "events.scans": "Index runs",
        "settings.appearance": "Appearance",
        "settings.theme": "Theme",
        "settings.theme.light": "Light",
        "settings.theme.dark": "Dark",
        "settings.theme.system": "System",
        "settings.accent": "Accent colour",
        "settings.brake.help":
            "When a limit is passed the run is held and nothing is carried "
            "out.",
        "plan.state.building": "being calculated",
        "plan.state.ready": "ready",
        "plan.state.blocked": "blocked",
        "plan.state.cancelled": "cancelled",

        "scan.summary": "{files} files · {size} · {hashed} newly hashed",
        "scan.removed": "{count} gone since the last run",
        "scan.vanished": "{count} disappeared while reading",
        "scan.errors": "{count} read errors",
        "brake.replace_absolute": "{count} files would be replaced, the limit is {limit}",
        "brake.replace_percent":
            "{percent}% of the archive would be replaced, the limit is "
            "{limit}%",
        "brake.unreadable": "{count} files could not be read while indexing",
        "brake.free_space": "{disk} would be left with less than {limit} GB free",
        "ready.no_master": "This set has no master",
        "ready.no_slave": "This set has no copy",
        "ready.not_indexed": "{disk} has not been indexed yet",
        "ready.unhashed": "{disk} still has {count} files without a hash",
        "events.technical":
            "Technical log - kept in English on purpose so messages stay "
            "searchable.",
    },
}


def translator(language: str):
    table = STRINGS.get(language) or STRINGS["de"]
    fallback = STRINGS["en"]

    def translate(key: str, **kwargs) -> str:
        text = table.get(key) or fallback.get(key) or key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text
        return text

    return translate


def pick_language(cookie: str | None, accept_language: str | None, default: str) -> str:
    if cookie in LANGUAGES:
        return cookie
    for part in (accept_language or "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in LANGUAGES:
            return code
    return default if default in LANGUAGES else "de"
