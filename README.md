# AmberSync

One-way disk mirroring with an approval step, for archives that should not
change behind your back.

You plug in a master disk and one or more copies. AmberSync reads both,
compares them by content hash, and shows you exactly what it would do. It
never deletes, never overwrites and never writes to the master.

Built for a photo and video archive: files get added, almost nothing is ever
changed, and a copy should stay a plain browsable folder tree rather than a
proprietary repository.

> **Status: stages 1, 2 and 4 are in.** Disks can be registered, mounted,
> indexed and compared; splitting and the coverage check work; the preview is
> complete. Nothing writes to a data disk yet - see [Roadmap](#roadmap).

## What makes it different from rsync

Nothing, if all you want is copying files. The parts that are not rsync:

- **The master is mounted read-only by the kernel.** Not "the program does not
  write there" - the filesystem is mounted `ro` and the mount is verified
  before anything is read.
- **Roles live outside the container.** A disk is identified by its filesystem
  UUID and its serial, and the mapping from disk to role sits in a root-owned
  file on the host. Renaming a folder or cloning a disk cannot flip a
  direction.
- **Nothing is deleted or overwritten without approval**, and answers are
  remembered so the same cases are not asked again on every run.
- **A brake**: more than N files or more than X percent about to be replaced
  stops the run instead of doing it.
- **Splitting**: one 4 TB master can be spread over several smaller copies,
  folder by folder, with a permanent warning for anything that ended up on no
  copy at all.

## Architecture

```
host                              container (unprivileged)
─────────────────────────────     ──────────────────────────
ambersync-helper (root)           web interface
  · lists block devices             · indexing and hashing
  · mounts master read-only         · comparison and preview
  · mounts copies writable          · assignment and coverage
  · owns /etc/ambersync/disks.conf  · SQLite database
        │                                    │
        └──── unix socket ───────────────────┘
        └──── /mnt/ambersync (rshared bind) ─┘
```

The container can only ask for a *set* to be mounted. It never names a device,
never names a mount option and never decides a role. That is what keeps the
master safe even if the container is fully compromised.

Registration is add-only over the socket. Changing a role or removing a
registration requires a deliberate command on the host - otherwise
delete-and-re-add would be a way around the rule.

## Requirements

- A Linux host with Docker and systemd
- `util-linux` (`lsblk`, `mount`), and the drivers for the filesystems you use
  (`exfat` and `ntfs3` are in the kernel since 5.7 and 5.15)
- `exfatprogs` if you use exFAT and want to be able to repair a dirty volume
- Python 3 on the host (standard library only - the helper has no dependencies)

## Install

```bash
git clone https://github.com/sphings79/ambersync.git
cd ambersync
sudo host/install.sh      # helper, systemd unit, group, directories
docker compose up -d
```

The interface listens on `127.0.0.1:8088` by default. Put it behind a reverse
proxy and restrict it to your own network - it has no authentication of its
own on purpose, because every deployment already has an opinion about that.

### Behind Traefik

Either add the usual labels to `compose.yaml`, or - if you keep your routers in
files - use `docs/traefik-ambersync.yml` as a starting point.

## Using it

1. **Disks** - plug a disk in, give it a name, pick a role, register it. The
   master is the one that is read; copies are written to.
2. **Overview** - mount the set, then index each disk. The first index run
   hashes everything and takes hours for a large archive; it can be paused and
   picks up where it left off.
3. **Split** (optional) - assign folders to copies. The tree starts at folder
   level 2, so `Photos/2019` is one unit. Anything unassigned is shown as a
   warning, because a folder nobody holds is the failure that goes unnoticed.
4. **Preview** - compare, then look at what would happen.

### Filesystems

exFAT and NTFS both work, and a set may mix them. Comparison is always by size
and SHA-256, never by timestamp: exFAT stores time with 10 ms resolution in
local time, so timestamps disagree between machines often enough to be
useless as evidence. Timestamps are only used to decide whether a file needs
re-hashing.

exFAT has no journal. AmberSync writes through a temporary file and renames
only after the hash matches, unmounts cleanly after every run, and refuses to
write to a volume whose dirty flag is set.

## Roadmap

| Stage | Contents | State |
| --- | --- | --- |
| 1 | Host helper, disk registration, mounting | done |
| 2 | Indexing, hashing, comparison, preview | done |
| 3 | Copying with verification, approvals, brake, history | planned |
| 4 | Splitting across several copies, coverage checks | done |
| 5 | Ransomware heuristics, notifications | rename detection done, rest planned |

## Licence

AGPL-3.0-or-later. See [LICENSE](LICENSE).
