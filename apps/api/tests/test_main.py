
import tempfile
import unittest
import hashlib
from pathlib import Path
from apps.api.main import get_repository_root
from unittest.mock import patch


from fastapi.testclient import TestClient

from apps.api.main import app, get_store
from services.indexer.store import (
    IndexedFile,
    IndexedSymbol,
    SQLiteIndexStore,
)

from unittest.mock import patch
from apps.api.main import get_repository_root



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


    def test_ask_returns_evidence(self):
        response = self.client.post(
            "/repos/demo-repo/ask",
            json={"question": "Where is RootLayout defined?"},
            headers={"X-Demo-User": "demo-user"},
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["repository_id"], "demo-repo")
        self.assertEqual(len(data["evidence"]), 1)
        self.assertEqual(
            data["evidence"][0]["path"],
            "src/app/layout.tsx",
        )
        self.assertEqual(
            data["evidence"][0]["line"],
            20,
        )
        self.assertEqual(
            data["evidence"][0]["sha256"],
            "a" * 64,
        )

        self.assertEqual(data["total_matches"], 1)
        self.assertFalse(data["truncated"])


    def test_ask_rejects_missing_identity(self):
        response = self.client.post(
            "/repos/demo-repo/ask",
            json={"question": "Where is RootLayout?"},
        )

        self.assertEqual(response.status_code, 401)

    def test_ask_rejects_wrong_owner(self):
        response = self.client.post(
            "/repos/demo-repo/ask",
            json={"question": "Where is RootLayout?"},
            headers={"X-Demo-User": "other-user"},
        )

        self.assertEqual(response.status_code, 403)

    def test_ask_unknown_repository(self):
        response = self.client.post(
            "/repos/unknown/ask",
            json={"question": "Where is RootLayout?"},
            headers={"X-Demo-User": "demo-user"},
        )

        self.assertEqual(response.status_code, 404)

    def test_ask_unknown_symbol(self):
        response = self.client.post(
            "/repos/demo-repo/ask",
            json={"question": "Where is MissingFunction?"},
            headers={"X-Demo-User": "demo-user"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["evidence"],
            [],
        )


    def test_ask_rejects_whitespace_question(self):
        response = self.client.post(
            "/repos/demo-repo/ask",
            json={"question": "   "},
            headers={"X-Demo-User": "demo-user"},
        )
        self.assertEqual(response.status_code, 422)

    def test_ask_rejects_overlong_question(self):
        response = self.client.post(
            "/repos/demo-repo/ask",
            json={"question": "x" * 201},
            headers={"X-Demo-User": "demo-user"},
        )
        self.assertEqual(response.status_code, 422)

    def test_ask_rejects_missing_question(self):
        response = self.client.post(
            "/repos/demo-repo/ask",
            json={},
            headers={"X-Demo-User": "demo-user"},
        )
        self.assertEqual(response.status_code, 422)

    def test_ask_rejects_non_string_question(self):
        response = self.client.post(
            "/repos/demo-repo/ask",
            json={"question": 123},
            headers={"X-Demo-User": "demo-user"},
        )
        self.assertEqual(response.status_code, 422)


    def test_unauthorized_search_does_not_read_store(self):
        with patch.object(
            self.store,
            "list_files",
        ) as read_files:
            response = self.client.get(
                "/repos/demo-repo/symbols",
                params={"q": "RootLayout"},
                headers={"X-Demo-User": "other-user"},
            )

        self.assertEqual(response.status_code, 403)
        read_files.assert_not_called()

    def test_unauthorized_ask_does_not_read_store(self):
        with patch.object(
            self.store,
            "list_files",
        ) as read_files:
            response = self.client.post(
                "/repos/demo-repo/ask",
                json={"question": "Where is RootLayout?"},
                headers={"X-Demo-User": "other-user"},
            )

        self.assertEqual(response.status_code, 403)
        read_files.assert_not_called()

    def test_unknown_repository_does_not_read_store(self):
        with patch.object(
            self.store,
            "list_files",
        ) as read_files:
            response = self.client.post(
                "/repos/unknown/ask",
                json={"question": "Where is RootLayout?"},
                headers={"X-Demo-User": "demo-user"},
            )

        self.assertEqual(response.status_code, 404)
        read_files.assert_not_called()

    def test_ask_reports_current_source(self):
        with patch(
            "apps.api.main.check_file_freshness",
            return_value="current",
        ) as checker:
            response = self.client.post(
                "/repos/demo-repo/ask",
                json={"question": "Where is RootLayout?"},
                headers={"X-Demo-User": "demo-user"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["evidence"][0]["freshness"],
            "current",
        )
        checker.assert_called_once()

    def test_ask_reports_stale_source(self):
        with patch(
            "apps.api.main.check_file_freshness",
            return_value="stale",
        ):
            response = self.client.post(
                "/repos/demo-repo/ask",
                json={"question": "Where is RootLayout?"},
                headers={"X-Demo-User": "demo-user"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["evidence"][0]["freshness"],
            "stale",
        )

    def test_ask_reports_not_verified_without_root(self):
        app.dependency_overrides[get_repository_root] = (
            lambda: None
        )

        response = self.client.post(
            "/repos/demo-repo/ask",
            json={"question": "Where is RootLayout?"},
            headers={"X-Demo-User": "demo-user"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["evidence"][0]["freshness"],
            "not_verified",
        )

    def test_unauthorized_ask_skips_freshness_check(self):
        with patch(
            "apps.api.main.check_file_freshness",
        ) as checker:
            response = self.client.post(
                "/repos/demo-repo/ask",
                json={"question": "Where is RootLayout?"},
                headers={"X-Demo-User": "other-user"},
            )

        self.assertEqual(response.status_code, 403)
        checker.assert_not_called()


    def test_ask_detects_actual_source_change(self):
        root = Path(self.temp.name) / "source"
        source = root / "src" / "app" / "layout.tsx"
        source.parent.mkdir(parents=True)

        original = b"export function RootLayout() {}"
        source.write_bytes(original)

        self.store.replace_snapshot(
            "demo-repo",
            [
                IndexedFile(
                    path="src/app/layout.tsx",
                    sha256=hashlib.sha256(original).hexdigest(),
                    size_bytes=len(original),
                    symbols=(
                        IndexedSymbol(
                            name="RootLayout",
                            kind="function",
                            line=1,
                        ),
                    ),
                ),
            ],
        )

        app.dependency_overrides[get_repository_root] = (
            lambda: root
        )

        def ask():
            return self.client.post(
                "/repos/demo-repo/ask",
                json={"question": "Where is RootLayout?"},
                headers={"X-Demo-User": "demo-user"},
            )

        current = ask()
        self.assertEqual(current.status_code, 200)
        self.assertEqual(
            current.json()["evidence"][0]["freshness"],
            "current",
        )

        source.write_bytes(
            b"export function RootLayout() { return 2; }"
        )

        stale = ask()
        self.assertEqual(stale.status_code, 200)
        self.assertEqual(
            stale.json()["evidence"][0]["freshness"],
            "stale",
        )

        source.unlink()

        missing = ask()
        self.assertEqual(missing.status_code, 200)
        self.assertEqual(
            missing.json()["evidence"][0]["freshness"],
            "missing",
        )




if __name__ == "__main__":
    unittest.main()
