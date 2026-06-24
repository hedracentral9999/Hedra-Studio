from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.adam_script_bot import (  # noqa: E402
    AdamScriptBot,
    BotConfig,
    CustomerMatch,
    Database,
    GeminiClient,
    PartnerStackClient,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self) -> dict:
        return self._payload


class FakePartnerStackSession:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, url, headers=None, params=None, timeout=None):  # noqa: ANN001
        self.calls += 1
        if self.calls == 1:
            return FakeResponse(
                200,
                {
                    "data": {
                        "has_more": True,
                        "items": [{"key": "cus_1", "email": "first@example.com"}],
                    }
                },
            )
        return FakeResponse(
            200,
            {
                "data": {
                    "has_more": False,
                    "items": [{"key": "cus_2", "email": "Target@Example.com"}],
                }
            },
        )


class FakeGeminiSession:
    def __init__(self) -> None:
        self.last_json = None

    def post(self, url, params=None, headers=None, json=None, timeout=None):  # noqa: ANN001
        self.last_json = json
        return FakeResponse(
            200,
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "[thoughtful] Kịch bản đã xử lý."}],
                        }
                    }
                ]
            },
        )


class FakeTelegram:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []
        self.documents: list[tuple[int, Path, str]] = []

    def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))

    def send_document(self, chat_id: int, path: Path, caption: str = "") -> None:
        self.documents.append((chat_id, path, caption))


class FakeGemini:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def enhance(self, script: str, system_prompt: str) -> str:
        self.calls.append((script, system_prompt))
        return "[thoughtful] Kịch bản đã xử lý."


class AdamScriptBotTests(unittest.TestCase):
    def test_partnerstack_finds_email_across_pages(self) -> None:
        client = PartnerStackClient(
            "api-key",
            max_pages=3,
            session=FakePartnerStackSession(),  # type: ignore[arg-type]
        )

        match = client.find_customer_by_email("target@example.com")

        self.assertIsInstance(match, CustomerMatch)
        self.assertEqual(match.key, "cus_2")
        self.assertEqual(match.email, "target@example.com")

    def test_gemini_uses_admin_prompt_as_system_instruction(self) -> None:
        session = FakeGeminiSession()
        client = GeminiClient("gemini-key", "gemini-3.1-flash-lite", session=session)  # type: ignore[arg-type]

        result = client.enhance("script input", "admin prompt")

        self.assertEqual(result, "[thoughtful] Kịch bản đã xử lý.")
        self.assertEqual(
            session.last_json["system_instruction"]["parts"][0]["text"],
            "admin prompt",
        )
        self.assertEqual(
            session.last_json["contents"][0]["parts"][0]["text"],
            "script input",
        )

    def test_database_tracks_prompt_and_daily_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "bot.sqlite3")
            db.init("initial prompt")
            db.upsert_user(123, "user", "First")

            self.assertEqual(db.get_setting("script_system_prompt"), "initial prompt")
            db.set_setting("script_system_prompt", "updated prompt")
            self.assertEqual(db.get_setting("script_system_prompt"), "updated prompt")

            self.assertEqual(db.usage_count(123, "2026-05-20"), 0)
            db.increment_usage(123, "2026-05-20")
            db.increment_usage(123, "2026-05-20")
            self.assertEqual(db.usage_count(123, "2026-05-20"), 2)
            db.close()

    def test_config_dataclass_can_hold_required_defaults(self) -> None:
        config = BotConfig(
            telegram_token="tg",
            admin_ids={1},
            partnerstack_api_key="ps",
            require_partnerstack=True,
            access_mode="verified",
            gemini_api_key="gm",
            gemini_model="gemini-3.1-flash-lite",
            elevenlabs_ref_link="https://try.elevenlabs.io/rinor1xaj4ze",
            db_path=Path("tools/adam_script_bot.sqlite3"),
            daily_user_quota=5,
            max_script_chars=5000,
            cooldown_seconds=30,
            poll_timeout=45,
            partnerstack_partner_key="",
            partnerstack_partnership_key="",
            partnerstack_max_pages=20,
            gemini_temperature=0.35,
            gemini_max_output_tokens=4000,
            initial_prompt="prompt",
        )

        self.assertEqual(config.daily_user_quota, 5)
        self.assertEqual(config.gemini_model, "gemini-3.1-flash-lite")

    def test_config_does_not_require_partnerstack_in_admin_only_mode(self) -> None:
        env = {
            "TELEGRAM_BOT_TOKEN": "tg",
            "TELEGRAM_ADMIN_IDS": "1",
            "GEMINI_API_KEY": "gm",
            "ACCESS_MODE": "admin_only",
            "REQUIRE_PARTNERSTACK": "false",
        }

        with patch.dict("os.environ", env, clear=True):
            config = BotConfig.from_env()

        self.assertEqual(config.access_mode, "admin_only")
        self.assertFalse(config.require_partnerstack)
        self.assertEqual(config.partnerstack_api_key, "")

    def test_admin_only_mode_allows_admin_to_generate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "bot.sqlite3")
            db.init("prompt")
            user = db.upsert_user(1, "admin", "Admin")
            telegram = FakeTelegram()
            gemini = FakeGemini()
            bot = AdamScriptBot(
                self._config(access_mode="admin_only"),
                db,
                telegram,  # type: ignore[arg-type]
                PartnerStackClient(""),
                gemini,  # type: ignore[arg-type]
            )

            bot.handle_script(99, 1, "shop ơi còn hàng không", user)

            self.assertEqual(len(gemini.calls), 1)
            self.assertIn("[thoughtful]", telegram.messages[-1][1])
            self.assertEqual(db.usage_count(1), 1)
            db.close()

    def test_admin_only_mode_blocks_non_admin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "bot.sqlite3")
            db.init("prompt")
            user = db.upsert_user(2, "user", "User")
            telegram = FakeTelegram()
            gemini = FakeGemini()
            bot = AdamScriptBot(
                self._config(access_mode="admin_only"),
                db,
                telegram,  # type: ignore[arg-type]
                PartnerStackClient(""),
                gemini,  # type: ignore[arg-type]
            )

            bot.handle_script(99, 2, "shop ơi còn hàng không", user)

            self.assertEqual(len(gemini.calls), 0)
            self.assertIn("test nội bộ", telegram.messages[-1][1])
            db.close()

    def test_verify_is_disabled_when_not_using_partnerstack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "bot.sqlite3")
            db.init("prompt")
            telegram = FakeTelegram()
            bot = AdamScriptBot(
                self._config(access_mode="admin_only", require_partnerstack=False),
                db,
                telegram,  # type: ignore[arg-type]
                PartnerStackClient(""),
                FakeGemini(),  # type: ignore[arg-type]
            )

            bot.verify_user(99, 1, "a@example.com")

            self.assertIn("tạm tắt", telegram.messages[-1][1])
            db.close()

    def test_multiline_commands_are_handled_individually(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "bot.sqlite3")
            db.init("prompt")
            telegram = FakeTelegram()
            bot = AdamScriptBot(
                self._config(access_mode="admin_only", require_partnerstack=False),
                db,
                telegram,  # type: ignore[arg-type]
                PartnerStackClient(""),
                FakeGemini(),  # type: ignore[arg-type]
            )

            bot.handle_update(
                {
                    "message": {
                        "chat": {"id": 99},
                        "from": {"id": 1, "username": "admin", "first_name": "Admin"},
                        "text": "/start\n/id",
                    }
                }
            )

            self.assertGreaterEqual(len(telegram.messages), 2)
            self.assertIn("Bot chuyển kịch bản", telegram.messages[0][1])
            self.assertIn("user_id=1", telegram.messages[1][1])
            db.close()

    def _config(self, access_mode: str = "verified", require_partnerstack: bool = True) -> BotConfig:
        return BotConfig(
            telegram_token="tg",
            admin_ids={1},
            partnerstack_api_key="ps" if require_partnerstack else "",
            require_partnerstack=require_partnerstack,
            access_mode=access_mode,
            gemini_api_key="gm",
            gemini_model="gemini-3.1-flash-lite",
            elevenlabs_ref_link="https://try.elevenlabs.io/rinor1xaj4ze",
            db_path=Path("tools/adam_script_bot.sqlite3"),
            daily_user_quota=5,
            max_script_chars=5000,
            cooldown_seconds=0,
            poll_timeout=45,
            partnerstack_partner_key="",
            partnerstack_partnership_key="",
            partnerstack_max_pages=20,
            gemini_temperature=0.35,
            gemini_max_output_tokens=4000,
            initial_prompt="prompt",
        )


if __name__ == "__main__":
    unittest.main()
