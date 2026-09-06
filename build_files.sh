#!/usr/bin/env bash
# Vercel build step for static assets.
#
# Runs in the @vercel/static-build container: install Django, collect the static
# files (our stylesheet plus the admin's CSS/JS) into staticfiles_build/, which
# Vercel publishes to its CDN and serves at /static/*.
set -euo pipefail

# Vercel's build image marks its system Python as externally managed (PEP 668),
# so `pip install` into it is refused outright. Install into a throwaway venv.
# If the image has no venv module, fall back to overriding the PEP 668 guard --
# this is a disposable build container, so there is nothing to protect.
if python3 -m venv .buildvenv >/dev/null 2>&1 && [ -x .buildvenv/bin/python3 ]; then
  PY=.buildvenv/bin/python3
  PIP_FLAGS=""
  echo "==> installing into .buildvenv"
else
  PY=python3
  PIP_FLAGS="--break-system-packages"
  echo "==> no venv available, installing with --break-system-packages"
fi

"$PY" -m pip install --disable-pip-version-check --quiet $PIP_FLAGS -r requirements.txt

# collectstatic touches no database, but settings.py refuses to import without
# these. Supply throwaway values if the build has no env vars -- neither is
# used to produce a single byte of output, and neither reaches the runtime.
export SECRET_KEY="${SECRET_KEY:-collectstatic-placeholder-not-a-runtime-secret}"
export DATABASE_URL="${DATABASE_URL:-postgresql://placeholder:placeholder@localhost:5432/placeholder?sslmode=require}"
export DEBUG=False

"$PY" manage.py collectstatic --noinput --clear

echo "==> collected:"
ls -R staticfiles_build/static | head -20
