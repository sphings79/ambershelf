<div align="center">

# AmberShelf

### Ransomware-resistant one-way disk sync for external drives — with an approval step

**Mirror a master disk onto one or more backup drives without ever deleting or overwriting
anything behind your back.** Self-hosted, Docker, web interface, exFAT and NTFS, built for
photo and video archives that live on disks in a drawer.

[![Licence: AGPL v3](https://img.shields.io/badge/Licence-AGPL%20v3-2ea44f?style=flat-square)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](compose.yaml)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](requirements.txt)
[![Self-hosted](https://img.shields.io/badge/Self--hosted-yes-e08b12?style=flat-square)](#quick-start)
[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-sphings-FFDD00?style=flat-square&logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/sphings)

**English** · [Deutsch](README.de.md)

**If AmberShelf is useful to you, please ⭐ star the repository** — it is the only way people
with the same problem find it.

<img src="docs/screenshots/overview-dark.png"
     alt="AmberShelf overview screen in dark mode showing a master disk mounted read-only and two backup copies with index status" width="880">

</div>

---

## The problem this solves

A photo archive does not change. Files get added; almost nothing is ever edited, and
deletions are rare and deliberate. Yet every ordinary sync tool treats "the source
changed" as an instruction to change the copy too — which is exactly what you do **not**
want when the source got encrypted by ransomware, corrupted by a failing cable, or wiped
by a mistyped command.

AmberShelf inverts that. It reads both sides, works out the difference by content hash, and
then **shows you what it would do**. Adding files is routine. Replacing or deleting one
needs your approval. A mass change trips a brake and stops the run.

It is built for the way external drives are actually used: plugged in occasionally,
carried between a Mac and a Windows PC, sitting in a drawer the rest of the time.

## Screenshots

| Overview — light | Split across several drives |
| --- | --- |
| <img src="docs/screenshots/overview-light.png" alt="AmberShelf overview in light mode with disk cards, capacity meters and index state" width="420"> | <img src="docs/screenshots/split-light.png" alt="AmberShelf split screen assigning folders of a photo archive to two backup drives with capacity bars" width="420"> |

**The preview** — nothing is carried out until you decide:

<img src="docs/screenshots/preview-dark.png" alt="AmberShelf preview showing new, changed, renamed, deleted and copy-only files per backup drive" width="880">

**Damage is recognised before it can be copied onward** — a JPEG that no longer
begins like a JPEG, a ransom note, a mass change in one minute:

<img src="docs/screenshots/findings-dark.png" alt="AmberShelf findings page listing a mass change and thirty files whose header no longer matches their extension, with the brake engaged" width="880">

**Every replacement, rename and deletion is yours to allow** — one by one or in
bulk, and the answer is remembered:

<img src="docs/screenshots/approvals-dark.png" alt="AmberShelf approval list: each changed file can be approved, skipped once or never asked about again, with a warning that the copy itself was altered rather than the master" width="880">

**Light, dark and system theme, five accent colours:**

<img src="docs/screenshots/settings-dark.png" alt="AmberShelf settings with theme switch, accent colour swatches and the brake thresholds" width="880">

## Features

- **The master is mounted read-only by the kernel.** Not "the program does not write
  there" — the filesystem is mounted `ro` and the flags are read back before a single byte
  is read. A bug, or somebody who owns the container, still cannot write to your original.
- **Ransomware-resistant by design.** Nothing is ever deleted or overwritten without your
  approval, and a mass replacement or deletion trips a configurable brake — by absolute
  count *and* by share of the archive. Releasing a tripped brake means typing the number
  of affected files, so it cannot be clicked past.
- **Every copy is proved.** Each file is written to a temporary name, flushed to the
  platter, read back and hashed, and only then renamed into place. An interrupted run
  leaves a stray temporary file, never half a photo under the right name.
- **Replaced and deleted files are parked**, not destroyed — under `.ambershelf-trash` on
  the copy, with the timestamp of the run, until you clear them out yourself.
- **Decisions are remembered.** Approve, skip once, or never ask again; you work through
  the backlog once instead of meeting the same fifty cases every run.
- **Damaged files are recognised, not guessed at.** Every file is checked against the
  magic bytes its extension promises — a `.jpg` that no longer starts `FF D8 FF` is
  broken, and that is exactly what encryption leaves behind, including the fast kind that
  only scrambles the first few hundred kilobytes. Plus ransom notes by name, meaningless
  second extensions, and a mass change inside one hour. Any finding holds the brake.
- **A webhook when it matters.** One URL, a small JSON object — Home Assistant, ntfy,
  Gotify or a script of your own. No account anywhere.
- **A password, unless nobody else could reach it.** scrypt from the standard library,
  server-side sessions, a lockout after five wrong attempts — and on first start a
  generated password in the log rather than a setup screen anyone could claim. It opens
  the door once: the first thing you are asked for is one of your own. Off only when the
  server listens on loopback alone.
- **Disk identity that cannot be faked from inside.** A drive is recognised by its
  filesystem UUID and serial; the mapping from drive to role lives in a root-owned file on
  the host, outside the container's reach. Renaming a folder or cloning a disk cannot flip
  a direction.
- **Content-hash comparison (SHA-256).** Never timestamps — exFAT stores time in local
  time with 10 ms resolution, which disagrees between machines often enough to be useless
  as evidence.
- **Rename detection.** A file that moved keeps its place instead of being copied again
  and then flagged as a stray.
- **Split one big master across several smaller drives**, folder by folder, with a
  permanent warning for anything that ended up on no copy at all — the silent failure that
  actually costs you data.
- **Resumable indexing.** The first hash run over a terabyte takes hours; it pauses,
  resumes, and survives a container restart with at most one file lost.
- **Plain, browsable copies.** A backup drive stays a normal folder tree you can open on
  any computer without AmberShelf, not a proprietary repository.
- **Unprivileged container.** No `privileged`, no capabilities, no device access.
- **German and English interface**, light/dark/system theme, five accent colours.

## How it works

```
host                                container (unprivileged)
──────────────────────────────      ────────────────────────────
ambershelf-helper (root)             web interface
  · lists block devices               · indexing and hashing
  · mounts the master read-only       · comparison and preview
  · mounts copies writable            · folder assignment
  · owns /etc/ambershelf/disks.conf    · SQLite index
          │                                      │
          └──── unix socket ─────────────────────┘
          └──── /mnt/ambershelf (rshared bind) ───┘
```

The container can only ask for a **set** to be mounted. It never names a device, never
names a mount option, and never decides a role — that is what keeps the master safe even
if the container is fully compromised.

Registration over the socket is **add-only** on purpose: an existing role is never
rewritten. A disk that has been a master is remembered by the host and can afterwards only
be registered as a master again - otherwise delete-and-re-add would be a way around the
rule.

You can lift that block, in the interface under "Give up master": acknowledge the warning,
type the disk name, give the password. The registration is **removed** rather than
rewritten - registering the disk as a copy afterwards is a second, separate step - and
giving a master up is refused while the set is mounted. The price is worth stating plainly:
this runs over the same socket as everything else, so whoever owns the container *and* gets
hold of the password can reach it too.

## Three ways to run it

| | Source held read-only | Needs | Get it |
| --- | --- | --- | --- |
| **Docker on Linux** | **yes, by the kernel** | a Linux host | [below](#quick-start) |
| **macOS application** | no | macOS 12+, Apple Silicon | [Download](https://github.com/sphings79/ambershelf/releases/latest) |
| **Windows application** | no | Windows 10+ | [Download](https://github.com/sphings79/ambershelf/releases/latest) |

The desktop builds read the disks your system has already mounted, need no
administrator rights, install no service and start no daemon. What they give up is
the one guarantee that needs a privileged half: **they cannot hold the master
read-only**, so they say so on every page instead. AmberShelf itself never writes to
it — but nothing stops anything else on that computer.

Either desktop application can also be pointed at an AmberShelf running elsewhere
(Settings → Connection), which turns it into a window onto the Docker one with the
full guarantee behind it.

Nothing is code-signed, so the first start takes one extra step: on macOS
right-click the app and choose **Open**; on Windows click **More info → Run anyway**
in the SmartScreen dialog.

## Quick start

Requirements: a Linux host with Docker and systemd, `util-linux`, and the kernel drivers
for your filesystems (`exfat` since 5.7, `ntfs3` since 5.15 — both ship with any current
distribution). `exfatprogs` if you want to repair a dirty exFAT volume.

```bash
git clone https://github.com/sphings79/ambershelf.git
cd ambershelf
sudo docker/install.sh      # helper, systemd unit, group, directories
docker compose up -d
```

A ready-made image is published to `ghcr.io/sphings79/ambershelf:latest` for
`linux/amd64` and `linux/arm64` — point `image:` at it in `compose.yaml` if you would
rather not build.

The interface listens on `127.0.0.1:8088`.

### Signing in

Anything not reachable on loopback alone asks for a password — which is every container
and every reverse-proxied setup. **On first start AmberShelf makes one up and writes it
to the log:**

```bash
docker compose logs ambershelf | grep -A4 "first start"
```

Sign in with it and you are asked to choose your own before anything else works. There
is deliberately no setup screen: a setup screen on a reachable address belongs to
whoever finds it first, while a generated password in the log only opens the door for
somebody who can already read that log.

One password for the whole application, hashed with scrypt from the standard library.
Sessions are kept server-side, so signing out takes effect everywhere at once, and five
wrong attempts from one address buy it a pause.

The desktop applications running locally listen on `127.0.0.1` only and do not ask —
they would be asking their own user. Point one at a remote AmberShelf and it signs in
like any browser would.

### Behind a reverse proxy

Copy [`docs/compose.override.example.yaml`](docs/compose.override.example.yaml) to
`compose.override.yaml` next to `compose.yaml`; Docker Compose merges it automatically.
It drops the localhost binding and joins the proxy network. A matching Traefik router is
in [`docs/traefik-ambershelf.yml`](docs/traefik-ambershelf.yml).

Restrict it to your own network anyway. A password is one lock; an interface that can
delete files on a backup disk deserves two.

## Using it

1. **Disks** — plug a drive in, name it, pick a role, register it. The master is read;
   copies are written to.
2. **Overview** — mount the set, then index each drive. The first run hashes everything.
3. **Split** (optional) — assign folders to copies. The tree starts at folder level 2, so
   `Photos/2019` is one unit. Anything unassigned is shown as a warning.
4. **Preview** — compare, then look at exactly what would happen.

### exFAT and NTFS

Both work, and a set may mix them.

**exFAT** is the only filesystem both macOS and Windows can read *and* write without extra
software, which is why it wins for drives that travel. It has no journal, so AmberShelf
writes through a temporary file and renames only after the hash matches, unmounts cleanly
after every run, and refuses to write to a volume whose dirty flag is set.

**NTFS** is journalled and more robust, but macOS can only read it.

## How it compares

| | AmberShelf | rsync | Syncthing | FreeFileSync |
| --- | --- | --- | --- | --- |
| Source physically write-protected | **yes, `ro` mount** | no | no | no |
| Deletions need approval | **yes** | no (`--delete` or nothing) | no | prompt only |
| Mass-change brake | **yes** | no | no | no |
| Split one source across several targets | **yes** | no | no | no |
| Remembers your decisions | **yes** | no | n/a | no |
| Target stays a plain folder tree | **yes** | yes | yes | yes |
| Continuous / two-way | no, by design | no | yes | no |
| Web interface | **yes** | no | yes | no |

If you want continuous two-way sync between machines, use Syncthing. If you want a
scriptable one-liner, use rsync. AmberShelf is for the case where the copy must not follow
the source into a bad state.

## FAQ

**Does this protect me from ransomware?**
It protects the *copy* from a master that has already been damaged — for example because
the drive was plugged into an infected Windows PC. Every file is checked against the
magic bytes its extension promises, ransom notes and meaningless second extensions are
recognised by name, and a mass change inside one hour is flagged; any of that holds the
brake and nothing is written. It does **not** protect against someone taking over the
host itself. Your real protection there is that the drives spend most of their life
unplugged, and AmberShelf is built not to undermine that.

**Why no entropy measurement?**
Because it does not work on a photo archive. JPEG and MP4 are already compressed and look
almost perfectly random, so "this looks encrypted" says nothing about them — it would only
lend false confidence. Text files are covered by a printable-characters check instead, and
photos and video by their headers, which encryption destroys either way.

**Why not just use rsync?**
rsync copies files well. What it does not have is an approval workflow, a state database,
rename detection by hash, splitting across targets, or a brake. Building those around
rsync means reimplementing most of this anyway, with less control over each step.

**Can it delete files on the copy?**
Only ones you approve, one by one or in bulk, and only once AmberShelf itself has written
to that copy — before that there is no way to tell a deleted file from one that was never
there, and it says so rather than guessing. Deleted files are moved to
`.ambershelf-trash` on the copy by default, so an approval you regret is still reversible.

**How long does the first run take?**
It reads and hashes everything. Expect roughly 4–8 hours per terabyte over USB 3,
depending on the drive and the file sizes. Later runs only hash what changed. The run can
be paused and resumed.

**Does it need the drives permanently connected?**
No. That is the point. Plug them in, run it, eject them.

**Can I run it without Docker?**
Yes — the macOS and Windows applications are exactly that. They carry the same engine
and the same interface; only the platform layer differs, and with it the read-only
guarantee, which those systems cannot give an unprivileged application.

**Why is the macOS app not signed?**
Because notarisation costs 99 € a year and this is a hobby project. Right-click the
app and choose **Open** the first time; macOS remembers the decision. If that changes,
the workflow that builds it is two lines away from signing.

**Does it work with a NAS share, SMB or NFS?**
Not currently. It identifies drives by filesystem UUID and serial, which a network share
does not have.

## Roadmap

| Stage | Contents | State |
| --- | --- | --- |
| 1 | Host helper, disk registration, mounting | ✅ done |
| 2 | Indexing, hashing, comparison, preview | ✅ done |
| 3 | Copying with verification, approvals, history | ✅ done |
| 4 | Splitting across several copies, coverage checks | ✅ done |
| 5 | Integrity checks, notifications | ✅ done |
| 6 | macOS and Windows desktop builds | ✅ done |

> The desktop builds do not hold the source read-only — that needs a privileged
> half neither system offers to an ordinary application — so they say so on every
> page instead of pretending.

## Contributing

Issues and pull requests are welcome — especially reports from filesystems and drive
enclosures I cannot test here. Comments, names and commit messages in English please.

## Support the project

If AmberShelf saved you a backup, or just saved you an evening:

<a href="https://buymeacoffee.com/sphings">
  <img src="https://img.shields.io/badge/Buy%20me%20a%20coffee-sphings-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy me a coffee">
</a>

And a ⭐ costs nothing and helps a lot.

## Licence

[AGPL-3.0-or-later](LICENSE). Run it, change it, share it — if you offer it to others over
a network, publish your changes too.

---

<sub>**Keywords:** disk sync · one-way sync · backup mirror · external hard drive backup ·
ransomware protection · append-only backup · photo archive backup · exFAT sync Linux ·
NTFS sync · self-hosted backup tool · docker backup · rsync alternative · FreeFileSync
alternative · read-only source · checksum verification · SHA-256 · split backup across
multiple drives · cold storage · USB drive mirroring · approval workflow</sub>
