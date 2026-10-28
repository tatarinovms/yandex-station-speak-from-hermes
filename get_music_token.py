#!/usr/bin/env python3
"""Получить MUSIC_TOKEN через Yandex OAuth Device Flow и записать в .env."""

import asyncio
import os
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
ENV_PATH = SKILL_DIR / ".env"


def put_env_value(path: Path, key: str, value: str) -> None:
    """Атомарно обновляет .env, не создавая секрет с широкими правами."""
    if path.is_symlink():
        raise ValueError(f"Refusing to write .env through a symbolic link: {path}")
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    prefix = f"{key}="
    result = []
    replaced = False
    for line in lines:
        if line.startswith(prefix):
            result.append(prefix + value)
            replaced = True
        else:
            result.append(line)
    if not replaced:
        result.append(prefix + value)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(result) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


async def main() -> None:
    try:
        from ya_passport_auth import PassportClient
    except ImportError:
        raise SystemExit(
            "Не найден ya-passport-auth. Запустите ./install.sh или установите "
            "зависимости командой: python3 -m pip install ya-passport-auth"
        )

    def show_code(session) -> None:
        print("\n1. Откройте в браузере:")
        print(session.verification_url)
        print("2. Войдите в аккаунт Яндекса, к которому привязана Станция.")
        print(f"3. Введите код: {session.user_code}")
        print("4. Подтвердите вход. Ожидание продолжится автоматически.\n")

    async with PassportClient.create() as client:
        credentials = await client.login_device_code(on_code=show_code)

    put_env_value(ENV_PATH, "MUSIC_TOKEN", credentials.music_token.get_secret())
    print(f"MUSIC_TOKEN сохранён в {ENV_PATH} (права 0600).")
    print("Следующий шаг: python3 scripts/tts_dialog.py --list-devices")


if __name__ == "__main__":
    asyncio.run(main())
