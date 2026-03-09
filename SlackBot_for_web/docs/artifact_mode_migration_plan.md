# Artifact Mode Migration Plan

작성일: 2026-03-08
대상 범위: `started.json`, `result.json`, `error.json`

## 목적
artifact 파일에서 legacy 키 `preset`을 제거하고 `mode` 단일 키 체계로 정리한다.

이 문서는 즉시 제거 문서가 아니라 단계적 마이그레이션 계획 문서다. 현재 코드는 이미 사용자 노출 계층에서는 `mode_key` 중심으로 동작하지만, artifact 계층은 아직 `schema_version = 1` 상태라 `preset`과 `mode`를 함께 기록한다.

## 현재 상태

### 이미 제거된 영역
- dashboard/API payload는 더 이상 `preset`을 노출하지 않는다.
- review/workflow UI도 `mode_key`, `mode_label`만 사용한다.
- 사용자 입력 경로는 `Full QA (E2E)` 단일 mode 기준으로 정리되어 있다.

### 아직 남아 있는 영역
- `webqa_runner.py`는 `started.json`, `result.json`, `error.json`에 `preset`과 `mode`를 함께 기록한다.
- 회귀 비교 로직은 과거 artifact 호환을 위해 `preset -> mode` fallback을 사용한다.
- `dashboard.py`는 과거 artifact를 읽기 위해 `result["preset"]`, `started["preset"]`를 fallback으로 읽는다.
- `validation_models.py`의 `ResultArtifactModel`은 아직 `preset`을 필수 필드로 본다.
- Slack 제출 스냅샷도 `preset`과 `mode`를 함께 남긴다.

## 왜 지금 바로 제거하지 않는가
지금 artifact에서 `preset`을 바로 삭제하면 아래 문제가 생긴다.

1. `schema_version = 1` artifact와 새 artifact를 같은 reader가 동시에 처리해야 한다.
2. 회귀 비교가 과거 run과 current run을 같은 버킷으로 묶는 과정에서 호환성이 깨질 수 있다.
3. `result.json` 검증 모델이 즉시 `ValidationError`를 발생시킬 수 있다.
4. 운영 중 남아 있는 기존 run 디렉터리들이 대시보드에서 일부 깨질 수 있다.

즉, payload layer는 지금 제거해도 안전했지만, artifact layer는 schema migration 없이 제거하면 운영 리스크가 크다.

## 목표 상태

### 최종 목표
- `started.json`, `result.json`, `error.json`은 `mode`만 기록한다.
- `schema_version = 2`를 사용한다.
- reader는 일정 기간 동안만 `preset` fallback을 지원한다.
- fallback 제거 이후에는 코드와 문서에서 artifact-level `preset` 의존성을 없앤다.

### 최종 artifact 예시
```json
{
  "schema_version": 2,
  "job_id": "JOB-1234abcd",
  "agent": "openai",
  "mode": "full_web_qa",
  "url": "https://example.com/",
  "status": "pass"
}
```

## 단계별 계획

### Phase 0. 현재 상태 유지
현재 상태를 명시적으로 인정한다.

- writer: `preset` + `mode` 동시 기록
- reader: `mode` 우선, `preset` fallback
- dashboard/API: `preset` 비노출
- schema: `schema_version = 1`

이 단계는 이미 적용된 상태다.

### Phase 1. Schema v2 도입
artifact schema에 명확한 버전 경계를 만든다.

필수 작업:
- `started.json`, `result.json`, `error.json`에 `schema_version`을 명시적으로 넣는다.
- 새 writer는 `schema_version = 2`에서 `mode`만 기록한다.
- legacy reader는 `schema_version = 1`이면 `preset` fallback을 허용한다.
- `validation_models.py`는 `schema_version` 기준으로 v1/v2를 함께 검증할 수 있게 분기한다.

권장 구현 방식:
- `ResultArtifactV1Model`
- `ResultArtifactV2Model`
- `StartedArtifactV1Model`
- `StartedArtifactV2Model`
- `ErrorArtifactV1Model`
- `ErrorArtifactV2Model`

### Phase 2. Reader 이행
runtime reader를 `mode` 중심으로 전환하되, 일정 기간 동안만 v1 fallback을 유지한다.

대상 파일:
- `src/slackbot_for_web/webqa_runner.py`
- `src/slackbot_for_web/dashboard.py`
- `src/slackbot_for_web/validation_models.py`
- `src/slackbot_for_web/slack_app.py`
- 필요 시 `src/slackbot_for_web/engine_cli.py`

원칙:
- `mode`가 있으면 그것만 신뢰한다.
- `preset`은 `schema_version = 1` legacy artifact에서만 읽는다.
- 새 코드 경로에서는 `preset`을 write하지 않는다.

### Phase 3. Backfill 또는 무마이그레이션 결정
운영 정책을 하나 선택한다.

옵션 A. 무마이그레이션
- 기존 artifact는 그대로 둔다.
- reader가 v1/v2를 모두 이해하도록 유지한다.
- 장점: 구현이 단순하다.
- 단점: fallback 코드가 더 오래 남는다.

옵션 B. 제한적 backfill
- 최근 N일 또는 최근 M개 run만 변환 스크립트로 `schema_version = 2`로 승격한다.
- 장점: 대시보드/회귀 코드 정리가 빨라진다.
- 단점: 변환 스크립트와 검증 부담이 생긴다.

현재 프로젝트에는 옵션 A가 더 현실적이다. artifact가 파일 시스템에 쌓이는 구조라 과거 run을 강제로 rewrite하는 이득이 크지 않다.

### Phase 4. Fallback 제거
아래 조건이 충족되면 fallback을 제거한다.

조건:
1. 새 run artifact가 모두 `schema_version = 2`다.
2. 최근 운영에 필요한 run이 모두 `mode` 기반으로 조회 가능하다.
3. 회귀 비교가 `preset` 없이 안정적으로 동작한다.
4. dashboard/review UI에서 legacy fallback이 더 이상 필요 없다.

제거 대상:
- `payload.get("preset") or payload.get("mode")`
- `result.get("preset")`
- `started.get("preset")`
- `ResultArtifactModel.preset`

## 구체 작업 목록

### 코드 작업
1. `webqa_runner.py`
- artifact writer에 `schema_version`
- v2부터 `preset` 제거

2. `validation_models.py`
- result/started/error artifact를 v1/v2 분리
- `preset` 필드를 legacy 전용으로 내림

3. `dashboard.py`
- `schema_version = 1`일 때만 `preset` fallback
- 이후 sunset 시 fallback 제거

4. `slack_app.py`
- 제출 스냅샷 payload도 `mode` only로 정리할지 결정

### 검증 작업
1. 신규 run 생성 후 `started.json`, `result.json`, `error.json` 확인
2. 과거 run 디렉터리로 `/api/runs`, `/review`, `/workflow` 회귀 확인
3. 회귀 diff가 old/new artifact 혼합 환경에서도 유지되는지 확인

## 제거 시점 판단
artifact-level `preset` 제거 시점은 `지금`이 아니다.

제거 시점은 아래 조건을 만족한 뒤가 맞다.
- `schema_version = 2` 도입 완료
- reader의 v1/v2 호환 경로 검증 완료
- 최근 운영 run이 전부 v2로 누적
- dashboard/API/회귀 diff 회귀 테스트 완료

즉, 지금은 `계획 수립 + schema 준비` 단계가 맞고, 실제 제거는 `v2 artifact rollout` 이후가 맞다.

## 롤백 전략
문제가 생기면 즉시 아래로 되돌린다.

- writer를 `preset` + `mode` dual-write로 복구
- validation model을 v1 허용 모드로 되돌림
- dashboard fallback 재활성화

artifact는 파일 기반이므로 rollback은 코드 rollback이 핵심이다. 과거 artifact 파일을 일괄 수정하는 방식은 rollback 비용이 크므로 권장하지 않는다.
