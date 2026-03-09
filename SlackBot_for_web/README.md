# SlackBot_for_web

"비개발자도 웹사이트를 자연어로 QA할 수 있는 AI"를 위한 Python Slack bot MVP.

## 현재 구현 범위

- `/webqa` 슬래시 커맨드 + 모달 입력
- 비동기 큐 실행
- `gemini > codex > claude` 우선순위 (기본값 `gemini`)
- Gemini **API** + Vibium MCP 기반 브라우저 QA 실행
- 프리셋별 지시문 분기(`qa_smoke`, `crawl_summary`, `bug_hunt`)
- 결과 요약 + step 로그 + 아티팩트 파일 Slack 전송 시도

## 1) 설치

```bash
cd SlackBot_for_web
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

## 2) 환경 변수

`.env.example`를 `.env`로 복사 후 설정:

필수:
- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`
- `GEMINI_API_KEY` (회사 공용 키)

선택:
- `DEFAULT_AGENT=gemini`
- `GEMINI_MODEL=gemini-2.5-flash`
- `GEMINI_TIMEOUT_SECONDS=300`
- `GEMINI_MAX_REMOTE_CALLS=80`
- `VIBIUM_MCP_COMMAND=npx`
- `VIBIUM_MCP_ARGS=vibium mcp --headless`
- `ARTIFACT_ROOT=artifacts`

## 3) Slack 앱 설정 (로컬 Socket Mode)

Bot Token Scopes:
- `commands`
- `chat:write`
- `files:write` (아티팩트 업로드용, 없으면 로컬 경로만 안내)

Slash command:
- `/webqa`

Socket Mode 활성화 후 앱 설치.

## 4) 실행

```bash
python -m slackbot_for_web.main
```

## 5) 실행 플로우

1. 사용자가 `/webqa` 실행
2. 모달에서 Agent/URL/Preset 선택
3. 큐에 작업 등록
4. 워커가 Gemini API 호출 + Vibium MCP 툴 실행
5. Slack에 요약/로그/아티팩트 전송

## 6) 아티팩트

작업별 경로:
- `artifacts/<JOB_ID>/started.json`
- `artifacts/<JOB_ID>/runner.log`
- `artifacts/<JOB_ID>/gemini_raw.txt`
- `artifacts/<JOB_ID>/result.json` 또는 `error.json`

## 7) 제한 사항

- `codex`, `claude`는 아직 placeholder adapter
- 현재는 단일 job/단일 워커 스레드 구조(영속 큐 아님)
