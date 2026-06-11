# Lapis Nexus — Claude 작업 가이드

## 프로젝트 정체성

**프로젝트명**: Lapis Nexus  
**목적**: 한국 세법 판결문 AI 분석 시스템. 판결문에서 법령 인용을 추출하고, 역사적 버전의 조문을 조회하며, 쟁점-논증 구조를 그래프로 표현.  
**사용자**: 윤승미 — 국세청 7년 경력, 국제조세(이전가격, GLOBE) 전문, Neo4j/Python/LangChain 능숙.

---

## 일하는 원칙

1. **확인 금지**: "해도 될까요?", "진행할까요?", "확인해주세요" 절대 금지. 무엇을 할지 한 줄로 설명하고 바로 실행.
2. **근본 해결**: 우회/임시방편/회피보다 근본 원인을 파악하고 정도로 해결.
3. **긴급 승인만 질문**: 개인정보 노출, 구조 설계 갈림길(복구 불가 수준), 외부 서비스 비용 폭증 예상 시에만 물어볼 것.
4. **간결하게**: 설명은 결과 중심으로 짧게. 코드 주석은 WHY가 비자명할 때만.

---

## 기술 스택

| 구성요소 | 내용 |
|---------|------|
| DB | Neo4j AuraDB (cloud) — `NEO4J_URI` env에서 로드 |
| LLM | GPT-4.1 (`gpt-4.1`) via LangChain ChatOpenAI |
| 법령 API | 법령정보센터 DRF API, OC=`seungmi0723`, HTTP (not HTTPS) |
| 백엔드 | FastAPI (`backend/main.py`) |
| 프론트 | Next.js (`law-frontend/`) |
| 판결문 파이프라인 | `bravo/` — 10단계 구조화 파이프라인 |
| Python 환경 | pypoetry venv `C:\Users\LG\AppData\Local\pypoetry\Cache\virtualenvs\langchain-kr-0bF25OO7-py3.11\Scripts\python.exe` |

---

## 프로젝트 구조 (핵심 폴더만)

```
29_FINAL/
├── app.py                    # FastAPI 앱 진입점 (판결문 업로드·파이프라인 API)
├── backend/
│   ├── main.py               # 백엔드 FastAPI (Clerk 인증, 라우터 등록)
│   ├── bravo/                # 판결문 10단계 분석 파이프라인
│   │   ├── stage10_citation.py  # 법령 인용 추출 + 버전 매칭
│   │   └── full_pipeline.py
│   ├── utils/
│   │   └── statute_version.py   # 법령 버전 조회 (핵심 유틸)
│   └── db/
│       ├── graph_ingest.py
│       └── itcl_search.py
├── ITCL/                     # 국제조세조정법 처리 파이프라인
│   ├── convert_drf_law_to_unified.py  # DRF JSON → unified schema
│   ├── pipeline.py           # 5단계 파이프라인 (unify→norm→semantic→reasoning→ingest)
│   ├── ingest_norm_itcl.py   # Neo4j norm 인제스트
│   ├── ingest_logic_itcl.py  # Neo4j logic 인제스트
│   ├── chain.py              # LLM 체인들
│   ├── models.py             # Pydantic 모델 + 스키마
│   └── domain_assign.py      # 챕터별 도메인 태그 맵
├── ITCL_integrated/          # 법+령+규칙 통합 분석
│   ├── pipeline.py           # 통합 파이프라인
│   ├── ingest.py             # IntegratedSnapshot 인제스트
│   └── models.py
├── law/                      # 법령 JSON DB (635MB, git 제외)
│   ├── gukse_basic/{law,decree}/       # 국세기본법
│   ├── gukse_collection/{law,decree,rule}/  # 국세징수법
│   ├── corporate_tax/{law,decree,rule}/     # 법인세법
│   ├── income_tax/{law,decree,rule}/        # 소득세법
│   ├── vat/{law,decree,rule}/               # 부가가치세법
│   ├── tax_crime/law/                       # 조세범처벌법
│   ├── tax_crime_proc/{law,decree}/         # 조세범처벌절차법
│   └── itcl/{law,decree,rule}/              # 국제조세조정법
│   각 폴더: MST_*.json (개별 버전) + _version_index.json (공포번호→버전 인덱스)
├── scripts/                  # 빌드·운영 스크립트 (루트 정리용)
│   ├── build_law_history_db.py       # DRF API 전체 다운로드
│   ├── build_law_index_only.py       # 인덱스 재빌드
│   ├── build_itcl_historical_snapshots.py  # ITCL 역사 스냅샷 Neo4j 빌드
│   ├── setup_constraints.py          # Neo4j 제약조건 설정
│   └── ...
├── RISK/                     # 개정 리스크 체인 (stub 수준)
├── bravo/                    # 판결문 파이프라인 (app.py용)
├── export/                   # 보고서 생성 (A/B/C 유형)
└── cache/                    # LLM 결과 캐시 (git 제외)
```

---

## Neo4j 그래프 스키마

### Norm 레이어 (법/령/규칙 구조)

```
Law (scope, id)
└─ HAS_VERSION
   └─ LawVersion (scope, law_id, version_key)   ← version_key = "공포일자_공포번호"
      └─ HAS_CHAPTER
         └─ Chapter (scope, law_id, version_key, id)   ← law_id 포함 (충돌 방지)
            └─ HAS_SECTION / HAS_ARTICLE
               └─ Article (scope, law_id, version_key, id)
                  ├─ HAS_PARAGRAPH → Paragraph
                  └─ NORM_UNIT_OF ← NormUnit
                       └─ REFERS_TO → LawTarget → RESOLVES_TO → Article
```

**⚠️ 중요**: Chapter/Article 등 중간 노드에 `law_id` 포함. 다중 법령 공존 시 충돌 방지.  
`scope` = "LAW" | "DECREE" | "RULE"  
`law_id` = 법령 고유 ID (법령MST 또는 공포번호 기반)

### Integrated 레이어 (통합 의미 분석)

```
IntegratedSnapshot (scope="INTEGRATED", set_key)
  set_key 형식: "LAW_{date}_{no}__DECREE_{date}_{no}__RULE_{date}_{no}"
└─ HAS_INTEGRATED_CHAPTER
   └─ IntegratedChapter (scope, set_key, chapter_id)
      ├─ DERIVED_FROM → Chapter (LAW/DECREE/RULE)
      ├─ HAS_INTEGRATED_SEMANTIC → SemanticIssue
      └─ HAS_INTEGRATED_REASONING → ReasoningIssue
           ├─ ALIGNED_WITH → SemanticIssue
           └─ HAS_STEP → ReasoningStep
                └─ BASED_ON → Article | LawTarget
```

---

## 법령 버전 조회 흐름 (`statute_version.py`)

판결문 citation → `resolve_citation_version()` → 3단계 조회:

1. **ITCL 계열** → Neo4j `IntegratedSnapshot`에서 set_key 매칭
2. **7개 세법** → 로컬 `law/{slug}/{kind}/_version_index.json` 에서 공포번호 매칭
3. **나머지** → GPT-4.1 지식 기반 (uncertainty 플래그)

인덱스 구조: `공포번호(lstrip "0") → {version_key, pdate, pno, eff_date, law_name, mst, file}`

---

## 법령 slug 매핑

| 법령 | slug | 보유 종류 |
|------|------|---------|
| 국세기본법 | gukse_basic | law, decree |
| 국세징수법 | gukse_collection | law, decree, rule |
| 법인세법 | corporate_tax | law, decree, rule |
| 소득세법 | income_tax | law, decree, rule |
| 부가가치세법 | vat | law, decree, rule |
| 조세범처벌법 | tax_crime | law (34버전, 시행령 없음) |
| 조세범처벌절차법 | tax_crime_proc | law, decree |
| 국제조세조정법 | itcl | law, decree, rule |

---

## 현재 완료된 작업

- [x] 7개 세법 역사적 버전 전체 다운로드 (`law/` 폴더, 1,786개 JSON)
- [x] `_version_index.json` 빌드 완료 (1,781개 항목)
- [x] `statute_version.py` 3단계 조회 연동
- [x] ITCL 역사적 IntegratedSnapshot 65개 Neo4j 빌드 (2010~2025)
- [x] 판결문 파이프라인 bravo/ 10단계 구현
- [x] 법령 개정 리스크 체인 stub (RISK/chain.py)

---

## 진행 중 / 다음 할 일

### 🔴 최우선: 7개 세법 Neo4j 인제스트 (Law_7 파이프라인)

**설계 결정 (확정)**:
- Phase 1: 현행 버전만 Norm 인제스트 (구조 + LLM NormUnit/CrossRef)
- Phase 2: 법+령+규칙 통합 Integrated 인제스트 (SemanticIssue/ReasoningIssue)
- Phase 3: 법령 간 CrossRef 해소 (EXTERNAL → 실제 Article 노드 연결)
- **DB 초기화 후 새 스키마** (Chapter 등 키에 `law_id` 추가)

**처리 순서**: 국세기본법 → 법인세법 → 소득세법 → 부가가치세법 → 국세징수법 → 조세범처벌법/절차법

**새로 만들 폴더**: `LAW_7/`  
파이프라인: ITCL/ + ITCL_integrated/ 코드 85% 재사용, 도메인 맵만 법별로 신규 작성

### 🟡 에이전트 개발 (인제스트 완료 후)

1. **법령 개정 리스크 알림** — `RISK/chain.py` 확장, 판례 재평가
2. **의뢰인 사건 전략** — 유사 판례 매칭 → 전략 권고 (경정청구/심판/소송)
3. **판례 트렌드** — 연도별·법원별 승소율 집계
4. **반론 초안** — 과세처분 이유서 입력 → 판례 기반 반론 생성
5. **ITCL 전문** — `ITCL/` + `ITCL_integrated/` 활용
6. **판례 비교** — 두 판결 issue_logic_chains 구조 비교

---

## 법령정보센터 DRF API

```python
# MST 목록 (HTML 파싱)
GET http://www.law.go.kr/DRF/lawSearch.do
  ?OC=seungmi0723&target=lsHistory&type=HTML&query={법령명}&display=100&page=1

# 개별 버전 JSON
GET http://www.law.go.kr/DRF/lawService.do
  ?OC=seungmi0723&target=law&MST={mst}&type=JSON
```

**주의**: `requests.Session()` 재사용 시 ConnectionResetError 발생. 요청마다 새 Session 생성 필수.

---

## 자주 쓰는 명령

```bash
# 법령 다운로드
python scripts/build_law_history_db.py --download --law 국세기본법

# 인덱스 재빌드
python scripts/build_law_index_only.py --law 국세기본법

# Neo4j 제약조건 설정
python scripts/setup_constraints.py

# ITCL 스냅샷 빌드
python scripts/build_itcl_historical_snapshots.py
```

---

## 환경변수 (.env)

```
NEO4J_URI=neo4j+s://3dfa7316.databases.neo4j.io
NEO4J_PASSWORD=...
OPENAI_API_KEY=...
CLERK_ISSUER=...
```
