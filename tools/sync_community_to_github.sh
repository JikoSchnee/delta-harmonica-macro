#!/usr/bin/env bash
# Sync accepted public uploads from the deployment Docker volume to GitHub.
# Intended to run as root from cron on the deployment host.
set -euo pipefail

REPOSITORY_DIR="${REPOSITORY_DIR:-/opt/delta-harmonica-github}"
DOCKER_VOLUME="${DOCKER_VOLUME:-delta-harmonica-data}"
GITHUB_REPOSITORY="${GITHUB_REPOSITORY:-JikoSchnee/delta-harmonica-macro}"
BRANCH="${BRANCH:-track}"
DEPLOY_KEY="${DEPLOY_KEY:-/root/.ssh/delta_harmonica_github}"
LOCK_FILE="${LOCK_FILE:-/var/lock/delta-harmonica-github-sync.lock}"

exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

if [[ ! -d "$REPOSITORY_DIR/.git" || ! -f "$DEPLOY_KEY" ]]; then
  echo "GitHub sync is not configured; skipping."
  exit 0
fi

export GIT_SSH_COMMAND="ssh -i $DEPLOY_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
git -C "$REPOSITORY_DIR" remote set-url origin "git@github.com:${GITHUB_REPOSITORY}.git"

# Do not copy or commit until the deploy key has GitHub access.
if ! git -C "$REPOSITORY_DIR" ls-remote --exit-code origin HEAD >/dev/null 2>&1; then
  echo "GitHub deploy key is not authorised yet; skipping."
  exit 0
fi

git -C "$REPOSITORY_DIR" fetch origin --prune
DEFAULT_BRANCH="$(git -C "$REPOSITORY_DIR" symbolic-ref --quiet --short refs/remotes/origin/HEAD)"
DEFAULT_BRANCH="${DEFAULT_BRANCH#origin/}"
if git -C "$REPOSITORY_DIR" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git -C "$REPOSITORY_DIR" switch "$BRANCH"
elif git -C "$REPOSITORY_DIR" show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
  git -C "$REPOSITORY_DIR" switch --track -c "$BRANCH" "origin/$BRANCH"
else
  git -C "$REPOSITORY_DIR" switch -c "$BRANCH" "origin/$DEFAULT_BRANCH"
fi

if git -C "$REPOSITORY_DIR" show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
  git -C "$REPOSITORY_DIR" pull --ff-only origin "$BRANCH"
fi

SOURCE_DIRECTORY="$(docker volume inspect --format '{{ .Mountpoint }}' "$DOCKER_VOLUME")"
install -d "$REPOSITORY_DIR/data/community-scores"
cp -a "$SOURCE_DIRECTORY/community-scores/." "$REPOSITORY_DIR/data/community-scores/"
cp -a "$SOURCE_DIRECTORY/community-songs.js" "$REPOSITORY_DIR/data/community-songs.js"
# macOS archive metadata is never a score package and must not enter Git.
find "$REPOSITORY_DIR/data/community-scores" -type f -name '._*' -delete

git -C "$REPOSITORY_DIR" add data/community-scores data/community-songs.js
if ! git -C "$REPOSITORY_DIR" diff --cached --quiet; then
  git -C "$REPOSITORY_DIR" commit -m "chore: sync community songs"
fi

if git -C "$REPOSITORY_DIR" show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
  AHEAD_COUNT="$(git -C "$REPOSITORY_DIR" rev-list --count "origin/$BRANCH..$BRANCH")"
else
  AHEAD_COUNT="$(git -C "$REPOSITORY_DIR" rev-list --count "origin/$DEFAULT_BRANCH..$BRANCH")"
fi

if [[ "$AHEAD_COUNT" -gt 0 ]]; then
  git -C "$REPOSITORY_DIR" push --set-upstream origin "$BRANCH"
  echo "Community songs pushed to $BRANCH."
fi
