#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ]; then
  echo 'Chưa có virtualenv. Làm theo README: tạo .venv và cài requirements.txt.' >&2
  exit 1
fi
export HOST="${HOST:-127.0.0.1}"
exec .venv/bin/python app.py
