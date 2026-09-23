#!/usr/bin/env bash
set -u

apps=(
  users
  institutions
  clinical
  therapeutic_sessions
  finance
  marketing
  evaluations
  onedrive
  uploads
)

failed=0
for app in "${apps[@]}"; do
  printf '\n==> Testing %s\n' "$app"
  if ! ./venv/bin/python manage.py test "$app" --noinput; then
    failed=1
  fi
done

exit "$failed"
