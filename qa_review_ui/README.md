# QA Review UI

미팅 메모 1건 기준으로 아래를 한 화면에서 리뷰하는 Streamlit UI입니다.

1. 메모 원문
2. `model_output` 판정 (`TP` / `FP` / `SKIP`)
3. `FN 후보` 판정 (`FN` / `NOT_FN` / `SKIP`)
4. 필드별 누적 집계 (`TP` / `FP` / `FN` + `precision` / `recall` / `f1_score`)

---

## 1) 실행

프로젝트 루트(`QA_tutorial`)에서 실행:

```bash
streamlit run qa_review_ui/app.py
```

명령이 안 잡히면:

```bash
python -m streamlit run qa_review_ui/app.py
```

---

## 2) 입력 파일

사이드바에서 아래 경로를 입력합니다.

- `Memo text (.txt)`: 메모 원문 텍스트 파일
- `candidate_pool (.json/.jsonl)`: Agent A 후보 풀 결과
- `model_output (.json/.jsonl)`: 실제 모델 출력
- `FN review input (.json/.jsonl)`: FN 후보 리뷰 입력 파일
- `effective_schema (.json)`: 해당 deal에서 유효한 필드 스키마

기본적으로 `memo_text / candidate_pool / model_output`은 필수입니다.

---

## 3) 자동 생성 기능

### 3-1. `effective_schema` 자동 생성

사이드바에서:

1. `deal_id` 입력
2. `Bearer token (RECATCH_FB_TOKEN)` 입력
3. `Generate effective_schema from deal_id` 클릭

성공 시:

- `schema_generator/output/effective_schema_<deal_id>.json` 생성
- `effective_schema` 경로에 자동 반영

내부적으로 아래 스크립트를 호출합니다.

- `schema_generator/build_effective_schema_from_deal.py`

### 3-2. `fn_review_input` 자동 생성

사이드바에서:

1. `candidate_pool`, `model_output`, `effective_schema` 경로 확인
2. `Suggested fields top-k` 설정
3. `Generate fn_review_input from candidate_pool` 클릭

성공 시:

- `schema_generator/output/<candidate_pool_stem>_fn_review_input.json` 생성
- `FN review input` 경로에 자동 반영

내부적으로 아래 스크립트를 호출합니다.

- `schema_generator/build_fn_review_input.py`

---

## 4) 판정 저장

`Save Decisions` 클릭 시 아래 파일에 저장됩니다.

- `qa_review_ui/data/decisions/{memo_id}.json`

저장 구조:

- `model_decisions`: 모델 출력별 판정
- `fn_decisions`: FN 후보별 판정 + 문맥 스냅샷

`fn_decisions`에는 디버깅용 정보가 함께 저장됩니다.

- `semantic_type`, `value_type`, `raw_text`, `normalized`
- `evidence_quote`, `evidence_section_path`, `evidence_segment_id`
- `start_char`, `end_char`, `line_no`, `line_text`
- `suggested_fields_snapshot`
- `assigned_field_id`, `assigned_field_label`

---

## 5) 지표 계산 방식

집계 테이블(`Field TP/FP/FN Aggregate`)은 필드별로 아래를 계산합니다.

- `precision = TP / (TP + FP)`
- `recall = TP / (TP + FN)`
- `f1_score = 2 * precision * recall / (precision + recall)`

분모가 0이면 해당 값은 `0.0`으로 처리합니다.

중요:

- 집계 테이블은 현재 화면의 1개 메모만 보는 값이 아니라,
  `qa_review_ui/data/decisions/*.json` 전체를 합산한 누적 결과입니다.
- 따라서 리뷰한 메모 수가 늘어날수록 필드별 지표가 계속 갱신됩니다.

---

## 6) 운영 권장 순서

1. 메모 원문 + `candidate_pool` + `model_output` 준비
2. `effective_schema` 자동 생성(또는 기존 파일 지정)
3. `fn_review_input` 자동 생성
4. `Load` 클릭
5. `Model Output Review` 판정
6. `FN Candidate Review` 판정
7. `Save Decisions` 저장

---

## 7) 자주 묻는 문제

### Q1. 새로고침하면 경로가 초기화됨
- 최신 버전은 `qa_review_ui/data/last_inputs.json`에 입력 경로를 저장/복원합니다.
- 경로가 유지되지 않으면 해당 파일 쓰기 권한과 경로 유효성을 확인하세요.

### Q2. 한글이 깨져 보임
- 원본 파일 인코딩 문제일 가능성이 큽니다.
- JSON/TXT를 UTF-8(권장: UTF-8 with BOM 허용)로 저장해 다시 로드하세요.

### Q3. `effective_schema` 자동 생성 실패
- 토큰/네트워크/API 권한 문제를 먼저 확인하세요.
- 오류 메시지 상세는 UI 하단 코드 블록에서 확인 가능합니다.
