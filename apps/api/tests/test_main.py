
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import app, get_store
from services.indexer.store import (
    IndexedFile,
    IndexedSymbol,
    SQLiteIndexStore,
)


class RepositorySearchAPITests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteIndexStore(
            Path(self.temp.name) / "test.sqlite3"
        )

        source = IndexedFile(
            path="src/app/layout.tsx",
            sha256="a" * 64,
            size_bytes=42,
            symbols=(
                IndexedSymbol(
                    name="RootLayout",
                    kind="function",
                    line=20,
                ),
            ),
        )

        self.store.replace_snapshot("demo-repo", [source])

        app.dependency_overrides[get_store] = lambda: self.store

        self.client = TestClient(app)
        self.url = "/repos/demo-repo/symbols"

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.temp.cleanup()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_owner_can_search_persisted_symbols(self):
        response = self.client.get(
            self.url,
            params={"q": "RootLayout"},
            headers={"X-Demo-User": "demo-user"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["count"], 1)
        self.assertEqual(
            data["results"][0]["name"],
            "RootLayout",
        )
        self.assertEqual(
            data["results"][0]["line"],
            20,
        )

    def test_missing_identity_returns_401(self):
        response = self.client.get(
            self.url,
            params={"q": "RootLayout"},
        )
        self.assertEqual(response.status_code, 401)

    def test_wrong_owner_returns_403(self):
        response = self.client.get(
            self.url,
            params={"q": "RootLayout"},
            headers={"X-Demo-User": "other-user"},
        )
        self.assertEqual(response.status_code, 403)

    def test_unknown_repository_returns_404(self):
        response = self.client.get(
            "/repos/unknown/symbols",
            params={"q": "RootLayout"},
            headers={"X-Demo-User": "demo-user"},
        )
        self.assertEqual(response.status_code, 404)

    def test_invalid_query_returns_422(self):
        response = self.client.get(
            self.url,
            params={"q": ""},
            headers={"X-Demo-User": "demo-user"},
        )
        self.assertEqual(response.status_code, 422)

    def test_reads_updated_sqlite_snapshot(self):
        replacement = IndexedFile(
            path="src/app/page.tsx",
            sha256="b" * 64,
            size_bytes=50,
            symbols=(
                IndexedSymbol(
                    name="UpdatedPage",
                    kind="function",
                    line=5,
                ),
            ),
        )

        self.store.replace_snapshot("demo-repo", [replacement])

        headers = {"X-Demo-User": "demo-user"}

        old = self.client.get(
            self.url,
            params={"q": "RootLayout"},
            headers=headers,
        )

        new = self.client.get(
            self.url,
            params={"q": "UpdatedPage"},
            headers=headers,
        )

        self.assertEqual(old.json()["count"], 0)
        self.assertEqual(new.json()["count"], 1)
        self.assertEqual(
            new.json()["results"][0]["path"],
            "src/app/page.tsx",
        )


if __name__ == "__main__":
    unittest.main()
