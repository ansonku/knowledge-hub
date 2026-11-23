#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
set -o noclobber
db_password=$(openssl rand -hex 32)
django_secret=$(openssl rand -hex 48)
{
    printf 'HUB_PORT=18080\nPOSTGRES_DB=hub\nPOSTGRES_USER=hub\n'
    printf 'POSTGRES_PASSWORD=%s\nDJANGO_SECRET_KEY=%s\n' "$db_password" "$django_secret"
} > .env
