# QA Dashboard UI

## Purpose
- Visualize LangGraph flow.
- Track artifact lineage from each agent stage to final QA report.
- View run-level metrics and QA outcomes in a dashboard.
- Provide a reviewer-friendly React screen with Agentation annotations.

## Run
```bash
webqa-dashboard --host 127.0.0.1 --port 8787
```

Or:
```bash
python -m slackbot_for_web.dashboard --host 127.0.0.1 --port 8787
```

Open:
- `http://127.0.0.1:8787`
- `http://127.0.0.1:8787/review` (React + Agentation)
- `http://127.0.0.1:8787/legacy` (existing static dashboard)

## What you can see
- LangGraph pipeline diagram (Map -> Plan -> Execute -> Report).
- Run list with status, token usage, finding count.
- Traceability chain by stage artifacts.
- QA result panel (`qa_report`, `result`, self-healing attempts, regression diff).
- Artifact browser (JSON/text/image files).
- Agentation toolbar for visual annotations on the review page.

## React Review UI (Agentation)

Install and build once:
```bash
cd review_ui
npm install
npm run build
```

After build, `webqa-dashboard` serves the React app at `/review`.

Local frontend development:
```bash
# terminal 1
webqa-dashboard --host 127.0.0.1 --port 8787

# terminal 2
cd review_ui
npm run dev
```

Open:
- `http://127.0.0.1:5173` (Vite dev server; `/api` is proxied to dashboard API)

## API endpoints
- `GET /api/runs?limit=300`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/files/{filename}`
