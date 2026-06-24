import unittest
from unittest.mock import patch

from app_workers import (
    DEFAULT_DEEPSEEK_TTS_MODEL,
    PromptGeneratorWorker,
    SuggestAnswersWorker,
    Worker,
    _normalise_deepseek_tts_model,
)


class _Response:
    status_code = 200
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class TTSModelTests(unittest.TestCase):
    def test_model_defaults_to_flash_and_rejects_unknown_values(self):
        self.assertEqual(DEFAULT_DEEPSEEK_TTS_MODEL, "deepseek-v4-flash")
        self.assertEqual(_normalise_deepseek_tts_model(None), "deepseek-v4-flash")
        self.assertEqual(_normalise_deepseek_tts_model("unknown"), "deepseek-v4-flash")
        self.assertEqual(_normalise_deepseek_tts_model("deepseek-v4-pro"), "deepseek-v4-pro")

    @patch("app_workers.read_style_prompt_file", return_value="Style prompt")
    @patch("app_workers.requests.post")
    def test_enhance_uses_selected_model(self, post, _read_prompt):
        post.return_value = _Response({
            "choices": [{"message": {"content": "Đã xử lý"}}],
        })
        worker = Worker("Nội dung", 1.0, "test", {
            "ds_api_key": "test-key",
            "deepseek_tts_model": "deepseek-v4-pro",
            "enhance_style_name": "Test",
            "enhance_prompt": "Style prompt",
            "eleven_v3_style_enabled": False,
        })

        self.assertEqual(worker._enhance("Nội dung"), "Đã xử lý")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "deepseek-v4-pro")

    @patch("app_workers.requests.post")
    def test_prompt_tools_use_selected_model(self, post):
        post.side_effect = [
            _Response({"choices": [{"message": {"content": "Prompt"}}]}),
            _Response({"choices": [{"message": {"content": "{\"purpose\": \"Bán hàng\"}"}}]}),
        ]
        prompt_results = []
        prompt_worker = PromptGeneratorWorker(
            "Sản phẩm/lĩnh vực: Test",
            "test-key",
            deepseek_model="deepseek-v4-pro",
        )
        prompt_worker.done.connect(prompt_results.append)
        prompt_worker.run()

        suggestion_results = []
        suggestion_worker = SuggestAnswersWorker(
            "Shop",
            "test-key",
            deepseek_model="deepseek-v4-flash",
        )
        suggestion_worker.done.connect(suggestion_results.append)
        suggestion_worker.run()

        self.assertEqual(prompt_results, ["Prompt"])
        self.assertEqual(suggestion_results, [{"purpose": "Bán hàng"}])
        self.assertEqual(post.call_args_list[0].kwargs["json"]["model"], "deepseek-v4-pro")
        self.assertEqual(post.call_args_list[1].kwargs["json"]["model"], "deepseek-v4-flash")


if __name__ == "__main__":
    unittest.main()
