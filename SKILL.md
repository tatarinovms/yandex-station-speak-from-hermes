---
name: yandex-station-speak
description: "Use when user asks to say text on Yandex Station."
version: 1.0.0
author: Maxim Tatarinov
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [smart-home, yandex-station, tts, glagol]
---

# Озвучка на Яндекс Станцию

## Триггер

Когда пользователь пишет **«скажи в станции: <текст>»**, **«скажи на станции: <текст>»** или **«скажи в Яндекс Станции: <текст>»**, сразу выполнить:

```bash
"${HERMES_HOME:-$HOME/.hermes}/skills/smart-home/yandex-station-speak/speak.sh" '<текст>'
```

- Обычную фразу озвучивать без уточнения: команда пользователя уже является явным поручением.
- Передавать только пользовательский текст после триггера; не добавлять пояснения, код, команды или секреты.
- После выполнения кратко сообщить результат.
- Для текста длиннее 500 символов попросить его сократить.
- `--nopause` применять только по явной просьбе говорить поверх музыки.

## Поведение

По умолчанию выполняется полный цикл:

1. определить, играла ли музыка;
2. сохранить текущую громкость;
3. поставить музыку на паузу;
4. установить громкость 80%;
5. произнести фразу голосом Алисы;
6. дождаться конца фразы;
7. вернуть громкость;
8. продолжить музыку, только если она играла до сообщения.

При ошибке отправки скрипт всё равно пытается восстановить громкость и музыку.

## Команды

Полный цикл:

```bash
"${HERMES_HOME:-$HOME/.hermes}/skills/smart-home/yandex-station-speak/speak.sh" 'ТЕКСТ'
```

Поверх музыки без изменения громкости:

```bash
"${HERMES_HOME:-$HOME/.hermes}/skills/smart-home/yandex-station-speak/speak.sh" --nopause 'ТЕКСТ'
```

Проверка устройств:

```bash
cd "${HERMES_HOME:-$HOME/.hermes}/skills/smart-home/yandex-station-speak"
python3 scripts/tts_dialog.py --list-devices
```

Получение `MUSIC_TOKEN`:

```bash
"${HERMES_HOME:-$HOME/.hermes}/skills/smart-home/yandex-station-speak/.token-venv/bin/python" \
  "${HERMES_HOME:-$HOME/.hermes}/skills/smart-home/yandex-station-speak/get_music_token.py"
```

Токен сохраняется прямо в `.env` с правами `0600`; не просить пользователя присылать его в чат.

## Ограничения

- Хост должен видеть Станцию в локальной сети на TCP 1961.
- Требуются `MUSIC_TOKEN`, `DEVICE_ID`, `DEVICE_PLATFORM` и `STATION_IP` в `.env`.
- Glagol недокументирован и может измениться после обновления прошивки.
- На Linux задавать статический `STATION_IP`; macOS дополнительно поддерживает mDNS через `dns-sd`.
