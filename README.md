# QA_tutorial

개인 QA 실험과 운영 도구를 한 저장소에서 관리하되, 성격이 다른 작업은 워크스페이스 단위로 분리해 둔 루트 저장소입니다.

## 워크스페이스

- `ai_field_mapping/`
  메모 기반 후보 추출, effective schema 생성, 휴먼 QA 리뷰 UI까지 이어지는 AI 필드 매핑 파이프라인입니다.
- `web_qa/`
  브라우저 기반 웹 QA 실행과 Slack 연동 실험을 모아 둔 공간입니다.

## 현재 포함된 프로젝트

- `ai_field_mapping/agent_a`
  메모 텍스트에서 `candidate_pool.jsonl` 을 생성하는 추출기
- `ai_field_mapping/schema_generator`
  effective schema, FN review input 생성기
- `ai_field_mapping/qa_review_ui`
  TP/FP/FN 리뷰와 필드별 지표 확인용 Streamlit UI
- `web_qa/SlackBot_for_web`
  Slack/CLI/대시보드 채널을 가진 웹 QA 엔진 MVP

## 별도 저장소

- `Codex/codex_QA_Automation`
  Re:catch 대량 업로드 자동화 전용 별도 저장소

## 관리 기준

- 자격 증명, 로컬 `.env`, 로그, 스크린샷, 임시 출력물은 커밋하지 않습니다.
- `node_modules/`, `.next/`, 가상환경 같은 무거운 로컬 의존성은 루트에서 무시합니다.
- 현재는 로컬 워크스페이스로 먼저 분리했고, GitHub 저장소도 이후 `ai_field_mapping` 과 `web_qa` 축으로 나누는 것을 염두에 두고 있습니다.
