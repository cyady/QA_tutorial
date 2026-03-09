# schema_generator

`agent_a`와 분리된, 딜별 **effective schema(실사용 필드 집합)** 생성용 도구입니다.

## 왜 필요한가

- `active/deal`은 팀 전체 활성 필드(거의 전체)라서 과다합니다.
- 딜 단위 평가(FN/TP/FP)에서는 실제 해당 딜에서 쓰이는 필드 집합이 필요합니다.
- 이 도구는 다음 신호를 합쳐서 effective schema를 만듭니다.
1. `active/deal`의 `system/standard` 필드
2. `views/sales-entity/deal/{dealId}`의 `deal.custom_field` 키
3. (선택) `record-type/{id}/views/details/settings`의 `is_visible=true` 필드

## 파일

- `generate_effective_schema.py`
- `build_fn_review_input.py`

## 실행 방법

### 1) API 직접 호출 모드

```bash
python schema_generator/generate_effective_schema.py \
  --from-api \
  --deal-id 566552 \
  --token "<_recatch_fb 토큰>" \
  --output schema_generator/output/effective_schema_566552.json
```

옵션:
- `--base-url` 기본값: `https://business-canvas.recatch.cc`
- `--api-base-url` 기본값: `https://api.recatch.cc`
- `--view-version` 기본값: `20250519`
- `--layout-version` 기본값: `20241114`

### 2) 로컬 JSON 입력 모드

```bash
python schema_generator/generate_effective_schema.py \
  --active-fields-json /path/active_deal.json \
  --deal-view-json /path/deal_view_566552.json \
  --layout-settings-json /path/layout_2035.json \
  --output schema_generator/output/effective_schema_566552.json
```

`--layout-settings-json`은 선택입니다.

## 출력 포맷

`effective_schema_*.json` 예시:

- `meta`
  - `deal_id`, `record_type_id`, `record_type_name`
- `counts`
  - `active_total`, `effective_total`, `custom_keys_in_deal_view` 등
- `effective_field_ids`
  - 최종 필드 id 리스트
- `effective_fields`
  - 최종 필드 정의 전체

## 팀 운영 팁

- QA 파이프라인에서는 `effective_fields`만 기준으로 model_output 매핑/판정을 거는 것을 권장합니다.
- 새 딜 타입이 추가되어도 `deal_id`만 바꿔 재생성하면 됩니다.

---

## FN 리뷰 입력 생성기

`build_fn_review_input.py`는 아래 3개를 받아서 휴먼 QA용 FN 후보 리스트를 만듭니다.

1. `candidate_pool` (agent_a 결과)
2. `model_output` (실제 모델 출력)
3. `effective_schema` (위 생성기로 만든 결과)

### 실행 예시

```bash
python schema_generator/build_fn_review_input.py \
  --candidate-pool agent_a/outputs/runs_manual/w1/candidate_pool_manual.jsonl \
  --model-output agent_a/outputs/preview/w1_model_output_preview_deal.json \
  --effective-schema schema_generator/output/effective_schema_566552.json \
  --output schema_generator/output/w1_fn_review_input.json \
  --top-k 5
```

### 출력 형식

각 레코드(후보)에는 다음이 포함됩니다.

- `candidate_id`, `semantic_type`, `value_type`, `raw_text`, `normalized`
- `evidence` (segment_id/quote/offset)
- `fn_candidate=true`
- `suggested_fields` (effective schema 기준 추천 필드 top-k)
- `qa_decision`, `qa_notes` (초기 null)

### 매칭 규칙(요약)

- 숫자/범위: 모델 `extracted_value`와 수치 일치 비교
- 텍스트: 정규화 문자열 포함 비교
- 이메일: 문자열 포함 비교

불일치면 FN 후보로 분류합니다.
