
"""Deterministic evidence-backed symbol question answering."""

import re

from services.indexer.store import IndexedFile


MAX_QUESTION_LENGTH = 200
MAX_EVIDENCE_RESULTS = 10


def answer_symbol_question(
    files: list[IndexedFile],
    question: str,
) -> dict:
    """Find indexed symbols explicitly mentioned in a question.

    This is not an LLM. It makes only location claims supported
    by the stored symbol snapshot.
    """

    if not isinstance(question, str):
        raise TypeError("Question must be a string")

    question = question.strip()

    if not question or len(question) > MAX_QUESTION_LENGTH:
        raise ValueError(
            "Question must contain 1-200 characters"
        )

    matches = []

    for source_file in files:
        for symbol in source_file.symbols:
            pattern = (
                r"(?<!\w)"
                + re.escape(symbol.name)
                + r"(?!\w)"
            )

            if not re.search(
                pattern,
                question,
                flags=re.IGNORECASE,
            ):
                continue

            matches.append(
                {
                    "path": source_file.path,
                    "line": symbol.line,
                    "name": symbol.name,
                    "kind": symbol.kind,
                    "sha256": source_file.sha256,
                }
            )

    matches.sort(
        key=lambda item: (
            -len(item["name"]),
            item["name"].casefold(),
            item["path"],
            item["line"],
        )
    )

    matches = matches[:MAX_EVIDENCE_RESULTS]

    if not matches:
        return {
            "answer": (
                "No explicitly named symbol in the question "
                "was found in the indexed snapshot."
            ),
            "evidence": [],
        }

    if len(matches) == 1:
        item = matches[0]

        answer = (
            f"Indexed symbol '{item['name']}' "
            f"({item['kind']}) is recorded at "
            f"{item['path']}:{item['line']}."
        )
    else:
        answer = (
            f"Found {len(matches)} matching indexed "
            "symbol locations. See the evidence entries."
        )

    return {
        "answer": answer,
        "evidence": matches,
    }
