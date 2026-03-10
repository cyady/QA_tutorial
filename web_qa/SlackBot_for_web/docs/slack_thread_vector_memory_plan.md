# Slack Thread Vector Memory Plan

작성일: 2026-03-11

## 문서 목적
이 문서는 Slack QA 스레드에 쌓이는 사람 리뷰를 수동 라벨링 파이프라인 없이 메모리 자산으로 축적하고, 이를 현재 QA 엔진의 planning 단계에서 retrieval로 활용하는 구조를 기록한다.

이 문서는 이제 단순 계획서가 아니라, 현재까지 구현된 상태와 남은 병목을 함께 적는 운영 문서다.

## 한 줄 요약
현재 프로젝트는 `Slack QA thread -> issue memory card -> local vector index -> planning retrieval` 경로까지 구현되어 있다.

핵심 방향은 다음과 같다.

1. 사람에게 추가 라벨링 업무를 만들지 않는다.
2. 이미 작성된 Slack QA 스레드를 raw archive로 저장한다.
3. 스레드를 `issue memory card`로 구조화한다.
4. 카드를 로컬 임베딩 인덱스에 넣고 cosine similarity로 조회한다.
5. 현재 run의 TC 생성과 visual probe 계획에 retrieval 결과를 반영한다.

## 왜 이 방향이 맞는가
현재 사람이 Slack 스레드에 남기는 QA 내용에는 아래 정보가 이미 들어 있다.

- 어떤 페이지에서 문제를 봤는지
- desktop / mobile / real mobile 중 어떤 맥락인지
- 어떤 시각적/상호작용 문제인지
- 왜 문제라고 판단했는지
- 스크린샷/영상 증거가 무엇인지

이 프로젝트가 지금 풀고 싶은 문제는 단순 DOM 오류보다 아래 영역에 더 가깝다.

- 스크롤 재진입 시 애니메이션 재실행
- 스크롤 경계 flicker
- 모바일 정렬 불일치
- depth / z-index / overlay 문제
- 줄바꿈 가독성
- 실제 모바일과 웹 inspector 뷰 차이

이런 문제는 일반 공개 웹 데이터보다 실제 Slack QA 스레드가 훨씬 더 가치 있는 메모리 소스다.

## 현재 구현 범위

### 1. Slack ingest
- Slack message shortcut: `Save Thread to QA Memory`
- shortcut 실행 시 해당 스레드의 메시지, 첨부파일 메타데이터, 파일 다운로드 결과를 `artifacts/_memory/MEM-*/` 아래에 저장한다.
- 사용자 피드백은 공개 스레드 댓글이 아니라 실행한 사용자만 보는 ephemeral message로 보낸다.

### 2. Raw archive
각 memory archive는 아래 파일을 가진다.

- `thread_manifest.json`
- `thread_messages.json`
- `file_manifest.json`
- `files/*`

### 3. Merge / dedupe
같은 스레드에서 shortcut을 여러 번 실행해도 새 memory archive를 무조건 만들지 않는다.

기준:
- `channel_id + thread_ts`

현재 merge 정책:
- 메시지: `ts` 기준 병합
- 첨부파일: `file_id` 기준 병합
- 카드: `dedupe_key` 기준 병합

즉, 스레드에 이슈 11번까지 있던 상태에서 한 번 저장하고, 나중에 12번 이슈가 추가된 뒤 다시 저장해도 기존 `MEM-*`를 갱신하는 구조다.

### 4. Issue memory card extraction
raw thread는 그대로 검색하지 않는다. 먼저 `issue memory card`로 구조화한다.

출력:
- `issue_memory_cards.json`

현재 카드 추출기는 규칙 기반이며 아래 이슈 타입을 처리한다.

- `animation_replay`
- `flicker`
- `mobile_alignment`
- `text_wrap`
- `share_preview`
- `mobile_overlay_depth`
- `mobile_media_render`
- `spacing_layout`
- `footer_alignment`
- `performance_motion`
- `close_button`
- `broken_link`
- `image_render`
- `menu_consistency`
- `click_affordance`
- `click_feedback`
- `responsive_overflow`
- `branding_render`
- `favicon_missing`
- `general_ui_issue`

### 5. Local vector index
- backend: `sentence_transformers`
- default embedding model: `intfloat/multilingual-e5-large-instruct`
- retrieval: cosine similarity
- index artifact:
  - `artifacts/_runtime/vector_memory/issue_memory_index.json`

### 6. Engine integration
planning 단계에서 local vector retrieval을 실행하고 아래 산출물을 생성한다.

- `memory_retrieval.json`

이 retrieval 결과는 아래에 반영된다.

- `coverage_plan.json`
- `test_cases.json`
- `visual_probe_plan.memory_issue_types`
- `visual_probe_plan.probe_directives`

즉, retrieval은 이미 TC 생성과 visual probe 선택에 연결되어 있다.

## 현재 검증 결과

### Retrieval benchmark
현재 기준 benchmark artifact:
- `artifacts/_runtime/vector_memory/benchmark_20260310T165457Z.json`

현재 성능:
- `top1_accuracy = 0.9`
- `top3_accuracy = 1.0`
- `mrr = 0.95`

해석:
- 임베딩 모델 교체 전의 실험용 hash embedding 수준은 이미 넘어섰다.
- 현재는 retrieval 구조 자체는 쓸 만한 수준이다.

### 실제 engine run 연결 검증
검증 run:
- `JOB-112efc31`
- target: `https://maroon-yards-063878.framer.app/alphakey-insight-rm`

확인된 점:
- `memory_retrieval.json` 생성됨
- planning 단계에 retrieval hit가 들어감
- `test_cases.json`에 `memory_hints`가 들어감
- visual probe plan에 memory-driven directives가 들어감

즉, `retrieval -> planning` 연결은 실제로 동작 중이다.

## 현재 병목
현재 가장 큰 병목은 임베딩 모델이 아니라 metadata 품질이다.

핵심 문제:
- 오래 저장된 memory manifest에는 `target_url`, `job_url`, `host`가 충분히 기록되지 않았다.
- 그래서 같은 도메인/같은 템플릿 스레드를 우선 회수하는 가중치가 약하다.
- 결과적으로 semantic similarity는 높아도, domain relevance가 낮은 카드가 상위에 올라올 수 있다.

즉 현재 상태는:

1. 카드 품질: usable
2. 임베딩 품질: usable
3. domain-aware retrieval: 아직 약함

## 왜 raw thread를 바로 벡터화하지 않는가
한 스레드에는 여러 이슈와 노이즈가 섞여 있다.

예:
- 일정 대화
- 잡담
- 정정 메시지
- 동일 이슈 반복 언급
- 첨부만 있는 메시지

raw thread를 그대로 벡터화하면 retrieval 결과가 커지고 흐려진다.

그래서 현재 구조는 아래로 고정한다.

- `raw_thread_archive`: 원문 보존
- `issue_memory_cards`: 검색 단위
- `vector_index(cards)`: retrieval 단위

## Issue Memory Card 정의
`issue memory card`는 Slack 스레드에서 추출한 단일 QA 이슈 단위의 메모리 객체다.

대표 필드:
- `card_id`
- `memory_id`
- `thread_ts`
- `page_url`
- `domain`
- `framework_hint`
- `platform`
- `issue_types`
- `summary`
- `observation`
- `expected_behavior`
- `severity_hint`
- `section_hint`
- `evidence_refs`
- `source_message_ts`
- `dedupe_key`
- `vector_text`

## 현재 retrieval 사용 위치

### Planning
현재 URL / host / route token / framework / title / CTA label을 바탕으로 query를 만들고 top-k hit를 찾는다.

활용 예:
- 과거 `animation_replay`가 많으면 re-entry 성격의 scroll probe를 우선 고려
- 과거 `share_preview`가 많으면 clickability 후보를 관련 CTA 쪽으로 우선 정렬
- 과거 `mobile_alignment`가 많으면 hover/click보다 layout hint를 더 강하게 준다

### Execute
execute 단계는 retrieval을 직접 다시 부르지는 않지만, planning이 남긴 `memory_hints`와 `probe_directives`를 통해 간접 활용한다.

현재 반영 대상:
- `scroll_probe`
- `hover_probe`
- `clickability_probe`

### Report
현재 report 단계에서 과거 memory를 finding 근거로 직접 인용하지는 않지만, artifact 수준에서는 retrieval 결과가 이미 남는다.

## 현재 선택한 임베딩 모델
기본 모델:
- `intfloat/multilingual-e5-large-instruct`

선택 이유:
- 한국어/영어 혼합 텍스트 대응
- retrieval 품질이 현재 데이터셋에서 충분히 좋음
- 로컬 실험용으로 바로 붙일 수 있음

이전 후보였던 `gte-multilingual-base`는 현재 환경에서 안정적으로 동작하지 않아 제외했다.

## 운영 명령어

### 카드 추출
```powershell
webqa-memory-extract --memory-id MEM-6d671b14
```

### 인덱스 빌드
```powershell
webqa-memory-index build
```

### 유사도 검색
```powershell
webqa-memory-index query --text "모바일 정렬 안맞음 스크롤 깜빡임 플로팅 CTA depth" --top-k 5
```

### 비교 benchmark
```powershell
webqa-memory-index compare --top-k 5
```

## 다음 우선순위
현재 다음 단계는 아래 순서가 맞다.

1. Slack memory 저장 시 `job_id`, `target_url`, `host`를 manifest에 함께 남긴다.
2. retrieval score에 `host / path / framework` metadata 가중치를 추가한다.
3. `/review` UI에 `memory_retrieval`과 `memory_hints`를 직접 노출한다.
4. 이후에야 execution 전용 memory-driven probe를 더 늘린다.

## 결론
현재 프로젝트 단계에서는 `수동 라벨링 기반 학습`보다 `Slack QA 스레드의 vector memory화`가 훨씬 현실적이다.

현재 구현 기준의 핵심 구조는 아래와 같다.

`Slack QA thread -> issue memory card -> local vector index -> planning retrieval`

이 구조는 이미 동작 중이며, 현재 남은 핵심 병목은 임베딩 모델이 아니라 `domain-aware metadata weighting`이다.
