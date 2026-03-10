# Slack Thread Vector Memory Plan

작성일: 2026-03-10

## 문서 목적
이 문서는 Slack QA 스레드에 쌓이는 사람 리뷰를 별도 수동 라벨링 작업 없이 `vector memory`로 활용하기 위한 실험 계획을 정리한다.

목표는 `모델 재학습`이 아니라 아래 두 가지다.

1. 과거 사람 QA 스레드를 현재 엔진이 검색 가능한 메모리로 활용
2. retrieval 결과를 `planning / execution / report`에 연결

## 한 줄 요약
현재 단계에서는 `수동 라벨링 파이프라인`보다 `Slack QA thread -> issue memory card -> local vector DB -> 엔진 retrieval` 구조가 더 실용적이다.

## 왜 이 방향이 맞는가
현재 사람이 Slack 스레드에 남기는 피드백은 이미 아래 정보를 포함한다.

- 어떤 URL/페이지에서 발견했는가
- desktop / mobile / 실기기 mobile 중 어느 환경인가
- 어떤 시각적/상호작용 이슈인가
- 왜 문제라고 판단했는가
- 스크린샷/영상 같은 증거가 무엇인가

이 정보는 일반 공개 웹페이지 데이터보다 현재 프로젝트 목표에 더 가깝다.

특히 다음 영역은 사람 QA 스레드가 매우 가치가 높다.

- 애니메이션 재실행
- 스크롤 경계 flicker
- 모바일 정렬 불일치
- z-index / depth 문제
- 줄바꿈 가독성
- 실기기와 데스크톱 에뮬레이션 차이

## 왜 전수 수동 라벨링은 피해야 하는가
- 팀이 별도 라벨링 업무를 떠안게 된다
- QA 리뷰와 별개로 데이터 제작 공정이 추가된다
- 장기적으로 유지 비용이 크다
- 라벨 품질이 담당자마다 흔들릴 가능성이 높다

따라서 현 단계의 원칙은 아래와 같다.

1. 사람이 새 라벨을 쓰게 하지 않는다
2. 이미 존재하는 Slack 스레드를 메모리 자산화한다
3. retrieval은 참고 신호로만 쓰고, 최종 판정은 현재 run evidence로 내린다

## 권장 아키텍처
권장 흐름은 아래와 같다.

1. Slack 스레드 적재 트리거 발생
2. 해당 스레드 원문/첨부파일/메타데이터 수집
3. raw thread를 `issue memory card`로 구조화
4. `issue memory card`를 임베딩하여 vector DB에 저장
5. 엔진이 현재 run 맥락으로 retrieval 수행
6. retrieval 결과를 planning / execution / report에 반영

핵심은 `raw thread`를 바로 벡터화하지 않고, `issue memory card`로 구조화한 뒤 벡터화하는 것이다.

## raw thread를 바로 벡터화하면 안 되는 이유
- 하나의 스레드에 여러 이슈가 섞일 수 있다
- 일정 대화, 정정, 잡담 같은 노이즈가 포함된다
- retrieval 결과가 너무 크고 덜 정확해진다
- metadata filter를 걸기 어렵다

따라서 저장 단위를 다음처럼 분리하는 것이 맞다.

- `raw_thread_archive`: 원문 보존용
- `issue_memory_cards`: 검색용 구조화 데이터
- `vector_index(cards)`: retrieval용 벡터 인덱스

## Issue Memory Card 정의
`issue memory card`는 Slack 스레드에서 추출한 단일 QA 이슈 단위의 메모리 객체다.

예시:

```json
{
  "card_id": "thread-1736429012-issue-04",
  "job_id": "JOB-a0a27da4",
  "thread_ts": "1736429012.552399",
  "page_url": "https://maroon-yards-063878.framer.app/alphakey-insight-rm",
  "domain": "maroon-yards-063878.framer.app",
  "framework_hint": "framer",
  "platform": "mobile",
  "issue_types": ["animation_replay", "flicker"],
  "summary": "스크롤 재진입 시 히어로 애니메이션이 다시 실행되고 경계 구간에서 깜빡임이 발생함",
  "observation": "스크롤을 위아래로 반복할 때 같은 애니메이션이 다시 재생되고 중간 구간에서 점멸이 보임",
  "expected_behavior": "최초 진입 시 한 번만 실행되고 이후 재진입에서는 반복 재생되지 않아야 함",
  "evidence_refs": ["slack-file-001.mov"],
  "source_message_ts": "1736429033.118799",
  "created_at": "2026-03-10T12:11:00+09:00"
}
```

## 카드 필수 필드 제안
최소 필드는 아래 정도면 충분하다.

- `card_id`
- `job_id`
- `thread_ts`
- `page_url`
- `domain`
- `framework_hint`
- `platform`
- `issue_types`
- `summary`
- `observation`
- `expected_behavior`
- `evidence_refs`
- `source_message_ts`
- `created_at`

선택 필드:

- `viewport`
- `section_hint`
- `severity_hint`
- `keywords`
- `raw_excerpt`
- `duplicate_of`

## 카드를 어떻게 생성할 것인가
초기 단계에서는 아래 순서를 권장한다.

1. raw thread 수집
2. 메시지별 텍스트/첨부파일 정리
3. LLM으로 이슈 분해
4. 카드 초안 생성
5. 바로 저장

즉, 사람 승인 단계를 처음부터 넣지 않는다.

초기 품질이 부족하면 나중에 아래만 추가한다.

- duplicate merge
- message noise filter
- confidence score

## Slack 스레드 적재 트리거
사용자가 제안한 `/RAG_DB` 흐름은 가능하다. 다만 구현상 아래 비교가 필요하다.

### 옵션 A: Slash Command
- 예: `/rag_db`
- 장점: 사용자에게 명시적
- 단점: 어떤 thread를 적재하는지 문맥이 모호할 수 있음

### 옵션 B: Message Shortcut
- 예: `Save Thread to QA Memory`
- 장점: 특정 스레드/메시지 컨텍스트가 명확함
- 단점: 설정이 조금 더 필요함

### 옵션 C: Reaction Trigger
- 예: 특정 이모지 반응 시 적재
- 장점: QA 팀 사용성은 좋을 수 있음
- 단점: 운영 규칙이 없으면 혼선 가능

현재 추천은 아래 순서다.

1. `message shortcut` 1순위
2. `/rag_db` 보조

이유는 스레드 문맥을 가장 안정적으로 잡기 쉽기 때문이다.

## 엔진에서 retrieval을 어디에 쓰는가
retrieval은 아래 세 지점에 연결하는 것이 좋다.

### 1. Planning
현재 URL/domain/framework/platform으로 유사 카드를 조회한 뒤, 해당 이슈 유형에 맞는 probe를 더 우선 생성한다.

예:
- 과거에 `animation_replay`가 많으면 `scroll re-entry probe` 추가
- 과거에 `mobile_overlay_depth`가 많으면 mobile probe 우선 생성

### 2. Execution
probe가 애매하게 실패할 때 유사 card를 다시 조회해 어떤 추가 확인이 필요할지 힌트를 얻는다.

예:
- 비슷한 Framer CTA는 click 후 modal depth 문제였음
- 비슷한 landing에서는 hover보다 scroll flicker가 핵심이었음

### 3. Report
현재 finding과 유사한 과거 사례를 첨부해 재발 패턴을 더 잘 설명한다.

예:
- `유사한 사람 QA 스레드 3건에서 같은 mobile alignment 문제가 관찰됨`

## retrieval이 정답이 아니어야 하는 이유
vector memory는 과거 메모리일 뿐, 현재 run의 사실을 대체하면 안 된다.

운영 원칙:

1. retrieval은 `힌트`
2. 최종 판정은 `현재 evidence`
3. 보고서에서 과거 사례를 쓸 때도 `유사 사례 참고`로만 표기

## 로컬 실험용 저장소 제안
초기 실험에서는 유료 vector DB가 필요 없다.

### 1차 추천
- `Chroma`
- 장점: 로컬 persistent 저장이 쉽고 metadata 붙이기 편함

### 대안
- `FAISS`
- 장점: 가볍고 빠름
- 단점: metadata 관리를 별도로 해야 함

### 운영형 후보
- `Qdrant`
- 장점: 나중에 서비스 구조로 옮기기 좋음
- 단점: 초기 실험엔 다소 무거움

현재 추천은 아래와 같다.

1. 빠른 실험: `Chroma`
2. 성능/제어 실험: `FAISS`
3. 운영 전환 시: `Qdrant`

## 임베딩 모델 제안
한국어와 영어가 섞일 가능성이 높으므로 multilingual 계열이 안전하다.

후보:

- `intfloat/multilingual-e5-base`
- `BAAI/bge-m3`

현재 목표는 최고 성능보다 `재현 가능한 로컬 실험`이므로, 초기에는 위 둘 중 하나로 시작하면 충분하다.

## 청킹 전략
초기 기준:

- `raw thread`: 원문 보존
- `issue memory card`: 검색 단위

즉, 주 retrieval 단위는 `card`다.

raw chunk는 아래 용도로만 둔다.

- 원문 감사
- 증거 재확인
- 보고서 인용 근거 확인

## 저장해야 할 메타데이터
최소 메타데이터:

- `job_id`
- `thread_ts`
- `channel_id`
- `page_url`
- `domain`
- `framework_hint`
- `platform`
- `issue_types`
- `created_at`

가능하면 같이 남길 것:

- `artifact_root`
- `slack_file_ids`
- `evidence_local_paths`
- `retrieved_from_message_ts`

## 실험 1단계 성공 기준
아래가 되면 1단계는 성공으로 본다.

1. 특정 Slack 스레드를 로컬에 저장할 수 있다
2. 한 스레드를 여러 개 `issue memory card`로 분해할 수 있다
3. 현재 URL/domain으로 유사 카드 top-k를 검색할 수 있다
4. 검색 결과를 planning prompt에 붙일 수 있다

## 지금 당장 하지 않을 것
- 수동 전수 라벨링
- fine-tuning
- 유료 vector DB 구매
- retrieval 결과를 자동 정답으로 취급

## 다음으로 필요한 Slack 앱 설정 작업
문서화 이후 바로 손대야 할 설정은 아래다.

1. `message shortcut` 추가 여부 결정
2. `/rag_db` slash command 추가 여부 결정
3. thread context에서 원문/첨부를 읽기 위한 scope 점검
4. Slack 파일을 로컬 artifact로 복사 저장하는 정책 정리
5. `job_id <-> thread_ts` 연결 메타데이터 저장 위치 결정

## 추천 구현 순서
1. 문서 확정
2. Slack 앱 설정 추가
3. raw thread ingest 구현
4. issue memory card 추출기 구현
5. local vector DB 저장
6. planning 단계 retrieval 연결
7. execution/report 단계 확장

## 결론
현재 프로젝트 단계에서는 `라벨링 기반 학습`보다 `Slack QA 스레드의 vector memory화`가 더 현실적이다.

정리하면 목표 구조는 아래 한 줄이다.

`Slack QA thread -> issue memory card -> local vector DB -> engine retrieval`
## 구현 상태

- 완료: Slack message shortcut `Save Thread to QA Memory`
- 완료: raw thread archive 저장 (`artifacts/_memory/MEM-*/`)
- 완료: 규칙 기반 `issue memory card` 추출 (`issue_memory_cards.json`)
- 완료: 로컬 vector memory index 빌드/조회 (`artifacts/_runtime/vector_memory/issue_memory_index.json`)
- 완료: planning 단계 retrieval 연결 (`memory_retrieval.json`)
- 다음: retrieval 결과를 리뷰 UI에서 더 직접적으로 노출하고 probe 우선순위 조정 규칙을 확장

## 현재 명령어

```powershell
webqa-memory-extract --memory-id MEM-6d671b14
webqa-memory-index build
webqa-memory-index query --text "모바일 정렬 안맞음 스크롤 깜빡임 플로팅 CTA depth" --top-k 5
```
