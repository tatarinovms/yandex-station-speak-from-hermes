---
name: yandex-station-speak
description: Озвучка текста на колонку Яндекс Мини через Алису.
---

# Озвучка на Яндекс Станцию (с поддержкой Glagol)

Отправляет текст на колонку Яндекс Станция голосом Алисы через протокол Glagol (WSS, порт 1961). Решает: пауза музыки, подъём громкости до 80% для озвучки, возврат громкости и музыки после.

## Ключевые факты (проверено на практике 2026-08-20)

- **Колонка:** Яндекс Станция с поддержкой Glagol (проверено: Станция Мини 2, `platform yandexmini_2`). Подставьте свои `deviceId`, `platform`, статический IP из `.env`.
- **Прямое подключение:** когда рабочий хост в локальной сети колонки — работает напрямую (материалы на `~/.hermes/skills/smart-home/yandex-station-speak/`). Если хост НЕ в сети колонки (например, Wi-Fi client isolation) — резерв через SSH на сервер, где колонка доступна.
- Скрипты на рабочем хосте: `~/.hermes/skills/smart-home/yandex-station-speak/` (`tts_dialog.py`, `speak.sh`, `.env`). На сервере-хабе — там же (для резервного режима).
- **Рабочий MUSIC_TOKEN** получается ТОЛЬКО через `https://oauth.mobile.yandex.net/1/token` (из Session_id). Эндпоинт `oauth.yandex.ru/token` из оригинального README даёт 403 `USER_IS_NOT_AUTHORIZED_FOR_API` (нет quasar-скоупа).

## Команда для озвучки (полный цикл)

**Прямое подключение (когда рабочий хост в локальной сети колонки):**

```bash
~/.hermes/skills/smart-home/yandex-station-speak/speak.sh 'ТЕКСТ ФРАЗЫ'
```

Полный вызов без обёртки:
```bash
cd ~/.hermes/skills/smart-home/yandex-station-speak && python3 scripts/tts_dialog.py --pause --volume 0.8 'ТЕКСТ'
```

> ⚠️ На macOS `python3` может быть 3.9 (не подходит). `speak.sh` сам выбирает
> Homebrew-версию 3.10+ (python3.13/3.11/3.10). Для ручного вызова используйте
> `/opt/homebrew/bin/python3.13`.

**Резервный режим через SSH** (когда рабочий хост НЕ в сети колонки):
```bash
ssh <host-где-колонка-доступна> "~/.hermes/skills/smart-home/yandex-station-speak/speak.sh 'ТЕКСТ'"
```

Порядок в полном цикле: пауза → громкость 0.8 → озвучка → `wait_until_idle` (ждёт конца фразы) → вернуть громкость → пауза 1с → продолжить музыку.

## Обёртка speak.sh

Есть обёртка `~/.hermes/skills/smart-home/yandex-station-speak/speak.sh` (пауза + громкость 0.8 по умолчанию):

```bash
~/.hermes/skills/smart-home/yandex-station-speak/speak.sh 'ТЕКСТ'
```

## Критические технические находки (не повторять ошибки)

1. **Команда `{"command":"stop"}` НЕ работает** — колонка отвечает `server sent close frame`. Правильная пауза = `sendText` «пауза» через авторизованный канал (с conversationToken).
2. **`aliceState` во время озвучки = `NONE`, не `SPEAKING`** и не `IDLE`.
3. **Гонка таймингов:** после отправки `repeat_phrase` колонка начинает говорить с задержкой ~1с. Нельзя сразу `продолжить`/вернуть громкость — оборвёшь фразу. Нужен `wait_until_idle`: спит 1.3с, затем ждёт два стабильных `IDLE` подряд (интервал 0.5с).
4. `setVolume` принимает 0.0–1.0, читается громкость через `getState` → `state.volume`. Возврат громкости после озвучки работает (`get_volume` → `cmd_set_volume(prev)`).
5. Чтение громкости через `iot.quasar.yandex.ru` даёт 401 (нужны cookies+CSRF) — не использовать, читать через `getState`.
6. **ВАЖНО — баг озвучки «0.8»:** скрипт принимает `--volume <число>` двумя аргументами. При фильтрации текста нужно ПРОГЛАТЫВАТЬ и `--volume`, и его значение (число), иначе `0.8` попадёт в озвучиваемую фразу («ноль целых восемь десятых …»). Исправлено через `skip_next` в цикле разбора аргументов. Не возвращать наивный фильтр `[a for a in argv if not a.startswith("--")]` — он оставляет значение volume в тексте.
7. **Баг «старт музыки из простоя» (исправлено):** если колонка до озвучки молчала (музыка не играла), а после озвучки слать `sendText "продолжить"` — колонка ВКЛЮЧАЕТ радио/музыку, хотя до этого ничего не играло. Решение: перед паузой через `getState`→`playerState.hasPause` определить `was_playing`; возобновление (`продолжить`) отправлять ТОЛЬКО если `was_playing=True`. Если колонка была в простое (`hasPause=False`) — «продолжить» не слать. Функция `is_playing()` возвращает `hasPause`.
8. **Надёжный детектор воспроизведения:** `playerState.hasPause == True` ⇔ что-то играет (музыка/радио/подкаст); `False` ⇔ простой. Использовать для `was_playing` перед паузой, чтобы корректно решать про возобновление.

## Протокол паузы/возобновления

Все команды — WSS на `<STATION_IP>:1961` (IP колонки из `.env`) с payload `{"conversationToken": <token>, "id": <uuid>, "payload": {...}, "sentTime": <ms>}`.

- Пауза: `payload={"command":"sendText","text":"пауза"}`
- Возобновить: `payload={"command":"sendText","text":"продолжить"}`
- Громкость: `payload={"command":"setVolume","volume":<0.0-1.0>}`
- Состояние: `payload={"command":"getState"}` → `state.aliceState`, `state.volume`
- Озвучка: `serverAction` → `update_form` → `personal_assistant.scenarios.quasar.iot.repeat_phrase`, слот `phrase_to_repeat`.

## Интеграция с Hermes-чатом

**Приоритет — прямое подключение (локальная сеть):**
```bash
~/.hermes/skills/smart-home/yandex-station-speak/speak.sh 'ТЕКСТ'
```

Если прямое подключение не сработало (хост вне сети колонки) — резерв через SSH:
```bash
ssh <host-где-колонка-доступна> "~/.hermes/skills/smart-home/yandex-station-speak/speak.sh 'ТЕКСТ'"
```

Скилл через `terminal`/`browser_exec` пытается сначала локально, при недоступности колонки — через SSH на сервер, где колонка доступна. Ограничения текста: ≤500 символов, без кода/JSON/спецсимволов, формулировать для устной речи.
