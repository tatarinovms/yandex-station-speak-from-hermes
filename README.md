# yandex-station-speak

Озвучка текста на колонку **Яндекс Станция** голосом Алисы через протокол **Glagol** (WSS :1961).

Полный звуковой цикл: **пауза музыки → громкость 80% → фраза → возврат громкости → продолжение музыки**.

Эволюция скилла `rasperepodvipodvert/claude-skill-yandex-tts` (MIT, автор Igor Filatov). Сохранено ~80% протокольной основы, добавлено ~20% — законченный аудио-цикл с прерыванием музыки и управлением громкостью.

## Возможности

- Отправить фразу на колонку голосом Алисы.
- **Прерывает музыку** (пауза перед озвучкой) и **возобновляет её после**.
- **Поднимает громкость до 80%** на время озвучки, затем возвращает прежнюю.
- Если колонка молчала до озвучки — музыка **не** включается (умный детект `hasPause`).
- Текст ≤500 символов, русский, без кода/JSON/спецсимволов.

## Установка

```bash
# скрипты
mkdir -p ~/.hermes/skills/smart-home/yandex-station-speak && cd $_
# положите сюда SKILL.md, speak.sh, scripts/tts_dialog.py, env.example

# зависимости: Python 3.10+
python3 --version   # должно быть 3.10+

# конфиг
cp env.example .env
# заполните .env: MUSIC_TOKEN, DEVICE_ID, DEVICE_PLATFORM, STATION_IP
```

### Получение MUSIC_TOKEN (важно!)

**Рабочий** токен даётся ТОЛЬКО через `oauth.mobile.yandex.net/1/token`
(см. раздел «Токены» ниже). Эндпоинт `oauth.yandex.ru/token` из оригинального
README даёт 403 `USER_IS_NOT_AUTHORIZED_FOR_API`.

## Использование

### Прямое подключение (колонка в той же LAN, что и рабочий хост)

```bash
~/.hermes/skills/smart-home/yandex-station-speak/speak.sh 'Текст'
```

### Через ssh на сервер, где колонка доступна

```bash
ssh host "~/.hermes/skills/smart-home/yandex-station-speak/speak.sh 'Текст'"
```

### Ручной вызов (полный контроль)

```bash
python3 scripts/tts_dialog.py --pause --volume 0.8 'Текст'
```

Флаги:
- `--pause` — пауза музыки перед озвучкой + возобновление после (пауза 1с).
- `--volume 0.8` — громкость 80% на время озвучки, возврат после.
- Без флагов — озвучить поверх (музыка приглушится, не прервётся).

> ⚠️ На macOS системный `python3` может быть 3.9 (не подходит). `speak.sh` сам
> выбирает 3.10+ (python3.13/3.12/3.11/3.10 или Homebrew). Вручную — используйте
> `/opt/homebrew/bin/python3.13`.

### Проверка устройств

```bash
python3 scripts/tts_dialog.py --list-devices
```

## Токены (Glagol / Quasar)

- **Управление колонкой** — Glagol WSS на `:1961`, сообщения с `conversationToken` (короткоживущий, ~30с, кешируется 25с).
- **Список устройств / token** — Quasar (`quasar.yandex.net/glagol/device_list`, `.../token`).
- **MUSIC_TOKEN** — получать через `oauth.mobile.yandex.net/1/token` (mobile-эндпоинт даёт нужный scope). `oauth.yandex.ru/token` → 403.

## Структура

```
SKILL.md           # (опционально) скилл-метаданные для Hermes/Claude
speak.sh           # обёртка: полный цикл паузы/громкости, авто-выбор Python 3.10+
scripts/
  tts_dialog.py    # основной скрипт (Glagol WSS + все команды)
env.example        # шаблон конфига (БЕЗ секретов)
install.sh         # установщик на новый хост
```

## Ключевые детали реализации (грабли)

1. Пауза музыки = `sendText "пауза"` (НЕ `{"command":"stop"}` — колонка отвечает close frame).
2. `aliceState` во время озвучки = `NONE`, не `SPEAKING`.
3. Перед возобновлением музыки ждать конца фразы (`wait_until_idle`: 1.3с лаг + 2 стабильных `IDLE`), иначе фраза обрывается и громкость падает.
4. **Возобновлять музыку только если она играла** (`playerState.hasPause`), иначе «продолжить» стартует радио из простоя.
5. Возврат громкости — `get_volume()` затем `cmd_set_volume(prev)`.
6. Не придумывать про «0.8» — в `--volume <число>` значение не должно попадать в текст (обрабатывается `skip_next`).

## Лицензия

MIT. Основа: `rasperepodvipodvert/claude-skill-yandex-tts` (c) Igor Filatov.
Модификации и полный аудио-цикл — этот репозиторий.

**Протокол Glagol недокументирован и может измениться прошивкой Яндекса в любой момент.**
