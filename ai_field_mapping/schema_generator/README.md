# schema_generator

`agent_a` 결과를 받아 Re:catch QA용 `effective_schema` 와 `fn_review_input` 을 만드는 도구 모음입니다.

## 역할

- 딜 단위로 실제 사용 가능한 필드 집합(`effective_schema`) 생성
- `candidate_pool` 과 `model_output` 을 비교해서 FN 후보 리뷰 입력 생성

## 주요 스크립트

- `generate_effective_schema.py`
- `build_effective_schema_from_deal.py`
- `build_fn_review_input.py`

## 실행 예시

루트 저장소(`QA_tutorial`) 기준:

### 1. API에서 `effective_schema` 생성

```bash
python ai_field_mapping/schema_generator/generate_effective_schema.py \
  --from-api \
  --deal-id 566552 \
  --token "<RECATCH_FB_TOKEN>" \
  --output ai_field_mapping/schema_generator/output/effective_schema_566552.json
```

### 2. 로컬 JSON에서 `effective_schema` 생성

```bash
python ai_field_mapping/schema_generator/generate_effective_schema.py \
  --active-fields-json /path/active_deal.json \
  --deal-view-json /path/deal_view_566552.json \
  --layout-settings-json /path/layout_2035.json \
  --output ai_field_mapping/schema_generator/output/effective_schema_566552.json
```

### 3. `fn_review_input` 생성

```bash
python ai_field_mapping/schema_generator/build_fn_review_input.py \
  --candidate-pool ai_field_mapping/agent_a/outputs/runs_manual/w1/candidate_pool_manual.jsonl \
  --model-output ai_field_mapping/agent_a/model_output/w1_model_output.json \
  --effective-schema ai_field_mapping/schema_generator/output/effective_schema_566552.json \
  --output ai_field_mapping/schema_generator/output/w1_fn_review_input.json \
  --top-k 5
```

## 출력

- `effective_schema_*.json`
- `*_fn_review_input.json`

생성 산출물은 기본적으로 `ai_field_mapping/schema_generator/output/` 아래에 두는 흐름을 권장합니다.

## 연결 관계

- 입력: `ai_field_mapping/agent_a`
- 후속 리뷰: `ai_field_mapping/qa_review_ui`
