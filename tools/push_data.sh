#!/usr/bin/env bash
# Commit generated data from a workflow: push_data.sh "<message>" <file>...
# On a work branch the files are committed to that branch. On main (which is protected and only
# changes through reviewed pull requests) they go to the `data` branch instead; the site deploy
# uses whichever copy is newer.
# Another data run may push first. Then we rebase onto it, and for the files we just generated our
# copy wins (it's the newer build). If the push still can't go through, the step fails loudly
# rather than reporting a change that never landed.
set -euo pipefail
msg=$1; shift
git config user.name "forever-xp data bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
out=${GITHUB_OUTPUT:-/dev/null}

push_with_retry() {  # push_with_retry <remote branch>
  local branch=$1
  for i in 1 2 3 4; do
    if git push -q origin "HEAD:$branch"; then return 0; fi
    echo "Push to $branch was rejected (try $i); rebasing onto the newer commit."
    git fetch -q origin "$branch"
    # -X theirs: while rebasing, "theirs" is our new commit, so the freshly built files win.
    if ! git rebase -q -X theirs FETCH_HEAD; then
      git rebase --abort || true
      echo "::error::Could not rebase the data commit onto $branch"
      return 1
    fi
    sleep $((i * 3))
  done
  echo "::error::Could not push the data commit to $branch"
  return 1
}

if [ "${GITHUB_REF:-}" != "refs/heads/main" ]; then
  git add "$@"
  if git diff --cached --quiet; then echo "No changes."; exit 0; fi
  git commit -qm "$msg"
  push_with_retry "${GITHUB_REF_NAME:-$(git rev-parse --abbrev-ref HEAD)}"
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
push_with_retry data
echo "changed=true" >> "$out"
