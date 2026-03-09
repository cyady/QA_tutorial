# SlackBot_for_web

Slack, CLI, 대시보드 채널에서 공통 웹 QA 엔진을 호출하는 Python 프로젝트입니다.

## 현재 범위

- `/webqa` 슬래시 커맨드 + 모달 입력
- 비동기 큐 실행
- Gemini API + Vibium MCP 기반 브라우저 QA
- 결과 요약, step 로그, artifact 기록

## 설치

루트 저장소(`QA_tutorial`) 기준:

```bash
cd web_qa/SlackBot_for_web
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

## 환경 변수

`.env.example` 를 `.env` 로 복사해서 사용합니다.

필수:

- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`
- `GEMINI_API_KEY`

선택:

- `DEFAULT_AGENT`
- `GEMINI_MODEL`
- `GEMINI_TIMEOUT_SECONDS`
- `GEMINI_MAX_REMOTE_CALLS`
- `VIBIUM_MCP_COMMAND`
- `VIBIUM_MCP_ARGS`
- `ARTIFACT_ROOT`

## 실행

```bash
python -m slackbot_for_web.main
```

## 참고

- 상세 아키텍처 문서는 `docs/` 아래에 정리되어 있습니다.
- 이 프로젝트는 `ai_field_mapping` 파이프라인과 분리해서 관리합니다.
