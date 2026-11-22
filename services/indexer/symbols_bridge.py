
import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PARSER_SCRIPT = (
    PROJECT_ROOT / "apps" / "web" / "scripts" / "symbols.cjs"
)

MAX_SOURCE_BYTES = 1024 * 1024


def extract_symbols(file_path: str, source: str) -> list[dict]:
    """Extract AST declarations using the TypeScript parser."""

    if not isinstance(file_path, str) or not file_path.endswith((".ts", ".tsx")):
        raise ValueError("Unsupported TypeScript file path")

    if not isinstance(source, str):
        raise TypeError("Source must be text")

    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError("Source exceeds size limit")

    request = json.dumps({
        "file": file_path,
        "source": source,
    })

    try:
        result = subprocess.run(
            ["node", str(PARSER_SCRIPT)],
            input=request,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("AST parser timed out") from error
    except OSError as error:
        raise RuntimeError("AST parser unavailable") from error

    if result.returncode != 0:
        raise RuntimeError("AST parser rejected the input")

    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Invalid parser response") from error

    if (
        not isinstance(response, dict)
        or response.get("file") != file_path
        or not isinstance(response.get("symbols"), list)
    ):
        raise RuntimeError("Unexpected parser response")

    return response["symbols"]
