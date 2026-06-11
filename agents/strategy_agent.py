"""
StrategyAgent — 의뢰인 사건 전략 에이전트

의뢰인 사건 요약 → 재결례 + 법원 판례 검색 →
경정청구 / 조세심판 / 행정소송 중 최적 전략 보고서 생성
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional, TypedDict

from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage
from utils.llm import get_llm, DEFAULT_MODEL

ROOT = Path(__file__).parent.parent

_llm = get_llm(temperature=0)


# ── 벡터 검색 헬퍼 ────────────────────────────────────────────────────────────

def _chroma_search(collection_name: str, chroma_dir: str, query: str,
                   n: int = 8, where: dict | None = None) -> list[dict]:
    """Chroma 벡터 검색 — 결과를 [{doc, meta}] 로 반환."""
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

TAX_TYPE_MAP = {
    "법인세": "법인", "소득세": "종합소득", "양도소득세": "양도",
    "부가가치세": "부가", "증여세": "증여", "상속세": "상속",
    "취득세": "취득", "종합부동산세": "종합부동산", "관세": "관세",
    "국제조세": "법인", "조세범처벌": None,
}


def _search_taxtr(query: str, tax_type: str = "", n: int = 8) -> list[dict]:
    where = None
    if tax_type:
        code = TAX_TYPE_MAP.get(tax_type)
        if code:
            where = {"tax_type": {"$eq": code}}
    return _chroma_search("taxtr_cases", TAXTR_DIR, query, n=n, where=where)


def _search_court(query: str, n: int = 6) -> list[dict]:
    return _chroma_search("court_cases", COURT_DIR, query, n=n)


# ── 1단계: 사실관계 추출 ──────────────────────────────────────────────────────

def _extract_facts(client_summary: str) -> dict:
    prompt = (
        "당신은 세무 전문가다. 아래 의뢰인 사건 요약을 분석해 JSON만 반환하라.\n\n"
        f"[사건 요약]\n{client_summary}\n\n"
        '{"key_facts":"핵심 사실관계(3~5문장)",'
        '"legal_issues":["쟁점1","쟁점2"],'
        '"tax_type":"세목(예:법인세,소득세,부가가치세,국제조세,조세범처벌)",'
        '"search_query":"벡터 검색용 핵심 키워드 문장"}'
    )
    resp = _llm.invoke([HumanMessage(content=prompt)])
    try:
        return json.loads(resp.content.strip().strip("```json").strip("```"))
    except Exception:
        return {
            "key_facts": client_summary,
            "legal_issues": [client_summary],
            "tax_type": "",
            "search_query": client_summary,
        }


# ── 2단계: 유사 판례 검색 ────────────────────────────────────────────────────

def _search_cases(facts: dict) -> dict:
    query     = facts.get("search_query", " ".join(facts.get("legal_issues", [])))
    tax_type  = facts.get("tax_type", "")

    taxtr_hits = _search_taxtr(query, tax_type=tax_type, n=8)
    court_hits = _search_court(query, n=5)

    # 재결례 요약
    taxtr_summaries = []
    for h in taxtr_hits:
        m = h["meta"]
        taxtr_summaries.append({
            "case_no":  m.get("case_no", ""),
            "date":     m.get("decision_date", ""),
            "tax_type": m.get("tax_type", ""),
            "decision": m.get("decision", ""),
            "title":    m.get("title", "")[:100],
            "snippet":  h["doc"][:200],
        })

    # 법원 판례 요약
    court_summaries = []
    for h in court_hits:
        m = h["meta"]
        court_summaries.append({
            "case_no":  m.get("case_no", ""),
            "court":    m.get("court", ""),
            "type":     m.get("case_type", ""),
            "snippet":  h["doc"][:200],
        })

    return {"taxtr": taxtr_summaries, "court": court_summaries}


# ── 3단계: 전략 보고서 생성 ───────────────────────────────────────────────────

def _generate_strategy(client_summary: str, facts: dict, cases: dict) -> str:
    taxtr_str = json.dumps(cases["taxtr"], ensure_ascii=False, indent=2)
    court_str = json.dumps(cases["court"], ensure_ascii=False, indent=2)

    prompt = (
        "당신은 국세청 경력 7년 출신 국제조세 전문 세무사다.\n"
        "아래 의뢰인 사건 정보와 유사 판례를 바탕으로 전략 보고서를 작성하라.\n\n"
        f"[의뢰인 사건 요약]\n{client_summary}\n\n"
        f"[핵심 사실관계]\n{facts.get('key_facts','')}\n\n"
        f"[주요 쟁점]\n" + "\n".join(f"- {i}" for i in facts.get("legal_issues", [])) + "\n\n"
        f"[유사 조세심판 재결례 {len(cases['taxtr'])}건]\n{taxtr_str}\n\n"
        f"[유사 법원 판례 {len(cases['court'])}건]\n{court_str}\n\n"
        "아래 구조로 전략 보고서를 작성하라:\n\n"
        "## 1. 사건 개요\n\n"
        "## 2. 핵심 쟁점 분석\n\n"
        "## 3. 유사 판례·재결례 분석\n"
        "   각 사례별: 사건번호, 결정/판결, 유사점, 이 사건 적용 가능성\n\n"
        "## 4. 전략 권고\n"
        "   ### 경정청구 — 가능 여부, 기한, 예상 승산\n"
        "   ### 조세심판 — 강점·약점, 예상 소요 기간\n"
        "   ### 행정소송 — 강점·약점, 비용·기간\n"
        "   ### 최종 권고: 어떤 경로를 먼저 선택해야 하는가\n\n"
        "## 5. 리스크 포인트\n\n"
        "## 6. 즉시 준비해야 할 증거·서류 체크리스트"
    )
    resp = _llm.invoke([HumanMessage(content=prompt)])
    return resp.content


# ── 퍼블릭 API ────────────────────────────────────────────────────────────────

class StrategyAgent:
    """
    의뢰인 사건 요약 → 재결례+판례 검색 → 전략 보고서

    result = agent.run("다국적기업 이전가격 과세처분 받음. 정상가격 산출방법 다툼.")
    result["final_report"]   # 전략 보고서 (마크다운)
    result["taxtr_cases"]    # 재결례 목록
    result["court_cases"]    # 법원 판례 목록
    """

    def run(self, client_summary: str) -> dict:
        facts = _extract_facts(client_summary)
        cases = _search_cases(facts)
        report = _generate_strategy(client_summary, facts, cases)
        return {
            "final_report": report,
            "key_facts":    facts.get("key_facts", ""),
            "legal_issues": facts.get("legal_issues", []),
            "tax_type":     facts.get("tax_type", ""),
            "taxtr_cases":  cases["taxtr"],
            "court_cases":  cases["court"],
        }


if __name__ == "__main__":
    import sys
    summary = " ".join(sys.argv[1:]) or (
        "법인세 이전가격 과세처분을 받았습니다. "
        "독일 모회사와의 로열티 거래에 대해 정상가격을 부인하고 200억 원 추징 예정입니다. "
        "TNMM 방법을 사용했으나 과세관청이 CUP 방법을 적용했습니다."
    )
    agent = StrategyAgent()
    result = agent.run(summary)
    print(result["final_report"])
