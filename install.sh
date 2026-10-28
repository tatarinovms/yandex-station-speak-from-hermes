#!/usr/bin/env bash
# Устанавливает skill в активный Hermes profile и готовит безопасное получение токена.
set -euo pipefail

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SKILL_DIR="$HERMES_HOME/skills/smart-home/yandex-station-speak"

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

echo "==> Установка в $SKILL_DIR"
mkdir -p "$SKILL_DIR/scripts"
install -m 0644 "$THIS_DIR/SKILL.md" "$SKILL_DIR/SKILL.md"
install -m 0755 "$THIS_DIR/speak.sh" "$SKILL_DIR/speak.sh"
install -m 0755 "$THIS_DIR/scripts/tts_dialog.py" "$SKILL_DIR/scripts/tts_dialog.py"
install -m 0755 "$THIS_DIR/get_music_token.py" "$SKILL_DIR/get_music_token.py"
install -m 0644 "$THIS_DIR/env.example" "$SKILL_DIR/env.example"
install -m 0644 "$THIS_DIR/requirements-auth.txt" "$SKILL_DIR/requirements-auth.txt"

if [ ! -f "$SKILL_DIR/.env" ]; then
  install -m 0600 "$THIS_DIR/env.example" "$SKILL_DIR/.env"
else
  chmod 0600 "$SKILL_DIR/.env"
  echo "==> Существующий .env сохранён"
fi

AUTH_READY=0
if [ "${YSS_SKIP_AUTH_DEPS:-0}" = "1" ]; then
  echo "==> получение MUSIC_TOKEN пропущено (YSS_SKIP_AUTH_DEPS=1)"
else
  if "$PY" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'; then
    echo "==> Установка helper для OAuth Device Flow"
    "$PY" -m venv "$SKILL_DIR/.token-venv"
    "$SKILL_DIR/.token-venv/bin/pip" install --disable-pip-version-check --quiet \
      -r "$SKILL_DIR/requirements-auth.txt"
    AUTH_READY=1
  else
    echo "WARNING: получение MUSIC_TOKEN требует Python 3.12+; основной TTS работает на 3.10+" >&2
  fi
fi

echo ""
echo "Установка завершена."
echo ""
if [ "$AUTH_READY" = "1" ]; then
  cat <<EOF
1. Получить MUSIC_TOKEN:
   $SKILL_DIR/.token-venv/bin/python $SKILL_DIR/get_music_token.py
EOF
else
  echo "1. Получение MUSIC_TOKEN не настроено. Нужен Python 3.12+ и повторный запуск ./install.sh."
fi
cat <<EOF

2. Найти DEVICE_ID и DEVICE_PLATFORM:
   $PY $SKILL_DIR/scripts/tts_dialog.py --list-devices
3. Заполнить STATION_IP в $SKILL_DIR/.env
4. Проверить озвучку:
   $SKILL_DIR/speak.sh 'Проверка озвучки'
EOF
