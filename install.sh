#!/usr/bin/env bash
# install.sh — развернуть озвучку Яндекс Станции Мини на новом хосте.
#
# Делает:
#   1. клонирует репо claude-skill-yandex-tts в ~/.claude/skills/speak
#   2. копирует обновлённый tts_dialog.py (полный цикл паузы/громкости) и speak.sh
#   3. создаёт .env из env.example
#
# Для завершения: заполнить MUSIC_TOKEN и DEVICE_ID в .env (см. SETUP.md /
# раздел «Получение MUSIC_TOKEN»), затем проверить:
#   python3 scripts/tts_dialog.py --list-devices
#
# ВАЖНО: работает на Linux-сервере. На macOS mDNS есть, но STATION_IP всё же
# настоятельно рекомендуется прописать статическим.
set -euo pipefail

SKILL_DIR="${HOME}/.claude/skills/speak"
REPO="https://github.com/rasperepodvipodvert/claude-skill-yandex-tts.git"
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Скилл будет установлен в: $SKILL_DIR"

# Python 3.10+?
py=$(command -v python3 || true)
if [ -n "$py" ]; then
  maj_min=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")
  echo "==> python3: $py ($maj_min), нужно 3.10+"
fi

mkdir -p "$(dirname "$SKILL_DIR")"
if [ ! -d "$SKILL_DIR/.git" ]; then
  echo "==> Клонирую репо..."
  git clone --depth 1 "$REPO" "$SKILL_DIR"
else
  echo "==> Репо уже есть, оставляю (для обновления: git -C $SKILL_DIR pull)"
fi

echo "==> Копирую обновлённые скрипты (tts_dialog.py, speak.sh)..."
cp "$THIS_DIR/tts_dialog.py" "$SKILL_DIR/scripts/tts_dialog.py"
chmod +x "$SKILL_DIR/scripts/tts_dialog.py"
cp "$THIS_DIR/speak.sh" "$SKILL_DIR/speak.sh"
chmod +x "$SKILL_DIR/speak.sh"

echo "==> Создаю .env из env.example (если нет)..."
if [ ! -f "$SKILL_DIR/.env" ]; then
  cp "$THIS_DIR/env.example" "$SKILL_DIR/.env"
fi

echo ""
echo "✅ Установка готова. Осталось заполнить $SKILL_DIR/.env:"
echo "   - MUSIC_TOKEN   (рабочий, через oauth.mobile.yandex.net — см. SETUP.md)"
echo "   - DEVICE_ID     (подставьте свой, из --list-devices)"
echo "   - DEVICE_PLATFORM (например yandexmini_2)"
echo "   - STATION_IP    (статический IP колонки, на Linux обязателен)"
echo ""
echo "Проверка:"
echo "   cd $SKILL_DIR && python3 scripts/tts_dialog.py --list-devices"
echo "Тест озвучки:"
echo "   python3 $SKILL_DIR/scripts/tts_dialog.py --pause --volume 0.8 'Привет'"
