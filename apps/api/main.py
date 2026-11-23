
"""NEURALFORGE read-only repository intelligence API."""

from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from services.indexer.evidence import answer_symbol_question
from services.indexer.retrieval import search_symbols
from services.indexer.store import SQLiteIndexStore

from typing import Literal

from services.indexer.freshness import check_file_freshness


from services.patcher.proposal import propose_replacement
from services.patcher.source import (
    SourceReadError,
    read_verified_indexed_source,
)


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
    question: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"(?s:.*\S.*)",
    )



class EvidenceItem(BaseModel):
    path: str
    line: int
    name: str
    kind: str
    sha256: str
    freshness: Literal[
        "current",
        "stale",
        "missing",
        "unavailable",
        "not_verified",
    ]





class AskResponse(BaseModel):
    repository_id: str
    question: str
    answer: str
    total_matches: int
    truncated: bool
    evidence: list[EvidenceItem]


class PatchProposalRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    old_text: str = Field(min_length=1, max_length=1048576)
    new_text: str = Field(max_length=1048576)
    expected_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )


class PatchProposalResponse(BaseModel):
    repository_id: str
    path: str
    original_sha256: str
    proposed_sha256: str
    unified_diff: str
    changed: bool
    applied: bool



# Development-only registry, NOT production authentication.
REPOSITORY_OWNERS = {
    "demo-repo": "demo-user",
}


def get_store() -> SQLiteIndexStore:
    """Provide the local SQLite snapshot store."""
    return SQLiteIndexStore(
        Path("neuralforge-api.sqlite3")
    )


def get_repository_root(repo_id: str) -> Path | None:
    """Resolve a server-configured, trusted development root."""

    project_root = Path(__file__).resolve().parents[2]

    roots = {
        "demo-repo": project_root / "apps" / "web",
    }

    return roots.get(repo_id)



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

    repository_root: Path | None = Depends(get_repository_root),

):
    # Authorize before reading the repository snapshot.
    authorize_repository(repo_id, x_demo_user)

    stored_files = store.list_files(repo_id)

    result = answer_symbol_question(
        stored_files,
        request.question,
    )

    files_by_path = {
        item.path: item
        for item in stored_files
    }

    evidence_with_freshness = []

    for item in result["evidence"]:
        indexed_file = files_by_path.get(item["path"])

        if repository_root is None:
            freshness = "not_verified"
        elif indexed_file is None:
            freshness = "unavailable"
        else:
            freshness = check_file_freshness(
                repository_root,
                indexed_file,
            )

        evidence_with_freshness.append(
            {
                **item,
                "freshness": freshness,
            }
        )




    return AskResponse(
        repository_id=repo_id,
        question=request.question,
        answer=result["answer"],
        total_matches=result["total_matches"],
        truncated=result["truncated"],
        evidence=evidence_with_freshness,
    )



@app.post(
    "/repos/{repo_id}/patch-proposals",
    response_model=PatchProposalResponse,
)
def create_patch_proposal(
    repo_id: str,
    request: PatchProposalRequest,
    x_demo_user: str | None = Header(default=None),
    store: SQLiteIndexStore = Depends(get_store),
    repository_root: Path | None = Depends(get_repository_root),
):
    """Generate a reviewed patch proposal without writing files."""

    # Authorization must precede reading repository data.
    authorize_repository(repo_id, x_demo_user)

    indexed_files = store.list_files(repo_id)

    indexed_file = next(
        (
            item
            for item in indexed_files
            if item.path == request.path
        ),
        None,
    )

    if indexed_file is None:
        raise HTTPException(
            status_code=404,
            detail="Indexed source file not found",
        )

    if repository_root is None:
        raise HTTPException(
            status_code=503,
            detail="Repository source root is not configured",
        )

    try:
        source = read_verified_indexed_source(
            repository_root,
            indexed_file,
            request.expected_sha256,
        )

    except SourceReadError as error:
        if error.reason == "stale":
            raise HTTPException(
                status_code=409,
                detail="Indexed source snapshot is stale",
            ) from error

        if error.reason == "missing":
            raise HTTPException(
                status_code=404,
                detail="Indexed source file is missing",
            ) from error

        if error.reason in {
            "invalid_digest",
            "invalid_path",
            "invalid_encoding",
        }:
            raise HTTPException(
                status_code=422,
                detail="Indexed source cannot be processed",
            ) from error

        raise HTTPException(
            status_code=503,
            detail="Indexed source is unavailable",
        ) from error

    try:
        proposal = propose_replacement(
            path=indexed_file.path,
            source=source,
            old_text=request.old_text,
            new_text=request.new_text,
            expected_sha256=request.expected_sha256,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    return PatchProposalResponse(
        repository_id=repo_id,
        **proposal,
    )
