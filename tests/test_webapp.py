from __future__ import annotations

import hashlib
import hmac
import json
import time
import unittest
from urllib.parse import urlencode

from app.qr_builder import build_custom_png, build_custom_svg
from app.webapp import verify_init_data


class WebAppTests(unittest.TestCase):
    def test_telegram_init_data_verification(self) -> None:
        token = "123456:TEST_TOKEN"
        values = {
            "auth_date": str(int(time.time())),
            "query_id": "AAE-test",
            "user": json.dumps({"id": 42, "first_name": "Cineora"}, separators=(",", ":")),
        }
        check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        user = verify_init_data(urlencode(values), token)
        self.assertEqual(user["id"], 42)

    def test_invalid_init_data_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            verify_init_data("auth_date=1&hash=bad", "token")

    def test_custom_qr_outputs_png_and_svg(self) -> None:
        design = {
            "fg": "#635BFF",
            "bg": "#FFFFFF",
            "gradient": True,
            "gradient_to": "#8B5CF6",
            "shape": "rounded",
            "frame": True,
            "frame_text": "CINEORA",
            "size": 512,
        }
        png = build_custom_png("https://t.me/cineora_qrbot", design)
        svg = build_custom_svg("https://t.me/cineora_qrbot", design)
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertIn(b"<svg", svg)
        self.assertIn(b"CINEORA", svg)


if __name__ == "__main__":
    unittest.main()
