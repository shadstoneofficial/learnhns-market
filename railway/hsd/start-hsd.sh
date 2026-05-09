#!/usr/bin/env sh
set -eu

if [ -z "${HSD_API_KEY:-}" ]; then
  echo "HSD_API_KEY is required" >&2
  exit 1
fi

mkdir -p "${HSD_PREFIX}"

echo "Starting HSD ${HSD_NETWORK} on ${HSD_HTTP_HOST}:${HSD_HTTP_PORT} with prefix ${HSD_PREFIX}"

exec env -i \
  HOME=/root \
  NODE_ENV=production \
  PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/hsd/bin:/opt/hsd/node_modules/.bin" \
  /usr/local/bin/node /opt/hsd/bin/node \
  --network="${HSD_NETWORK}" \
  --prefix="${HSD_PREFIX}" \
  --http-host="${HSD_HTTP_HOST}" \
  --http-port="${HSD_HTTP_PORT}" \
  --api-key="${HSD_API_KEY}" \
  --no-wallet \
  --log-console=true \
  --log-level="${HSD_LOG_LEVEL}" \
  ${HSD_EXTRA_ARGS:-}
