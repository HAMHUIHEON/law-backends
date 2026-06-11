"""
RebuttalAgent — 반론 초안 생성 에이전트

과세처분 이유서 입력 →
납세자 승소 재결례·판례에서 반론 논거 추출 →
이의신청서·심판청구서 초안 생성
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage
from utils.llm import get_llm

ROOT = Path(__file__).parent.parent
_llm = get_llm(temperature=0)


# ── 벡터 검색 헬퍼 (strategy_agent와 공유 가능하나 독립 유지) ─────────────────

def _chroma_search(collection_name: str, chroma_dir: str, query: str,
                   n: int = 8, where: dict | None = None) -> list[dict]:
    try:
        import chromadb
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        ef = OpenAIEmbeddingFunction(
            api_key=os.environ["OPENAI_API_KEY"],
            model_name="text-embedding-3-small",
        )
        client = chromadb.PersistentClient(path=chroma_dir)
        col = client.get_collection(collection_name, embedding_function=ef)
        kwargs: dict = {"query_texts": [query], "n_results": min(n, col.count() or 1)}
        if where:
            kwargs["where"] = where
        res = col.query(**kwargs)
        return [
            {"doc": d, "meta": m}
            for d, m in zip(res["documents"][0], res["metadatas"][0])
        ]
    except Exception as e:
        return [{"doc": f"[검색 오류: {e}]", "meta": {}}]


TAXTR_DIR = str(ROOT / "vector_db" / "chroma")
COURT_DIR = str(ROOT / "chroma_db")


def _search_winning_taxtr(query: str, n: int = 10) -> list[dict]:
    """취소·경정 결정만 필터."""
    # Chroma는 $in 미지원 → 취소만 where, 경정은 별도 검색 후 합치기
    hits_cancel = _chroma_search(
        "taxtr_cases", TAXTR_DIR, query, n=n,
        where={"decision": {"$eq": "취소"}},
    )
    hits_correct = _chroma_search(
        "taxtr_cases", TAXTR_DIR, query, n=n // 2,
        where={"decision": {"$eq": "경정"}},
    )
    return hits_cancel + hits_correct


def _search_winning_court(query: str, n: int = 5) -> list[dict]:
    return _chroma_search("court_cases", COURT_DIR, query, n=n)


# ── 1단계: 과세관청 주장 추출 ─────────────────────────────────────────────────

def _extract_claims(disposition_text: str) -> dict:
    prompt = (
        "당신은 조세 전문 변호사다. 아래 과세처분 이유서에서 과세관청의 논거를 분석하라.\n\n"
        f"[과세처분 이유서]\n{disposition_text}\n\n"
        "JSON만 반환:\n"
        '{"tax_claims":["과세관청 주요 주장1","주장2"],'
        '"key_issues":["반론해야 할 핵심 쟁점1","쟁점2"],'
        '"tax_type":"세목",'
        '"search_query":"납세자 승소 판례 검색용 키워드 문장"}'
    )
    resp = _llm.invoke([HumanMessage(content=prompt)])
    try:
        return json.loads(resp.content.strip().strip("```json").strip("```"))
    except Exception:
        return {
            "tax_claims": [disposition_text[:200]],
            "key_issues": [disposition_text[:200]],
            "tax_type": "",
            "search_query": disposition_text[:200],
        }


# ── 2단계: 납세자 승소 판례 검색 ────────────────────────────────────────────

def _search_winning_cases(claims: dict) -> dict:
    query = claims.get("search_query", " ".join(claims.get("key_issues", [])))
    taxtr = _search_winning_taxtr(query, n=10)
    court = _search_winning_court(query, n=5)

    taxtr_list = [
        {
            "case_no":  h["meta"].get("case_no", ""),
            "date":     h["meta"].get("decision_date", ""),
            "decision": h["meta"].get("decision", ""),
            "title":    h["meta"].get("title", "")[:100],
            "snippet":  h["doc"][:300],
        }
        for h in taxtr if h["meta"].get("decision") in ("취소", "경정")
    ]

    court_list = [
        {
            "case_no": h["meta"].get("case_no", ""),
            "court":   h["meta"].get("court", ""),
            "snippet": h["doc"][:300],
        }
        for h in court
    ]

    return {"taxtr": taxtr_list, "court": court_list}


# ── 3단계: 반론 초안 작성 ─────────────────────────────────────────────────────

def _draft_rebuttal(disposition_text: str, claims: dict, winning: dict) -> str:
    taxtr_str = json.dumps(winning["taxtr"], ensure_ascii=False, indent=2)
    court_str = json.dumps(winning["court"], ensure_ascii=False, indent=2)

    prompt = (
        "당신은 국세청 경력 7년 출신 세무사 겸 조세전문 변호사다.\n"
        "아래 과세처분 이유서와 납세자 승소 판례를 바탕으로 심판청구서 반론 초안을 작성하라.\n\n"
        f"[과세처분 이유서]\n{disposition_text[:2000]}\n\n"
        f"[과세관청 주요 주장]\n" + "\n".join(f"- {c}" for c in claims.get("tax_claims", [])) + "\n\n"
        f"[납세자 승소 재결례 {len(winning['taxtr'])}건]\n{taxtr_str}\n\n"
        f"[납세자 승소 법원 판례 {len(winning['court'])}건]\n{court_str}\n\n"
        "아래 구조로 심판청구서 반론 초안을 작성하라:\n\n"
        "## 청구 취지\n\n"
        "## 청구 이유\n\n"
        "### 1. 처분의 개요\n\n"
        "### 2. 이 건 처분의 위법·부당성\n"
        "   각 쟁점별로:\n"
        "   - 과세관청 주장 요약\n"
        "   - 납세자 반론 (법령 근거, 판례 인용)\n"
        "   - 유사 취소 재결례·판례 적용\n\n"
        "### 3. 결론\n\n"
        "## 증거 자료 목록 (제출해야 할 서류)\n\n"
        "## 판례·재결례 인용 목록"
    )
    resp = _llm.invoke([HumanMessage(content=prompt)])
    return resp.content


# ── 퍼블릭 API ────────────────────────────────────────────────────────────────

class RebuttalAgent:
    """
    과세처분 이유서 → 납세자 승소 판례 검색 → 심판청구서 반론 초안

    result = agent.run(disposition_text="...")
    result["draft"]          # 반론 초안 (마크다운)
    result["winning_taxtr"]  # 인용된 재결례
    result["winning_court"]  # 인용된 법원 판례
    """

    def run(self, disposition_text: str) -> dict:
        claims  = _extract_claims(disposition_text)
        winning = _search_winning_cases(claims)
        draft   = _draft_rebuttal(disposition_text, claims, winning)
        return {
            "draft":         draft,
            "tax_claims":    claims.get("tax_claims", []),
            "key_issues":    claims.get("key_issues", []),
            "winning_taxtr": winning["taxtr"],
            "winning_court": winning["court"],
        }


if __name__ == "__main__":
    sample = (
        "처분 이유: 청구법인은 독일 모법인 A사와 체결한 기술용역 계약에 따라 "
        "매출액의 5%를 로열티로 지급하였으나, 조사 결과 동 계약은 특수관계자 간 "
        "거래로서 정상가격(2%)을 초과하는 차액 상당액에 대해 법인세법 제52조에 의한 "
        "부당행위계산 부인을 적용하여 익금산입 처리함."
    )
    agent = RebuttalAgent()
    result = agent.run(sample)
    print(result["draft"])
