#!/bin/sh
set -eu

cd "$(dirname "$0")"
.venv/bin/python -m app.scripts.migrate

if [ "${SKIP_OLLAMA_WARMUP:-0}" != "1" ]; then
  if ! .venv/bin/python -u -m app.scripts.warm_model; then
    echo "Tiếp tục khởi động API bằng parser fallback." >&2
  fi
fi

exec .venv/bin/uvicorn app.main:app --workers 1 --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
