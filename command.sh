#!/usr/bin/env bash
# Передаёт текст Алисе как команду без голосового пробуждения колонки.
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$SKILL_DIR/scripts/tts_dialog.py"

PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && \
     "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "ERROR: требуется Python 3.10+" >&2
  exit 2
fi

if [ "${1:-}" = "--file" ]; then
  if [ "$#" -ne 2 ]; then
    echo "ERROR: использование: command.sh --file <путь>" >&2
    exit 2
  fi
  out=$(cd "$SKILL_DIR" && "$PY" "$SCRIPT" --command-file "$2" 2>&1)
else
  TEXT="$*"
  if [ -z "$TEXT" ]; then
    echo "ERROR: пустая команда. Использование: command.sh <команда Алисе>" >&2
    exit 2
  fi
  if [ "${#TEXT}" -gt 500 ]; then
    echo "ERROR: команда длиннее 500 символов (${#TEXT}). Сократить." >&2
    exit 2
  fi
  out=$(cd "$SKILL_DIR" && "$PY" "$SCRIPT" --command "$TEXT" 2>&1)
fi
code=$?
if [ "$code" -eq 0 ]; then
  echo "OK: команда отправлена Алисе."
else
  echo "FAIL ($code): $out" >&2
fi
exit "$code"
