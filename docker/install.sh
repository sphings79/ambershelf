#!/bin/bash
# Installs the AmberShelf host helper on a Docker host.
# Run as root from the repository directory: sudo docker/install.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "run this as root" >&2
    exit 1
fi

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

echo "== dependencies =="
missing=()
for tool in lsblk mount umount; do
    command -v "$tool" >/dev/null || missing+=("$tool")
done
if [[ ${#missing[@]} -gt 0 ]]; then
    echo "missing: ${missing[*]}" >&2
    exit 1
fi

for fs in exfat ntfs3; do
    if ! grep -q "$fs" /proc/filesystems && ! /sbin/modinfo "$fs" >/dev/null 2>&1; then
        echo "warning: no $fs driver found - disks with that filesystem cannot be mounted"
    fi
done

if ! command -v fsck.exfat >/dev/null; then
    echo "note: exfatprogs is not installed - repairing a dirty exFAT volume will not work"
    echo "      install it with: apt install exfatprogs"
fi

echo "== group =="
if ! getent group ambershelf >/dev/null; then
    groupadd --system ambershelf
    echo "created group ambershelf"
fi
GID=$(getent group ambershelf | cut -d: -f3)
echo "ambershelf gid: $GID"

echo "== directories =="
install -d -m 0755 /etc/ambershelf
install -d -m 0755 /mnt/ambershelf
install -d -m 0755 /run/ambershelf

echo "== helper =="
install -m 0755 "$HERE/helper/ambershelf-helper.py" /usr/local/bin/ambershelf-helper
install -m 0644 "$HERE/helper/ambershelf-helper.service" /etc/systemd/system/ambershelf-helper.service
systemctl daemon-reload
systemctl enable --now ambershelf-helper.service
sleep 1
systemctl is-active --quiet ambershelf-helper.service && echo "helper is running"

echo "== compose environment =="
ENV_FILE="$HERE/../.env"
if [[ -f $ENV_FILE ]] && grep -q '^AMBERSHELF_GID=' "$ENV_FILE"; then
    sed -i "s/^AMBERSHELF_GID=.*/AMBERSHELF_GID=$GID/" "$ENV_FILE"
else
    echo "AMBERSHELF_GID=$GID" >> "$ENV_FILE"
fi
echo "wrote AMBERSHELF_GID=$GID to $(realpath "$ENV_FILE")"

cat <<TXT

Done. Next:

  docker compose up -d

Registered disks live in /etc/ambershelf/disks.conf. The container may add
entries but can never rewrite a role - that is deliberate. To change one:

  sudo ambershelf-helper --admin list
  sudo ambershelf-helper --admin set-role <fs-uuid> slave

Giving a master up so the disk can be a copy is possible from the interface,
behind a warning, the disk name and the password. To take that away and keep
it here on the host only, put this in /etc/ambershelf/disks.conf:

  "allow_demote": false

To see what is connected right now:

  sudo ambershelf-helper --admin scan
TXT
