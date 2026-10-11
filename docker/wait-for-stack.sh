#!/bin/sh
# Compose versions without `up --wait` still expose Docker container health.
set -eu

project_root=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
compose() {
    docker compose -f "$project_root/docker/docker-compose.yml" "$@"
}

timeout=${QUICKSTART_TIMEOUT:-180}
case "$timeout" in
    ''|*[!0-9]*|0) echo "QUICKSTART_TIMEOUT must be a positive number of seconds" >&2; exit 2 ;;
esac
if [ "$#" -eq 0 ]; then
    set -- influxdb grafana collector
fi

diagnostics() {
    compose ps >&2 || true
    compose logs --tail 30 "$@" >&2 || true
}

deadline=$(( $(date +%s) + timeout ))
echo "Waiting for healthy services: $* (up to ${timeout}s)..."
while :; do
    ready=true
    for service in "$@"; do
        container=$(compose ps -q "$service")
        state=missing
        if [ -n "$container" ]; then
            state=$(docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}missing-healthcheck{{end}}' "$container")
        fi
        case "$state" in
            'running healthy') ;;
            exited*|dead*)
                echo "$service stopped before becoming healthy ($state)." >&2
                diagnostics "$@"
                exit 1
                ;;
            *) ready=false ;;
        esac
    done
    if [ "$ready" = true ]; then
        echo "Ready: $*."
        case " $* " in
            *" collector "*) echo "Recent configured ticks verified in InfluxDB." ;;
        esac
        echo "Dashboard: http://localhost:3000/d/yliveticker-dashboard"
        exit 0
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
        echo "Timed out waiting for healthy services; inspect the startup logs below." >&2
        diagnostics "$@"
        exit 1
    fi
    sleep 2
done
