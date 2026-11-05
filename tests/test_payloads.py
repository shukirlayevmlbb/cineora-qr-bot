import unittest

from app.payloads import build_payload, make_label


class PayloadTests(unittest.TestCase):
    def test_wifi_payload_escapes_reserved_characters(self):
        value = build_payload(
            "wifi",
            {"ssid": "Office;5G", "password": "p:a,ss", "security": "WPA", "hidden": "false"},
        )
        self.assertEqual(value, r"WIFI:T:WPA;S:Office\;5G;P:p\:a\,ss;H:false;;")

    def test_open_wifi_uses_nopass(self):
        value = build_payload(
            "wifi", {"ssid": "Guest", "password": "", "security": "WPA", "hidden": "false"}
        )
        self.assertTrue(value.startswith("WIFI:T:nopass;"))

    def test_email_payload(self):
        value = build_payload(
            "email", {"email": "a@example.com", "subject": "Salom", "body": "Test xat"}
        )
        self.assertEqual(value, "mailto:a@example.com?subject=Salom&body=Test+xat")

    def test_whatsapp_payload(self):
        value = build_payload("whatsapp", {"phone": "+998901234567", "message": "Salom dunyo"})
        self.assertEqual(value, "https://wa.me/998901234567?text=Salom%20dunyo")

    def test_contact_payload(self):
        value = build_payload(
            "contact",
            {"name": "Sarvar", "phone": "+998901234567", "email": "", "organization": "Cineora"},
        )
        self.assertIn("BEGIN:VCARD", value)
        self.assertIn("FN:Sarvar", value)
        self.assertIn("ORG:Cineora", value)

    def test_label_is_limited(self):
        self.assertLessEqual(len(make_label("text", {"text": "x" * 100})), 80)


if __name__ == "__main__":
    unittest.main()
