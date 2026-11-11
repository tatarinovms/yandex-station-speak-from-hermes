#!/usr/bin/env bash
# speak.sh — отправить текст на Яндекс Станцию (Glagol) для озвучки голосом Алисы.
#
# Использование:
#   speak.sh "текст"              # озвучить фразу
#   speak.sh --nopause "текст"    # без паузы и подъёма громкости (поверх музыки)
#   speak.sh файл_с_текстом      # озвучить содержимое файла
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$SKILL_DIR/scripts/tts_dialog.py"

PY=""
for candidate in python3.13 python3.12 python3.11 python3.10; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PY="$candidate"
      break
    fi
  fi
done
[ -n "$PY" ] || PY="python3"
if ! "$PY" -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  echo "ERROR: требуется Python 3.10+ (найден $($PY --version 2>&1))"
  exit 2
fi

pause=1
volume=0.8
args=()

for a in "$@"; do
  if [ "$a" = "--nopause" ]; then
    pause=0
  elif [ -f "$a" ]; then
    # передан файл со текстом — читаем построчно
    while IFS= read -r line || [ -n "$line" ]; do
      args+=("$line")
    done < "$a"
  else
    args+=("$a")
  fi
done

if [ "${#args[@]}" -eq 0 ]; then
  echo "ERROR: пустая фраза. Использование: speak.sh <текст> [--nopause] [<файл>]"
  exit 2
fi

TEXT="${args[*]}"
if [ "${#TEXT}" -gt 500 ]; then
  echo "ERROR: текст длиннее 500 символов (${#TEXT}). Сократить."
  exit 2
fi

FLAGS=()
if [ "$pause" -eq 1 ]; then
  FLAGS+=("--pause" "--volume" "$volume")
fi

out=$("$PY" "$SCRIPT" "${FLAGS[@]}" "${args[@]}" 2>&1)
code=$?

if [ "$code" -eq 0 ]; then
  echo "OK: фраза отправлена на Яндекс Станцию."
  if [ "$pause" -eq 0 ]; then
    echo "    (режим --nopause: музыка и громкость не менялись)"
  fi
else
  echo "FAIL ($code): $out"
fi

exit "$code"
