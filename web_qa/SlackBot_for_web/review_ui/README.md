# Review UI (React + Agentation)

## 목적
- 기존 Python 대시보드 API(`/api/runs*`)를 그대로 사용
- 비개발자 QA 리뷰어가 읽기 쉬운 화면 제공
- Agentation으로 화면 요소 주석/피드백 수집

## 개발 실행
```bash
# terminal 1: backend API
webqa-dashboard --host 127.0.0.1 --port 8787

# terminal 2: frontend dev
cd review_ui
npm install
npm run dev
```

브라우저: `http://127.0.0.1:5173`

## 빌드 후 Python 서버에서 서빙
```bash
cd review_ui
npm run build
```

그 다음 `webqa-dashboard` 실행 시:
- `http://127.0.0.1:8787/review` 에서 React UI 접근 가능
- `http://127.0.0.1:8787/legacy` 에서 기존 내장 대시보드 접근 가능
