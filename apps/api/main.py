
"""NEURALFORGE read-only repository intelligence API."""

from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from services.indexer.evidence import answer_symbol_question
from services.indexer.retrieval import search_symbols
from services.indexer.store import SQLiteIndexStore


app = FastAPI(
    title="NEURALFORGE API",
    version="0.3.0",
)


class SymbolResult(BaseModel):
    path: str
    name: str
    kind: str
    line: int
    score: int


class SearchResponse(BaseModel):
    repository_id: str
    query: str
    count: int
    results: list[SymbolResult]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=200)


class EvidenceItem(BaseModel):
    path: str
    line: int
    name: str
    kind: str
    sha256: str


class AskResponse(BaseModel):
    repository_id: str
    question: str
    answer: str
    evidence: list[EvidenceItem]


# Development-only registry, NOT production authentication.
REPOSITORY_OWNERS = {
    "demo-repo": "demo-user",
}


def get_store() -> SQLiteIndexStore:
    """Provide the local SQLite snapshot store."""
    return SQLiteIndexStore(
        Path("neuralforge-api.sqlite3")
    )


def authorize_repository(
    repo_id: str,
    x_demo_user: str | None,
) -> None:
    """Check demonstration ownership before retrieving data."""

    if not x_demo_user:
        raise HTTPException(
            status_code=401,
            detail="Demo identity required",
        )

    owner = REPOSITORY_OWNERS.get(repo_id)

    if owner is None:
        raise HTTPException(
            status_code=404,
            detail="Repository not found",
        )

    if owner != x_demo_user:
        raise HTTPException(
            status_code=403,
            detail="Repository access denied",
        )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get(
    "/repos/{repo_id}/symbols",
    response_model=SearchResponse,
)
def get_symbols(
    repo_id: str,
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    x_demo_user: str | None = Header(default=None),
    store: SQLiteIndexStore = Depends(get_store),
):
    authorize_repository(repo_id, x_demo_user)

    stored_files = store.list_files(repo_id)

    indexed_files = [
        {
            "path": file.path,
            "symbols": [
                asdict(symbol)
                for symbol in file.symbols
            ],
        }
        for file in stored_files
    ]

    results = search_symbols(
        indexed_files,
        q,
        limit,
    )

    return SearchResponse(
        repository_id=repo_id,
        query=q,
        count=len(results),
        results=results,
    )


@app.post(
    "/repos/{repo_id}/ask",
    response_model=AskResponse,
)
def ask_repository(
    repo_id: str,
    request: AskRequest,
    x_demo_user: str | None = Header(default=None),
    store: SQLiteIndexStore = Depends(get_store),
):
    # Authorize before reading the repository snapshot.
    authorize_repository(repo_id, x_demo_user)

    stored_files = store.list_files(repo_id)

    result = answer_symbol_question(
        stored_files,
        request.question,
    )

    return AskResponse(
        repository_id=repo_id,
        question=request.question,
        answer=result["answer"],
        evidence=result["evidence"],
    )
