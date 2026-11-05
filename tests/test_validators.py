import unittest

from app.validators import (
    ValidationError,
    coordinates,
    email,
    event_datetime,
    phone,
    telegram,
    website,
)


class ValidatorTests(unittest.TestCase):
    def test_website_adds_https(self):
        self.assertEqual(website("cineora.uz"), "https://cineora.uz")

    def test_website_rejects_invalid_value(self):
        with self.assertRaises(ValidationError):
            website("localhost")

    def test_phone_normalizes(self):
        self.assertEqual(phone("+998 90 123-45-67"), "+998901234567")

    def test_email_normalizes_case(self):
        self.assertEqual(email("User@Example.COM"), "user@example.com")

    def test_telegram_accepts_link(self):
        self.assertEqual(telegram("https://t.me/CineoraUz"), "CineoraUz")

    def test_coordinates(self):
        self.assertEqual(coordinates("41.3111, 69.2797"), (41.3111, 69.2797))

    def test_coordinates_reject_out_of_range(self):
        with self.assertRaises(ValidationError):
            coordinates("101, 69")

    def test_event_datetime(self):
        self.assertEqual(event_datetime("25.12.2026 18:30"), "20261225T183000")


if __name__ == "__main__":
    unittest.main()
