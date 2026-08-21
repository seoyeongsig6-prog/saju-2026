import os
import tempfile
import unittest
from pathlib import Path

os.environ["APP_AUTH_SECRET"] = "release-test-secret-do-not-use"
os.environ["WRITER_LAUNCH_MODE"] = "1"
os.environ.pop("DATABASE_URL", None)

from thelife.server import db

_TEMP = tempfile.TemporaryDirectory()
db.DB_PATH = Path(_TEMP.name) / "release-test.db"

from fastapi.testclient import TestClient
from thelife.server.novelist_main import app
from thelife.server import writer


class ReleaseSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.uid = "12345678-1234-4234-9234-123456789abc"
        auth = cls.client.post("/api/writer/auth/device", json={"user_id": cls.uid})
        assert auth.status_code == 200 and auth.json()["ok"]
        cls.token = auth.json()["device_token"]
        cls.headers = {"X-User-Id": cls.uid, "X-Device-Token": cls.token}

    def test_api_rejects_missing_device_signature(self):
        response = self.client.get("/api/writer/config", headers={"X-User-Id": self.uid})
        self.assertEqual(response.status_code, 401)

    def test_recovery_code_restores_same_identity(self):
        code = self.client.get("/api/writer/auth/recovery-code", headers=self.headers).json()
        self.assertTrue(code["ok"])
        recovered = self.client.post("/api/writer/auth/recover",
                                     json={"recovery_code": code["recovery_code"]}).json()
        self.assertEqual(recovered["user_id"], self.uid)
        self.assertEqual(recovered["device_token"], self.token)

    def test_plan_has_only_declared_limits(self):
        config = self.client.get("/api/writer/config", headers=self.headers).json()
        self.assertNotIn("pens", config)
        self.assertNotIn("daily_cap", config)
        self.assertEqual(config["tiers"]["free"]["world_limit"], 3)
        self.assertEqual(config["tiers"]["light"]["label"], "MASTER")
        self.assertEqual(config["tiers"]["pro"]["sample_limit"], 20)

    def test_counter_never_exceeds_limit(self):
        with db.connect() as c:
            self.assertTrue(writer._counter_spend(c, "test-counter", 2))
            self.assertTrue(writer._counter_spend(c, "test-counter", 2))
            self.assertFalse(writer._counter_spend(c, "test-counter", 2))

    def test_personal_data_export_is_available_on_free(self):
        data = self.client.get("/api/writer/account/export", headers=self.headers).json()
        self.assertTrue(data["ok"])

    def test_public_account_deletion_page_is_available(self):
        page = self.client.get("/delete-account")
        self.assertEqual(page.status_code, 200)
        self.assertIn("계정 및 데이터 삭제", page.text)


if __name__ == "__main__":
    unittest.main()
