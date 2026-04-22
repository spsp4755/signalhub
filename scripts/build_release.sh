#!/usr/bin/env bash
# Build the SignalHub image and produce a compressed tarball for offline distribution.
# Usage: bash scripts/build_release.sh [tag]
set -euo pipefail

TAG="${1:-latest}"
IMAGE="signalhub:${TAG}"
DATE=$(date +%Y%m%d)
OUT_DIR="dist"
OUT_FILE="${OUT_DIR}/signalhub-${TAG}-${DATE}.tar.gz"

if [[ -n "${CONTAINER_ENGINE:-}" ]]; then
  ENGINE="${CONTAINER_ENGINE}"
elif command -v podman >/dev/null 2>&1; then
  ENGINE="podman"
elif command -v docker >/dev/null 2>&1; then
  ENGINE="docker"
else
  echo "error: neither podman nor docker is installed" >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

echo "==> engine: ${ENGINE}"
echo "==> building ${IMAGE}"
"${ENGINE}" build -t "${IMAGE}" .

echo "==> saving -> ${OUT_FILE}"
"${ENGINE}" save "${IMAGE}" | gzip -9 > "${OUT_FILE}"

echo
echo "done: ${OUT_FILE} ($(du -h "${OUT_FILE}" | cut -f1))"
echo "load on a target host: podman load -i ${OUT_FILE##*/}"
