import tempfile
import unittest
from pathlib import Path

from app.db import Database


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "test.sqlite3")
        await self.db.initialize()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_default_settings_are_privacy_friendly(self):
        settings = await self.db.get_settings(100)
        self.assertTrue(settings.history_enabled)
        self.assertFalse(settings.save_wifi_history)
        self.assertEqual(settings.default_style, "classic")

    async def test_record_is_scoped_to_owner(self):
        record_id = await self.db.add_record(100, "web", "https://example.com", "Example", "classic", True)
        self.assertIsNotNone(await self.db.get_record(record_id, 100))
        self.assertIsNone(await self.db.get_record(record_id, 200))

    async def test_history_only_returns_saved_records(self):
        await self.db.add_record(100, "text", "saved", "Saved", "classic", True)
        await self.db.add_record(100, "text", "temporary", "Temporary", "classic", False)
        records = await self.db.list_history(100)
        self.assertEqual([record.label for record in records], ["Saved"])

    async def test_delete_cannot_cross_user_boundary(self):
        record_id = await self.db.add_record(100, "text", "secret", "Secret", "classic", True)
        self.assertFalse(await self.db.delete_record(record_id, 200))
        self.assertIsNotNone(await self.db.get_record(record_id, 100))


if __name__ == "__main__":
    unittest.main()
