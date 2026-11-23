#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

origin=${1:-http://localhost:18080}
probe_id=$(python3 -c 'import uuid; print(uuid.uuid4().hex)')

probe_sql() {
    docker compose exec -T db sh -ec 'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
}

cleanup() {
    probe_sql <<< "DROP TABLE IF EXISTS m0_smoke_${probe_id};" >/dev/null
}
trap cleanup EXIT

wait_for_health() {
    for ((attempt = 1; attempt <= 30; attempt++)); do
        if [[ "$(curl -fsS --max-time 2 "$origin/api/health" 2>/dev/null)" == '{"status":"ok"}' ]]; then
            return
        fi
        sleep 2
    done
    echo "Health endpoint unavailable at $origin/api/health" >&2
    return 1
}

wait_for_health
page=$(curl -fsS --max-time 5 "$origin/")
[[ "$page" == *'<title>Knowledge Hub</title>'* ]]
asset=$(sed -nE 's/.*src="(\/assets\/[^"]+\.js)".*/\1/p' <<< "$page")
[[ -n "$asset" ]]
curl -fsS --max-time 5 "$origin$asset" >/dev/null
login=$(curl -fsS --max-time 5 "$origin/accounts/login/")
[[ "$login" == *'name="csrfmiddlewaretoken"'* ]]
status=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 "$origin/api/auth/me")
[[ "$status" == 403 ]]

probe_sql <<< "CREATE TABLE m0_smoke_${probe_id} (marker integer NOT NULL);
INSERT INTO m0_smoke_${probe_id} VALUES (1);"
docker compose restart db
wait_for_health
[[ "$(probe_sql <<< "SELECT marker FROM m0_smoke_${probe_id};")" == 1 ]]
echo "Frontend, login, API health and PostgreSQL persistence verified."
