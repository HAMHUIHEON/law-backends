# Lapis Nexus — 에이전트 아키텍처 & 데이터 소스 전체 현황

> 업데이트: 2026-06-14  
> 백엔드 repo: `HAMHUIHEON/law-backend` (Railway)  
> 프론트 repo: `HAMHUIHEON/law-frontend` (Vercel)

---

## 전체 데이터 소스 지도

| # | 데이터 소스 | 저장소 | 건수 | 임베딩 | 접근 방식 |
|---|-----------|--------|------|--------|-----------|
| 1 | Neo4j — 국제조세 판례 그래프 | AuraDB Cloud | Case수백+, Paragraph 112K, Article 41K | `text-embedding-3-small` (1536d) | LegalGraphSearch, 실시간 벡터 쿼리 |
| 2 | Chroma `taxlaw_prec` | Railway Volume (`/app/chroma`) | 32,628건 | text-embedding-3-small | NTS taxlaw.nts.go.kr 법원 판례 요약+원문 |
| 3 | Chroma `taxtr_cases` | Railway Volume | 2,463건 | text-embedding-3-small | 조세심판원 재결례 |
| 4 | Chroma `law_articles` | Railway Volume | 6,687 조문 | text-embedding-3-small | 14개 세법 조문 전문 (국조법 353조 포함) |
| 5 | Chroma `pdf_court_cases` | Railway Volume | 500+건 (embed 중) | text-embedding-3-small | uploads/+CASE/ PDF 원문 판례 전문 |
| 6 | `issue_index/issue_vectors.pkl` | Docker 이미지 | 1,021 쟁점 / 270건 | text-embedding-3-small | bravo 파이프라인 구조화 분석 결과 |

### Chroma 현황 상세

```
taxlaw_prec   : 32,628건  (case_no, tax_type, decision, attr_yr, title)
taxtr_cases   :  2,463건  (dem_no, case_no, tax_type, decision, related_laws)
law_articles  :  6,687 조문 (slug, law_name, scope, article_no, title)
  └─ slugs: gukse_basic(289) corporate_tax(613) income_tax(989) vat(301)
            gukse_collection(329) customs(1008) capital_market(1210)
            inheritance_tax(304) joseteukrejehan(1079) itcl(353)
            tax_crime(23) tax_crime_proc(23) individual_consumption(104)
            comprehensive_realty(62)
pdf_court_cases: 500+건   (case_id, court, case_no, tax_type, source=pdf)
```

### 임베딩 모델: OpenAI `text-embedding-3-small` (1536차원)

모든 Chroma 컬렉션과 Neo4j 벡터 인덱스, issue_vectors.pkl 전부 동일 모델 사용.  
쿼리도 반드시 같은 모델로 임베딩해야 함 (`db/chroma_search.py::_get_ef()` 참조).

---

## 에이전트 × 데이터 소스 매핑

| 에이전트 | Neo4j | taxlaw_prec | taxtr_cases | law_articles | pdf_court_cases | issue_cache |
|---------|:-----:|:-----------:|:-----------:|:------------:|:---------------:|:-----------:|
| MULTI (SupervisorAgent) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| INSIGHT (InsightAgent) | ✓ | — | — | — | — | — |
| TAXLAW_PREC (TaxlawPrecAgent) | — | ✓ | — | — | — | — |
| TAXTR (TaxtrAgent) | — | — | ✓ | — | — | — |
| STRATEGY (StrategyAgent) | — | ✓ | ✓ | ✓ | — | — |
| REBUTTAL (RebuttalAgent) | — | ✓(승소) | ✓(인용) | ✓ | — | — |
| TREND (TrendAgent) | — | ✓ | — | — | — | — |
| ITCL (ITCLAgent) | ✓(선택) | ✓ | — | ✓(itcl) | — | — |
| RISK (RiskAgent) | — | ✓ | ✓ | ✓ | — | — |

**gap 분석**: INSIGHT, TAXLAW_PREC, TAXTR, STRATEGY, REBUTTAL, TREND, ITCL, RISK 에이전트들은  
`pdf_court_cases` 및 `issue_cache`를 참조하지 않음 → 향후 개선 필요

---

## 왜 ITCL은 Neo4j와 Chroma 두 곳에 있는가?

| | Neo4j | Chroma `law_articles` |
|--|------|----------------------|
| 저장 내용 | ITCL 법령 구조 + SemanticIssue (쟁점) + ReasoningStep (근거) | ITCL 조문 전문 (LAW 353조) |
| 검색 방식 | 벡터 쿼리 → `itcl_issue_embedding` 인덱스 | 텍스트 임베딩 유사도 |
| 용도 | 쟁점-논거 추적, 챕터별 구조 탐색 (ITCLAgent) | 조문 전문 검색 (multi_agent search_law) |
| 접근 에이전트 | ITCLAgent, MULTI(search_cases) | MULTI(search_law), STRATEGY |

두 저장소는 역할이 다름. Neo4j는 **구조화 그래프** (챕터→쟁점→논거→조문 연결),  
Chroma는 **전문 텍스트 검색** (단순 유사도).

---

## 에이전트 상세

### 1. SupervisorAgent (`MULTI`) — 종합 리서치

**파일**: `backend/agents/multi_agent.py`  
**엔드포인트**: `POST /api/agent/multi`  
**입력**: `{ "query": "string" }`

LangGraph `StateGraph` — Supervisor가 질문 분석 → 6개 도구 중 필요한 것 선택 → 병렬 실행 → Synthesizer 통합 보고서.

```
START
  └─▶ supervisor  ── JSON: {tools, law_query, prec_query, taxtr_query}
        ├─▶ search_cases         ── Neo4j 벡터 + 패턴 (국제조세 특화)
        ├─▶ search_law           ── Chroma law_articles (14개 세법 조문, 국조법 포함)
        ├─▶ search_taxlaw_prec   ── Chroma taxlaw_prec (NTS 법원 판례 32K)
        ├─▶ search_taxtr         ── Chroma taxtr_cases (조세심판 2,463건)
        ├─▶ search_pdf_cases     ── Chroma pdf_court_cases (PDF 원문 판례)
        └─▶ search_issue_cache   ── issue_vectors.pkl (구조화 쟁점 1,021건)
        └─▶ synthesizer          ── 통합 실무 보고서
END
```

#### ITCL/이전가격 쿼리 처리

`_ITCL_KEYWORDS`에 "정상이자율", "이전가격", "국제조세", "정상가격", "국조법" 등 포함.  
키워드 감지 시:
- `search_law` → 추가로 `_ITCL_LAW_QUERY` 전용 쿼리 실행 후 결과 병합
- `search_taxlaw_prec` → 추가로 `_ITCL_PREC_QUERY` 전용 쿼리 실행 후 병합
- `search_pdf_cases` → ITCL 전용 쿼리로 검색

#### Supervisor 도구 선택 규칙

| 질문 유형 | 선택 도구 |
|-----------|-----------|
| 이전가격·국제조세·정상가격 | 6개 모두 + ITCL fallback |
| 판례·법원 결정 | search_cases + search_taxlaw_prec |
| 조세심판·재결례 | search_taxtr |
| 조문·법령 해석 | search_law |
| 종합 분석·전략 | 6개 모두 |

---

### 2. InsightAgent (`INSIGHT`) — 판례 심층 분석

**파일**: `backend/agents/insight_agent.py`  
**엔드포인트**: `POST /api/agent/insight`  
**입력**: `{ "query": "string", "case_id": "string (선택)" }`  
**데이터**: Neo4j LegalGraphSearch 전용

Plan → Execute → Reflect → Report 4단계.  
`case_id` 제공 시 ExportC 수준 deep insight 추가.

---

### 3. TaxlawPrecAgent (`TAXLAW_PREC`) — NTS 법원 판례

**파일**: `backend/agents/taxlaw_prec_agent.py`  
**엔드포인트**: `POST /api/prec/ask`  
**데이터**: Chroma `taxlaw_prec` (32,628건)

질문 → 벡터 검색 (top-8) → GPT-4.1 답변

추가 엔드포인트:
- `GET /api/prec/stats` — DB 현황
- `POST /api/prec/search` — 벡터 검색 (tax_type, decision 필터 가능)
- `GET /api/prec/case/{doc_id}` — 판례 전문
- `GET /api/prec/trend` — 연도별 트렌드
- `POST /api/prec/winning` — 납세자 승소 판례 검색

---

### 4. TaxtrAgent (`TAXTR`) — 조세심판 재결례

**파일**: `backend/agents/taxtr_agent.py`  
**엔드포인트**: `POST /api/taxtr/ask`  
**데이터**: Chroma `taxtr_cases` (2,463건)

TaxlawPrecAgent 동일 패턴. decision: 기각/인용/취소/일부인용/경정/각하

---

### 5. StrategyAgent (`STRATEGY`) — 불복전략

**파일**: `backend/agents/strategy_agent.py`  
**엔드포인트**: `POST /api/strategy/strategy`  
**입력**: `{ "summary": "사건 요약" }` 또는 **`POST /api/strategy/strategy/upload` (PDF/TXT 파일 업로드)**  
**데이터**: Chroma 3종 (taxlaw_prec 승소 필터, taxtr 인용 필터, law_articles)

---

### 6. RebuttalAgent (`REBUTTAL`) — 반론초안

**파일**: `backend/agents/rebuttal_agent.py`  
**엔드포인트**:
- `POST /api/strategy/rebuttal` — 텍스트 입력 `{ "disposition_text": "..." }`
- `POST /api/strategy/rebuttal/upload` — **PDF/TXT 파일 업로드** (신규 추가)

**데이터**: Chroma 3종 (taxlaw_prec 승소 필터, taxtr 인용/취소 필터, law_articles)

흐름: ClaimExtractor → CaseSearcher → DraftWriter → Reflector  
- ClaimExtractor: 과세처분 이유서에서 과세관청 주장 + 핵심 쟁점 추출
- CaseSearcher: 납세자 승소/인용 판례 검색 (filter_winning=True)
- DraftWriter: 이의신청서·심판청구서 초안 생성
- Reflector: 자기 검토 + 보완

---

### 7. TrendAgent (`TREND`) — 판례 트렌드

**파일**: `backend/agents/trend_agent.py`  
**엔드포인트**: `POST /api/trend/ask`  
**데이터**: Chroma `taxlaw_prec` 연도별 집계

---

### 8. ITCLAgent (`ITCL`) — 국제조세법 전문

**파일**: `backend/agents/itcl_agent.py`  
**엔드포인트**: `POST /api/itcl/ask`  
**데이터**: Chroma `taxlaw_prec` + `law_articles(itcl)` + Neo4j ITCLSearch (선택)

---

### 9. RiskAgent (`RISK`) — 법령 개정 리스크

**파일**: `backend/agents/risk_agent.py`  
**엔드포인트**: `POST /api/strategy/risk`  
**데이터**: Chroma 3종

---

## 현재 커버하지 못하는 데이터 (개선 계획)

| 데이터 | 현황 | 개선 방향 |
|--------|------|-----------|
| 사전질의 법령해석 (국세청) | 미임베딩 | `taxlaw_prec` 추가 또는 새 컬렉션 |
| 과세자문기준 | 미임베딩 | 새 컬렉션 `advisory_opinions` |
| 불복심판 결정문 전문 (PDF) | 일부 uploads/ 있으나 미임베딩 | `pdf_court_cases`에 통합 예정 |
| 세무조사 실무 메뉴얼 | 미임베딩 | 참고자료 컬렉션 |
| OECD BEPS 가이드라인 | 영문 PDF만 있음 | 번역 후 임베딩 필요 |

---

## Railway 배포 구조

```
GitHub push → Railway auto-deploy (주의: health check 실패 시 rollback)
railway up   → 로컬 파일 업로드 → 안정적 배포 (권장)
```

배포 시 실행 순서 (`start.py`):
1. `init_chroma.py` — `CHROMA_DOWNLOAD_URL`에서 Chroma tar.gz 다운로드 (`/app/chroma`)
2. `scripts/add_itcl_to_chroma.py` — ITCL 조문 353건 추가 (이미 있으면 스킵)
3. `uvicorn main:app` — FastAPI 서버 시작

Railway 환경변수:
- `CHROMA_DIR=/app/chroma` — init_chroma, add_itcl, chroma_search 전부 이 경로 사용
- `CHROMA_DOWNLOAD_URL` — GitHub releases에서 `chroma_v2.tar.gz` 다운로드
- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` — `a0c49c04` AuraDB 인스턴스

---

## Chroma 업데이트 절차

로컬 Chroma를 수정(임베딩 추가)한 후 Railway에 반영하려면:

```powershell
# 1. 로컬 Chroma를 tar.gz로 압축
cd 29_FINAL/vector_db
tar -czf chroma_v2.tar.gz chroma/

# 2. GitHub releases에 업로드 (tag: chroma-v2)
gh release upload chroma-v2 chroma_v2.tar.gz --clobber --repo HAMHUIHEON/law-backend

# 3. Railway 재배포 (CHROMA_VERSION="v2"이므로 다운로드 스킵됨 — 버전 올려야 갱신)
# init_chroma.py의 CHROMA_VERSION을 "v3"으로 올린 후 railway up
```

**주의**: `CHROMA_VERSION`을 올려야 Railway가 기존 캐시 삭제 후 재다운로드함.

---

## 로컬 개발

```powershell
# 환경 변수
$python = poetry env info --path 셸에서 확인 후 Scripts\python.exe 사용

# 백엔드
Set-Location 29_FINAL/backend
& $python -m uvicorn main:app --host 127.0.0.1 --port 8000

# PDF 임베딩 (로컬 Chroma 업데이트)
& $python scripts/embed_pdf_cases.py --dirs uploads ../CASE

# 프론트엔드
Set-Location 29_FINAL/law-frontend
npm run dev
```

`.env` 위치: `29_FINAL/.env` (gitignore됨)

---

## Git 구조

- `C:\Users\LG\Documents\langchain-kr\` — teddylee777/langchain-kr (상위, 강의 자료)
- `C:\Users\LG\Documents\langchain-kr\29_FINAL\` — **HAMHUIHEON/law-backend** (백엔드)
- `C:\Users\LG\Documents\langchain-kr\29_FINAL\law-frontend\` — **HAMHUIHEON/law-frontend**

백엔드 git 작업은 반드시 `29_FINAL/` 폴더 안에서 수행.
