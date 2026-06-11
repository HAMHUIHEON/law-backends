
#
"""
29_FINAL.cypher의 Docstring
IntegratedSnapshot에 valid_from / valid_to가 date 타입으로 정확히 들어가 있어야 이 쿼리가 동작함.

MATCH (s:IntegratedSnapshot {scope:"INTEGRATED"})
RETURN
  s.set_key,
  s.valid_from,
  s.valid_to,
  s.promulgated_at,
  s.effective_at
ORDER BY s.valid_from;
	s.valid_from	s.valid_to	s.promulgated_at	s.effective_at
"LAW_20201222_17651__DECREE_20210217_31448__RULE_20210316_00840"	"20210316"	"20211230"	"20201222"	"20210101"
"LAW_20201222_17651__DECREE_20211228_32274__RULE_20210316_00840"	"20211230"	"20220101"	"20201222"	"20210101"
"LAW_20211221_18588__DECREE_20211228_32274__RULE_20210316_00840"	"20220101"	"20220215"	"20211221"	"20220101"
"LAW_20211221_18588__DECREE_20220215_32423__RULE_20210316_00840"	"20220215"	"20220318"	"20211221"	"20220101"
"LAW_20211221_18588__DECREE_20220215_32423__RULE_20220318_00901"	"20220318"	"20221227"	"20211221"	"20220101"
"LAW_20211221_18588__DECREE_20221227_33140__RULE_20220318_00901"	"20221227"	"20230101"	"20211221"	"20220101"
"LAW_20221231_19191__DECREE_20221227_33140__RULE_20220318_00901"	"20230101"	"20230228"	"20221231"	"20230101"
"LAW_20221231_19191__DECREE_20230228_33272__RULE_20220318_00901"	"20230228"	"20230320"	"20221231"	"20230101"
"LAW_20221231_19191__DECREE_20230228_33272__RULE_20230320_00983"	"20230320"	"20240101"	"20221231"	"20230101"
"LAW_20231231_19928__DECREE_20231229_34064__RULE_20230320_00983"	"20240101"	"20240229"	"20231231"	"20240101"
"LAW_20231231_19928__DECREE_20240229_34264__RULE_20230320_00983"	"20240229"	"20240322"	"20231231"	"20240101"


WITH "20211219" AS 기준일
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED"})
WHERE s.valid_from <= 기준일
  AND (s.valid_to IS NULL OR s.valid_to > 기준일)
RETURN
  s.set_key,
  s.valid_from,
  s.valid_to
ORDER BY s.valid_from;

s.set_key	s.valid_from	s.valid_to
"LAW_20201222_17651__DECREE_20210217_31448__RULE_20210316_00840"	"20210316"	"20211230"

A IntegratedSnapshot / set_key 관리 쿼리 (메타 레벨)

A-1. 전체 set_key 목록
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED"})
RETURN s.set_key
ORDER BY s.set_key;

A-2. set_key + 유효기간 디버그
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED"})
RETURN
  s.set_key,
  s.valid_from,
  s.valid_to,
  s.promulgated_at,
  s.effective_at
ORDER BY s.valid_from DESC;

A-3. 특정 set_key 하나 보기
MATCH (s:IntegratedSnapshot {
  scope:"INTEGRATED",
  set_key:"LAW_20201222_17651__DECREE_20210217_31448__RULE_20210316_00840"
})
RETURN s;
👉 용도: 스냅샷 존재/기간/메타 검증
👉 시각화 목적 ❌ / 상태 점검용

B Integrated ↔ Source Chapter 구조 검증 (핵심 연결)
B-1. IntegratedChapter → LAW/DECREE/RULE 매핑 확인
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic)
      -[:DERIVED_FROM]->(c:Chapter)
RETURN
  ic.chapter_id,
  c.scope        AS source_scope,
  c.version_key,
  c.id           AS chapter_id
ORDER BY ic.chapter_id, source_scope;
👉 기대: chapter_id당 LAW / DECREE / RULE 3줄
👉 용도: 구조 무결성 검증

C Integrated Semantic / Reasoning 정합성 검증
C-1. 챕터별 Semantic 묶임 확인
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic)
OPTIONAL MATCH (ic)-[:HAS_INTEGRATED_SEMANTIC]->(sem:SemanticIssue)
WHERE sem.chapter_id = ic.chapter_id
RETURN
  ic.chapter_id,
  count(sem) AS semantic_cnt
ORDER BY ic.chapter_id;

C-2. Semantic 오염 탐지
MATCH (ic:IntegratedChapter {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_SEMANTIC]->(sem:SemanticIssue)
WHERE sem.chapter_id <> ic.chapter_id
RETURN ic.chapter_id, sem.chapter_id, sem.issue_id;

C-3. Reasoning ↔ Semantic alignment 검증
MATCH (r:ReasoningIssue {scope:"INTEGRATED", set_key:$set_key})
      -[a:ALIGNED_WITH]->(s:SemanticIssue {scope:"INTEGRATED", set_key:$set_key})
WHERE r.chapter_id = s.chapter_id
RETURN
  r.chapter_id,
  r.issue_title,
  s.issue_id,
  a.confidence
ORDER BY r.chapter_id;

C-4. Alignment 오염 탐지
MATCH (r:ReasoningIssue {scope:"INTEGRATED", set_key:$set_key})
      -[:ALIGNED_WITH]->(s:SemanticIssue {scope:"INTEGRATED", set_key:$set_key})
WHERE r.chapter_id <> s.chapter_id
RETURN
  r.chapter_id,
  r.issue_title,
  s.chapter_id,
  s.issue_id;


👉 용도: Integrated logic 신뢰성 보장

D Norm(법/령/규칙) ingest 구조 검증
D-1. Law → Chapter → Article
MATCH (l:Law)-[:HAS_VERSION]->(v:LawVersion)
      -[:HAS_CHAPTER]->(c:Chapter)
      -[:HAS_ARTICLE]->(a:Article)
RETURN
  l.scope,
  v.version_key,
  c.id,
  count(a) AS article_cnt
ORDER BY l.scope, v.version_key;

D-2. NormUnit 연결 확인
MATCH (n:NormUnit)-[:NORM_UNIT_OF]->(a:Article)
RETURN
  n.scope,
  n.version_key,
  count(n) AS norm_cnt
ORDER BY n.scope, n.version_key;

E Integrated “구조 시각화” 쿼리들 (네 핵심 관심사)
E-1. IntegratedChapter 기준 장/절/관/조문 펼치기
MATCH (s:IntegratedSnapshot {set_key:$set_key})
-[:HAS_INTEGRATED_CHAPTER]->(ic {chapter_id:"CH_2"})
-[:DERIVED_FROM]->(c:Chapter)

OPTIONAL MATCH (c)-[:HAS_ARTICLE]->(a1)
OPTIONAL MATCH (c)-[:HAS_SECTION]->(sec)
OPTIONAL MATCH (sec)-[:HAS_ARTICLE]->(a2)
OPTIONAL MATCH (sec)-[:HAS_SUBDIVISION]->(sd)
OPTIONAL MATCH (sd)-[:HAS_ARTICLE]->(a3)

RETURN ic, c, sec, sd, a1, a2, a3;


👉 완전 시각화용 / 구조 감상용

F Integrated 사고 흐름 시각화 (Reasoning 중심)
F-1. Reasoning ↔ Semantic 사고 맵
MATCH (snap:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic {chapter_id:"CH_2"})
      -[:HAS_INTEGRATED_REASONING]->(r)
      -[:ALIGNED_WITH]->(sem)
RETURN ic, r, sem;

F-2. ReasoningStep ↔ Article 연결 (가장 중요)
MATCH (rs:ReasoningStep {scope:"INTEGRATED"})-[:BASED_ON]->(a:Article)
RETURN
  rs.chapter_id,
  rs.issue_title,
  rs.step_id,
  rs.step_type,
  rs.description,
  a.id,
  a.title
ORDER BY rs.chapter_id, rs.issue_idx, rs.step_id;

G 역방향 조회 / 청소 / 활용 쿼리
G-1. 특정 조문이 Integrated 어디서 쓰였는지
MATCH (a:Article {id:"ART_65"})<-[:BASED_ON]-(rs:ReasoningStep {scope:"INTEGRATED"})
RETURN
  rs.chapter_id,
  rs.issue_title,
  rs.step_id,
  rs.description;

G-2. 아직 Article로 못 간 citation
MATCH (rs:ReasoningStep {scope:"INTEGRATED"})-[:BASED_ON]->(t:IntegratedLawTarget)
RETURN
  rs.chapter_id,
  rs.issue_title,
  rs.step_id,
  t.target_scope,
  t.name;



🧭 소비자 관점 시각화 쿼리 전체 지도
① 법 구조를 보는 시각화
② 통합 사고(Reasoning–Semantic)를 보는 시각화
③ 법과 사고가 만나는 지점을 보는 시각화
④ 탐색·디버깅·확인용 그래프

① 📚 법 구조 시각화 (Structure View)

“법이 어떻게 생겼는가”

✅ ①-A. IntegratedChapter 기준 장/절/관/조문 펼치기 ← 네가 말한 E-1
MATCH (s:IntegratedSnapshot {set_key:$set_key})
-[:HAS_INTEGRATED_CHAPTER]->(ic {chapter_id:"CH_2"})
-[:DERIVED_FROM]->(c:Chapter)

OPTIONAL MATCH (c)-[:HAS_ARTICLE]->(a1)
OPTIONAL MATCH (c)-[:HAS_SECTION]->(sec)
OPTIONAL MATCH (sec)-[:HAS_ARTICLE]->(a2)
OPTIONAL MATCH (sec)-[:HAS_SUBDIVISION]->(sd)
OPTIONAL MATCH (sd)-[:HAS_ARTICLE]->(a3)

RETURN ic, c, sec, sd, a1, a2, a3;


용도
소비자가 “법 조문 트리”를 직관적으로 이해
대학원생/연구자에게 매우 좋음
법 그 자체의 형태를 보는 뷰

✅ ①-B. LAW / DECREE / RULE 각각 펼쳐보기
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic {chapter_id:"CH_2"})
MATCH (ic)-[:DERIVED_FROM]->(c:Chapter)
OPTIONAL MATCH (c)-[r:HAS_SECTION|HAS_ARTICLE]->(n)
RETURN ic, c, r, n;


용도
“같은 2장이라도 법/령/규칙이 이렇게 다르다”
비교 학습 / 구조 차이 인식
E-1보다 ‘비교적’인 구조 뷰

② 🧠 통합 사고 시각화 (Reasoning–Semantic View)
“이 장에서 어떤 사고가 일어나는가”
✅ ②-A. Reasoning ↔ Semantic 사고 연결 (핵심)
MATCH (snap:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic {chapter_id:"CH_2"})
      -[:HAS_INTEGRATED_REASONING]->(r)
      -[:ALIGNED_WITH]->(sem:SemanticIssue)
RETURN ic, r, sem;


용도
이 장에서의 논리 지도
“쟁점 ↔ 의미” 관계 한눈에 보기
네 SaaS의 정체성에 가장 가까운 뷰

✅ ②-B. SemanticIssue만 집중해서 보기
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic {chapter_id:"CH_2"})
      -[:HAS_INTEGRATED_SEMANTIC]->(sem:SemanticIssue)
RETURN ic, sem;

용도
“이 장의 쟁점 목록”
사고 맵의 인덱스 역할
학습·요약에 좋음

③ ⚖️ 법 ↔ 사고 연결 시각화 (Most Important)
“어떤 사고가 어떤 조문을 근거로 삼는가”

✅ ③-A. ReasoningStep ↔ Article 연결 (가장 중요)
MATCH (rs:ReasoningStep {scope:"INTEGRATED"})-[:BASED_ON]->(a:Article)
RETURN rs, a
LIMIT 50;

또는 챕터 한정:
MATCH (ic:IntegratedChapter {scope:"INTEGRATED", chapter_id:"CH_2"})
OPTIONAL MATCH (ic)-[:HAS_INTEGRATED_REASONING]->(ri)
OPTIONAL MATCH (ri)-[:HAS_STEP]->(rs)
OPTIONAL MATCH (rs)-[:BASED_ON]->(a)
RETURN ic, ri, rs, a;

또는 챕터-버전키 한정:
MATCH (ic:IntegratedChapter {
  scope:"INTEGRATED",
  set_key:$set_key,
  chapter_id:"CH_2"
})
OPTIONAL MATCH (ic)-[:HAS_INTEGRATED_REASONING]->(ri)
OPTIONAL MATCH (ri)-[:HAS_STEP]->(rs)
OPTIONAL MATCH (rs)-[:BASED_ON]->(a)
RETURN ic, ri, rs, a;

용도
“이 논리는 이 조문에 기대고 있다”
법적 설득 구조를 시각적으로 보여줌
실무자에게 가장 설득력 있는 그래프

✅ ③-B. 특정 조문이 Integrated 어디서 쓰였는지 (역방향)
MATCH (a:Article {id:"ART_65"})<-[:BASED_ON]-(rs:ReasoningStep {scope:"INTEGRATED"})
MATCH (ri:ReasoningIssue)-[:HAS_STEP]->(rs)
MATCH (ic:IntegratedChapter)-[:HAS_INTEGRATED_REASONING]->(ri)
RETURN a, rs, ri, ic;

✅ 정석: “Article 기준 + 특정 IntegratedSnapshot” 쿼리
MATCH (snap:IntegratedSnapshot {
  scope:"INTEGRATED",
  set_key:$set_key
})
-[:HAS_INTEGRATED_CHAPTER]->(ic)
-[:HAS_INTEGRATED_REASONING]->(ri)
-[:HAS_STEP]->(rs)
-[:BASED_ON]->(a:Article {id:"ART_65"})
RETURN a, rs, ri, ic;

✅ Article도 “버전 고정”까지 하고 싶다면 (선택)
만약 “ART_65의 LAW/DECREE/RULE 버전까지 고정”하고 싶다면
(예: 2021년 버전의 65조만)
MATCH (snap:IntegratedSnapshot {
  scope:"INTEGRATED",
  set_key:$set_key
})
-[:HAS_INTEGRATED_CHAPTER]->(ic)
-[:HAS_INTEGRATED_REASONING]->(ri)
-[:HAS_STEP]->(rs)
-[:BASED_ON]->(a:Article {id:"ART_65"})

MATCH (a)<-[:HAS_ARTICLE]-(src)
MATCH (src)<-[:HAS_CHAPTER|HAS_SECTION|HAS_SUBDIVISION*0..]-(c:Chapter)
RETURN a, rs, ri, ic, c;

용도
“이 조문이 실제로 어떻게 쓰이는가”
입법 취지 / 판례 연결 / 전략 설계

④ 🔍 탐색·디버깅·검증용 그래프
“잘 들어갔나? 오염은 없나?”
이건 소비자보다는 너와 내부 사용자용이지만,
그래도 “시각화 쿼리”엔 포함됨.

✅ ④-A. Integrated 풀 맵 (디버그)
MATCH (snap:IntegratedSnapshot {
  scope:"INTEGRATED",
  set_key:$set_key
})
-[:HAS_INTEGRATED_CHAPTER]->(ic {chapter_id:"CH_2"})

OPTIONAL MATCH (ic)-[:HAS_INTEGRATED_REASONING]->(ri)
OPTIONAL MATCH (ri)-[:HAS_STEP]->(rs)
OPTIONAL MATCH (rs)-[:BASED_ON]->(a)
OPTIONAL MATCH (ic)-[:DERIVED_FROM]->(c)

RETURN ic, ri, rs, a, c;

✅ ④-B. 오염 탐지 그래프
MATCH (snap:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
      -[:HAS_INTEGRATED_CHAPTER]->(ic {chapter_id:"CH_2"})
      -[:HAS_INTEGRATED_REASONING]->(r)
      -[:ALIGNED_WITH]->(sem:SemanticIssue)
WHERE sem.chapter_id <> ic.chapter_id
RETURN ic, r, sem;
-> no changes나오면 오케이

⭐ [추천] 날짜 기준 자동 스냅샷 선택
GET /api/law/snapshot/by-date?date=2021-12-19
MATCH (s:IntegratedSnapshot {scope:"INTEGRATED"})
WHERE s.valid_from <= $date
  AND (s.valid_to IS NULL OR s.valid_to > $date)
RETURN s
ORDER BY s.valid_from DESC
LIMIT 1;

"""