#!/usr/bin/env bash
# Smoke test against a running container (CI docker job, P11.4):
# health -> admin login -> scan pasted text -> wait -> download cleaned file.
# Usage: scripts/smoke.sh http://localhost:8000 admin@example.com 'password'
set -euo pipefail
BASE=${1:?base url}; EMAIL=${2:?email}; PASSWORD=${3:?password}
JAR=$(mktemp); trap 'rm -f "$JAR"' EXIT
H=(-H "Origin: $BASE")

echo "waiting for the model to load"
for _ in $(seq 1 90); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/health")" = 200 ] && break
  sleep 2
done
curl -sf "$BASE/health" | grep -q '"model_ready":true'

curl -sf "${H[@]}" -c "$JAR" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" "$BASE/api/v1/auth/login"
curl -sf -b "$JAR" "$BASE/api/v1/auth/me" | grep -q '"role":"admin"'

ID=$(curl -sf "${H[@]}" -b "$JAR" -F 'text=Patient Rahul Sharma, call 98470 12345, rahul@example.com' \
  "$BASE/api/v1/scans" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "scan $ID"
STATUS=""
for _ in $(seq 1 60); do
  STATUS=$(curl -sf -b "$JAR" "$BASE/api/v1/scans/$ID" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  case "$STATUS" in done|failed|needs_review) break ;; esac
  sleep 1
done
echo "status $STATUS"
if [ "$STATUS" = needs_review ]; then  # random fake model: answer every item, then wait again
  python3 - "$BASE" "$ID" "$JAR" <<'PY'
import http.cookiejar, json, sys, urllib.request
base, sid, jar = sys.argv[1:]
cj = http.cookiejar.MozillaCookieJar(jar); cj.load()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
items = json.load(op.open(f"{base}/api/v1/scans/{sid}"))["review"]["items"]
body = json.dumps({"answers": [{"index": i["index"], "verdict": "protect"} for i in items]}).encode()
req = urllib.request.Request(f"{base}/api/v1/scans/{sid}/answers", body, method="POST",
                             headers={"Origin": base, "Content-Type": "application/json"})
op.open(req)
PY
  for _ in $(seq 1 60); do
    STATUS=$(curl -sf -b "$JAR" "$BASE/api/v1/scans/$ID" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
    [ "$STATUS" = done ] && break
    sleep 1
  done
fi
[ "$STATUS" = done ] || { echo "scan did not finish: $STATUS"; exit 1; }
CLEAN=$(curl -sf -b "$JAR" "$BASE/api/v1/scans/$ID/download?kind=cleaned")
echo "$CLEAN" | grep -q "98470 12345" && { echo "phone number leaked"; exit 1; }
echo "$CLEAN" | grep -q "rahul@example.com" && { echo "email leaked"; exit 1; }
echo "smoke test passed"
