# QA Review UI

`candidate_pool`, `model_output`, `effective_schema`, `fn_review_input` 을 한 화면에서 검토하는 Streamlit UI입니다.

## 실행

루트 저장소(`QA_tutorial`) 기준:

```bash
streamlit run ai_field_mapping/qa_review_ui/app.py
```

또는:

```bash
python -m streamlit run ai_field_mapping/qa_review_ui/app.py
```

## 주요 입력

- `Memo text (.txt)`
- `candidate_pool (.json/.jsonl)`
- `model_output (.json/.jsonl)`
- `FN review input (.json/.jsonl)`
- `effective_schema (.json)`

기본값은 `ai_field_mapping` 워크스페이스 기준 경로로 채워집니다.
UI는 repo 루트 기준 경로와 워크스페이스 상대 경로를 모두 해석하도록 맞춰 두었습니다.

## 자동 생성 기능

### `effective_schema` 생성

- `deal_id`
- `Bearer token (RECATCH_FB_TOKEN)`
- `Generate effective_schema from deal_id`

성공 시:

- `ai_field_mapping/schema_generator/output/effective_schema_<deal_id>.json` 생성
- 입력 경로에 자동 반영

내부 호출 스크립트:

- `ai_field_mapping/schema_generator/build_effective_schema_from_deal.py`

### `fn_review_input` 생성

- `candidate_pool`, `model_output`, `effective_schema` 확인
- `Suggested fields top-k` 설정
- `Generate fn_review_input from candidate_pool`

성공 시:

- `ai_field_mapping/schema_generator/output/<candidate_pool_stem>_fn_review_input.json` 생성
- 입력 경로에 자동 반영

내부 호출 스크립트:

- `ai_field_mapping/schema_generator/build_fn_review_input.py`

## 저장 위치

리뷰 결과 저장:

- `ai_field_mapping/qa_review_ui/data/decisions/{memo_id}.json`

최근 입력 경로 저장:

- `ai_field_mapping/qa_review_ui/data/last_inputs.json`

## 권장 흐름

1. `agent_a` 로 `candidate_pool` 생성
2. `schema_generator` 로 `effective_schema` 생성
3. `schema_generator` 로 `fn_review_input` 생성
4. UI에서 TP/FP/FN 리뷰
5. `Save Decisions` 로 저장
