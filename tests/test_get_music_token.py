import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "get_music_token.py"
spec = importlib.util.spec_from_file_location("get_music_token", MODULE_PATH)
assert spec is not None and spec.loader is not None
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class EnvWriterTests(unittest.TestCase):
    def test_replaces_token_without_changing_other_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("MUSIC_TOKEN=old\nDEVICE_ID=device-1\n", encoding="utf-8")

            helper.put_env_value(path, "MUSIC_TOKEN", "new-token")

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "MUSIC_TOKEN=new-token\nDEVICE_ID=device-1\n",
            )
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_adds_missing_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("DEVICE_ID=device-1\n", encoding="utf-8")

            helper.put_env_value(path, "MUSIC_TOKEN", "new-token")

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "DEVICE_ID=device-1\nMUSIC_TOKEN=new-token\n",
            )

    def test_rejects_symlink_env_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.write_text("MUSIC_TOKEN=old\n", encoding="utf-8")
            path = Path(tmp) / ".env"
            path.symlink_to(target)

            with self.assertRaisesRegex(ValueError, "symbolic link"):
                helper.put_env_value(path, "MUSIC_TOKEN", "new-token")

            self.assertEqual(target.read_text(encoding="utf-8"), "MUSIC_TOKEN=old\n")


if __name__ == "__main__":
    unittest.main()
