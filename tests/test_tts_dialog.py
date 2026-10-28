import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "tts_dialog.py"
spec = importlib.util.spec_from_file_location("tts_dialog", MODULE_PATH)
tts = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(tts)


class AudioCycleTests(unittest.TestCase):
    def test_save_env_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.write_text("MUSIC_TOKEN=keep\n", encoding="utf-8")
            path = Path(tmp) / ".env"
            path.symlink_to(target)

            with self.assertRaisesRegex(ValueError, "symbolic link"):
                tts.save_env(str(path), {"MUSIC_TOKEN": "replace"})

            self.assertEqual(target.read_text(encoding="utf-8"), "MUSIC_TOKEN=keep\n")

    def test_save_env_writes_with_mode_0600(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            tts.save_env(str(path), {"MUSIC_TOKEN": "token"})

            self.assertEqual(path.read_text(encoding="utf-8"), "MUSIC_TOKEN=token\n")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_get_alice_state_propagates_get_state_failure(self):
        with patch.object(tts, "_ws_cmd", side_effect=OSError("getState failed")):
            with self.assertRaisesRegex(OSError, "getState failed"):
                tts.get_alice_state("192.168.0.101", "token")

    def test_get_volume_propagates_get_state_failure(self):
        with patch.object(tts, "_ws_cmd", side_effect=OSError("getState failed")):
            with self.assertRaisesRegex(OSError, "getState failed"):
                tts.get_volume("192.168.0.101", "token")

    def test_is_playing_propagates_get_state_failure(self):
        with patch.object(tts, "_ws_cmd", side_effect=OSError("getState failed")):
            with self.assertRaisesRegex(OSError, "getState failed"):
                tts.is_playing("192.168.0.101", "token")

    def test_aborts_before_changes_when_original_volume_is_unknown(self):
        with (
            patch.object(tts, "get_volume", side_effect=OSError("getState failed")),
            patch.object(tts, "cmd_pause_music") as pause_music,
            patch.object(tts, "cmd_set_volume") as set_volume,
            patch.object(tts, "ws_send_and_receive") as send,
        ):
            with self.assertRaisesRegex(OSError, "getState failed"):
                tts.run_audio_cycle(
                    "192.168.0.101", "token", "payload", pause=True, volume=0.8
                )

        pause_music.assert_not_called()
        set_volume.assert_not_called()
        send.assert_not_called()

    def test_aborts_before_pause_when_player_state_is_unknown(self):
        with (
            patch.object(tts, "get_volume", return_value=0.3),
            patch.object(tts, "is_playing", side_effect=OSError("getState failed")),
            patch.object(tts, "cmd_pause_music") as pause_music,
            patch.object(tts, "cmd_set_volume") as set_volume,
            patch.object(tts, "ws_send_and_receive") as send,
        ):
            with self.assertRaisesRegex(OSError, "getState failed"):
                tts.run_audio_cycle(
                    "192.168.0.101", "token", "payload", pause=True, volume=0.8
                )

        pause_music.assert_not_called()
        set_volume.assert_not_called()
        send.assert_not_called()

    def test_restores_volume_and_music_when_speech_send_fails(self):
        events = []

        with (
            patch.object(tts, "get_volume", return_value=0.3),
            patch.object(tts, "is_playing", return_value=True),
            patch.object(tts, "cmd_pause_music", side_effect=lambda *_: events.append("pause")),
            patch.object(tts, "cmd_set_volume", side_effect=lambda *args: events.append(("volume", args[-1]))),
            patch.object(tts, "ws_send_and_receive", side_effect=OSError("send failed")),
            patch.object(tts, "cmd_resume_music", side_effect=lambda *_: events.append("resume")),
            patch.object(tts.time, "sleep"),
        ):
            with self.assertRaisesRegex(OSError, "send failed"):
                tts.run_audio_cycle("192.168.0.101", "token", "payload", pause=True, volume=0.8)

        self.assertEqual(
            events,
            ["pause", ("volume", 0.8), ("volume", 0.3), "resume"],
        )

    def test_does_not_resume_music_that_was_not_playing(self):
        with (
            patch.object(tts, "get_volume", return_value=0.3),
            patch.object(tts, "is_playing", return_value=False),
            patch.object(tts, "cmd_pause_music"),
            patch.object(tts, "cmd_set_volume"),
            patch.object(tts, "ws_send_and_receive", return_value="{}"),
            patch.object(tts, "wait_until_idle", return_value=True),
            patch.object(tts, "cmd_resume_music") as resume,
        ):
            tts.run_audio_cycle("192.168.0.101", "token", "payload", pause=True, volume=0.8)

        resume.assert_not_called()


if __name__ == "__main__":
    unittest.main()
