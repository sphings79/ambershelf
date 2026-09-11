#!/bin/bash
# Installs the AmberSync host helper on a Docker host.
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
if ! getent group ambersync >/dev/null; then
    groupadd --system ambersync
    echo "created group ambersync"
fi
GID=$(getent group ambersync | cut -d: -f3)
echo "ambersync gid: $GID"

echo "== directories =="
install -d -m 0755 /etc/ambersync
install -d -m 0755 /mnt/ambersync
install -d -m 0755 /run/ambersync

echo "== helper =="
install -m 0755 "$HERE/helper/ambersync-helper.py" /usr/local/bin/ambersync-helper
install -m 0644 "$HERE/helper/ambersync-helper.service" /etc/systemd/system/ambersync-helper.service
systemctl daemon-reload
systemctl enable --now ambersync-helper.service
sleep 1
systemctl is-active --quiet ambersync-helper.service && echo "helper is running"

echo "== compose environment =="
ENV_FILE="$HERE/../.env"
if [[ -f $ENV_FILE ]] && grep -q '^AMBERSYNC_GID=' "$ENV_FILE"; then
    sed -i "s/^AMBERSYNC_GID=.*/AMBERSYNC_GID=$GID/" "$ENV_FILE"
else
    echo "AMBERSYNC_GID=$GID" >> "$ENV_FILE"
fi
echo "wrote AMBERSYNC_GID=$GID to $(realpath "$ENV_FILE")"

cat <<TXT

Done. Next:

  docker compose up -d

Registered disks live in /etc/ambersync/disks.conf. The container may add
entries but can never change a role or delete one - that is deliberate. To
change a role:

  sudo ambersync-helper --admin list
  sudo ambersync-helper --admin set-role <fs-uuid> slave

To see what is connected right now:

  sudo ambersync-helper --admin scan
TXT
