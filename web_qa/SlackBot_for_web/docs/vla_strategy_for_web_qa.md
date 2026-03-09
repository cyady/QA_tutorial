# VLA 도입 전략 문서: Web QA 엔진용 시각적 상호작용 확장

작성일: 2026-03-07  
참조 대상: OpenVLA / OpenVLA-OFT 공식 사이트, OpenVLA 공식 GitHub README, OpenVLA 논문

## 문서 목적

이 문서는 현재 Web QA 엔진에 VLA(Vision-Language-Action) 성격의 능력을 붙이기 위한 전략 문서다.

핵심 목적은 두 가지다.

1. 현재 엔진이 약한 `시각적 상호작용 QA` 영역을 명확히 정의한다.
2. OpenVLA에서 가져올 수 있는 설계 원칙과, 웹 QA 도메인에 맞게 바꿔야 하는 부분을 분리한다.

이 문서는 `지금 당장 OpenVLA 모델을 붙인다`는 구현 문서가 아니다.  
정확히는 `웹 QA용 VLA-like 아키텍처`를 설계하기 위한 기준 문서다.

## 한 줄 결론

우리에게 필요한 것은 `로봇용 OpenVLA 자체`가 아니라, OpenVLA가 보여준 다음 구조다.

- 시각 입력을 읽고
- 자연어 목표를 이해하고
- 행동을 연속적으로 선택하며
- 시각 피드백을 다시 받아
- 실패 시 재시도/보정하는 폐루프(closed-loop) 정책

이 개념은 웹 QA에도 매우 유효하다. 다만 action space, 데이터셋, 성공 기준, 실행 도구는 브라우저 도메인에 맞게 완전히 다시 정의해야 한다.

## 1. 현재 엔진의 출발점

현재 엔진은 LangGraph 기반 `Map -> Plan -> Execute -> Report` 구조이며, 강점은 아래에 있다.

- 페이지 접근 가능 여부 확인
- URL 이동/라우팅 확인
- 헤더/CTA/푸터/폼 중심의 구조적 커버리지
- 기본 렌더링 이상 탐지
- artifact 중심 추적성과 회귀 비교

반대로 현재 약한 영역은 아래다.

- 스크롤에 따라 나타나는 애니메이션/섹션 상태 검증
- hover 상태에서만 보이는 UI 검증
- 클릭 가능한 것처럼 보이지만 실제 클릭이 막히는 상태
- overlay, sticky, z-index, pointer-events로 인한 시각적 클릭 방해
- 이미지/캔버스/애니메이션 중심 페이지에서의 실질적 품질 판단
- before/after 화면 비교 기반의 시각 회귀 검출

즉, 현재 엔진은 `navigation/render QA`에 강하고, `visual interaction QA`에는 아직 약하다.

## 2. 직전 대화 기준: VLA로 강해지는 QA 영역

아래 영역은 VLA 또는 VLA-like 구조를 붙일 때 실질적으로 강해지는 영역이다.

### 2.1 VLA 적용 시 강해지는 영역

- 스크롤 트리거 애니메이션 검증
- hover 상태 검증
- 클릭 가능성의 시각 검증
- 레이아웃 파손 검출
- 이미지/캔버스/WebGL 중심 UI 검증
- sticky/fixed 요소가 본문을 가리는 문제 검출
- 팝업/툴팁/드롭다운/mega menu 상태 전이 검증
- before/after 캡처 기반 상태 변화 검증
- 시각 회귀(diff)와 상호작용 후 회귀 검출

### 2.2 VLA 없이 특히 어려운 영역

- DOM에는 있는데 화면에는 안 보이는 문제
- hover 전용 UI 문제
- scroll reveal 실패
- 클릭 불가의 시각적 원인 파악
- 텍스트가 거의 없는 Framer/랜딩 페이지 QA
- 캔버스, Lottie, SVG 중심 UI의 맥락 파악
- 실제 사용자 눈에 보이는 우선순위에 따른 QA

### 2.3 VLA가 있어도 별도 증거가 필요한 영역

VLA가 들어와도 아래는 DOM/DevTools/API/로그 기반 검증이 여전히 필요하다.

- 라우팅/링크 목적지의 정확성
- 폼 validation 로직
- 네트워크/API 실패 원인
- 접근성 세부 규칙
- SEO/메타태그
- 인증/결제/민감 플로우
- 서버 상태/데이터 정합성

따라서 목표는 `VLA 단독 QA`가 아니라 `VLA + DOM/DevTools + deterministic browser actions`의 하이브리드다.

## 3. OpenVLA에서 가져와야 할 핵심 아이디어

OpenVLA는 `이미지 관측 + 자연어 지시 -> 행동 예측` 구조의 open-source VLA다. 논문은 OpenVLA가 이미지 관측과 자연어 task instruction을 입력받아 robot control action을 예측한다고 설명한다. OpenVLA-OFT는 여기에 다중 이미지 입력, 더 빠른 추론, 재시도 성향이 있는 closed-loop behavior를 강화하는 방향을 보여준다.

웹 QA에 그대로 가져와야 할 것은 모델명이 아니라 아래 원칙들이다.

### 3.1 Observation -> Instruction -> Action 구조

OpenVLA는 `이미지 관측`과 `언어 지시`를 함께 받아 행동을 예측한다.  
웹 QA에서도 이 구조는 그대로 유효하다.

브라우저 QA로 번역하면 아래와 같다.

- Observation:
  - 전체 화면 스크린샷
  - 섹션 crop 이미지
  - DOM/a11y tree
  - URL
  - viewport
  - 콘솔/네트워크 요약
  - 직전 액션과 결과
- Instruction:
  - "이 CTA가 실제 클릭 가능한지 검증하라"
  - "스크롤 후 reveal 섹션이 정상 렌더링되는지 확인하라"
  - "hover 후 메뉴가 보이고 클릭 가능한지 확인하라"
- Action:
  - scroll
  - hover
  - click
  - focus/tab
  - wait
  - inspect text/style/layout
  - capture screenshot/crop

즉, 웹 QA용 VLA도 결국은 `현재 화면을 보고 다음 액션을 고르는 정책`이다.

### 3.2 시각 피드백 기반 폐루프(closed-loop)

OpenVLA/OFT 자료에서 중요한 점은 단순 일회성 예측이 아니라, 시각 피드백을 반영하는 강한 closed-loop behavior다. OFT 사이트는 visual feedback 반응성과 retrying behavior를 중요한 질적 차이로 제시한다.

이건 웹 QA에서 매우 중요하다.

예시:

- 첫 hover 후 메뉴가 안 보이면 다시 hover 위치/대상을 조정
- scroll 후 섹션이 안 나타나면 추가 scroll 또는 wait
- 클릭 후 overlay 때문에 실패하면 다른 좌표/대상 재시도
- sticky header가 가리면 viewport 조정 후 다시 클릭

즉, 웹 QA용 VLA는 `한 번 행동하고 끝`이 아니라 `행동 -> 관측 -> 수정 행동` 구조여야 한다.

### 3.3 다중 시점 입력(multi-image / temporal context)

OpenVLA-OFT는 다중 이미지 입력을 지원하고, 여러 카메라 입력을 활용하는 방향을 보여준다.

웹 QA로 번역하면 이는 아래와 같다.

- 현재 화면 1장만 보지 않는다.
- 아래 묶음을 같이 본다.
  - interaction 전 전체 스크린샷
  - interaction 후 전체 스크린샷
  - 대상 요소 crop 전/후
  - viewport 정보
  - 필요 시 모바일/데스크톱 비교 프레임

즉, 웹 QA용 VLA는 단일 정적 스크린샷보다 `짧은 상태 시퀀스`를 입력으로 삼는 것이 맞다.

### 3.4 Action chunking 개념

OFT는 action chunking과 병렬 decoding으로 속도를 크게 끌어올린다.

웹 QA로 바로 번역하면, "한 토큰당 한 행동"보다 아래가 더 적합하다.

- micro-plan 단위 action chunk
  - 예: `scroll 2회 -> wait 500ms -> hover CTA -> capture crop`
- probe template 단위 action chunk
  - 예: `clickability probe`, `hover probe`, `reveal probe`

즉, 우리 엔진도 나중에는 단일 행동 나열보다 `재사용 가능한 상호작용 묶음`을 정책 단위로 가져가는 편이 낫다.

### 3.5 적응 가능성(fine-tuning / adaptation)

OpenVLA의 큰 장점 중 하나는 다양한 환경에 대해 fine-tuning/adaptation을 강조한다는 점이다. 공식 README는 LoRA 같은 parameter-efficient fine-tuning, REST API 배포, 다양한 데이터 혼합을 강조한다.

웹 QA에도 같은 철학이 필요하다.

- 모든 사이트에 같은 정책을 하드코딩하지 않는다.
- 공통 정책 위에 사이트/프레임워크/패턴별 적응층을 둔다.
- Framer/Webflow/Next.js/SPA/캔버스형 랜딩 페이지 등 유형별 adapter를 둔다.
- reviewer correction을 다음 정책 개선 데이터로 축적한다.

## 4. OpenVLA를 그대로 쓰면 안 되는 이유

이 부분은 분명히 해둘 필요가 있다.

OpenVLA는 매우 유익한 참조 사례이지만, 현재 우리에게는 `직접 도입 모델`이 아니다.

### 4.1 action space가 다르다

OpenVLA는 7-DoF robot control action을 예측한다. 웹 QA는 아래 같은 action space가 필요하다.

- `scroll(amount, direction)`
- `hover(selector|ref|bbox|xy)`
- `click(selector|ref|bbox|xy)`
- `focus(selector)`
- `press(key)`
- `type(selector, text)`
- `wait(condition|ms)`
- `snapshot(full|crop|element)`
- `inspect_dom(selector)`
- `inspect_style(selector)`
- `inspect_hit_test(xy)`

즉, 브라우저 action tokenizer와 policy head는 별도로 설계해야 한다.

### 4.2 데이터가 다르다

OpenVLA는 로봇 demonstration 데이터로 학습되었다. 우리에게 필요한 데이터는 아래다.

- 브라우저 상호작용 trajectory
- before/after 스크린샷
- DOM/a11y snapshot
- action log
- reviewer verdict
- defect label
- issue severity

즉, `Open X-Embodiment` 대신 `Web QA Interaction Dataset`이 필요하다.

### 4.3 성공 기준이 다르다

로봇은 물체 조작 성공률을 본다. 웹 QA는 아래를 본다.

- 사용자가 기대한 UI 변화가 있었는가
- 클릭 가능한 것처럼 보이는 요소가 실제로 클릭 가능한가
- scroll/hover 이후 콘텐츠가 정상적으로 보이는가
- layout overlap/occlusion이 발생했는가
- evidence가 충분한가

### 4.4 계산 비용이 작지 않다

OpenVLA-OFT FAQ는 inference조차 대략 16GB 전후급 GPU 메모리를 전제로 설명한다. 이 수치는 로봇 정책 기준이지만, 핵심 메시지는 명확하다. `self-hosted VLA는 즉시 운영 기본값으로 두기 어렵다.`

따라서 우리 전략은 아래처럼 가는 것이 맞다.

- 단기: API 기반 멀티모달 + deterministic 브라우저 툴
- 중기: 웹 QA 전용 VLA-like policy 실험
- 장기: 자체 fine-tuned browser interaction policy

## 5. 우리 엔진에 필요한 VLA-like 목표 상태

우리가 목표로 해야 하는 것은 아래 4층 구조다.

### 5.1 Perception Layer

입력 수집 계층

필수 입력:

- full-page screenshot
- viewport screenshot
- element crop
- DOM/a11y tree
- URL/title/text
- computed style 일부
- element bounding box
- z-index / pointer-events / visibility 정보
- console/network summary
- 직전 action/result

선택 입력:

- scroll 전/후 프레임
- hover 전/후 프레임
- mobile/desktop 비교 프레임
- video-like frame sequence

### 5.2 Policy Layer

자연어 목표와 현재 관측을 받아 다음 action 또는 action chunk를 선택하는 계층

예시 목표:

- "이 hero CTA가 실제 클릭 가능한지 검증하라"
- "3번째 섹션 reveal animation이 정상 종료되는지 확인하라"
- "hover 후 submenu가 보이는지, 그리고 클릭 가능한지 확인하라"

출력 예시:

- `hover(@cta_hero_primary)`
- `scroll(down, 2)`
- `wait_for_visual_change(800ms)`
- `capture_crop(@cta_hero_primary)`
- `click(@cta_hero_primary)`

### 5.3 Execution Layer

정책이 제안한 action을 Vibium/DevTools/브라우저 skill로 실제 실행하는 계층

원칙:

- action은 전부 실제 도구로 수행
- 실패 시 action-level retry와 대안 action 수행
- destructive action은 여전히 금지

### 5.4 Verification Layer

실행 전/후 관측을 비교해서 성공/실패/needs_review를 판정하는 계층

예시:

- hover 후 opacity 변화 없음 -> hover 반응 실패 후보
- click 후 URL 변화 없음 + modal 없음 + console error -> click failure 후보
- scroll 후 section bbox가 viewport 안으로 들어왔으나 여전히 invisible -> reveal/render 이슈 후보
- 요소 bbox는 노출 상태인데 상단 fixed overlay와 hit-test 충돌 -> 클릭 방해 이슈 후보

## 6. Web QA용 action space 제안

초기 버전 action space는 아래처럼 제한하는 것이 좋다.

### 6.1 핵심 상호작용 action

- `scroll_viewport`
- `scroll_element`
- `hover_element`
- `click_element`
- `focus_element`
- `press_key`
- `wait`
- `snapshot_page`
- `snapshot_element`

### 6.2 진단 action

- `read_dom`
- `read_a11y_tree`
- `read_computed_style`
- `read_bbox`
- `hit_test`
- `list_console_errors`
- `list_network_failures`

### 6.3 probe 단위 action chunk

이 문서 기준으로는 아래 3개를 우선 1급 시민으로 올리는 것이 맞다.

- `scroll_probe`
  - scroll -> wait -> capture -> compare
- `hover_probe`
  - hover -> wait -> capture -> style/bbox compare
- `clickability_probe`
  - ensure visible -> hit-test -> click -> observe route/state change

이 세 가지가 현재 엔진의 가장 큰 약점을 가장 직접적으로 보완한다.

## 7. 데이터 전략

VLA-like 엔진은 결국 데이터 품질이 중요하다. OpenVLA가 대규모 demonstration과 adaptation을 강조한 이유도 여기에 있다.

우리 쪽 데이터는 아래 형태로 축적해야 한다.

### 7.1 수집 단위

한 샘플은 아래를 포함한다.

- page metadata
- pre-action screenshot
- post-action screenshot
- DOM/a11y snapshot
- action spec
- action result
- expected visual change
- actual visual change
- verdict: pass/fail/needs_review
- finding label
- reviewer comment

### 7.2 데이터 소스

- 현재 run artifact
- `execution_log.json`
- `test_case_results.json`
- `qa_report.json`
- quick preview에서 reviewer가 본 evidence
- Agentation annotation 결과
- 실패 케이스 재실행 결과
- 회귀 diff 결과

### 7.3 라벨링 우선순위

처음부터 모든 문제를 라벨링할 필요는 없다. 아래부터 시작하는 것이 효율적이다.

1. hover failure
2. click blocked
3. reveal animation missing
4. sticky occlusion
5. overlay occlusion
6. layout overlap
7. text invisible despite DOM presence

## 8. 평가 전략

웹 QA용 VLA-like 엔진은 단순 accuracy보다 `실제 QA 성공`을 기준으로 봐야 한다.

### 8.1 핵심 지표

- issue detection recall
- false positive rate
- evidence sufficiency rate
- retry recovery rate
- interaction success rate
- time-to-verdict
- token/compute cost per verified issue

### 8.2 케이스군

반드시 별도 벤치셋으로 관리해야 할 케이스

- Framer landing pages
- animation-heavy pages
- hover menu pages
- sticky header heavy pages
- canvas/svg-heavy pages
- lazy-load image grids
- mobile-only / desktop-only interaction pages

### 8.3 baseline 비교

최소한 아래 세 기준과 비교해야 한다.

- 현재 엔진
- 현재 엔진 + rule-based probe
- VLA-like policy + rule-based verifier

즉, VLA를 붙인다고 바로 끝이 아니라 `규칙 기반 대비 얼마나 더 잡는가`를 반드시 확인해야 한다.

## 9. 권장 도입 단계

### Phase 0. VLA 없이 먼저 할 일

이건 반드시 선행해야 한다.

- `scroll_probe`, `hover_probe`, `clickability_probe`를 deterministic rule로 먼저 구현
- artifact schema에 visual-interaction evidence 필드 추가
- issue taxonomy에 visual-interaction 계열 추가
- baseline false positive / false negative 측정

이 단계 없이 바로 VLA로 가면 "모델이 좋아졌는지"를 측정할 기준이 없다.

### Phase 1. VLA-like planner

멀티모달 API를 사용하되 action은 deterministic tool layer가 수행

역할:

- 어떤 probe를 어디에 적용할지 결정
- 어느 요소가 시각적으로 중요한지 판단
- 상호작용 후 어떤 변화가 기대되는지 기술

이 단계는 가장 현실적이고 현재 엔진과도 잘 맞는다.

### Phase 2. Closed-loop interaction policy

정책이 `관측 -> action -> 재관측 -> 수정 action`을 2~4 step 정도 반복할 수 있게 한다.

예시:

- hover 실패 -> 위치 조정 후 재hover
- click 실패 -> scroll align 후 재click
- reveal 실패 -> wait 추가 후 재검증

이 단계부터 비로소 VLA-like 성격이 강해진다.

### Phase 3. Browser-domain adaptation

실행 데이터와 reviewer correction을 축적한 뒤, 브라우저 도메인 전용 정책을 별도 fine-tuning하거나 distillation한다.

가능 후보:

- screenshot + DOM 요약 + action history -> next action
- screenshot pair -> visual change classifier
- screenshot crop + style snapshot -> clickability blocker classifier

### Phase 4. 자체 Web QA VLA

장기적으로는 아래 구조까지 갈 수 있다.

- vision encoder
- language/policy backbone
- browser action head
- evidence verifier head
- defect classifier head

이 단계는 연구 과제다. 제품 MVP의 즉시 목표는 아니다.

## 10. 실무 결론

실무적으로는 아래 판단이 맞다.

### 10.1 지금 당장 해야 할 것

- OpenVLA를 설치해서 붙이는 것 아님
- OpenVLA의 개념을 가져와 `VLA-like browser policy` 설계를 시작하는 것
- 우선은 rule-based probe + multimodal planner 조합부터 시작하는 것

### 10.2 지금 당장 하지 말아야 할 것

- 로봇용 action model을 브라우저에 억지로 적용
- 대규모 self-hosted VLA를 운영 기본값으로 채택
- benchmark 없이 VLA 성능이 좋아졌다고 가정

### 10.3 가장 중요한 설계 원칙

`시각 품질 판단`과 `실제 행동 실행`은 분리한다.

- 판단: 멀티모달/VLA-like policy
- 실행: Vibium/DevTools
- 검증: before/after evidence + DOM/diagnostics
- 최종 판정: deterministic schema + HITL fallback

이 구조가 현재 엔진과 가장 잘 이어진다.

## 10.1 현재 구현 상태

이 문서 작성 이후 초기 구현이 반영되었다.

- `domain_context_map.json`에 interaction target/hint 추출 추가
- `coverage_plan.json`과 `test_cases.json`에 `visual_probe_plan` 추가
- execution 단계에 아래 deterministic probe 추가
  - `scroll_probe`
  - `hover_probe`
  - `clickability_probe`
- probe 산출물 `visual_probes.json` 추가
- probe summary를 `test_case_results.json`, `qa_report.json`, `result.json`에 반영

즉, 현재는 `Phase 0 + 일부 Phase 1` 수준으로 볼 수 있다.  \n멀티모달 planner 자체는 아직 없고, 시각적 상호작용 evidence를 deterministic probe로 먼저 쌓는 단계다.

## 11. 현재 프로젝트 기준 제안

현재 코드베이스 기준 다음 순서가 가장 현실적이다.

1. `visual_probe_policy.md` 작성
   - scroll/hover/clickability probe 정의
2. `execution_log.json`, `test_case_results.json`에 visual probe evidence 추가
3. planning 단계에서 `interaction targets` 추출 추가
4. execution 단계에서 deterministic probe 우선 실행
5. report 단계에서 visual-interaction issue taxonomy 추가
6. 그 다음에야 multimodal planner/VLA-like closed-loop 실험 시작

즉, VLA는 다음 단계이고, 그 전에 `probe contract`를 먼저 잠가야 한다.

## 12. 참고 소스와 해석

### 핵심 참고 사실

- OpenVLA는 이미지 관측과 자연어 지시를 입력받아 행동을 예측하는 open-source VLA다.
- OpenVLA는 970k robot trajectories 기반 generalist manipulation policy를 강조한다.
- OpenVLA README는 lightweight inference interface, REST serving, LoRA fine-tuning, 다양한 데이터 혼합을 제공한다.
- OpenVLA-OFT는 다중 이미지 입력, 더 빠른 inference, 더 나은 성공률, retrying behavior와 visual feedback 반응성을 강조한다.

### 우리 프로젝트에 대한 해석

위 사실들로부터 아래를 도출할 수 있다.

- 웹 QA에도 `observation + instruction + action + feedback` 구조가 필요하다.
- 단일 스크린샷보다 multi-frame / before-after 입력이 유리하다.
- 단일 click보다 action chunk와 retry loop가 유리하다.
- 대규모 모델 자체보다, adaptation 가능한 action policy 설계가 더 중요하다.
- 초기 단계는 fine-tuned VLA보다 `하이브리드 정책`이 현실적이다.

## Sources

- OpenVLA project site: https://openvla.github.io/
- OpenVLA GitHub README: https://github.com/openvla/openvla
- OpenVLA paper: https://arxiv.org/abs/2406.09246
- OpenVLA-OFT site: https://openvla-oft.github.io/
