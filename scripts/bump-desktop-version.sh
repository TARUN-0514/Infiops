#!/usr/bin/env bash
# Set the Windows app's version everywhere it is recorded, ready to tag a release.
#   scripts/bump-desktop-version.sh 0.2.0
set -euo pipefail
cd "$(dirname "$0")/.."
v=${1:?new version, e.g. 0.2.0}
[[ "$v" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Use a version like 0.2.0" >&2; exit 1; }
node -e '
  const fs = require("fs"), v = process.argv[1];
  for (const f of ["apps/desktop/src-tauri/tauri.conf.json", "apps/desktop/package.json"]) {
    const j = JSON.parse(fs.readFileSync(f, "utf8")); j.version = v;
    fs.writeFileSync(f, JSON.stringify(j, null, 2) + "\n");
  }
' "$v"
sed -i.bak -E "0,/^version = \".*\"/s//version = \"$v\"/" apps/desktop/src-tauri/Cargo.toml
rm -f apps/desktop/src-tauri/Cargo.toml.bak
(cd apps/desktop/src-tauri && cargo update -p nexus-desktop --offline >/dev/null 2>&1 || cargo update -p nexus-desktop)
echo "Version set to $v. Commit, then: git tag desktop-v$v && git push origin desktop-v$v"
