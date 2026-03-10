# 현재 엔진 버전 문서 (v0.2.0)

작성일: 2026-03-07  
기준 코드 버전: `slackbot-for-web 0.2.0`

## 문서 목적
이 문서는 현재 코드베이스가 실제로 제공하는 웹 QA 엔진의 실행 구조, 운영 정책, 산출물, 한계를 기록하기 위한 구현 기준 문서다.

이 문서는 `목표 아키텍처` 문서가 아니라 `현재 구현 상태` 문서다. 이후 엔진 정책이나 산출물 계약이 바뀌면 이 문서를 함께 갱신해야 한다.

## 한 줄 요약
현재 엔진은 `Slack-first`가 아니라 `engine-first` 구조다. Slack은 입력 채널일 뿐이고, 실제 QA 실행은 공통 엔진이 담당한다. 기본 실행 경로는 LangGraph 기반 `Map -> Plan -> Execute -> Report` 파이프라인이며, 산출물은 모두 `artifacts/<JOB_ID>/` 아래에 기록된다.

## 1. 현재 엔진의 정의
현재 프로젝트에서 "엔진"은 아래 공통 실행 경로를 의미한다.

1. 요청 수신
2. `QaRunRequest` 생성
3. `QaEngine.run()` 호출
4. LangGraph 파이프라인 실행
5. 산출물 저장
6. 채널별 응답 렌더링

즉, Slack, CLI, 대시보드는 엔진 자체가 아니라 엔진을 호출하거나 결과를 소비하는 바깥 채널이다.

## 2. 주요 진입점
### 실행 진입점
- `webqa-engine`: CLI로 엔진 직접 실행
- `webqa-slack`: Slack 앱 실행
- `webqa-dashboard`: 리뷰 UI 및 artifact API 실행

### 핵심 런타임 파일
- `src/slackbot_for_web/qa_engine.py`: 공통 엔진 진입점
- `src/slackbot_for_web/webqa_runner.py`: 실제 QA 파이프라인 및 실행 정책
- `src/slackbot_for_web/models.py`: 요청/응답 모델
- `src/slackbot_for_web/config.py`: `.env` 기반 설정 로딩
- `src/slackbot_for_web/validation_models.py`: 일부 산출물과 설정 검증

### 채널/운영 파일
- `src/slackbot_for_web/slack_app.py`: Slack transport
- `src/slackbot_for_web/queue_worker.py`: 비동기 실행 경로
- `src/slackbot_for_web/engine_cli.py`: 단일 실행 및 실패 케이스 배치 재실행
- `src/slackbot_for_web/dashboard.py`: `/review`, `/workflow`, `/api` 제공

### 사용자 노출 정책
- Slack 사용자 화면은 복수 mode 선택을 제공하지 않는다.
- Slack 진입점은 내부적으로 항상 `full_web_qa`를 사용한다.
- 사용자에게 보이는 실행 모드 문구는 `Full QA (E2E)`로 고정한다.
- agent도 사용자 선택이 아니라 `.env`의 `DEFAULT_AGENT`를 사용한다. 지원 범위를 벗어나면 `openai`로 fallback한다.
- 런타임은 legacy mode alias(`qa_smoke`, `landing_page_qa`)가 들어와도 실제 실행 시 `full_web_qa`로 정규화한다.
- Slack 앱에는 QA 스레드를 raw thread archive로 저장하기 위한 message shortcut `save_thread_to_qa_memory`가 추가되었다.
- planning 단계는 local vector memory index를 조회해 `memory_retrieval.json`을 생성하고, test case/probe 계획에 과거 human QA memory를 반영한다.

## 3. 현재 실행 흐름
현재 기본 실행 흐름은 아래와 같다.

1. 채널이 URL과 옵션을 받아 `QaRunRequest`를 만든다.
2. `QaEngine.run()`이 agent 종류를 보고 OpenAI 또는 Gemini 실행 경로를 선택한다.
3. 실행 함수는 `webqa_runner.py`로 들어간다.
4. `USE_LANGGRAPH=true`이면 LangGraph 파이프라인을 돈다.
5. 파이프라인은 `Map -> Plan -> Execute -> Report` 순서로 진행된다.
6. 각 단계는 JSON 산출물을 job artifact 디렉터리에 기록한다.
7. 최종적으로 `result.json`과 `regression_diff.json`이 생성된다.
8. Slack/CLI/대시보드는 이 산출물을 기반으로 결과를 표시한다.

## 4. LangGraph 사용 방식
LangGraph는 현재 "복잡한 다중 분기 워크플로우"보다는 "단계형 오케스트레이터"로 사용 중이다.

### 현재 사용 방식
- 기본값: `USE_LANGGRAPH=true`
- 파이프라인 노드:
  - `map`
  - `plan`
  - `execute`
  - `report`
- 각 노드는 자체 산출물을 쓴다.
- LangGraph가 비활성화되면 provider 직실행 경로로 내려갈 수 있다.

### 현재 시점의 장점
- 단계별 실패 지점이 명확하다.
- 산출물이 단계별로 남아 회귀 비교가 쉽다.
- Slack 외 채널에서도 같은 엔진 경로를 재사용할 수 있다.
- self-healing, timeout, needs_review 정책을 한 곳에서 관리할 수 있다.

### 현재 시점의 한계
- 아직 고급 분기, checkpoint 재개, 인간 승인 워크플로우까지는 사용하지 않는다.
- 현재 LangGraph는 "엔진의 뼈대" 역할이지, 전체 운영 문제를 자동으로 해결하는 수준은 아니다.

## 5. 현재 provider 지원 상태
### OpenAI
- 사용 가능
- 현재 실사용 기준 provider 중 하나
- `.env`의 `OPENAI_API_KEY`, `OPENAI_MODEL` 사용

### Gemini
- 사용 가능
- `.env`의 `GEMINI_API_KEY` 또는 `GOOGLE_API_KEY` 사용
- fallback model 목록도 설정 가능

### Claude
- 아직 placeholder 수준
- 현재는 실제 실행 엔진으로 연결되지 않았다
- 요청 시 `needs_review` 성격의 placeholder 결과를 반환한다

## 6. 현재 운영 정책
### 6.1 하드 타임아웃
- 현재 run 단위 강제 종료 기준은 `HARD_TIMEOUT_MINUTES`
- 기본값은 `60`분
- 이 값은 실제 코드에서 강제되는 정책이다

### 6.2 self-healing / fallback 정책
현재 1회 실행 내부에서 아래 순서로 자가회복을 시도한다.

1. Phase 1: Vibium 재시도 5회 -> DevTools 진단 세트 3회
2. Phase 2: Vibium 재시도 5회 -> DevTools 진단 세트 2회
3. Phase 3: Vibium 재시도 5회 -> 추가 DevTools 없이 종료 판단
4. 해결되지 않으면 `needs_review`

정리하면 현재 기본 정책은 아래와 같다.

- Vibium 총 재시도 한도: `15`
- DevTools 진단 세트 총 한도: `5`
- 최종 미해결 상태: `needs_review`

여기서 `DevTools 5회`는 단순 클릭 5회가 아니라 `진단 시도 세트 5회`를 의미한다.

### 6.3 needs_review 트리거
현재 기본 트리거는 아래 다섯 가지다.

- auth wall
- captcha
- anti-bot
- 증거 충돌
- 도구 실패 누적

이 값은 실행 및 보고 산출물에도 반영된다.

### 6.4 커버리지/탐색 철학
현재 MVP 철학은 `QA 대상 품질 우선`이다. 즉, 내부 비용을 아끼기 위해 URL/액션 수를 먼저 강하게 제한하는 구조는 아니다.

다만 실제 코드에서 강제되는 핵심 제약은 현재 기준으로는 아래 두 축이다.

- run-level hard timeout
- action-level self-healing / fallback state machine

즉, 현재 엔진은 "무제한 탐색"을 이상으로 두되, 실제 운영 안전장치는 `시간 제한 + 단계별 fallback`에 둔다.

### 6.5 도메인 경계
현재 문서/프롬프트 기준 내부 범위는 `시작 URL이 속한 canonical host` 기준이다.

예시:
- 내부: `https://www.meisterkor.com/company`
- 내부: `https://www.meisterkor.com/contact`
- 외부: `https://recatch.cc/ko`
- 외부: 임베드 지도
- 외부: YouTube, Instagram 등 외부 플랫폼 링크

외부 링크는 맥락으로는 기록할 수 있지만, 외부 도메인 전체를 깊게 테스트하는 것은 현재 엔진 목표가 아니다.

## 7. 현재 산출물 구조
모든 run은 기본적으로 `artifacts/<JOB_ID>/` 아래에 기록된다.

### 주요 산출물
- `started.json`: 실행 시작 메타데이터
- `domain_context_map.json`: Map 단계 산출물
- `coverage_plan.json`: Coverage/Plan 단계 산출물
- `test_cases.json`: 테스트 케이스 설계 산출물
- `execution_log.json`: 실행 단계 로그
- `test_case_results.json`: 테스트 케이스별 결과
- `qa_report.json`: 최종 QA 리포트
- `result.json`: 채널 소비용 최종 결과 요약
- `regression_diff.json`: 이전 run 대비 변화량
- `runner.log`: 런타임 로그
- `openai_raw.txt` 또는 `gemini_raw.txt`: provider raw 응답 기록
- `traceback.txt`: 예외 발생 시 상세 traceback

### 공통 운영 포인트
- 현재 `schema_version = 1`
- artifact는 단계별 추적이 가능하도록 분리 저장된다
- 대시보드와 회귀 비교는 이 파일 구조를 전제로 동작한다
- dashboard/API payload는 이미 `mode_key` 중심이며 `preset`을 노출하지 않는다
- 다만 artifact-level `preset` 제거는 아직 하지 않았고, `started.json`/`result.json`/`error.json`은 현재 `preset` + `mode`를 함께 기록한다
- artifact-level 제거 계획은 `docs/artifact_mode_migration_plan.md`를 따른다

## 8. 현재 Pydantic 검증 범위
Pydantic은 현재 "전면 도입"이 아니라 "경계층 부분 도입" 상태다.

### 현재 검증되는 항목
- `.env` -> `Settings`
- `result.json`
- `test_case_results.json`
- `qa_report.json`

### 아직 전면 검증하지 않는 항목
- `domain_context_map.json`
- `coverage_plan.json`
- `test_cases.json`
- `execution_log.json`
- MCP 원시 응답 전체
- 내부 런타임 state 전체

### 이렇게 둔 이유
중간 산출물과 도구 응답은 변동성이 커서, 이 부분까지 엄격 검증을 걸면 run이 너무 자주 조기 실패할 수 있다. 현재는 최종 출력 안정성부터 확보하는 쪽으로 범위를 제한했다.

## 9. 토큰 및 회귀 지원
### 토큰 usage
현재 엔진은 provider 응답에서 토큰 사용량을 누적 집계하여 결과 구조에 남긴다. 이 값은 향후 비용 최적화와 회귀 분석의 기준 데이터로 사용한다.

### 회귀 비교
현재 엔진은 같은 `(url, agent, normalized mode)` 조합의 이전 run이 있으면 `regression_diff.json`을 생성한다.

여기서 normalized mode는 아래를 하나로 본다.
- `full_web_qa`
- `qa_smoke`
- `landing_page_qa`

현재 diff는 주로 아래 항목을 비교한다.
- overall status 방향성
- findings 수 변화
- critical findings 변화
- token total 변화
- visual probe summary / per-kind breakdown 변화

즉, 현재 엔진은 "이번 실행이 이전보다 나아졌는지/나빠졌는지"를 artifact 수준에서 추적할 수 있다.

### 실패군 배치 재실행
CLI는 특정 run의 실패 케이스를 골라 배치 재실행할 수 있다.

이 기능의 목적은 아래와 같다.
- 수정 후 실패군만 빠르게 재검증
- 회귀 확인 속도 향상
- full rerun 이전의 선별 검증

## 9.1 현재 적용된 VLA-like 하이브리드
현재 엔진에는 초기 VLA-like 하이브리드가 들어가 있다. 아직 자체 VLA 모델은 없지만, 아래 조합이 실제 실행 경로에 적용되었다.

- DOM 기반 interaction hint 추출
- planning 단계의 `visual_probe_plan`
- execution 단계의 deterministic visual probes
  - `scroll_probe`
  - `hover_probe`
  - `clickability_probe`
- probe 결과를 `visual_probes.json`으로 별도 저장
- probe evidence를 `test_case_results.json`, `qa_report.json`, `result.json`에 반영
- probe bbox / viewport 메타데이터와 overlay annotation 메타데이터를 함께 저장
- `regression_diff.json`에 visual probe diff를 포함

즉, 현재 버전은 `VLA 단독 QA`가 아니라 `DOM + deterministic browser actions + LLM report synthesis` 형태의 1차 하이브리드다.

## 10. 대시보드/UI 현재 상태
현재 대시보드는 실행 엔진이라기보다 `리뷰/추적 도구`다.

### 현재 제공 페이지
- `/review`: run 리뷰 중심 화면
- `/workflow`: 단계 흐름과 산출물 연결 화면
- `/api`: Python API/엔드포인트 안내 화면

### 현재 리뷰 UI가 제공하는 것
- run 목록과 선택
- run list 수준의 interaction regression 방향/증감 요약
- Run Overview
- QA Report 요약
- Visual Probes 요약 및 interaction regression 카드
- structured/text artifact 링크
- passed case 브라우저
- case 단위 steps / evidences quick preview
- visual probe 단위 quick preview
- visual probe before/after compare 뷰
- evidence 이미지 오버레이 레이어
- evidence 이미지 미리보기 및 확대/축소

### 현재 워크플로우 UI가 제공하는 것
- 세로형 workflow map
- 단계별 agent 역할 요약
- 단계별 산출물 연결

### 현재 대시보드의 역할 한계
- 대시보드는 현재 결과를 읽고 보여주는 계층이다
- 엔진의 source of truth는 artifact와 runtime 코드다
- UI는 운영 가시성을 높이지만, 엔진 품질 자체를 대체하지는 않는다

## 11. 스크린샷/증거 파일 처리
현재 Vibium 스크린샷 원본 저장 위치는 외부 경로를 사용할 수 있다. 이때 리뷰 UI에서 동일 run 산출물처럼 다루기 위해 artifact 폴더 쪽으로 파일을 물질화한다.

현재 우선순위는 아래와 같다.
1. 하드 링크 생성 시도
2. 실패 시 파일 복사

이 정책을 둔 이유는 아래와 같다.
- Vibium 기본 저장 위치를 건드리지 않기 위해
- run artifact 관점의 추적성을 유지하기 위해
- 리뷰 UI에서 증거 파일을 일관되게 열기 위해

## 12. 현재 명령어 기준 운영 방법
### 엔진 단일 실행
```powershell
webqa-engine --url https://example.com --agent openai --mode full_web_qa
```

또는

```powershell
python -m slackbot_for_web.engine_cli --url https://example.com --agent openai --mode full_web_qa
```

### 실패 케이스 배치 재실행
```powershell
python -m slackbot_for_web.engine_cli --rerun-failures-from JOB-1234abcd --max-cases 20
```

### 대시보드 실행
```powershell
python -m slackbot_for_web.dashboard --host 127.0.0.1 --port 8787
```

### Slack thread memory card 추출
```powershell
python -m slackbot_for_web.memory_cards --memory-id MEM-fb9c644c
```

### Local vector memory index build/query
```powershell
python -m slackbot_for_web.memory_index build
python -m slackbot_for_web.memory_index query --text "모바일 정렬 안맞음 스크롤 깜빡임 플로팅 CTA depth" --top-k 5
```

### Slack 앱 실행
```powershell
webqa-slack
```

현재 Slack 모달은 `Target URL`만 입력받고, 내부적으로 `Full QA (E2E)` 단일 모드로 큐잉한다.
CLI도 같은 방향으로 정리되어 `--mode full_web_qa`를 기본 진입점으로 사용하고, `--preset`은 hidden compatibility alias로만 남겨둔다.

## 13. 현재 버전의 강점
- Slack 의존성을 엔진에서 분리했다
- LangGraph 기반 단계형 파이프라인이 실제 코드에 적용돼 있다
- 산출물 중심 추적 구조가 정착돼 있다
- 회귀 diff와 실패군 재실행 루프가 있다
- UI가 run 결과와 workflow를 운영 관점에서 확인할 수 있다
- 설정 및 핵심 최종 산출물에 Pydantic 검증이 붙어 있다

## 14. 현재 버전의 한계
- Claude 경로는 아직 미구현이다
- stage artifact schema는 아직 전부 엄격하게 잠기지 않았다
- HITL은 현재 상태값과 트리거 수준이지, 전용 승인 워크플로우까지는 없다
- legacy alias는 입력값 정규화(`qa_smoke`, `landing_page_qa` -> `full_web_qa`)에만 남아 있고, 내부 식별자는 `mode` 기준으로 정리됐다
- built-in mode catalog는 이제 `full_web_qa` 하나만 노출된다
- 대시보드는 운영 가시성은 높였지만, 비개발자용 제품 수준 UX로 완결된 상태는 아니다
- full-domain E2E 품질은 계속 회귀 기반으로 다듬어야 한다

## 15. 다음 문서 갱신 시점
아래 항목 중 하나라도 바뀌면 이 문서를 갱신한다.

- 버전 번호 변경
- LangGraph 단계 변경
- fallback 정책 변경
- needs_review 트리거 변경
- artifact 파일 구조 변경
- Pydantic 검증 범위 확대
- dashboard 리뷰 흐름 변경

## 관련 문서
- `docs/engine_first_architecture.md`: 엔진 우선 구조 요약
- `docs/mvp_spec_v1.md`: MVP 계약과 정책
- `docs/fallback_state_machine.md`: fallback 상태 머신 상세
- `docs/hitl_trigger_matrix.md`: HITL/needs_review 기준
- `docs/dashboard_ui.md`: 대시보드/UI 실행 메모
- `docs/vla_strategy_for_web_qa.md`: VLA 도입 전략과 시각적 상호작용 QA 확장 방향
- `docs/artifact_mode_migration_plan.md`: artifact의 `preset -> mode` 마이그레이션 계획
- `docs/slack_thread_vector_memory_plan.md`: Slack QA 스레드를 issue memory card와 local vector DB로 연결하는 실험 계획
