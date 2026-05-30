from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_utils import (  # noqa: E402
    DEFAULT_OUT,
    LEGACY_DEFAULT_OUT,
    _default_settings,
    _normalize_output_dir,
    is_auto_video_unlocked,
    is_chat_script_unlocked,
    is_feature_unlocked,
    validate_pro_license_key,
)
from auto_video_workers import (  # noqa: E402
    OneShotBatchWorker,
    OneShotRenderWorker,
    _auto_batch_concurrency,
    _best_rule_thumbnail_title,
    _build_upload_metadata,
    _clean_thumbnail_title,
    _draw_boxphonefarm_thumbnail,
    _estimate_ai_cost,
    _estimate_gemini_cost,
    _file_slug,
    _fallback_thumbnail_title,
    _thumbnail_lines_for_mode,
    _split_thumbnail_lines,
    _sum_ai_costs_by_kind,
    _thumbnail_output_path,
    _upload_video_output_path,
    _thumbnail_title_quality,
    _pick_best_thumbnail_title,
    _is_weak_thumbnail_title,
    _one_shot_final_status,
    _one_shot_metadata_plan,
    _one_shot_render_profile,
    _thumbnail_layout_quality,
    _thumbnail_review_gate,
    _thumbnail_render_title,
    _parse_thumbnail_title_payload,
    _parse_thumbnail_title_response,
    _video_file_title,
    _video_output_path,
    escbase_create_project,
    escbase_dependency_status,
    escbase_root,
    escbase_script_lines,
    escbase_template_status,
)


class OneShotHelperTests(unittest.TestCase):
    def test_pro_license_cache_unlocks_only_allowed_features(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        settings = {
            "pro_license_cache": {
                "valid": True,
                "features": ["chat_script"],
                "checked_at": now,
            }
        }
        with patch.dict(os.environ, {
            "HEDRA_PRO_UNLOCK": "",
            "HEDRA_CHAT_SCRIPT_UNLOCK": "",
            "HEDRA_AUTO_VIDEO_UNLOCK": "",
        }):
            self.assertTrue(is_chat_script_unlocked(settings))
            self.assertFalse(is_auto_video_unlocked(settings))

            settings["pro_license_cache"]["features"] = ["all"]
            self.assertTrue(is_chat_script_unlocked(settings))
            self.assertTrue(is_auto_video_unlocked(settings))

    def test_pro_license_cache_expires_after_grace_window(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        settings = {
            "pro_license_cache": {
                "valid": True,
                "features": ["auto_video"],
                "checked_at": old,
            }
        }
        with patch.dict(os.environ, {
            "HEDRA_PRO_UNLOCK": "",
            "HEDRA_AUTO_VIDEO_UNLOCK": "",
        }):
            self.assertFalse(is_feature_unlocked(settings, "auto_video"))

    def test_validate_pro_license_requires_requested_feature(self) -> None:
        class _Response:
            status_code = 200

            def json(self):
                return {
                    "valid": True,
                    "features": ["chat_script"],
                    "message": "OK",
                }

        with patch("app_utils.requests.post", return_value=_Response()):
            ok, msg, cache = validate_pro_license_key("PRO-123", "auto_video")

        self.assertFalse(ok)
        self.assertIn("chưa mở tính năng auto_video", msg)
        self.assertTrue(cache["valid"])
        self.assertEqual(set(cache["features"]), {"chat_script"})

    def test_validate_pro_license_reports_server_offline_without_unlock(self) -> None:
        requests = __import__("requests")
        with patch("app_utils.requests.post", side_effect=requests.Timeout("timeout")):
            ok, msg, cache = validate_pro_license_key("PRO-123", "auto_video")

        self.assertFalse(ok)
        self.assertIn("Không kiểm tra được key", msg)
        self.assertEqual(cache, {})

    def test_glossary_corrections_keep_tech_terms(self) -> None:
        self.assertEqual(
            _clean_thumbnail_title("hấp samsung dex 4k 120hz ngon bổ rẻ"),
            "HUB SAMSUNG DEX 4K 120HZ NGON BỔ RẺ",
        )
        self.assertEqual(
            _split_thumbnail_lines("HUB SAMSUNG DEX 4K 120HZ NGON BỔ RẺ"),
            ["HUB", "SAMSUNG DEX 4K", "120HZ NGON BỔ RẺ"],
        )
        self.assertEqual(
            _clean_thumbnail_title("pocket bar vẫn quá tuyệt vời 2025"),
            "POCKET 3 VẪN QUÁ TUYỆT VỜI 2025",
        )
        self.assertEqual(
            _clean_thumbnail_title("tu vit xiaomi sửa điện thoại cực đã"),
            "TUA VÍT XIAOMI SỬA ĐIỆN THOẠI CỰC ĐÃ",
        )
        self.assertEqual(_clean_thumbnail_title("sét play samsung deck"), "CH PLAY SAMSUNG DEX")
        self.assertEqual(_clean_thumbnail_title("hub type c cho samsung dex"), "HUB TYPE-C CHO SAMSUNG DEX")
        self.assertEqual(_clean_thumbnail_title("sạc nhanh 27w cho iphone"), "SẠC NHANH 27W CHO IPHONE")
        self.assertEqual(_clean_thumbnail_title("thanh toán mô mô bằng viet qr"), "THANH TOÁN MOMO BẰNG VIETQR")
        self.assertEqual(_clean_thumbnail_title("zalo pay và shopee pay"), "ZALOPAY VÀ SHOPEEPAY")
        self.assertEqual(_clean_thumbnail_title("caption full anh em xem nè sợi cáp hdmi"), "ANH EM XEM NÈ SỢI CÁP HDMI")
        self.assertEqual(_clean_thumbnail_title("hashtags samsung dex hubdex xạcnhanh"), "SAMSUNG DEX HUB DEX SẠC NHANH")
        self.assertEqual(_clean_thumbnail_title("cắp hdmi 2.0 giá rẻ cho samsung deck"), "CÁP HDMI 2.0 GIÁ RẺ CHO SAMSUNG DEX")
        self.assertEqual(_clean_thumbnail_title("máy cạo dâu sạc taxi tiện lợi"), "MÁY CẠO RÂU SẠC TYPE-C TIỆN LỢI")
        self.assertEqual(_clean_thumbnail_title("rắc 100w 8k cho samsung dex gọn gàng"), "JACK 100W 8K CHO SAMSUNG DEX GỌN GÀNG")

    def test_phrase_aware_line_splits(self) -> None:
        cases = {
            "HDMI 4K SAMSUNG DEX CHỈ 80K": ["HDMI 4K", "SAMSUNG DEX", "CHỈ 80K"],
            "SẠC NHANH 27W CHO IPHONE": ["SẠC NHANH", "27W", "CHO IPHONE"],
            "HUB TYPE-C CHO SAMSUNG DEX": ["HUB TYPE-C", "CHO SAMSUNG DEX"],
            "MUA HUB SAMSUNG DEX NHỚ KIỂM TRA 4K": ["MUA HUB", "SAMSUNG DEX", "NHỚ KIỂM TRA 4K"],
            "JACK 100W 8K CHO SAMSUNG DEX GỌN GÀNG": ["JACK 100W 8K", "CHO SAMSUNG DEX", "GỌN GÀNG"],
            "HỘP CHIA ĐỒ CHO THỢ SỬA GỌN GÀNG": ["HỘP CHIA", "ĐỒ CHO THỢ", "SỬA GỌN GÀNG"],
            "KHỞI ĐỘNG LẠI SAMSUNG DEX BỊ ĐƠ": ["KHỞI ĐỘNG LẠI", "SAMSUNG DEX", "BỊ ĐƠ"],
            "SETUP SAMSUNG DEX DỄ HƠN": ["SETUP", "SAMSUNG DEX", "DỄ HƠN"],
            "LOA MOMO CÓ SIM 4G": ["LOA MOMO", "CÓ SIM 4G"],
            "USB 2TB ĐỪNG LÀM Ổ CHÍNH": ["USB 2TB", "ĐỪNG LÀM Ổ CHÍNH"],
            "USB GIÁ RẺ CHỈ DÙNG TẠM": ["USB GIÁ RẺ", "CHỈ DÙNG TẠM"],
            "HDMI 2.0 4K120 CHÍNH HÃNG": ["HDMI 2.0", "4K 120HZ", "CHÍNH HÃNG"],
            "POCKET 3 VẪN QUÁ TUYỆT VỜI 2025": ["POCKET 3", "VẪN QUÁ TUYỆT VỜI", "2025"],
            "TUA VÍT XIAOMI SỬA ĐIỆN THOẠI CỰC ĐÃ": ["TUA VÍT", "XIAOMI SỬA", "ĐIỆN THOẠI CỰC ĐÃ"],
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(_split_thumbnail_lines(title), expected)

    def test_caption_friendly_mp4_and_thumbnail_slug(self) -> None:
        out_dir = Path("/tmp")
        source_stem = "DJI_20260523100432_0012_D"
        title = "HDMI 4K SAMSUNG DEX CHỈ 80K"

        self.assertEqual(
            _video_output_path(out_dir, source_stem, title).name,
            "HDMI 4K Samsung Dex Chỉ 80K 0012.mp4",
        )
        meta = _build_upload_metadata(title, source_stem, [{"text": "HDMI 4K Samsung Dex chỉ 80k"}])
        self.assertEqual(
            _upload_video_output_path(out_dir, source_stem, meta).name,
            "HDMI 4K Samsung Dex Chỉ 80K #SamsungDex #DayHDMI #LamViecDiDong.mp4",
        )
        self.assertEqual(
            _thumbnail_output_path(out_dir, source_stem, title).name,
            "hdmi_4k_samsung_dex_chi_80k_0012_thumbnail.png",
        )
        self.assertLessEqual(len(_file_slug(title, max_len=80)), 80)

    def test_upload_title_keeps_industry_canonical_terms(self) -> None:
        self.assertEqual(_video_file_title("LOA MOMO CÓ SIM 4G"), "Loa MoMo Có SIM 4G")
        self.assertEqual(_video_file_title("SETUP SAMSUNG DEX DỄ HƠN"), "Setup Samsung Dex Dễ Hơn")
        self.assertEqual(_video_file_title("USB 2TB ĐỪNG LÀM Ổ CHÍNH"), "USB 2TB Đừng Làm Ổ Chính")
        self.assertEqual(_video_file_title("HDMI 2.0 4K120 CHÍNH HÃNG"), "HDMI 2.0 4K 120Hz Chính Hãng")

    def test_auto_batch_concurrency_caps_by_cpu_and_total(self) -> None:
        with patch("auto_video_workers.os.cpu_count", return_value=12):
            self.assertEqual(_auto_batch_concurrency(15), 1)
            self.assertEqual(_auto_batch_concurrency(2), 1)
        with patch("auto_video_workers.os.cpu_count", return_value=8):
            self.assertEqual(_auto_batch_concurrency(15), 1)
        with patch("auto_video_workers.os.cpu_count", return_value=4):
            self.assertEqual(_auto_batch_concurrency(15), 1)
        self.assertEqual(_auto_batch_concurrency(0), 0)

    def test_one_shot_settings_defaults_include_new_keys(self) -> None:
        settings = _default_settings()
        self.assertIn("one_shot_ai_review_thumbnail", settings)
        self.assertIn("one_shot_last_video_dir", settings)
        self.assertIn("one_shot_last_batch_dir", settings)
        self.assertIn("one_shot_last_lut_dir", settings)
        self.assertIs(settings["one_shot_ai_review_thumbnail"], True)
        self.assertEqual(settings["one_shot_thumbnail_size"], "large")
        self.assertEqual(settings["one_shot_thumbnail_lines"], "auto")
        self.assertEqual(settings["one_shot_thumbnail_position"], "center")
        self.assertEqual(settings["one_shot_thumbnail_title_mode"], "expert")
        self.assertEqual(settings["one_shot_render_profile"], "multi_1080")
        self.assertEqual(settings["one_shot_industry"], "tech")
        self.assertEqual(settings["output_dir"], DEFAULT_OUT)
        self.assertEqual(_normalize_output_dir(LEGACY_DEFAULT_OUT), DEFAULT_OUT)

    def test_one_shot_render_profiles_are_explicit(self) -> None:
        self.assertEqual(_one_shot_render_profile("multi_1080")["width"], 1080)
        self.assertEqual(_one_shot_render_profile("sharp_1440")["height"], 2560)
        self.assertEqual(_one_shot_render_profile("source", {"width": 1728, "height": 3072})["width"], 1728)

    def test_manual_thumbnail_line_modes_set_requested_line_count(self) -> None:
        title = "LÊN ĐƠN BOX SAMSUNG DEX S20 SHIP HỎA TỐC CÓ GIÁ 1900K"
        self.assertEqual(len(_thumbnail_lines_for_mode(title, "2")), 2)
        self.assertEqual(len(_thumbnail_lines_for_mode(title, "3")), 3)
        self.assertEqual(_thumbnail_lines_for_mode("HDMI 4K SAMSUNG DEX CHỈ 80K", "auto"), [
            "HDMI 4K", "SAMSUNG DEX", "CHỈ 80K",
        ])

    def test_thumbnail_render_uses_uniform_font_size_and_keeps_terms(self) -> None:
        from PyQt6.QtGui import QColor, QImage
        from PyQt6.QtWidgets import QApplication

        _app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            frame = Path(tmp) / "frame.png"
            out = Path(tmp) / "thumbnail.png"
            img = QImage(1080, 1920, QImage.Format.Format_RGB32)
            img.fill(QColor("#777777"))
            self.assertTrue(img.save(str(frame)))

            for title in [
                "HUB 511 GIÚP LÊN SAMSUNG DEX DỄ HƠN",
                "MUA HUB SAMSUNG DEX NHỚ KIỂM TRA 4K",
                "SETUP SAMSUNG DEX DỄ HƠN",
                "RẮC 100W 8K CHO SAMSUNG DEX GỌN GÀNG",
                "HỘP CHIA ĐỒ CHO THỢ SỬA GỌN GÀNG",
                "USB 2TB ĐỪNG LÀM Ổ CHÍNH",
                "HDMI 2.0 4K120 CHÍNH HÃNG",
                "ĐÃ CÓ SẴN MÁY CÓ THỂ MUA BOX KHÔNG VỀ TỰ LẮP ĐƯỢC KHÔNG",
            ]:
                with self.subTest(title=title):
                    meta = _draw_boxphonefarm_thumbnail(frame, out, title)
                    sizes = meta["font_size_by_line"]
                    self.assertGreaterEqual(len(sizes), 2)
                    self.assertEqual(len(set(sizes)), 1)
                    self.assertEqual(meta["uniform_font_size"], sizes[0])
                    self.assertEqual(meta["text_render_engine"], "pillow_freetype_stroke")
                    self.assertGreater(meta["layout_score"], 0)
                    self.assertLessEqual(max(meta["line_widths"]), meta["safe_zone"]["right"] - meta["safe_zone"]["left"])
                    self.assertEqual(_thumbnail_layout_quality(meta)["label"], "OK")
                    joined = " / ".join(meta["lines"])
                    self.assertNotIn("SAMSUNG / DEX", joined)
                    self.assertNotIn("KIỂM / TRA", joined)
                    self.assertNotIn("GỌN / GÀNG", joined)
                    self.assertNotIn("DỄ / HƠN", joined)
                    self.assertNotIn("TỰ / LẮP", joined)
                    self.assertNotIn("ĐỪNG LÀM / Ổ CHÍNH", joined)
                    self.assertNotIn("HDMI 2.0 4K 120HZ", joined)

    def test_thumbnail_render_uses_vietnamese_safe_text_engine(self) -> None:
        from PyQt6.QtGui import QColor, QImage
        from PyQt6.QtWidgets import QApplication

        _app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            frame = Path(tmp) / "frame.png"
            out = Path(tmp) / "thumbnail.png"
            img = QImage(1080, 1920, QImage.Format.Format_RGB32)
            img.fill(QColor("#d7d7d7"))
            self.assertTrue(img.save(str(frame)))

            meta = _draw_boxphonefarm_thumbnail(
                frame,
                out,
                "CÁP HDMI GIÁ RẺ HỖ TRỢ 4K 120HZ",
                font_key="arial_black",
            )
            self.assertTrue(out.exists())
            self.assertEqual(meta["text_render_engine"], "pillow_freetype_stroke")
            joined = " ".join(meta["lines"])
            self.assertIn("CÁP", joined)
            self.assertIn("RẺ", joined)

    def test_thumbnail_render_title_shortens_long_grid_copy(self) -> None:
        render_title, info = _thumbnail_render_title(
            "ĐÃ CÓ SẴN MÁY CÓ THỂ MUA BOX KHÔNG VỀ TỰ LẮP ĐƯỢC KHÔNG"
        )

        self.assertEqual(render_title, "MUA BOX CÓ SẴN HAY TỰ LẮP")
        self.assertTrue(info["changed"])
        self.assertIn("rút gọn", " ".join(info["reasons"]))

    def test_thumbnail_title_quality_rejects_filenames_and_unsupported_claims(self) -> None:
        segments = [{"text": "Mình test hub Type-C cho Samsung Dex, cắm màn hình và sạc rất tiện."}]
        context = " ".join(seg["text"] for seg in segments)
        self.assertTrue(_is_weak_thumbnail_title("DJI 20260527165018 0073 D MP4", context))
        self.assertTrue(_is_weak_thumbnail_title("HUB 999K CHO SAMSUNG DEX", context))
        self.assertFalse(_is_weak_thumbnail_title("JACK 100W 8K CHO SAMSUNG DEX", "Jack 100W 8K cho Samsung Dex gọn gàng"))
        quality = _thumbnail_title_quality("HUB TYPE-C CHO SAMSUNG DEX", "DJI_0073_D", segments)
        self.assertEqual(quality["status"], "expert_checked")
        self.assertEqual(quality["publish_label"], "Đăng được ngay")

    def test_ai_candidate_picker_ignores_bad_titles(self) -> None:
        segments = [{"text": "Sạc nhanh 27W cho iPhone chỉ cần một sợi dây gọn hơn."}]
        picked = _pick_best_thumbnail_title(
            [
                "DJI 20260527165018 0073 D",
                "Sản phẩm hay",
                "Sạc nhanh 27W cho iPhone",
            ],
            "DJI_0073_D",
            segments,
        )
        self.assertEqual(picked, "SẠC NHANH 27W CHO IPHONE")

    def test_rule_title_repairs_hdmi_viewer_filler_fallback(self) -> None:
        segments = [
            {"start": 7.76, "end": 11.76, "text": "Đây nè xem nhá, nhận 4K, 120 hãng Z luôn"},
            {"start": 11.76, "end": 14.76, "text": "Và đây là 1 sợi dây HDMI giả rẻ của chính hành O-Kring"},
            {"start": 17.76, "end": 21.76, "text": "Và đây là 1 sợi dây có tốc độ cao HDMI 2.0 của O-Kring"},
            {"start": 21.76, "end": 24.76, "text": "Anh em mua về với giá nên quanh đôi tầm 7,80.000"},
        ]

        bad = "ANH EM XEM NÀY SỢI DÂY HDMI 2.0 O KRING GIÁ CHỈ"
        self.assertTrue(_is_weak_thumbnail_title(bad, " ".join(seg["text"] for seg in segments)))
        fixed = _best_rule_thumbnail_title("DJI_20260528220358_0072_D", segments)

        self.assertEqual(fixed, "CÁP HDMI 2.0 4K 120HZ GIÁ 80K")
        self.assertEqual(_thumbnail_title_quality(fixed, "DJI_20260528220358_0072_D", segments)["publish_status"], "ready")

    def test_rule_titles_are_ready_for_common_fallback_categories(self) -> None:
        cases = [
            (
                "DJI_0080_D",
                [{"text": "Loa thanh toán Momo kèm sim 4G, dùng thanh toán rất tiện."}],
                "LOA THANH TOÁN KÈM SIM 4G",
            ),
            (
                "DJI_0083_D",
                [{"text": "USB 2TB fake, tốc độ chậm, chỉ hợp chép nhạc thôi."}],
                "USB GIÁ RẺ CHỈ CHÉP NHẠC",
            ),
            (
                "DJI_0087_D",
                [{"text": "Sợi cáp HDMI chính hãng hỗ trợ 4K cho màn hình."}],
                "CÁP HDMI 4K",
            ),
        ]
        for source, segments, expected in cases:
            with self.subTest(source=source):
                title = _best_rule_thumbnail_title(source, segments)
                self.assertEqual(title, expected)
                self.assertEqual(_thumbnail_title_quality(title, source, segments)["publish_status"], "ready")

    def test_upload_metadata_stays_cross_platform_safe(self) -> None:
        segments = [{"text": "Hub Type-C cho Samsung Dex giúp cắm màn hình, bàn phím và làm việc di động gọn hơn."}]
        meta = _build_upload_metadata("HUB TYPE-C CHO SAMSUNG DEX", "DJI_20260527165018_0073_D", segments)
        self.assertLessEqual(len(meta["upload_title"]), 90)
        self.assertLessEqual(len(meta["caption_short"]), 120)
        self.assertLessEqual(len(meta["caption_full"]), 220)
        self.assertGreaterEqual(len(meta["hashtags"]), 3)
        self.assertLessEqual(len(meta["hashtags"]), 4)
        self.assertEqual(meta["caption_full"], meta["upload_title"])
        self.assertEqual(meta["platform_caption"], f"{meta['upload_title']}\n{' '.join(meta['hashtags'])}")
        joined = " ".join([meta["upload_title"], meta["caption_full"], " ".join(meta["hashtags"])])
        self.assertNotIn("DJI", joined)
        self.assertIn("#SamsungDex", meta["hashtags"])
        self.assertIn("#HubTypeC", meta["hashtags"])

    def test_metadata_plan_uses_thumbnail_title_and_moderate_hashtags(self) -> None:
        segments = [{"text": "Lên đơn box Samsung Dex S20 cho khách, có giá 1900k."}]
        plan = _one_shot_metadata_plan("LÊN ĐƠN BOX SAMSUNG DEX S20 CÓ GIÁ 1900K", "DJI_0092_D", segments)

        self.assertEqual(
            plan["final_video_name"],
            "Lên Đơn Box Samsung Dex S20 Có Giá 1900K #SamsungDex #BoxSamsungDex #KinhNghiemMuaHang.mp4",
        )
        self.assertGreaterEqual(len(plan["final_hashtags"]), 3)
        self.assertLessEqual(len(plan["final_hashtags"]), 4)

    def test_upload_metadata_filters_unsupported_brand_hashtags(self) -> None:
        segments = [{"text": "Sạc nhanh 27W cho iPhone chỉ cần một sợi dây gọn hơn."}]
        meta = _build_upload_metadata("SẠC NHANH 27W CHO IPHONE", "VID_0001", segments)
        self.assertIn("#iPhone", meta["hashtags"])
        self.assertIn("#SacNhanh", meta["hashtags"])
        self.assertNotIn("#Anker", meta["hashtags"])

    def test_upload_metadata_adds_payment_tags(self) -> None:
        segments = [{"text": "Khách thanh toán Momo bằng VietQR rất nhanh."}]
        meta = _build_upload_metadata("THANH TOÁN MOMO BẰNG VIETQR", "VID_0079", segments)

        self.assertEqual(meta["upload_title"], "Thanh Toán MoMo Bằng VietQR")
        self.assertIn("#Momo", meta["hashtags"])
        self.assertIn("#VietQR", meta["hashtags"])
        self.assertIn("#ThanhToanQR", meta["hashtags"])
        self.assertEqual(meta["platform_caption"], f"{meta['upload_title']}\n{' '.join(meta['hashtags'])}")

    def test_upload_hashtags_avoid_numeric_start_when_possible(self) -> None:
        segments = [{"text": "Dây HDMI hỗ trợ 120Hz cho màn hình cao tần."}]
        meta = _build_upload_metadata("DÂY HDMI 120HZ SIÊU GỌN", "VID_0079", segments)
        self.assertNotIn("#120Hz", meta["hashtags"])
        self.assertFalse(any(tag.startswith("#1") for tag in meta["hashtags"]))

    def test_upload_hashtags_prefer_specific_momo_tags(self) -> None:
        segments = [{"text": "Loa thanh toán Momo có sim data 4G để dùng khi mất wifi."}]
        meta = _build_upload_metadata("LOA MOMO CÓ SIM 4G", "VID_0082", segments)
        self.assertIn("#LoaMomo", meta["hashtags"])
        self.assertIn("#ThanhToanQR", meta["hashtags"])
        self.assertIn("#Sim4G", meta["hashtags"])
        self.assertNotIn("#Momo", meta["hashtags"])

    def test_thumbnail_review_gate_skips_clean_deterministic_items(self) -> None:
        title_quality = {"publish_status": "ready", "risk_flags": []}
        layout_quality = {"ok": True, "issues": []}
        gate = _thumbnail_review_gate(
            "CÁP HDMI 2.0 GIÁ 80K",
            "VID_0072",
            [{"text": "cáp HDMI 2.0 giá 80k"}],
            title_quality,
            layout_quality,
            True,
        )
        self.assertEqual(gate["status"], "skipped")
        self.assertFalse(gate["enabled"])
        self.assertFalse(gate["blocking"])

    def test_thumbnail_review_gate_calls_for_risky_items(self) -> None:
        title_quality = {"publish_status": "fallback", "risk_flags": ["fallback"]}
        layout_quality = {"ok": True, "issues": []}
        gate = _thumbnail_review_gate(
            "USB 2TB ĐỪNG LÀM Ổ CHÍNH",
            "VID_0083",
            [{"text": "USB 2TB fake tốc độ chậm đừng làm ổ chính"}],
            title_quality,
            layout_quality,
            True,
        )
        self.assertTrue(gate["enabled"])
        self.assertIn("title_gate_not_ready", gate["reasons"])

    def test_network_review_error_does_not_lower_ready_status(self) -> None:
        title_quality = {"publish_status": "ready"}
        layout_quality = {"ok": True, "issues": []}
        review = {"enabled": True, "status": "network_error", "blocking": False, "ok": False}
        self.assertEqual(_one_shot_final_status(title_quality, layout_quality, review), "ready")

    def test_upload_metadata_uses_valid_ai_title_and_hashtags(self) -> None:
        raw = __import__("json").dumps({
            "titles": ["HUB TYPE-C CHO SAMSUNG DEX"],
            "upload_title": "Hub Type-C Cho Samsung Dex",
            "hashtags": ["#SamsungDex", "#HubTypeC", "#PhuKienCongNghe"],
        })
        parsed = _parse_thumbnail_title_response(raw)
        meta = _build_upload_metadata(
            parsed["titles"][0],
            "DJI_20260527165018_0073_D",
            [{"text": "Hub Type-C cho Samsung Dex cắm màn hình rất tiện."}],
            ai_metadata=parsed,
        )

        self.assertEqual(meta["upload_title"], "Hub Type-C Cho Samsung Dex")
        self.assertEqual(meta["hashtags"], ["#SamsungDex", "#HubTypeC", "#PhuKienCongNghe"])
        self.assertEqual(meta["platform_caption"], "Hub Type-C Cho Samsung Dex\n#SamsungDex #HubTypeC #PhuKienCongNghe")

    def test_upload_metadata_ignores_bad_ai_caption_payload(self) -> None:
        raw = __import__("json").dumps({
            "titles": ["HUB TYPE-C CHO SAMSUNG DEX"],
            "upload_title": "DJI 20260527165018 0073 D",
            "caption_full": "Gọn hơn cho setup Samsung Dex và làm việc di động. " * 8,
            "hashtags": ["#fyp", "#viral", "#SamsungDex", "#HubTypeC"],
        })
        titles = _parse_thumbnail_title_payload(raw)
        parsed = _parse_thumbnail_title_response(raw)
        meta = _build_upload_metadata(
            titles[0],
            "DJI_20260527165018_0073_D",
            [{"text": "Hub Type-C cho Samsung Dex cắm màn hình rất tiện."}],
            ai_metadata=parsed,
        )

        self.assertEqual(meta["caption_full"], meta["upload_title"])
        self.assertEqual(meta["upload_title"], "HUB Type-C Cho Samsung Dex")
        self.assertNotIn("Gọn hơn", meta["platform_caption"])
        self.assertNotIn("#fyp", meta["hashtags"])
        self.assertNotIn("#viral", meta["hashtags"])

    def test_batch_summary_items_keep_upload_metadata(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            tmp_dir = Path(tmp)
            source = tmp_dir / "DJI_20260527165018_0073_D.mp4"
            source.write_bytes(b"fake")
            export_dir = tmp_dir / "Exports"
            export_dir.mkdir()
            plan_path = tmp_dir / "cuts.json"
            plan_path.write_text(__import__("json").dumps({"source_video": str(source)}), encoding="utf-8")
            meta = _build_upload_metadata(
                "HUB TYPE-C CHO SAMSUNG DEX",
                source.stem,
                [{"text": "Hub Type-C cho Samsung Dex cắm màn hình rất tiện."}],
            )
            report_path = tmp_dir / "edit-report.json"
            report_path.write_text(__import__("json").dumps({
                "video": str(export_dir / "HUB Type-C Cho Samsung Dex 0073.mp4"),
                "export_video": str(export_dir / "HUB Type-C Cho Samsung Dex 0073.mp4"),
                "export_dir": str(export_dir),
                "thumbnail_title": "HUB TYPE-C CHO SAMSUNG DEX",
                "thumbnail_title_quality": {"reasons": ["đúng thuật ngữ"]},
                "upload_metadata": meta,
                "upload_title": meta["upload_title"],
                "platform_caption": meta["platform_caption"],
            }), encoding="utf-8")

            worker = OneShotBatchWorker([str(source)], {"output_dir": str(tmp_dir)}, {"cut_video": False})
            worker._run_analyze = lambda *_args, **_kwargs: (str(plan_path), "")  # type: ignore[method-assign]
            worker._run_render = lambda *_args, **_kwargs: (str(report_path), "")  # type: ignore[method-assign]
            result: dict[str, str] = {}
            worker.finished.connect(lambda path: result.__setitem__("summary", path))
            worker.error.connect(lambda msg: result.__setitem__("error", msg))
            worker.run()

            self.assertNotIn("error", result)
            summary = __import__("json").loads(Path(result["summary"]).read_text(encoding="utf-8"))
            item = summary["items"][0]
            self.assertEqual(item["upload_metadata"]["caption_full"], item["upload_title"])
            self.assertEqual(item["platform_caption"], f"{item['upload_title']}\n{' '.join(item['upload_metadata']['hashtags'])}")

    def test_ai_costs_are_grouped_by_kind(self) -> None:
        title_cost = _estimate_ai_cost(
            "deepseek",
            "deepseek-v4-flash",
            {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200},
        )
        review_cost = _estimate_gemini_cost(
            "gemini-2.5-flash-lite",
            {"promptTokenCount": 500, "candidatesTokenCount": 50, "totalTokenCount": 550},
        )

        grouped = _sum_ai_costs_by_kind([title_cost, review_cost])

        self.assertIn("title", grouped)
        self.assertIn("thumbnail_review", grouped)
        self.assertGreater(grouped["title"]["total_tokens"], 0)
        self.assertGreater(grouped["thumbnail_review"]["total_tokens"], 0)

    @unittest.skipUnless(os.environ.get("RUN_MEDIA_SMOKE") == "1", "set RUN_MEDIA_SMOKE=1 to run media smoke")
    def test_render_smoke_embeds_cover_and_exports_mp4_only(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            tmp_dir = Path(tmp)
            source = tmp_dir / "DJI_20260523100432_0012_D.mp4"
            frame = tmp_dir / "frame.png"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "color=c=black:s=720x1280:d=0.6",
                    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(source),
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(source), "-frames:v", "1", str(frame)],
                check=True,
                capture_output=True,
            )
            plan = {
                "source_video": str(source),
                "output_dir": str(tmp_dir),
                "duration": 0.6,
                "cuts": [],
                "transcript": [{"start": 0, "end": 0.5, "text": "HDMI 4K Samsung Dex chỉ 80k"}],
                "thumbnail_frame": str(frame),
                "thumbnail_title_suggestion": "HDMI 4K SAMSUNG DEX CHỈ 80K",
                "ai_costs": [],
            }
            plan_path = tmp_dir / "cuts.json"
            plan_path.write_text(__import__("json").dumps(plan), encoding="utf-8")

            worker = OneShotRenderWorker(
                str(plan_path),
                [],
                {
                    "cut_video": False,
                    "ai_review_thumbnail": False,
                    "export_thumbnail": False,
                    "prepend_thumbnail_cover": True,
                    "thumbnail_title": "HDMI 4K SAMSUNG DEX CHỈ 80K",
                    "thumbnail_size": "large",
                    "thumbnail_lines": "auto",
                    "thumbnail_position": "center",
                    "render_profile": "multi_1080",
                },
            )
            from PyQt6.QtWidgets import QApplication

            _app = QApplication.instance() or QApplication([])
            result: dict[str, str] = {}
            worker.finished.connect(lambda path: result.__setitem__("report", path))
            worker.error.connect(lambda msg: result.__setitem__("error", msg))
            worker.run()

            self.assertNotIn("error", result)
            report = __import__("json").loads(Path(result["report"]).read_text(encoding="utf-8"))
            self.assertEqual(
                Path(report["export_video"]).name,
                "HDMI 4K Samsung Dex Chỉ 80K #SamsungDex #DayHDMI #LamViecDiDong.mp4",
            )
            self.assertEqual(report["video"], report["export_video"])
            self.assertTrue(report["render_to_final"])
            self.assertEqual(report["export_thumbnail"], "")
            self.assertTrue(Path(report["export_video"]).exists())
            self.assertEqual(report["thumbnail_style"]["size_preset"], "large")
            self.assertEqual(report["thumbnail_style"]["lines"], ["HDMI 4K", "SAMSUNG DEX", "CHỈ 80K"])
            self.assertEqual(len(report["thumbnail_style"]["font_size_by_line"]), 3)
            self.assertEqual(report["thumbnail_render_title"], "HDMI 4K SAMSUNG DEX CHỈ 80K")
            self.assertTrue(report["thumbnail_layout_quality"]["ok"])
            self.assertEqual(report["thumbnail_title_quality"]["publish_label"], "Đăng được ngay")
            self.assertEqual(report["thumbnail_frame_mode"], "source")
            self.assertEqual(report["thumbnail_frame_processed"], "")
            self.assertIn("render_profile", report)
            self.assertEqual(report["render_profile"]["render_method"], "encode")
            self.assertEqual(report["render_profile"]["output_profile"]["id"], "multi_1080")
            self.assertIn("ffmpeg_render", report["render_profile"]["steps"])
            self.assertIn("thumbnail_frame_processed", report["render_profile"]["steps"])

    def test_render_fast_path_uses_stream_copy_when_no_processing_needed(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            tmp_dir = Path(tmp)
            source = tmp_dir / "DJI_20260523100432_0012_D.mp4"
            frame = tmp_dir / "frame.png"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "color=c=black:s=720x1280:d=0.4",
                    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(source),
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(source), "-frames:v", "1", str(frame)],
                check=True,
                capture_output=True,
            )
            plan = {
                "source_video": str(source),
                "output_dir": str(tmp_dir),
                "duration": 0.4,
                "cuts": [],
                "transcript": [{"start": 0, "end": 0.3, "text": "HDMI 4K Samsung Dex chỉ 80k"}],
                "thumbnail_frame": str(frame),
                "thumbnail_title_suggestion": "HDMI 4K SAMSUNG DEX CHỈ 80K",
                "ai_costs": [],
            }
            plan_path = tmp_dir / "cuts.json"
            plan_path.write_text(__import__("json").dumps(plan), encoding="utf-8")

            worker = OneShotRenderWorker(
                str(plan_path),
                [],
                {
                    "cut_video": False,
                    "noise_reduce": False,
                    "apply_lut": False,
                    "ai_review_thumbnail": False,
                    "export_thumbnail": False,
                    "prepend_thumbnail_cover": False,
                    "thumbnail_title": "HDMI 4K SAMSUNG DEX CHỈ 80K",
                },
            )
            from PyQt6.QtWidgets import QApplication

            _app = QApplication.instance() or QApplication([])
            result: dict[str, str] = {}
            worker.finished.connect(lambda path: result.__setitem__("report", path))
            worker.error.connect(lambda msg: result.__setitem__("error", msg))
            worker.run()

            self.assertNotIn("error", result)
            report = __import__("json").loads(Path(result["report"]).read_text(encoding="utf-8"))
            self.assertEqual(report["render_profile"]["render_method"], "stream_copy")
            self.assertEqual(report["video_encoder"], "copy")
            self.assertEqual(report["thumbnail_frame_mode"], "source")

    def test_render_thumbnail_uses_processed_lut_frame_when_available(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            tmp_dir = Path(tmp)
            source = tmp_dir / "DJI_20260523100432_0012_D.mp4"
            frame = tmp_dir / "frame.png"
            lut = tmp_dir / "identity.cube"
            lut.write_text(
                "TITLE \"identity\"\n"
                "LUT_3D_SIZE 2\n"
                "0 0 0\n0 0 1\n0 1 0\n0 1 1\n1 0 0\n1 0 1\n1 1 0\n1 1 1\n",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "color=c=blue:s=720x1280:d=0.4",
                    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(source),
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(source), "-frames:v", "1", str(frame)],
                check=True,
                capture_output=True,
            )
            plan = {
                "source_video": str(source),
                "output_dir": str(tmp_dir),
                "duration": 0.4,
                "cuts": [],
                "transcript": [{"start": 0, "end": 0.3, "text": "HDMI 4K Samsung Dex chỉ 80k"}],
                "thumbnail_frame": str(frame),
                "thumbnail_title_suggestion": "HDMI 4K SAMSUNG DEX CHỈ 80K",
                "lut_path": str(lut),
                "ai_costs": [],
            }
            plan_path = tmp_dir / "cuts.json"
            plan_path.write_text(__import__("json").dumps(plan), encoding="utf-8")

            worker = OneShotRenderWorker(
                str(plan_path),
                [],
                {
                    "cut_video": False,
                    "noise_reduce": False,
                    "apply_lut": True,
                    "lut_path": str(lut),
                    "ai_review_thumbnail": False,
                    "export_thumbnail": False,
                    "prepend_thumbnail_cover": False,
                    "thumbnail_title": "HDMI 4K SAMSUNG DEX CHỈ 80K",
                },
            )
            from PyQt6.QtWidgets import QApplication

            _app = QApplication.instance() or QApplication([])
            result: dict[str, str] = {}
            worker.finished.connect(lambda path: result.__setitem__("report", path))
            worker.error.connect(lambda msg: result.__setitem__("error", msg))
            worker.run()

            self.assertNotIn("error", result)
            report = __import__("json").loads(Path(result["report"]).read_text(encoding="utf-8"))
            self.assertEqual(report["thumbnail_frame_mode"], "lut_processed")
            self.assertTrue(Path(report["thumbnail_frame_processed"]).exists())
            self.assertIn("thumbnail_frame_processed", report["render_profile"]["steps"])


class EscbaseTemplateTests(unittest.TestCase):
    def test_escbase_vendor_template_is_detected(self) -> None:
        root = escbase_root()
        status = escbase_template_status(root)

        self.assertEqual(status["status"], "ok")
        self.assertEqual(status["template_id"], "escbase-slide-starter")
        self.assertTrue((root / "hedra_manifest.json").exists())

    def test_escbase_script_lines_match_starter_reveal_counts(self) -> None:
        source = (
            "Samsung Dex cần hub Type-C ổn định. "
            "Cắm HDMI, chuột và bàn phím để làm việc di động. "
            "Sạc PD giúp máy không tụt pin khi trình chiếu. "
            "Ưu tiên hub nhỏ gọn, dây chắc và đủ cổng."
        )
        lines = escbase_script_lines(source)

        self.assertEqual(len(lines), 6)
        self.assertTrue(all(line.strip() for line in lines))
        self.assertIn("Samsung Dex", " ".join(lines))

    def test_escbase_create_project_and_validate_starter(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            project = escbase_create_project(
                "Samsung Dex cần hub Type-C gọn. Cắm màn hình, chuột, bàn phím là làm việc được.",
                Path(tmp),
                "Samsung Dex Hub",
            )

            project_dir = Path(project["project_dir"])
            script_path = Path(project["script_path"])
            metadata_path = Path(project["metadata_path"])
            self.assertTrue(project_dir.exists())
            self.assertTrue(script_path.exists())
            self.assertTrue(metadata_path.exists())
            metadata = __import__("json").loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["template"], "escbase-slide-starter")
            self.assertEqual(len(project["script_lines"]), 6)

            validate = subprocess.run(
                [sys.executable, str(escbase_root() / "validate_slide.py"), str(project_dir), "--skip-safezone"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(validate.returncode, 0, validate.stdout + validate.stderr)

    def test_escbase_dependency_status_reports_missing_template(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            status = escbase_dependency_status(Path(tmp))

        self.assertIn(status["status"], {"missing_template", "invalid_template"})
        self.assertNotEqual(status["status"], "ready")


if __name__ == "__main__":
    unittest.main()
