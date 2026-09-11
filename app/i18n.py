# AmberSync - Copyright (C) 2026 Dennis Arning - AGPL-3.0-or-later
"""Two languages, one dictionary. Missing keys fall back to the key itself,
which is ugly enough to be noticed during testing."""
from __future__ import annotations

LANGUAGES = {"de": "Deutsch", "en": "English"}

STRINGS: dict[str, dict[str, str]] = {
    "de": {
        "app.name": "AmberSync",
        "app.tagline": "Plattenabgleich mit Freigabe",

        "nav.overview": "Übersicht",
        "nav.disks": "Platten",
        "nav.assign": "Aufteilung",
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
                               "Prüfe auf dem Host: systemctl status ambersync-helper",

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
        "disks.role_locked": "Rollen und Löschungen nur auf dem Host",
        "disks.role_locked_help":
            "Der Container darf Platten hinzufügen, aber keine Rolle ändern und "
            "nichts entfernen. Das geht bewusst nur auf dem Host: "
            "sudo ambersync-helper --admin set-role <uuid> slave",
        "disks.register_help":
            "Der Master wird immer nur lesend eingehängt. Prüfe die Rolle, bevor "
            "du registrierst — ändern lässt sie sich danach nur noch am Host.",

        "assign.title": "Aufteilung",
        "assign.split_off": "Alle Kopien tragen den vollständigen Bestand.",
        "assign.split_on": "Der Bestand ist auf die Kopien verteilt.",
        "assign.enable": "Aufteilen einschalten",
        "assign.disable": "Aufteilen ausschalten",
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
            "Löschungen erscheinen erst, wenn AmberSync selbst einmal geschrieben hat. "
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
        "app.name": "AmberSync",
        "app.tagline": "Disk mirroring with an approval step",

        "nav.overview": "Overview",
        "nav.disks": "Disks",
        "nav.assign": "Split",
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
                               "systemctl status ambersync-helper",

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
        "disks.role_locked": "Roles and removals are host-only",
        "disks.role_locked_help":
            "The container may add disks but can never change a role or remove one. "
            "That is deliberate and has to be done on the host: "
            "sudo ambersync-helper --admin set-role <uuid> slave",
        "disks.register_help":
            "A master is always mounted read-only. Check the role before registering - "
            "afterwards it can only be changed on the host.",

        "assign.title": "Split",
        "assign.split_off": "Every copy carries the full archive.",
        "assign.split_on": "The archive is split across the copies.",
        "assign.enable": "Turn splitting on",
        "assign.disable": "Turn splitting off",
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
            "Deletions only appear once AmberSync has written to a copy itself. "
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
