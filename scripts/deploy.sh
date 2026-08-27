#!/usr/bin/env bash
# Deploy the public site (Cloud Run service xsdviewer, project xsd-viewer-495407).
#
# 1. Downloads the current GeoLite2-Country database into backend/geoip/ (key
#    from Secret Manager) so the Dockerfile bakes it into the image — one
#    MaxMind download per deploy instead of one per Cloud Run instance.
# 2. Runs `gcloud run deploy --source .` with the project flag set explicitly.
#
# Usage: scripts/deploy.sh            (from the repo root or anywhere)
#        SKIP_GEOIP=1 scripts/deploy.sh   (deploy without refreshing the DB)
set -euo pipefail

PROJECT=xsd-viewer-495407
REGION=europe-west1
SERVICE=xsdviewer
EDITION=GeoLite2-Country

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DEST="backend/geoip/${EDITION}.mmdb"

if [[ "${SKIP_GEOIP:-}" != "1" ]]; then
  echo ">> fetching MaxMind license key from Secret Manager"
  KEY="$(gcloud secrets versions access latest --secret=xsdviewer-maxmind-license-key --project "$PROJECT" | tr -d '\n')"
  TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
  echo ">> downloading ${EDITION}"
  # -s: never echo the URL (it carries the key); --netrc-free query auth is what MaxMind offers for GeoLite.
  curl -fsSL --retry 3 --retry-delay 5 -o "$TMP/db.tar.gz" \
    "https://download.maxmind.com/app/geoip_download?edition_id=${EDITION}&license_key=${KEY}&suffix=tar.gz"
  tar -xzf "$TMP/db.tar.gz" -C "$TMP" --wildcards "*/${EDITION}.mmdb"
  mkdir -p backend/geoip
  mv "$TMP"/*/"${EDITION}.mmdb" "$DEST"
  echo ">> $DEST ($(du -h "$DEST" | cut -f1))"
fi

[[ -s "$DEST" ]] || echo "!! $DEST missing — the image will fall back to a runtime download" >&2

echo ">> deploying $SERVICE to $PROJECT/$REGION"
gcloud run deploy "$SERVICE" --source . --region "$REGION" --project "$PROJECT"
