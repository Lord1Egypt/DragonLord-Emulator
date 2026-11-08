#!/bin/bash
# Build DragonLord.exe (Windows x64, static, no runtime needed) from WSL/Linux with Go 1.22+:  ./build.sh [OUT]
set -euo pipefail
cd "$(dirname "$0")"
OUT="${1:-../.work/dist/DragonLord.exe}"
mkdir -p "$(dirname "$OUT")"
gofmt -l . | (! grep .) || { echo "run gofmt -w ." >&2; exit 1; }
GOOS=windows go vet ./...
GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o "$OUT" .
sha256sum "$OUT"
