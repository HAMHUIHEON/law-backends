from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any

from issue_vector_index import load_index, search

router = APIRouter()

INDEX = None

@router.on_event("startup")
def load_vector_index():
    global INDEX
    INDEX = load_index()
    print(f"[vector index loaded] {len(INDEX)} issues")


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


@router.post("/issues")
def search_issues(req: SearchRequest):

    if INDEX is None:
        return {"error": "index not loaded"}

    results = search(INDEX, req.query, req.top_k)

    return {
        "query": req.query,
        "results": results
    }