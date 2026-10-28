# yandex-station-speak-from-hermes

Hermes skill для озвучки текста и выполнения команд на **Яндекс Станции** через локальный протокол **Glagol** (WSS, порт 1961).

Полный звуковой цикл: **пауза музыки → временная громкость 80% → фраза → возврат громкости → продолжение музыки**.

Форк [`Realmagnum/yandex-station-speak`](https://github.com/Realmagnum/yandex-station-speak), основанного на `rasperepodvipodvert/claude-skill-yandex-tts`. Добавлены установка для Hermes, безопасное получение токена через OAuth Device Flow, тесты и гарантированное восстановление состояния колонки после ошибки.

## Возможности

- Озвучивает фразы длиной до 500 символов.
- Приостанавливает музыку и возвращает её после сообщения.
- Временно повышает громкость до 80%, затем восстанавливает исходную.
- Не запускает музыку, если до сообщения колонка молчала.
- При ошибке отправки всё равно пытается вернуть прежнюю громкость и музыку.
- Работает локально, без облачного TTS-файла: фразу произносит Алиса.
- В Hermes реагирует на запросы вида `скажи в станции: <текст>`.
- Выполняет обычные команды Алисы: свет, музыка, таймеры, сценарии умного дома и другие действия аккаунта.

> Glagol — недокументированный протокол Яндекса. Его поведение может измениться после обновления прошивки.

## Требования

- Linux или macOS;
- Hermes Agent;
- Python 3.10+ для озвучки;
- Python 3.12+ для автоматического получения `MUSIC_TOKEN`;
- рабочий хост и Станция в одной локальной сети;
- статический DHCP lease для Станции рекомендуется.

## Установка

```bash
git clone https://github.com/tatarinovms/yandex-station-speak-from-hermes.git
cd yandex-station-speak-from-hermes
./install.sh
```

Skill устанавливается в:

```text
${HERMES_HOME:-$HOME/.hermes}/skills/smart-home/yandex-station-speak
```

Повторный запуск установщика обновляет файлы skill, но сохраняет существующий `.env`.

## 1. Получение MUSIC_TOKEN

Установщик создаёт отдельное окружение `.token-venv` и устанавливает `ya-passport-auth`. Запустите:

```bash
"${HERMES_HOME:-$HOME/.hermes}/skills/smart-home/yandex-station-speak/.token-venv/bin/python" \
  "${HERMES_HOME:-$HOME/.hermes}/skills/smart-home/yandex-station-speak/get_music_token.py"
```

Скрипт покажет адрес Яндекса и короткий код:

1. откройте адрес в браузере;
2. войдите в аккаунт, к которому привязана Станция;
3. введите код и подтвердите вход.

`MUSIC_TOKEN` не выводится в терминал: он сразу записывается в `.env`, которому выставляются права `0600`.

## 2. Поиск устройства

```bash
cd "${HERMES_HOME:-$HOME/.hermes}/skills/smart-home/yandex-station-speak"
python3 scripts/tts_dialog.py --list-devices
```

Пример:

```text
Яндекс Мини  platform=yandexmini  id=0123456789ABCDEF
```

Перенесите `id` и `platform` в `.env`:

```ini
DEVICE_ID=0123456789ABCDEF
DEVICE_PLATFORM=yandexmini
```

## 3. IP-адрес Станции

Найдите адрес колонки в DHCP leases роутера и задайте его в `.env`:

```ini
STATION_IP=192.168.0.50
```

На macOS скрипт также умеет искать `_yandexio._tcp` через `dns-sd`, но статический DHCP lease надёжнее.

## 4. Проверка

```bash
"${HERMES_HOME:-$HOME/.hermes}/skills/smart-home/yandex-station-speak/speak.sh" \
  'Проверка. Озвучка Яндекс Станции подключена.'
```

Без паузы и изменения громкости:

```bash
"${HERMES_HOME:-$HOME/.hermes}/skills/smart-home/yandex-station-speak/speak.sh" --nopause \
  'Сообщение поверх музыки.'
```

Ручной вызов:

```bash
python3 scripts/tts_dialog.py --pause --volume 0.8 'Текст'
```

## Использование в Hermes

После установки достаточно написать:

```text
скажи в станции: Через десять минут пора выходить
```

Skill передаёт только текст после команды. Он не добавляет пояснений и не отправляет секреты, код или служебные данные.

Команды Алисе отправляются отдельным триггером:

```text
команда Алисе: включи свет
```

Hermes сначала безопасно записывает текст в отдельный файл, а затем вызывает фиксированную команду без подстановки пользовательского текста в shell:

```bash
"${HERMES_HOME:-$HOME/.hermes}/skills/smart-home/yandex-station-speak/command.sh" \
  --file /root/.hermes/cache/scratch/alice-command.txt
```

Работают те же формулировки, которые Алиса понимает с голоса: управление светом и другими устройствами, запуск музыки и радио, таймеры, погода и сценарии умного дома. Возможности зависят от устройств и навыков, подключённых к аккаунту Яндекса.

Для потенциально опасных действий (замки, ворота, сигнализация, нагреватели, духовка), а также сценариев с неизвестным составом действий, в `SKILL.md` предусмотрено подтверждение пользователя перед отправкой. Это правило агента; при ручном запуске `command.sh` отдельной проверки нет.

## Как это работает

- Список устройств и `conversationToken` запрашиваются через Quasar API.
- `MUSIC_TOKEN` получается обменом авторизации через `oauth.mobile.yandex.net/1/token`; helper скрывает детали обмена за OAuth Device Flow.
- Команды отправляются напрямую на `wss://<STATION_IP>:1961`.
- Пауза и продолжение — команды `sendText` со словами «пауза» и «продолжить».
- Озвучка — `serverAction` со сценарием `personal_assistant.scenarios.quasar.iot.repeat_phrase`.
- `conversationToken` действует примерно 30 минут и обновляется после 25 минут.
- Конец фразы определяется по возврату `aliceState` в стабильный `IDLE`.

## Тесты

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh speak.sh command.sh
python3 -m py_compile scripts/tts_dialog.py get_music_token.py
```

## Файлы

```text
SKILL.md                 инструкции для Hermes
speak.sh                 короткая обёртка полного аудиоцикла
command.sh               передача обычной команды Алисе через sendText
scripts/tts_dialog.py    Glagol/Quasar-клиент
get_music_token.py       безопасный OAuth Device Flow
requirements-auth.txt    зависимость только для получения токена
install.sh               установка в активный Hermes profile
env.example              шаблон конфигурации без секретов
tests/                   автоматические тесты
```

## Лицензия

MIT. Исходная протокольная основа: Igor Filatov (`rasperepodvipodvert/claude-skill-yandex-tts`). Полный аудиоцикл: `Realmagnum/yandex-station-speak`. Hermes-интеграция и последующие исправления — этот fork.
