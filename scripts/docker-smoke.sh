#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)
DOCKER=${DOCKER:-docker}
COMPOSE_FILE=${COMPOSE_FILE:-${ROOT_DIR}/compose.yaml}
FRONTEND_URL=${FRONTEND_URL:-http://127.0.0.1:3000}
LOAD_BALANCER_URL=${LOAD_BALANCER_URL:-http://127.0.0.1:8080}
WAIT_ATTEMPTS=${WAIT_ATTEMPTS:-60}
backend_a_needs_restore=0

compose() {
  "${DOCKER}" compose -f "${COMPOSE_FILE}" "$@"
}

fail() {
  printf 'Docker smoke test failed: %s\n' "$1" >&2
  exit 1
}

cleanup() {
  if [[ ${backend_a_needs_restore} -eq 1 ]]; then
    compose start backend-a >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

for command in "${DOCKER}" curl python3; do
  command -v "${command}" >/dev/null 2>&1 \
    || fail "required command not found: ${command}"
done

wait_for_url() {
  local label=$1
  local url=$2
  local attempt

  for ((attempt = 1; attempt <= WAIT_ATTEMPTS; attempt += 1)); do
    if curl --fail --silent --show-error --max-time 2 "${url}" >/dev/null 2>&1; then
      printf 'Ready: %s\n' "${label}"
      return 0
    fi
    sleep 1
  done

  fail "${label} did not become ready at ${url}"
}

wait_for_backend_health() {
  local backend_name=$1
  local expected=$2
  local attempt snapshot

  for ((attempt = 1; attempt <= WAIT_ATTEMPTS; attempt += 1)); do
    snapshot=$(curl --fail --silent --show-error --max-time 2 \
      "${LOAD_BALANCER_URL}/api/v1/dashboard" 2>/dev/null || true)
    if [[ -n ${snapshot} ]] && printf '%s' "${snapshot}" | python3 -c '
import json
import sys

document = json.load(sys.stdin)
name = sys.argv[1]
expected = sys.argv[2] == "true"
backend = next(item for item in document["backends"] if item["name"] == name)
raise SystemExit(0 if backend["healthy"] == expected else 1)
' "${backend_name}" "${expected}"; then
      printf 'Observed: %s healthy=%s\n' "${backend_name}" "${expected}"
      return 0
    fi
    sleep 1
  done

  fail "${backend_name} did not reach healthy=${expected}"
}

collect_backends() {
  local request_count=$1
  local path_prefix=$2
  local index response backend names=""

  for ((index = 1; index <= request_count; index += 1)); do
    if ! response=$(curl --fail --silent --show-error --max-time 5 \
      "${LOAD_BALANCER_URL}/${path_prefix}/${index}"); then
      fail "routing request ${path_prefix}/${index} failed"
    fi
    if ! backend=$(printf '%s' "${response}" | python3 -c \
      'import json, sys; print(json.load(sys.stdin)["backend"])'); then
      fail "routing request ${path_prefix}/${index} returned invalid JSON"
    fi
    names+=" ${backend}"
  done

  printf '%s' "${names}"
}

assert_seen() {
  local names=$1
  local expected=$2
  [[ " ${names} " == *" ${expected} "* ]] \
    || fail "expected traffic to reach ${expected}; observed:${names}"
}

assert_not_seen() {
  local names=$1
  local unexpected=$2
  [[ " ${names} " != *" ${unexpected} "* ]] \
    || fail "traffic unexpectedly reached ${unexpected}; observed:${names}"
}

wait_for_url "load balancer" "${LOAD_BALANCER_URL}/api/v1/dashboard"
wait_for_url "frontend" "${FRONTEND_URL}/health"
wait_for_backend_health backend-a true
wait_for_backend_health backend-b true
wait_for_backend_health backend-c true

frontend_html=$(curl --fail --silent --show-error "${FRONTEND_URL}/")
[[ ${frontend_html} == *'<div id="root"></div>'* ]] \
  || fail "frontend did not return the React application shell"

frontend_snapshot=$(curl --fail --silent --show-error \
  "${FRONTEND_URL}/api/v1/dashboard")
printf '%s' "${frontend_snapshot}" | python3 -c '
import json
import sys

document = json.load(sys.stdin)
assert set(document) == {"generated_at", "summary", "backends", "recent_requests"}
assert len(document["backends"]) == 3
' || fail "frontend API proxy returned an invalid dashboard document"

initial_backends=$(collect_backends 12 "docker-smoke/initial")
assert_seen "${initial_backends}" backend-a
assert_seen "${initial_backends}" backend-b
assert_seen "${initial_backends}" backend-c
printf 'Initial routing:%s\n' "${initial_backends}"

dashboard_snapshot=$(curl --fail --silent --show-error \
  "${LOAD_BALANCER_URL}/api/v1/dashboard")
printf '%s' "${dashboard_snapshot}" | python3 -c '
import json
import sys

document = json.load(sys.stdin)
assert document["summary"]["requests_total"] >= 12
assert document["recent_requests"]
' || fail "dashboard counters did not record smoke traffic"

printf 'Stopping backend-a to verify failure isolation...\n'
compose stop backend-a >/dev/null
backend_a_needs_restore=1
wait_for_backend_health backend-a false

degraded_backends=$(collect_backends 8 "docker-smoke/degraded")
assert_not_seen "${degraded_backends}" backend-a
assert_seen "${degraded_backends}" backend-b
assert_seen "${degraded_backends}" backend-c
printf 'Degraded routing:%s\n' "${degraded_backends}"

printf 'Restarting backend-a to verify recovery...\n'
compose start backend-a >/dev/null
wait_for_backend_health backend-a true
backend_a_needs_restore=0

recovered_backends=$(collect_backends 12 "docker-smoke/recovered")
assert_seen "${recovered_backends}" backend-a
printf 'Recovered routing:%s\n' "${recovered_backends}"

printf 'Docker smoke test passed.\n'
