# Candidate Pool 운영 규칙 (Tenant-agnostic)

이 문서는 `data_w` 외 다른 테넌트 데이터(`data_bc` 등)에도 동일하게 적용할 수 있는
`candidate_pool` 생성/보강 규칙을 정리한 운영 가이드다.

## 1) 목표와 원칙
- 목표: FN 후보 생성용 `high-recall` 후보 풀 확보
- 우선순위: 재현율 > 정밀도
- 필수 조건: 모든 후보는 근거(`exact_quote`, `start_char`, `end_char`, `segment_id`)를 가져야 함
- 금지: 근거 없는 추정/환각 후보 생성
- CRM 필드 ID 직접 바인딩 금지: `semantic_type` 기반으로 유지

## 2) 입력/출력 표준
- 입력(메모): `data_<tenant>/memo_<tenant><n>.txt` 또는 `memos_*.jsonl`
- structured 출력: `outputs/structured_runs/<run_name>/...`
- 기본 추출 출력: `outputs/runs/<run_name>/candidate_pool.jsonl`
- 수동 보강 출력: `outputs/runs_manual/<run_name>/candidate_pool_manual.jsonl`
- 최종 병합 출력(권장): `outputs/runs_merged/<run_name>/candidate_pool.jsonl`

`run_name` 예시: `w1`, `bc42`, `x_20260222_001`

## 3) 후보 생성 규칙

### 3-1. 하드 추출(코드 기반, 결정적)
소스: `agent_a/rules/regex_extractors.py`

- 수치/범위/퍼센트/통화/기간/날짜/이메일/전화/멘션 추출
- 한국어 수치 정규화(만/억/천만/복합/여)
- 컨텍스트 기반 semantic 분기
  - `명`: `target_population` / `team_size` / `people_count`
  - `건`: `lead_volume` / `sales_activity` / `case_metric`
  - `%`: `match_rate`(기본), `attrition_rate`(키워드 힌트 시)
- 제목/불릿 기반 텍스트 후보
  - Action/Sentiment/Need/문의 계열은 텍스트 후보로 승격
- overlap suppression
  - 범위/기간 스팬과 중복되는 단일 숫자 후보 억제
- 단위 예외
  - `개(?!월)` 규칙으로 `개월`을 `개`로 오인식하지 않음

### 3-2. 소프트 보강(LLM 없이 수동 규칙)
소스: `agent_a/manual_augment.py`

- 라인 단위 cue 규칙으로 아래 semantic 생성
  - `action_item`, `risk_or_concern`, `constraint`,
    `collaboration_need`, `kpi_definition`, `deliverable_scope`
- 정규화 텍스트 기준 dedupe 키 생성
- confidence는 규칙성 기반 고정값 사용

## 4) dedupe/merge 규칙
소스: `agent_a/merge.py`

- hard 후보: `semantic_type + normalized signature`로 dedupe
- soft 후보: 공백/대소문자 정규화 텍스트 해시로 dedupe
- 통화 후보 dedupe 시 `approx`는 키에서 제외
  - 병합 시 `approx = OR` 처리
- 중복 시 mention만 누적, confidence는 최대값 유지

## 5) runs_merged 생성 규칙 (운영)
`runs_merged`는 “최종 리뷰 기준”으로 아래 우선순위를 사용한다.

우선순위(높음 -> 낮음):
1. `runs_manual_q*` (개별 수동 QA/핫픽스 결과)
2. `runs_manual` (규칙 기반 수동 보강 결과)
3. `runs` (기본 하드 추출 결과)

같은 `run_name`이 여러 소스에 존재하면 우선순위가 높은 파일을 채택한다.

## 6) 테넌트 확장 체크리스트
새 테넌트(`data_bc`) 적용 시 아래를 먼저 확인:

1. 메모 포맷
- 제목/불릿 중심인지, 줄바꿈+콜론 중심인지
- 연락처/날짜/시간 표기 스타일(예: `7/15`, `오후 2시`) 포함 여부

2. 용어 사전
- `rules/keywords.yaml`에 테넌트 고유 용어 추가
- 채널/툴/팀명/내부 용어(약어) 업데이트

3. 수치 규칙
- 자주 쓰는 단위(명/건/회/%/원/개월) 이상치 여부 확인
- 월 단독 표현 등 저가치 날짜 노이즈 허용 범위 합의

4. QA 정책
- `SKIP` 허용 기준 문서화
- 애매한 필드의 기본 판정(예: `NOT_FN` vs `SKIP`) 합의

## 7) 최소 품질 게이트
테넌트별 최초 적용 시 샘플 30~50건으로 아래를 점검:

- 후보 0~2개 비율
- evidence 누락률(반드시 0%)
- 범위/기간 오인식 케이스
- 이메일/전화/날짜 누락률
- Action/Sentiment 계열 텍스트 후보 생성률

게이트 통과 후 전량 배치 실행.

## 8) 재현 커맨드 템플릿
기본 추출:

```bash
python -m agent_a.batch_regenerate \
  --data-root data_<tenant> \
  --structured-root outputs/structured_runs \
  --runs-root outputs/runs \
  --start 1 --end <N> \
  --summary outputs/reports/regenerate_<tenant>.json
```

수동 보강 큐 생성:

```bash
python -m agent_a.llm_queue_selector \
  --runs-root outputs/runs \
  --structured-root outputs/structured_runs \
  --start 1 --end <N> \
  --output outputs/llm_queue/queue_<tenant>.jsonl \
  --report outputs/llm_queue/report_<tenant>.json
```

수동 보강 실행:

```bash
python -m agent_a.manual_augment \
  --queue outputs/llm_queue/queue_<tenant>.jsonl \
  --output-root outputs/runs_manual \
  --summary outputs/reports/manual_augment_<tenant>.json
```

## 9) 변경 이력 관리 권장
- 규칙 수정 시 반드시 기록:
  - 변경 이유
  - 영향 범위(precision/recall/FN 후보량)
  - 롤백 방법
- 추천 위치:
  - `outputs/reports/`
  - 또는 `docs/changelog_candidate_pool.md`
