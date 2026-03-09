# Agent A: candidate_pool 추출기

회의 메모 텍스트를 입력받아 `candidate_pool.jsonl`을 생성하는 하이브리드 추출기입니다.

- 하드 추출: 규칙/정규식 기반(결정적)
- 소프트 추출: LLM 기반(선택 사항)

## 설치

```bash
pip install -e .
pip install -e .[dev]
```

## 사용법

JSONL 입력 파일 사용:

```bash
python -m agent_a.cli --input memos.jsonl --output outputs/candidate_pool.jsonl
```

대량 실행 시 run 폴더 저장(권장):

```bash
python -m agent_a.cli --input data_w/memos_w_all.jsonl --output-dir outputs/runs --run-name w_all_no_llm --no-llm
```

TXT 단일 파일 빠른 테스트:

```bash
python -m agent_a.cli --input-txt tests/fixtures/sample_memo.txt --memo-id M-001 --output outputs/candidate_pool.jsonl
```

LLM 비활성화:

```bash
python -m agent_a.cli --input memos.jsonl --output outputs/candidate_pool.jsonl --no-llm
```

메모 원문을 JSON/JSONL로 변환:

```bash
python -m agent_a.memo_to_json --input-txt memo.txt --memo-id M-001 --output-json outputs/memo_structured.json --output-jsonl outputs/memos.jsonl
```

structured/jsonl도 run 폴더로 저장:

```bash
python -m agent_a.memo_to_json --input-txt memo.txt --memo-id M-001 --output-dir outputs/structured_runs --run-name w1
```

CSV의 `text`를 폴더별 TXT + JSONL로 분리:

```bash
python -m agent_a.csv_to_memo_txt --csv "C:\\Users\\cyady\\Downloads\\미팅노트 예시 - Sheet1.csv" --out-dir outputs/memo_corpus
```

기본 동작:
- 폴더 분리 기준: `is_example_format` 컬럼
- 파일 생성: `outputs/memo_corpus/<group>/memo_<memo_id>.txt`
- 그룹별 입력 파일: `outputs/memo_corpus/<group>/memos.jsonl`
- 전체 입력 파일: `outputs/memo_corpus/memos_all.jsonl`
- 인덱스: `outputs/memo_corpus/manifest.csv`

LLM 보강 대상 선별(큐 생성):

```bash
python -m agent_a.llm_queue_selector --runs-root outputs/runs --structured-root outputs/structured_runs --start 1 --end 6000 --output outputs/llm_queue/queue.jsonl --report outputs/llm_queue/report.json
```

룰 보강 후 전량 재생성:

```bash
python -m agent_a.batch_regenerate --data-root data_w --structured-root outputs/structured_runs --runs-root outputs/runs --start 1 --end 6000 --summary outputs/reports/regenerate_summary.json
```

큐 대상 수동 보강(candidate_pool_manual):

```bash
python -m agent_a.manual_augment --queue outputs/llm_queue/queue.jsonl --output-root outputs/runs_manual --summary outputs/reports/manual_augment_summary.json
```

고정 검증셋 100건 생성:

```bash
python -m agent_a.select_validation_set --queue outputs/llm_queue/queue.jsonl --runs-root outputs/runs --structured-root outputs/structured_runs --size 100 --queue-size 70 --seed 20260221 --output-jsonl outputs/validation/fixed_100.jsonl --output-csv outputs/validation/fixed_100.csv --summary outputs/validation/fixed_100_summary.json
```

## 입력 포맷

`memos.jsonl`의 각 라인은 아래 형식입니다.

```json
{"memo_id": "M-001", "text": "full memo text"}
```

원문에서 자동 생성하려면 `memo_to_json` 유틸을 사용하세요.
- 구조화 JSON: 섹션(`###`) + 불릿(`-`) 기준 분해
- JSONL: 추출기 입력용 최소 포맷(`memo_id`, `text`)

## 출력 포맷

`candidate_pool.jsonl`에 메모 1건당 1줄(JSON)로 기록됩니다.
`--output-dir`를 쓰면 `outputs/runs/<run-name>/candidate_pool.jsonl` 형태로 저장됩니다.

- `run_id`: `RUN-YYYYMMDD-HHMMSS`
- `memo_id`: 입력 메모 ID
- `candidates`: 하드/소프트 후보 목록(근거 포함)
- `extraction_metadata`: 추출 메타데이터

각 후보는 근거를 반드시 포함합니다.

- `mentions[].exact_quote`
- `mentions[].start_char`
- `mentions[].end_char`
- `mentions[].segment_id`

## 기본 동작/가정

- 목표는 **정밀도보다 재현율(High Recall)** 입니다.
- 하드 추출은 세그먼트 내 매칭 위치 + 세그먼트 절대 오프셋으로 근거 위치를 계산합니다.
- `raw_text`와 `normalized`를 분리합니다.
- CRM 필드 ID와 바인딩하지 않고 `semantic_type`만 사용합니다.
- LLM은 선택 사항입니다.
  - `--no-llm`이면 소프트 추출을 건너뜁니다.
  - `OPENAI_API_KEY`가 없으면 자동으로 mock(빈 결과) 클라이언트를 사용합니다.
- LLM 호출 시 `temperature=0`, JSON 스키마 검증을 사용합니다.

운영 규칙(테넌트 확장/병합 우선순위/품질 게이트)은 아래 문서를 참고하세요.

- `docs/candidate_pool_rules.md`

## 하드 추출 커버리지

- 이메일
- 금액(KRW)
- 건수/인원 수치(한글 단위 포함: 만/억/천만/복합 표기)
- 수치 범위(예: `4~5회`)
- 퍼센트 범위(예: `30~50%`)
- 기간(예: `약 2.5개월`)
- 날짜 표현식(절대 날짜 + 한국어 월/일/중순 표현)
- 사전 기반 키워드 후보(tool/channel, KPI 힌트 등)

## 테스트

```bash
pytest -q
```

테스트 범위:

- 세그먼트 분할/오프셋 일관성
- 한국어 수치 정규화(`만/억/천만/복합/여`)
- 하드 추출 기대값 검증
- 병합/중복 제거 동작

## 빠른 실행 예시

```bash
python -m agent_a.cli --input-txt tests/fixtures/sample_memo.txt --memo-id M-001 --output outputs/candidate_pool.jsonl --no-llm
```
