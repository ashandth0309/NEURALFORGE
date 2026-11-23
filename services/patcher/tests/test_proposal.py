
import subprocess
import tempfile
from pathlib import Path

import hashlib
import unittest

from services.patcher.proposal import propose_replacement


class PatchProposalTests(unittest.TestCase):

    def setUp(self):
        self.source = (
            "export function greet() {\n"
            '  return "hello";\n'
            "}\n"
        )

        self.digest = hashlib.sha256(
            self.source.encode("utf-8")
        ).hexdigest()

    def propose(self, **overrides):
        options = {
            "path": "src/greet.ts",
            "source": self.source,
            "old_text": '"hello"',
            "new_text": '"hello world"',
            "expected_sha256": self.digest,
        }

        options.update(overrides)

        return propose_replacement(**options)

    def test_generates_reviewable_unified_diff(self):
        result = self.propose()

        self.assertIn("--- a/src/greet.ts", result["unified_diff"])
        self.assertIn("+++ b/src/greet.ts", result["unified_diff"])
        self.assertIn('-  return "hello";', result["unified_diff"])
        self.assertIn(
            '+  return "hello world";',
            result["unified_diff"],
        )
        self.assertFalse(result["applied"])

    def test_rejects_stale_snapshot(self):
        with self.assertRaises(ValueError):
            self.propose(expected_sha256="0" * 64)

    def test_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            self.propose(path="../outside.ts")

    def test_rejects_windows_absolute_path(self):
        with self.assertRaises(ValueError):
            self.propose(path="C:\\temp\\file.ts")

    def test_rejects_missing_target(self):
        with self.assertRaises(ValueError):
            self.propose(old_text="doesNotExist")

    def test_rejects_ambiguous_target(self):
        source = '"hello"\n"hello"\n'

        digest = hashlib.sha256(
            source.encode("utf-8")
        ).hexdigest()

        with self.assertRaises(ValueError):
            self.propose(
                source=source,
                expected_sha256=digest,
            )

    def test_rejects_no_op_replacement(self):
        with self.assertRaises(ValueError):
            self.propose(new_text='"hello"')


    def test_diff_preserves_separate_lines_without_final_newline(self):
        source = 'export const greeting = "hello";'
        digest = hashlib.sha256(
            source.encode("utf-8")
        ).hexdigest()

        result = self.propose(
            source=source,
            expected_sha256=digest,
        )

        diff = result["unified_diff"]

        self.assertIn(
            '-export const greeting = "hello";\n',
            diff,
        )
        self.assertIn(
            '+export const greeting = "hello world";',
            diff,
        )
        self.assertNotIn(
            '"hello";+export',
            diff,
        )

    def test_proposal_does_not_mutate_input(self):
        original = self.source

        result = self.propose()

        self.assertEqual(self.source, original)
        self.assertFalse(result["applied"])
        self.assertNotEqual(
            result["original_sha256"],
            result["proposed_sha256"],
        )


    def test_generated_patch_applies_to_temporary_copy(self):
        cases = [
            (
                "with_final_newline",
                'export const greeting = "hello";\n',
            ),
            (
                "without_final_newline",
                'export const greeting = "hello";',
            ),
        ]

        for label, source in cases:
            with self.subTest(case=label):
                digest = hashlib.sha256(
                    source.encode("utf-8")
                ).hexdigest()

                proposal = self.propose(
                    source=source,
                    expected_sha256=digest,
                )


                with tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)

                    init_result = subprocess.run(
                        [
                            "git",
                            "init",
                            "--quiet",
                            "--initial-branch=main",
                        ],
                        cwd=root,
                        capture_output=True,
                        text=True,
                        check=False,
                    )

                    self.assertEqual(
                        init_result.returncode,
                        0,
                        init_result.stderr,
                    )

                    target = root / "src" / "greet.ts"

                    target.parent.mkdir(parents=True)
                    target.write_bytes(source.encode("utf-8"))


                    patch_bytes = proposal[
                        "unified_diff"
                    ].encode("utf-8")

                    check = subprocess.run(
                        [
                            "git",
                            "-c",
                            "core.autocrlf=false",
                            "apply",
                            "--check",
                            "-",
                        ],
                        input=patch_bytes,
                        cwd=root,
                        capture_output=True,
                        check=False,
                    )


                    self.assertEqual(
                        check.returncode,
                        0,
                        check.stderr,
                    )

                    # Git applies the patch only inside
                    # this disposable temporary directory.

                    apply_result = subprocess.run(
                        [
                            "git",
                            "-c",
                            "core.autocrlf=false",
                            "apply",
                            "-",
                        ],
                        input=patch_bytes,
                        cwd=root,
                        capture_output=True,
                        check=False,
                    )


                    self.assertEqual(
                        apply_result.returncode,
                        0,
                        apply_result.stderr,
                    )

                    expected = source.replace(
                        '"hello"',
                        '"hello world"',
                        1,
                    )

                    actual = target.read_bytes()

                    self.assertEqual(
                        actual,
                        expected.encode("utf-8"),
                    )

                    self.assertEqual(
                        hashlib.sha256(actual).hexdigest(),
                        proposal["proposed_sha256"],
                    )


if __name__ == "__main__":
    unittest.main()
