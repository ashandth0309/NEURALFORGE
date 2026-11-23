
"""NEURALFORGE read-only repository search API."""

from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

from services.indexer.retrieval import search_symbols
from services.indexer.store import SQLiteIndexStore


app = FastAPI(
    title="NEURALFORGE API",
    version="0.2.0",
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


# Development-only ownership registry.
# This is NOT a production authentication system.
REPOSITORY_OWNERS = {
    "demo-repo": "demo-user",
}


def get_store() -> SQLiteIndexStore:
    """Provide the local SQLite persistence adapter."""
    return SQLiteIndexStore(
        Path("neuralforge-api.sqlite3")
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

    # Read the persisted snapshot only after checking access.
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
