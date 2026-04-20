#!/usr/bin/env bash
# Starts (or replaces) the online-xsd-viewer container.
# Binds to 127.0.0.1:8180 so only the local Apache reverse proxy can reach it.
# Restarts automatically on failure and on host reboot.

set -euo pipefail

NAME="online-xsd-viewer"
IMAGE="${IMAGE:-online-xsd-viewer:test}"
HOST_PORT="${HOST_PORT:-8180}"

# If a stale container exists (running or stopped) drop it first.
if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  docker rm -f "$NAME" >/dev/null
fi

docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  -p "127.0.0.1:${HOST_PORT}:8080" \
  -e LOG_LEVEL=INFO \
  -e MAX_UPLOAD_MB=50 \
  -e ALLOWED_SCHEMA_HOSTS='^raw\.githubusercontent\.com$,^github\.com$,^release-assets\.githubusercontent\.com$,^objects\.githubusercontent\.com$' \
  "$IMAGE"

echo "Started $NAME on 127.0.0.1:${HOST_PORT} from image $IMAGE"
docker ps --filter "name=$NAME" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
