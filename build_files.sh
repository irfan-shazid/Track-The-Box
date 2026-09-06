#!/usr/bin/env bash
# Vercel build step for static assets.
#
# Runs in the @vercel/static-build container: install deps, collect Django's
# static files (our stylesheet plus the admin's CSS/JS) into staticfiles_build/,
# which Vercel then serves straight from its CDN at /static/*.
set -e

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

python3 manage.py collectstatic --noinput --clear
