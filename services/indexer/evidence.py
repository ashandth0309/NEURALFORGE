
"""Deterministic evidence-backed symbol question answering."""

import re

from services.indexer.store import IndexedFile


MAX_QUESTION_LENGTH = 200
MAX_EVIDENCE_RESULTS = 10


def answer_symbol_question(
    files: list[IndexedFile],
    question: str,
) -> dict:
    """Locate explicitly named symbols in an indexed snapshot.

    This is not an LLM. Evidence describes stored symbol
    metadata, not necessarily the current filesystem state.
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

    total_matches = len(matches)
    truncated = total_matches > MAX_EVIDENCE_RESULTS
    evidence = matches[:MAX_EVIDENCE_RESULTS]

    if total_matches == 0:
        answer = (
            "No explicitly named symbol in the question "
            "was found in the indexed snapshot."
        )

    elif total_matches == 1:
        item = evidence[0]

        answer = (
            f"Indexed symbol '{item['name']}' "
            f"({item['kind']}) is recorded at "
            f"{item['path']}:{item['line']}."
        )

    elif truncated:
        answer = (
            f"Found {total_matches} matching indexed "
            f"symbol locations. Showing the first "
            f"{len(evidence)} evidence entries."
        )

    else:
        answer = (
            f"Found {total_matches} matching indexed "
            "symbol locations. See the evidence entries."
        )

    return {
        "answer": answer,
        "total_matches": total_matches,
        "truncated": truncated,
        "evidence": evidence,
    }
