# Lapis Nexus — Legal Reasoning Support System

> 판례를 요약하는 AI가 아닌, 법원의 **논증 구조**를 분석하는 AI

**라이브 서비스: [https://lapis.nexus](https://lapis.nexus)**
Backend: FastAPI on Railway | Frontend: Next.js on Vercel

---

## 왜 만들었나

국세청에서 7년간 세무 검토 및 조사를 담당했습니다.

판례를 다루다 보면 두 가지 작업이 완전히 다르다는 걸 체감합니다.

- "이 판결이 무엇에 관한 것인가" -> 요약으로 해결됨
- "이 판결은 왜 이 결론에 도달했는가" -> 논증 구조를 읽어야 함

기존 법률 AI는 전자에 집중합니다. 실무에서 실제로 필요한 건 후자입니다.
Lapis Nexus는 그 gap을 메우기 위해 만들었습니다.

---

## 무엇을 하는가

판결문 PDF 하나를 입력하면, 다음을 자동으로 수행합니다.

```
판결문 PDF
    |
문단 구조 복원 (단순 텍스트 추출이 아닌 논리 단위 분리)
    |
문장 역할 분류 (사실인정 / 법리 / 판단 / 결��)
    |
논증 블록 생성 (premise -> evidence -> rule -> inference -> conclusion)
    |
쟁점별 구조 분석 (issue framing + issue logic)
    |
법령 판례 인용 연결 (Neo4j 그래프)
    |
3종 보고서 생성 (A: 요약 / B: 구조 브리핑 / C: 실무 인사이��)
```

### 보고서 C — 실무 인사이트 (핵심)

단순 요약이 아니라 변호사·세무사가 **의사결정에 바로 쓸 수 있는** 분석을 생성합니다.

| 항목 | 내용 |
|------|------|
| `one_liner` | 판결 본질을 40자 이내로 압�� |
| `core_issues` | 판결이 실제로 해결한 법적 쟁점 2~4개 |
| `judicial_logic` | 법원의 논증 ��조 + 핵심 법리 포인트 |
| `party_positions` | 납세자 vs 과세관청 포지션 대비 + 구조적 약점 |
| `risk_view` | 리스크 현실화 조건 + 실무 체크리스��� |
| `precedent_signal` | 향후 유사 사건에서 활용 가능한 전략적 시사점 |

---

## 어떻게 발전해왔나

이 프로젝트는 6번의 주요 iteration을 거쳤습니다.

| 버전 | 핵심 변화 | 이유 |
|------|-----------|------|
| v1 (MVP) | RAG 기반 판례 검색 | 일단 검색이라도 되게 |
| v2 | 문단 구조 복원 추가 | 검색 결과가 문맥을 잃어버림 |
| v3 | 10단계 파이프라인 설계 | 요약만으론 논증 구조를 못 잡음 |
| v4 | Neo4j 그래프 DB 도입 | 판례-법령 관계를 RDBMS로 못 표현 |
| v5 | 3종 보고서 + 실무 인사이트 | 구조 분석 결과를 실무에 연결 |
| v6 (현재) | LangGraph 기반 AI Agent 시스템 | 응답 시간 30초 이내, 품질 자동 보장 |

---

## AI Agent 시스템

두 가지 에이전트가 `/agent` 페이지에서 실시간으로 동작합니다. **응답 시간 30초 이내.**

### InsightAgent — 판례 심층 분석

사건번호를 입력하면 해당 판례의 논증 구조를 LangGraph 5-node 파이프라인으로 분석합니다.

```
[Planner]  쿼리 분해 + 검색 전략 수립
    |
[Executor] Neo4j 벡터 검색 (유사 판례 + 쟁점 매핑)
    |
[Insight]  ExportC 심층 분석 (보고서 C 수준)
    |
[Critic]   결과 충분성 자동 검토 -> 필요 시 재검색
    |
[Reporter] 전략 보고서 생성
           - 핵심 요약 / 주요 판례 시사점
           - 승소 전략 / 리스크 경고
           - 실무 체크리스트
```

### SupervisorAgent — 종합 리서치

자연어 질의만으로 판례 DB와 ITCL 법령을 동시에 탐색해 교차 분석 보고서를 생성합니다.

```
[Supervisor] 질의 라우팅 + 에이전트 조율
    |-- CaseSearchAgent  -> Neo4j: 유사 판례 벡터 검색
    |-- PatternAgent     -> Neo4j: 판례 패턴 분석
    |-- LawSearchAgent   -> ITCL 법령 쟁점 조문 검색
    +-- ReportAgent      -> 통합 전략 보고서 생성
```

### Self-Reflection Agent (품질 자동 보장)

```
분석 결과 생성
    |
critique (7개 기준 자동 비평)
    - one_liner 정확성 / core_issues 완결성
    - judicial_logic 논증 충분성 / risk_view 실무 연결성
    |
[score 4+ -> 통과] [score 3 이하 -> refine -> 재비평, 최대 2회]
```

---

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| Backend | FastAPI (Python 3.11) |
| AI Pipeline | LangChain + LangGraph |
| LLM | OpenAI GPT-4.1 |
| Graph DB | Neo4j (판례-법령 관계 그래프) |
| Vector Search | Neo4j Vector Index (코사인 유사도) |
| Cache | JSON + Supabase Storage |
| Auth | Clerk (JWT) |
| Frontend | Next.js 16 (TypeScript) |
| Deployment | Railway (backend) + Vercel (frontend) |

---

## 핵심 설계 원칙

**1. 새로운 해석을 생성하지 않는다**
원문에 존재하는 논증 구조를 명시적으로 드러내는 것이 목표입니다.
AI가 법률 판단을 대신하는 게 아니라, 법률가의 사고 과정을 지원합니다.

**2. 도메인 전문가가 설계한 파이프라인**
각 분석 단계는 국세청 조사 실무에서 실제로 이루어지는 판단 과정을 역설계했습니다.
"AI가 할 수 있는 것"이 아니라 "실무자가 필요로 하는 것"을 기준으로 설계했습니다.

**3. 속도와 품질을 동시에**
LangGraph 비동기 파이프라인으로 응답 시간을 30초 이내로 단축했습니다.
Self-Reflection Agent가 매 분석마다 자동으로 품질을 검증합니다.

---

## 로컬 실행

### 사전 준비

- Python 3.11+
- Neo4j 인스턴스 (로컬 또는 [AuraDB 무료 플랜](https://neo4j.com/cloud/platform/aura-graph-database/))
- OpenAI API 키

### 환경변수 설정

`backend/` 폴더에 `.env` 파일을 생성합니다.

```env
OPENAI_API_KEY=sk-...

NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password

SUPABASE_URL=https://...supabase.co
SUPABASE_SERVICE_ROLE_KEY=...

CLERK_ISSUER=https://...clerk.accounts.dev

# 로컬 테스트 시 Clerk JWT 인증 우회
DEV_MODE=true
```

### 실행

```bash
cd backend

pip install -r requirements.txt

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

-> [http://localhost:8000/docs](http://localhost:8000/docs) 에서 Swagger UI 확인

### API 직접 테스트 (DEV_MODE=true 시 인증 불필요)

```bash
# 종합 리서치 에이전트
curl -X POST http://localhost:8000/api/agent/multi \
  -H "Content-Type: application/json" \
  -d '{"query": "이전가격 과세처분 판례 주요 판단 기준"}'

# 판례 심층 분석 에이전트
curl -X POST http://localhost:8000/api/agent/insight \
  -H "Content-Type: application/json" \
  -d '{"query": "정상가격 산정 기준", "case_id": "2009누513"}'
```

---

## 프로젝트 구조

```
backend/
├── agents/         # AI Agent 시스템
│   ├── insight_agent.py     # InsightAgent (LangGraph 5-node)
│   ├── multi_agent.py       # SupervisorAgent (멀티 에이전트)
│   └── self_reflection.py   # Self-Reflection Agent
├── bravo/          # 10단계 판례 분석 파이프라인 (stage0~stage10)
├── export/         # 3종 보고서 생성 (A/B/C)
├── db/             # Neo4j 그래프 DB 클라이언트
├── ITCL/           # 법령 구조화 모듈
├── routers/        # FastAPI 엔드포인트
└── utils/          # 캐시 관리
```

---

## 만든 사람

국세청 경력 7년 -> Legal AI Product Builder

세무조사 현장에서 판례와 법령이 실제로 어떻게 작동하는지 경험했습니다.
그 경험을 바탕으로 법률가가 실제로 필요로 하는 AI 시스템을 직접 설계하고 구현하고 있습니다.

- Email: seungmiyoon0723@gmail.com
