#!/usr/bin/env bash
# Commit generated data from a workflow: push_data.sh "<message>" <file>...
# On a work branch the files are committed to that branch. On main (which is protected and only
# changes through reviewed pull requests) they go to the `data` branch instead; the site deploy
# uses whichever copy is newer.
set -euo pipefail
msg=$1; shift
git config user.name "forever-xp data bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
out=${GITHUB_OUTPUT:-/dev/null}

if [ "${GITHUB_REF:-}" != "refs/heads/main" ]; then
  git add "$@"
  if git diff --cached --quiet; then echo "No changes."; exit 0; fi
  git commit -qm "$msg"
  git pull --rebase -q && git push -q
  echo "changed=true" >> "$out"; exit 0
fi

keep=$(mktemp -d)
for f in "$@"; do mkdir -p "$keep/$(dirname "$f")"; cp "$f" "$keep/$f"; done
git reset -q --hard && git clean -qfd
if git ls-remote --exit-code --heads origin data >/dev/null 2>&1; then
  git fetch -q origin data && git checkout -q -B data FETCH_HEAD
else
  git checkout -q -B data
fi
for f in "$@"; do mkdir -p "$(dirname "$f")"; cp "$keep/$f" "$f"; done
git add "$@"
if git diff --cached --quiet; then echo "No changes."; exit 0; fi
git commit -qm "$msg"
for i in 1 2 3; do
  git push -q origin data && break
  git fetch -q origin data && git rebase -q FETCH_HEAD
done
echo "changed=true" >> "$out"
