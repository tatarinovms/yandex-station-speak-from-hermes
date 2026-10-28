import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class InstallerTests(unittest.TestCase):
    def test_installs_hermes_skill_and_protects_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            hermes_home = home / ".hermes-test"
            home.mkdir()
            env = os.environ | {
                "HOME": str(home),
                "HERMES_HOME": str(hermes_home),
                "YSS_SKIP_AUTH_DEPS": "1",
            }

            result = subprocess.run(
                ["bash", str(ROOT / "install.sh")],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("получение MUSIC_TOKEN пропущено", result.stdout)
            self.assertNotIn(".token-venv/bin/python", result.stdout)
            dest = hermes_home / "skills/smart-home/yandex-station-speak"
            self.assertTrue((dest / "scripts/tts_dialog.py").is_file())
            self.assertTrue((dest / "get_music_token.py").is_file())
            self.assertTrue((dest / "command.sh").is_file())
            self.assertEqual(stat.S_IMODE((dest / ".env").stat().st_mode), 0o600)
            self.assertFalse((dest / ".git").exists())

            (dest / "scripts/tts_dialog.py").write_text(
                "import sys\nprint('ARGS=' + '|'.join(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            speak = subprocess.run(
                [str(dest / "speak.sh"), "тестовая фраза"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(speak.returncode, 0, speak.stdout + speak.stderr)
            self.assertIn("OK: фраза отправлена", speak.stdout)

            (dest / "scripts/tts_dialog.py").write_text(
                "import sys\nraise SystemExit(0 if sys.argv[1:] == ['--command', 'Выключи свет'] else 3)\n",
                encoding="utf-8",
            )
            command = subprocess.run(
                [str(dest / "command.sh"), "Выключи свет"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(command.returncode, 0, command.stdout + command.stderr)
            self.assertIn("OK: команда отправлена", command.stdout)

            command_file = Path(tmp) / "alice-command.txt"
            command_file.write_text("Включи свет'; touch /tmp/nope; #", encoding="utf-8")
            (dest / "scripts/tts_dialog.py").write_text(
                "import sys\nraise SystemExit(0 if sys.argv[1:] == ['--command-file', sys.argv[2]] else 3)\n",
                encoding="utf-8",
            )
            command = subprocess.run(
                [str(dest / "command.sh"), "--file", str(command_file)],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(command.returncode, 0, command.stdout + command.stderr)

    def test_preserves_existing_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            hermes_home = home / ".hermes-test"
            dest = hermes_home / "skills/smart-home/yandex-station-speak"
            dest.mkdir(parents=True)
            (dest / ".env").write_text("MUSIC_TOKEN=keep-me\n", encoding="utf-8")
            env = os.environ | {
                "HOME": str(home),
                "HERMES_HOME": str(hermes_home),
                "YSS_SKIP_AUTH_DEPS": "1",
            }

            result = subprocess.run(
                ["bash", str(ROOT / "install.sh")],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                (dest / ".env").read_text(encoding="utf-8"),
                "MUSIC_TOKEN=keep-me\n",
            )


if __name__ == "__main__":
    unittest.main()
