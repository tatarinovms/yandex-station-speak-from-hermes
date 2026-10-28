#!/usr/bin/env bash
# speak.sh — отправить текст на Яндекс Станцию (Glagol) для озвучки голосом Алисы.
#
# Использование:
#   speak.sh "текст"      # полный цикл: пауза + громкость 0.8 + озвучка + возврат
#   speak.sh --nopause "текст"   # без паузы и без подъёма громкости (поверх музыки)
#
# Полный цикл (по умолчанию):
#   1. поставить музыку на паузу (sendText 'пауза')
#   2. поднять громкость до 0.8
#   3. озвучить repeat_phrase
#   4. дождаться конца фразы (wait_until_idle)
#   5. вернуть прежнюю громкость
#   6. пауза 1с, затем возобновить музыку (sendText 'продолжить')
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$SKILL_DIR/scripts/tts_dialog.py"

# Требуется Python 3.10+. На macOS системный python3 может быть 3.9,
# поэтому выбираем свежий из Homebrew /usr/local /opt/homebrew.
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
      PY="$candidate"
      break
    fi
  fi
done
[ -n "$PY" ] || PY="python3"
if ! "$PY" -c 'import sys; exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
  echo "ERROR: требуется Python 3.10+ (найден $($PY --version 2>&1))"
  exit 2
fi

FLAGS="--pause --volume 0.8"
args=()
for a in "$@"; do
  if [ "$a" = "--nopause" ]; then FLAGS=""; else args+=("$a"); fi
done

TEXT="${args[*]:-}"

if [ -z "$TEXT" ]; then
  echo "ERROR: пустая фраза. Использование: speak.sh <текст> [--nopause]"
  exit 2
fi

if [ "${#TEXT}" -gt 500 ]; then
  echo "ERROR: текст длиннее 500 символов (${#TEXT}). Сократить."
  exit 2
fi

out=$(cd "$SKILL_DIR" && "$PY" "$SCRIPT" $FLAGS "$TEXT" 2>&1)
code=$?

if [ $code -eq 0 ]; then
  echo "OK: фраза отправлена на Яндекс Станцию."
  if [ -z "$FLAGS" ]; then
    echo "    (режим --nopause: музыка и громкость не менялись)"
  fi
else
  echo "FAIL ($code): $out"
fi

exit $code
