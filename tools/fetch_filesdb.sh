#!/usr/bin/env bash
# Download the repos' file lists (what `pacman -Fy` would, without root) into
# build/filesdb so tests can check which package ships each systemd unit.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB="$ROOT/build/filesdb"
mkdir -p "$DB/sync" "$DB/local"
MIRROR=$(grep -m1 -E '^Server' /etc/pacman.d/mirrorlist | sed -E 's/^Server *= *//')
for repo in core extra multilib; do
    url=$(echo "$MIRROR" | sed "s/\$repo/$repo/; s/\$arch/x86_64/")
    curl -fsSL -o "$DB/sync/$repo.files" "$url/$repo.files"
    echo "fetched $repo.files"
done
