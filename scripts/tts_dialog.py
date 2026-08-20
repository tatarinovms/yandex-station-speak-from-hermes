#!/usr/bin/env python3
"""TTS через Яндекс Станцию — отправка текста для озвучки голосом Алисы.

Чистый Python 3 (только stdlib). WebSocket реализован через ssl + socket.
"""

import base64
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import time
import uuid
import urllib.parse
import urllib.request
import urllib.error


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load_env(path: str) -> dict[str, str]:
    """Читает .env файл (ключ=значение, с/без кавычек)."""
    if not os.path.isfile(path):
        die(f"Config not found: {path}")
    env: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Убираем обрамляющие кавычки
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            env[key] = value
    return env


def save_env(path: str, env: dict[str, str]) -> None:
    """Перезаписывает .env файл, сохраняя порядок ключей и комментарии."""
    lines: list[str] = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()

    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in env:
                new_lines.append(f"{key}={env[key]}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line if line.endswith("\n") else line + "\n")

    # Добавляем ключи, которых ещё не было в файле
    for key, value in env.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    os.chmod(path, 0o600)


def clean_text(text: str) -> str:
    """Очищает текст от markdown-разметки."""
    # Блоки кода ```...```
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Инлайн-код `...`
    text = re.sub(r"`[^`]*`", "", text)
    # Ссылки [text](url)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Заголовки
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Bold **text**
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    # Italic *text*
    text = re.sub(r"\*([^*]*)\*", r"\1", text)
    # Strikethrough ~~text~~
    text = re.sub(r"~~([^~]*)~~", r"\1", text)
    # HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Цитаты
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)
    # Списки
    text = re.sub(r"^[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[0-9]+\.\s+", "", text, flags=re.MULTILINE)
    # Переносы строк → точки
    text = text.replace("\n", ". ")
    text = re.sub(r"\.(\s*\.)+", ". ", text)
    # Спецсимволы
    text = re.sub(r"[`~|]", "", text)
    # Пробелы
    text = text.strip()
    # Обрезка до 500 символов
    return text[:500]


# ---------------------------------------------------------------------------
# Минимальный WebSocket-клиент (RFC 6455)
# ---------------------------------------------------------------------------

_HANDSHAKE_BUF_LIMIT = 65536
MAX_PAYLOAD = 1_048_576  # 1 MB


class _WsConnection:
    """Обёртка над SSL-сокетом с внутренним буфером для WebSocket."""

    def __init__(self, sock: ssl.SSLSocket) -> None:
        self.sock = sock
        self._buf = b""

    def push_remainder(self, data: bytes) -> None:
        self._buf = data + self._buf

    def recv_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(4096)
            if not chunk:
                die("WebSocket: connection closed while reading")
            self._buf += chunk
        result = self._buf[:n]
        self._buf = self._buf[n:]
        return result


def _ws_handshake(sock: ssl.SSLSocket, host: str, port: int) -> _WsConnection:
    """Выполняет WebSocket Upgrade handshake. Возвращает _WsConnection с буфером."""
    key = _ws_random_key()
    request = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"\r\n"
    )
    sock.sendall(request.encode("utf-8"))

    # Читаем ответ до \r\n\r\n
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            die("WebSocket handshake: connection closed")
        buf += chunk
        if len(buf) > _HANDSHAKE_BUF_LIMIT:
            die("WebSocket handshake: response too large")

    header_end = buf.index(b"\r\n\r\n")
    header_part = buf[:header_end].decode("utf-8", errors="replace")
    remainder = buf[header_end + 4:]

    status_line = header_part.split("\r\n")[0]
    parts = status_line.split()
    if len(parts) < 2 or parts[1] != "101":
        die(f"WebSocket handshake failed: {status_line}")

    # Валидация Sec-WebSocket-Accept (RFC 6455 Section 4.2.2)
    _WS_MAGIC = "258EAFA5-E914-47DA-95CA-5AB4AA40E516"
    expected_accept = base64.b64encode(
        hashlib.sha1((key + _WS_MAGIC).encode("ascii")).digest()
    ).decode("ascii")

    accept_value = ""
    for hdr_line in header_part.split("\r\n")[1:]:
        if ":" in hdr_line:
            hdr_name, _, hdr_val = hdr_line.partition(":")
            if hdr_name.strip().lower() == "sec-websocket-accept":
                accept_value = hdr_val.strip()
                break

    if accept_value and accept_value != expected_accept:
        # Яндекс Станция может некорректно реализовать RFC 6455 — предупреждаем, но продолжаем
        print(f"WARNING: Sec-WebSocket-Accept mismatch (local trusted device)", file=sys.stderr)

    ws = _WsConnection(sock)
    if remainder:
        ws.push_remainder(remainder)
    return ws


def _ws_random_key() -> str:
    """Генерирует случайный Sec-WebSocket-Key (base64 из 16 случайных байт)."""
    return base64.b64encode(os.urandom(16)).decode("ascii")


def _ws_send_text(sock: ssl.SSLSocket, data: str) -> None:
    """Отправляет текстовый WebSocket-фрейм (masked, как требует RFC 6455 для клиента)."""
    payload = data.encode("utf-8")
    length = len(payload)
    mask_key = os.urandom(4)

    # Первый байт: FIN=1, opcode=0x1 (text)
    frame = bytearray([0x81])

    # Длина + бит маски
    if length <= 125:
        frame.append(0x80 | length)
    elif length <= 65535:
        frame.append(0x80 | 126)
        frame.extend(struct.pack("!H", length))
    else:
        frame.append(0x80 | 127)
        frame.extend(struct.pack("!Q", length))

    frame.extend(mask_key)

    # Маскировка payload
    masked = bytearray(length)
    for i in range(length):
        masked[i] = payload[i] ^ mask_key[i % 4]
    frame.extend(masked)

    sock.sendall(bytes(frame))


def _ws_recv_text(ws: _WsConnection, timeout: float = 10.0) -> str:
    """Читает один текстовый WebSocket-фрейм (цикл вместо рекурсии)."""
    ws.sock.settimeout(timeout)

    while True:
        header = ws.recv_exact(2)
        opcode = header[0] & 0x0F
        is_masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F

        if length == 126:
            length = struct.unpack("!H", ws.recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", ws.recv_exact(8))[0]

        if length > MAX_PAYLOAD:
            die(f"WebSocket: payload too large ({length} bytes, max {MAX_PAYLOAD})")

        mask_key = ws.recv_exact(4) if is_masked else None

        payload = ws.recv_exact(length)

        if is_masked and mask_key:
            payload = bytearray(payload)
            for i in range(length):
                payload[i] ^= mask_key[i % 4]
            payload = bytes(payload)

        if opcode == 0x1:  # text
            return payload.decode("utf-8", errors="replace")
        elif opcode == 0x8:  # close
            die("WebSocket: server sent close frame")
        elif opcode == 0x9:  # ping — ответить pong и читать дальше
            _ws_send_pong(ws.sock, payload)
            continue
        else:
            # Пропускаем другие фреймы, читаем следующий
            continue


def _ws_send_pong(sock: ssl.SSLSocket, payload: bytes) -> None:
    """Отправляет pong-фрейм (payload обрезается до 125 байт по RFC 6455)."""
    payload = payload[:125]
    mask_key = os.urandom(4)
    length = len(payload)
    frame = bytearray([0x8A])  # FIN=1, opcode=0xA (pong)
    frame.append(0x80 | length)
    frame.extend(mask_key)
    masked = bytearray(length)
    for i in range(length):
        masked[i] = payload[i] ^ mask_key[i % 4]
    frame.extend(masked)
    sock.sendall(bytes(frame))


def _ws_send_close(sock: ssl.SSLSocket, code: int = 1000) -> None:
    """Отправляет WebSocket Close frame (RFC 6455 Section 5.5.1)."""
    payload = struct.pack("!H", code)
    mask_key = os.urandom(4)
    length = len(payload)
    frame = bytearray([0x88])  # FIN=1, opcode=0x8 (close)
    frame.append(0x80 | length)
    frame.extend(mask_key)
    masked = bytearray(length)
    for i in range(length):
        masked[i] = payload[i] ^ mask_key[i % 4]
    frame.extend(masked)
    sock.sendall(bytes(frame))


def ws_send_and_receive(host: str, port: int, message: str) -> str:
    """Подключается по WebSocket (wss), отправляет сообщение, возвращает ответ."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    raw_sock = socket.create_connection((host, port), timeout=10)
    sock = ctx.wrap_socket(raw_sock, server_hostname=host)

    try:
        ws = _ws_handshake(sock, host, port)
        _ws_send_text(sock, message)
        return _ws_recv_text(ws)
    finally:
        try:
            _ws_send_close(sock)
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Получение списка устройств
# ---------------------------------------------------------------------------

def fetch_devices(music_token: str) -> list[dict]:
    """Получает список устройств через Yandex Quasar API.

    Возвращает список словарей с ключами: id, platform, name.
    """
    url = "https://quasar.yandex.net/glagol/device_list"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Oauth {music_token}")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        die(f"Failed to fetch device list: {e}")
    except json.JSONDecodeError as e:
        die(f"Invalid JSON in device list response: {e}")

    devices = []
    for d in data.get("devices", []):
        devices.append({
            "id": d.get("id", ""),
            "platform": d.get("platform", ""),
            "name": d.get("config", {}).get("name", d.get("name", "")),
        })
    return devices


# ---------------------------------------------------------------------------
# mDNS-обнаружение IP станции (macOS dns-sd)
# ---------------------------------------------------------------------------

def discover_station_ip(device_id: str) -> str | None:
    """Ищет IP Яндекс Станции по device_id через mDNS (dns-sd на macOS).

    Возвращает IP-адрес или None, если не найдено / не macOS.
    Таймаут ~5 секунд на каждый шаг.
    """
    if platform.system() != "Darwin":
        return None
    if not shutil.which("dns-sd"):
        return None

    # Шаг 1: browse + lookup — ищем hostname устройства с нужным device_id
    hostname = _mdns_find_hostname(device_id)
    if not hostname:
        return None

    # Шаг 2: resolve hostname → IP
    return _mdns_resolve_ip(hostname)


def _mdns_browse_services() -> list[str]:
    """Browse mDNS: возвращает список instance names для _yandexio._tcp."""
    try:
        proc = subprocess.Popen(
            ["dns-sd", "-B", "_yandexio._tcp", "local"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            time.sleep(3)
            proc.terminate()
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        browse_output = proc.stdout.read()
    except Exception:
        return []

    # Парсим имена сервисов из вывода dns-sd -B
    # Формат строк: "Timestamp  A/R  Flags  if  Domain  Service Type  Instance Name"
    service_names: list[str] = []
    for line in browse_output.splitlines():
        parts = line.split()
        if len(parts) >= 7 and parts[1] == "Add":
            instance_name = " ".join(parts[6:])
            service_names.append(instance_name)
    return service_names


def _mdns_lookup_service(name: str) -> tuple[str | None, str]:
    """Lookup mDNS сервиса: возвращает (hostname | None, raw_output)."""
    try:
        proc = subprocess.Popen(
            ["dns-sd", "-L", name, "_yandexio._tcp", "local"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            time.sleep(2)
            proc.terminate()
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        lookup_output = proc.stdout.read()
    except Exception:
        return None, ""

    hostname = None
    for ln in lookup_output.splitlines():
        m = re.search(r"can be reached at\s+(\S+?):\d+", ln)
        if m:
            hostname = m.group(1)
            break
    return hostname, lookup_output


def _mdns_find_hostname(device_id: str) -> str | None:
    """Ищет hostname устройства через dns-sd -B + dns-sd -L."""
    service_names = _mdns_browse_services()

    # Для каждого найденного сервиса делаем Lookup и ищем device_id в TXT-записях
    for name in service_names:
        hostname, lookup_output = _mdns_lookup_service(name)
        # Проверяем, содержит ли TXT-запись наш device_id
        if device_id in lookup_output and hostname:
            return hostname
    return None


def _mdns_resolve_ip(hostname: str) -> str | None:
    """Резолвит hostname через dns-sd -G v4."""
    try:
        proc = subprocess.Popen(
            ["dns-sd", "-G", "v4", hostname],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            time.sleep(3)
            proc.terminate()
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        output = proc.stdout.read()
    except Exception:
        return None

    # Парсим IP из вывода: "Timestamp  A/R Flags if Hostname Address  TTL"
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[1] == "Add":
            ip_candidate = parts[5]
            # Проверяем, что это валидный IPv4
            try:
                socket.inet_aton(ip_candidate)
                return ip_candidate
            except socket.error:
                continue
    return None


def ping_host(ip: str) -> bool:
    """Проверяет доступность хоста одним пингом."""
    try:
        flag = "-c" if platform.system() != "Windows" else "-n"
        proc = subprocess.run(
            ["ping", flag, "1", "-W", "2", ip],
            capture_output=True, timeout=5,
        )
        return proc.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Получение conversation token
# ---------------------------------------------------------------------------

def fetch_conversation_token(music_token: str, device_id: str, device_platform: str) -> str:
    """Получает conversation token через Yandex Quasar API."""
    params = urllib.parse.urlencode({"device_id": device_id, "platform": device_platform})
    url = f"https://quasar.yandex.net/glagol/token?{params}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Oauth {music_token}")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        die(f"Failed to get conversation token: {e}")
    except json.JSONDecodeError as e:
        die(f"Invalid JSON in token response: {e}")

    token = data.get("token", "")
    if not token:
        die(f"Empty token in response: {data}")
    return token


# ---------------------------------------------------------------------------
# Построение JSON payload
# ---------------------------------------------------------------------------

def build_payload(text: str, conversation_token: str, dialog: bool = False) -> str:
    """Формирует JSON-сообщение для TTS через serverAction.

    dialog=True -> сценарий repeat_after_me (полное прерывание/пауза музыки).
    dialog=False -> repeat_phrase (приглушает музыку, не прерывает).
    """
    if dialog:
        # "Повтори за мной" — как настоящая голосовая команда Алисе:
        # ставит воспроизведение на паузу. Текст верхним регистром (fix_dialog_text).
        text = " ".join(w.upper() for w in text.split())
        form_name = "personal_assistant.scenarios.repeat_after_me"
        slot_name = "request"
    else:
        form_name = "personal_assistant.scenarios.quasar.iot.repeat_phrase"
        slot_name = "phrase_to_repeat"
    msg = {
        "conversationToken": conversation_token,
        "id": str(uuid.uuid4()),
        "payload": {
            "command": "serverAction",
            "serverActionEventPayload": {
                "type": "server_action",
                "name": "update_form",
                "payload": {
                    "form_update": {
                        "name": form_name,
                        "slots": [
                            {
                                "type": "string",
                                "name": slot_name,
                                "value": text,
                            }
                        ],
                    },
                    "resubmit": True,
                },
            },
        },
        "sentTime": int(time.time() * 1000),
    }
    return json.dumps(msg, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Команды колонки (пауза, громкость, состояние)
# ---------------------------------------------------------------------------

def _ws_cmd(station_ip: str, conversation_token: str, payload: dict) -> str:
    """Отправляет команду с conversationToken на колонку через Glagol WSS."""
    msg = json.dumps({
        "conversationToken": conversation_token,
        "id": str(uuid.uuid4()),
        "payload": payload,
        "sentTime": int(time.time() * 1000),
    })
    return ws_send_and_receive(station_ip, 1961, msg)


def get_volume(station_ip: str, conversation_token: str) -> float:
    """Читает текущую громкость колонки (0.0–1.0) через getState."""
    try:
        raw = _ws_cmd(station_ip, conversation_token, {"command": "getState"})
        data = json.loads(raw)
        return float(data["state"]["volume"])
    except Exception:
        return 0.5  # значение по умолчанию, если не смогли прочитать


def cmd_pause_music(station_ip: str, conversation_token: str) -> None:
    """Ставит музыку на паузу голосовой командой (sendText 'пауза')."""
    _ws_cmd(station_ip, conversation_token, {"command": "sendText", "text": "пауза"})


def cmd_resume_music(station_ip: str, conversation_token: str) -> None:
    """Возобновляет музыку (sendText 'продолжить')."""
    _ws_cmd(station_ip, conversation_token, {"command": "sendText", "text": "продолжить"})


def is_playing(station_ip: str, conversation_token: str) -> bool:
    """Проверяет, играет ли сейчас на колонке что-то (hasPause == True).

    Возвращает True, если есть активный плеер (музыка/радио/подкаст),
    False — если колонка в простое. По умолчанию False при ошибке чтения.
    """
    try:
        raw = _ws_cmd(station_ip, conversation_token, {"command": "getState"})
        data = json.loads(raw)
        return bool(data.get("state", {}).get("playerState", {}).get("hasPause"))
    except Exception:
        return False


def cmd_set_volume(station_ip: str, conversation_token: str, volume: float) -> None:
    """Устанавливает громкость (0.0–1.0)."""
    v = max(0.0, min(1.0, round(float(volume), 2)))
    _ws_cmd(station_ip, conversation_token, {"command": "setVolume", "volume": v})


def get_alice_state(station_ip: str, conversation_token: str) -> str:
    """Читает состояние Алисы (IDLE/SPEAKING/...)."""
    try:
        raw = _ws_cmd(station_ip, conversation_token, {"command": "getState"})
        data = json.loads(raw)
        return str(data.get("state", {}).get("aliceState", "")).upper()
    except Exception:
        return ""


def wait_until_idle(station_ip: str, conversation_token: str,
                    timeout: int = 60, poll: float = 0.5) -> bool:
    """Ждёт, пока Алиса закончит говорить (aliceState из NONE обратно в IDLE).

    Важно: колонка начинает говорить с задержкой после repeat_phrase, поэтому
    сначала ждём старта (идл-лаг), затем ловим переход NONE -> стабильный IDLE.
    Возвращает True, если озвучка завершилась; False по таймауту.
    """
    end = time.time() + timeout
    # 1) Пропускаем задержку старта озвучки — иначе увидим IDLE, хотя голос ещё не начался
    time.sleep(1.3)
    idle_ticks = 0
    while time.time() < end:
        state = get_alice_state(station_ip, conversation_token)
        if state == "IDLE":
            idle_ticks += 1
            # Требуем два последовательных IDLE (~1с стабильности), чтобы не
            # принять предстартовый IDLE/мигание NONE->IDLE за конец озвучки.
            if idle_ticks >= 2:
                return True
        else:
            idle_ticks = 0
        time.sleep(poll)
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _mdns_browse_all() -> dict[str, str]:
    """Один browse + batch resolve: возвращает {device_id: ip}."""
    if platform.system() != "Darwin" or not shutil.which("dns-sd"):
        return {}

    service_names = _mdns_browse_services()

    # Собираем device_id из имён сервисов (формат: YandexIOReceiver-DEVICE_ID)
    result: dict[str, str] = {}
    seen_ids: list[tuple[str, str]] = []  # (service_name, device_id)
    for instance in service_names:
        if instance.startswith("YandexIOReceiver-"):
            dev_id = instance[len("YandexIOReceiver-"):]
            seen_ids.append((instance, dev_id))

    # Resolve каждого через dns-sd -L + dns-sd -G
    for service_name, dev_id in seen_ids:
        hostname, _ = _mdns_lookup_service(service_name)
        if hostname:
            ip = _mdns_resolve_ip(hostname)
            if ip:
                result[dev_id] = ip

    return result


def _print_devices(devices: list[dict], discover: bool = False) -> None:
    """Выводит список устройств в читаемом формате."""
    if not devices:
        print("No devices found.")
        return
    ip_map: dict[str, str] = {}
    if discover:
        print("Scanning local network via mDNS...")
        ip_map = _mdns_browse_all()
    for d in devices:
        ip_info = ""
        if discover:
            ip = ip_map.get(d["id"])
            ip_info = f"  IP: {ip}" if ip else ""
        print(f"  {d['name']}  platform={d['platform']}  id={d['id']}{ip_info}")


def main() -> None:
    # Путь к .env (../.env относительно скрипта)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    conf_path = os.path.join(script_dir, "..", ".env")
    conf_path = os.path.normpath(conf_path)

    # Загрузка конфига
    env = load_env(conf_path)

    # --- CLI: --list-devices ---
    if "--list-devices" in sys.argv:
        if not env.get("MUSIC_TOKEN"):
            die(f"MUSIC_TOKEN not set in {conf_path}")
        print("Fetching device list...")
        devices = fetch_devices(env["MUSIC_TOKEN"])
        _print_devices(devices, discover=True)
        sys.exit(0)

    # --- CLI: --discover ---
    if "--discover" in sys.argv:
        if not env.get("DEVICE_ID"):
            die(f"DEVICE_ID not set in {conf_path}")
        print(f"Discovering IP for device {env['DEVICE_ID']} via mDNS...")
        ip = discover_station_ip(env["DEVICE_ID"])
        if ip:
            env["STATION_IP"] = ip
            save_env(conf_path, env)
            print(f"Found station IP: {ip} (saved to {conf_path})")
        else:
            die("Could not discover station IP via mDNS. "
                "Make sure you are on the same network and the station is online.")
        sys.exit(0)

    # --- Проверка обязательных параметров ---
    if not env.get("MUSIC_TOKEN"):
        die(f"MUSIC_TOKEN not set in {conf_path}")

    if not env.get("DEVICE_ID"):
        # Показываем список устройств, чтобы помочь пользователю
        print("DEVICE_ID is not set. Fetching available devices...", file=sys.stderr)
        devices = fetch_devices(env["MUSIC_TOKEN"])
        if devices:
            print("\nAvailable devices:", file=sys.stderr)
            _print_devices(devices)
        die(f"Set DEVICE_ID in {conf_path}")

    if not env.get("DEVICE_PLATFORM"):
        die(f"DEVICE_PLATFORM not set in {conf_path}")

    # --- Автообнаружение / проверка STATION_IP ---
    station_ip = env.get("STATION_IP", "")
    need_discover = False

    if not station_ip:
        need_discover = True
    elif not ping_host(station_ip):
        print(f"Station {station_ip} is not reachable, trying mDNS discovery...",
              file=sys.stderr)
        need_discover = True

    if need_discover:
        discovered_ip = discover_station_ip(env["DEVICE_ID"])
        if discovered_ip:
            print(f"Discovered station IP via mDNS: {discovered_ip}", file=sys.stderr)
            env["STATION_IP"] = discovered_ip
            save_env(conf_path, env)
            station_ip = discovered_ip
        else:
            if not station_ip:
                die(f"STATION_IP not set in {conf_path} and mDNS discovery failed. "
                    f"Use --discover or set STATION_IP manually.")
            else:
                # IP задан, но не пингуется и mDNS не помог — пробуем с тем что есть
                print(f"mDNS discovery failed, using configured IP {station_ip}",
                      file=sys.stderr)

    # --- Входной текст ---
    # Отфильтровываем CLI-флаги и значения флагов с аргументом (--volume <число>),
    # чтобы значение 0.8 не попадало в озвучиваемый текст.
    dialog = "--dialog" in sys.argv
    args: list[str] = []
    skip_next = False
    for a in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if a == "--volume":
            skip_next = True  # значение volume проглатываем
            continue
        if a.startswith("--"):
            continue
        args.append(a)
    text = " ".join(args)
    if not text:
        die(f"Usage: {sys.argv[0]} <text to speak>")

    text = clean_text(text)
    if not text:
        die("Text is empty after cleanup")

    # Управление токеном
    now = int(time.time())
    conversation_token = env.get("CONVERSATION_TOKEN", "")
    try:
        expires = int(env.get("CONVERSATION_TOKEN_EXPIRES", "0"))
    except ValueError:
        expires = 0

    if not conversation_token or expires <= now:
        conversation_token = fetch_conversation_token(
            env["MUSIC_TOKEN"], env["DEVICE_ID"], env["DEVICE_PLATFORM"]
        )
        # Токен валиден ~30 минут, обновляем через 25
        expires = now + 1500
        env["CONVERSATION_TOKEN"] = conversation_token
        env["CONVERSATION_TOKEN_EXPIRES"] = str(expires)
        save_env(conf_path, env)

    # Формируем и отправляем payload
    payload = build_payload(text, conversation_token, dialog=dialog)

    # Полный сценарий озвучки (если --pause и/или --volume):
    #   1. прочитать текущую громкость (для возврата)
    #   2. поставить музыку на паузу (если --pause)
    #   3. поднять громкость (если --volume)
    #   4. озвучить фразу
    #   5. продолжить музыку (если --pause)
    #   6. вернуть громкость (если --volume задан)
    pause = "--pause" in sys.argv
    volume = None
    if "--volume" in sys.argv:
        try:
            volume = float(sys.argv[sys.argv.index("--volume") + 1])
        except (ValueError, IndexError):
            die("Некорректное значение --volume (нужно число 0.0–1.0)")
    prev_volume = None
    was_playing = False

    if (pause or volume is not None):
        # читаем текущую громкость ДО паузы, чтобы вернуть её в конце
        try:
            prev_volume = get_volume(station_ip, conversation_token)
        except Exception as _e:
            print(f"WARNING: не удалось прочитать громкость: {_e}", file=sys.stderr)

    if pause:
        # запоминаем, играла ли музыка ДО паузы, чтобы в конце возобновлять
        # только если она реально играла (иначе «продолжить» стартует музыку
        # из простоя — баг: колонка включала радио, хотя до озвучки молчала).
        try:
            was_playing = is_playing(station_ip, conversation_token)
        except Exception as _e:
            print(f"WARNING: не удалось определить состояние музыки: {_e}", file=sys.stderr)
            was_playing = True  # консервативно: если не смогли — считаем что играла
        try:
            cmd_pause_music(station_ip, conversation_token)
        except Exception as _e:
            print(f"WARNING: не удалось поставить музыку на паузу: {_e}", file=sys.stderr)

    if volume is not None:
        try:
            cmd_set_volume(station_ip, conversation_token, volume)
        except Exception as _e:
            print(f"WARNING: не удалось поднять громкость: {_e}", file=sys.stderr)

    try:
        _response = ws_send_and_receive(station_ip, 1961, payload)
    except socket.timeout:
        die(f"Timeout connecting to station at {station_ip}:1961")
    except OSError as e:
        die(f"Connection to station failed: {e}")

    # Ждём, пока Алиса реально закончит говорить, прежде чем возвращать
    # музыку и громкость. Иначе "продолжить" и setVolume сработают мгновенно,
    # прервав длинную фразу (гонка таймингов).
    waited = wait_until_idle(station_ip, conversation_token, timeout=60)
    if not waited:
        print("WARNING: Алиса не вернулась в IDLE за 60с, продолжаем без ожидания",
              file=sys.stderr)

    # Сначала возвращаем прежнюю громкость, даём паузу 1с, и только потом
    # возобновляем музыку — чтобы не было резкого скачка громкости при старте.
    if volume is not None and prev_volume is not None:
        try:
            cmd_set_volume(station_ip, conversation_token, prev_volume)
        except Exception as _e:
            print(f"WARNING: не удалось вернуть громкость: {_e}", file=sys.stderr)

    if pause and was_playing:
        # пауза между возвратом громкости и возобновлением музыки
        time.sleep(1.0)
        try:
            cmd_resume_music(station_ip, conversation_token)
        except Exception as _e:
            print(f"WARNING: не удалось продолжить музыку: {_e}", file=sys.stderr)
    elif pause:
        # музыка ДО паузы не играла (колонка была в простое) — НЕ возобновляем,
        # иначе «продолжить» стартует радио/музыку из ничего.
        print("INFO: музыка не играла до озвучки — возобновление пропущено",
              file=sys.stderr)

    print("OK")


if __name__ == "__main__":
    main()
