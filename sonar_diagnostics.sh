#!/usr/bin/env bash

set -uo pipefail

HOST_URL="${SONAR_HOST_URL:-https://sonar.isilp.com}"
PROJECT_KEY="${SONAR_PROJECT:-cbm-backend}"
BRANCH="${SONAR_BRANCH:-feat/project-hardening}"
PULL_REQUEST="${SONAR_PR:-}"

clean_value() {
    printf '%s' "$1" | tr -d '\302\240\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

HOST_URL="$(clean_value "$HOST_URL")"
PROJECT_KEY="$(clean_value "$PROJECT_KEY")"
BRANCH="$(clean_value "$BRANCH")"
PULL_REQUEST="$(clean_value "$PULL_REQUEST")"
HOST_URL="${HOST_URL%/}"

if ! command -v curl >/dev/null 2>&1; then
    echo "Error: curl no está instalado." >&2
    exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
    echo "Error: jq no está instalado." >&2
    exit 1
fi

if [[ -z "${SONAR_TOKEN:-}" ]]; then
    read -rsp "Token SonarQube: " SONAR_TOKEN
    echo
fi

if [[ -z "$SONAR_TOKEN" ]]; then
    echo "Error: SONAR_TOKEN está vacío." >&2
    exit 1
fi

echo "SonarQube: $HOST_URL"
echo "Proyecto:  <$PROJECT_KEY>"
if [[ -n "$PULL_REQUEST" ]]; then
    echo "Pull Request: $PULL_REQUEST"
else
    echo "Rama:      <$BRANCH>"
fi

query() {
    local title="$1"
    local endpoint="$2"
    shift 2

    printf '\n=== %s ===\n' "$title"
    if ! curl --fail-with-body -sS -u "${SONAR_TOKEN}:" --get \
        "${HOST_URL}${endpoint}" "$@" | jq; then
        echo "Error consultando $title" >&2
    fi
}

if [[ -n "$PULL_REQUEST" ]]; then
    query "QUALITY GATE" \
        "/api/qualitygates/project_status" \
        --data-urlencode "projectKey=${PROJECT_KEY}" \
        --data-urlencode "pullRequest=${PULL_REQUEST}"
else
    query "QUALITY GATE" \
        "/api/qualitygates/project_status" \
        --data-urlencode "projectKey=${PROJECT_KEY}" \
        --data-urlencode "branch=${BRANCH}"
fi

if [[ -n "$PULL_REQUEST" ]]; then
    MEASURE_SCOPE=(--data-urlencode "pullRequest=${PULL_REQUEST}")
    ISSUE_SCOPE=(--data-urlencode "pullRequest=${PULL_REQUEST}")
else
    MEASURE_SCOPE=(--data-urlencode "branch=${BRANCH}")
    ISSUE_SCOPE=(--data-urlencode "branch=${BRANCH}")
fi

query "METRICS" \
    "/api/measures/component" \
    --data-urlencode "component=${PROJECT_KEY}" \
    "${MEASURE_SCOPE[@]}" \
    --data-urlencode "metricKeys=alert_status,coverage,new_coverage,lines_to_cover,uncovered_lines,new_lines_to_cover,new_uncovered_lines,bugs,vulnerabilities,security_hotspots,code_smells,duplicated_lines_density,new_duplicated_lines_density"

query "LATEST ANALYSES" \
    "/api/project_analyses/search" \
    --data-urlencode "project=${PROJECT_KEY}" \
    --data-urlencode "ps=20"

query "OPEN ISSUES" \
    "/api/issues/search" \
    --data-urlencode "componentKeys=${PROJECT_KEY}" \
    "${ISSUE_SCOPE[@]}" \
    --data-urlencode "resolved=false" \
    --data-urlencode "ps=500"

query "COMPUTE ENGINE TASKS" \
    "/api/ce/activity" \
    --data-urlencode "component=${PROJECT_KEY}" \
    --data-urlencode "ps=20"
