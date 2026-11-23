
"""Tests for Docker executable resolution."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.validator.docker_executable import (
    resolve_docker_executable,
)


class DockerExecutableTests(unittest.TestCase):

    def test_accepts_existing_absolute_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "docker.exe"
            executable.write_bytes(b"test-only-file")

            with patch.dict(
                os.environ,
                {
                    "NEURALFORGE_DOCKER_EXECUTABLE":
                        str(executable)
                },
            ):
                result = resolve_docker_executable()

            self.assertEqual(
                result,
                str(executable.resolve()),
            )

    def test_rejects_relative_path(self):
        with patch.dict(
            os.environ,
            {"NEURALFORGE_DOCKER_EXECUTABLE": "docker.exe"},
        ):
            self.assertIsNone(
                resolve_docker_executable()
            )

    def test_rejects_missing_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing-docker.exe"

            with patch.dict(
                os.environ,
                {
                    "NEURALFORGE_DOCKER_EXECUTABLE":
                        str(missing)
                },
            ):
                self.assertIsNone(
                    resolve_docker_executable()
                )

    def test_rejects_empty_override(self):
        with patch.dict(
            os.environ,
            {"NEURALFORGE_DOCKER_EXECUTABLE": ""},
        ):
            self.assertIsNone(
                resolve_docker_executable()
            )

    def test_rejects_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(
                os.environ,
                {
                    "NEURALFORGE_DOCKER_EXECUTABLE":
                        temporary
                },
            ):
                self.assertIsNone(
                    resolve_docker_executable()
                )


if __name__ == "__main__":
    unittest.main()
