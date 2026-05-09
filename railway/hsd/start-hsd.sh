#!/usr/bin/env sh
set -eu

if [ -z "${HSD_API_KEY:-}" ]; then
  echo "HSD_API_KEY is required" >&2
  exit 1
fi

mkdir -p "${HSD_PREFIX}"

exec node /opt/hsd/bin/hsd \
  --network="${HSD_NETWORK}" \
  --prefix="${HSD_PREFIX}" \
  --http-host="${HSD_HTTP_HOST}" \
  --http-port="${HSD_HTTP_PORT}" \
  --api-key="${HSD_API_KEY}" \
  --no-wallet \
  --log-level="${HSD_LOG_LEVEL}" \
  ${HSD_EXTRA_ARGS:-}
