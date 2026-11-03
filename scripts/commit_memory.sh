#!/usr/bin/env bash
# Saves what the bot learned (memory/, downloaded library files) back into the repository.
# Safe to run when nothing changed. Used by the GitHub workflow after every run.
set -u
PATHS="memory assets/library custom outputs"
if [ -n "${GITHUB_TOKEN:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ]; then
  # the checkout step does not keep credentials on disk (so AI-written code can never read them); authenticate only here
  HOST="${GITHUB_SERVER_URL:-https://github.com}"; HOST="${HOST#https://}"
  git remote set-url origin "https://x-access-token:${GITHUB_TOKEN}@${HOST}/${GITHUB_REPOSITORY}.git"
fi
git config user.name  "motion-graphic-bot"
git config user.email "motion-graphic-bot@users.noreply.github.com"
for p in $PATHS; do [ -e "$p" ] && git add -A "$p"; done
if git diff --cached --quiet; then
  echo "memory: nothing new to save"
  exit 0
fi
git commit -q -m "bot: update memory and library [skip ci]" || exit 0
for i in 1 2 3; do
  if git pull -q --rebase --autostash && git push -q; then
    echo "memory: saved to the repository"
    exit 0
  fi
  echo "memory: push attempt $i failed, retrying..."
  sleep $((i * 3))
done
echo "memory: could NOT push (check Settings -> Actions -> General -> Workflow permissions = Read and write)"
exit 0
