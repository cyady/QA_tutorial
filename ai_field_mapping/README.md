# ai_field_mapping

메모 기반 구조화 추출과 필드 매핑 QA 흐름을 한 폴더에서 관리하는 워크스페이스입니다.

## 구성

- `agent_a`
  메모 텍스트를 후보 풀(`candidate_pool`)로 변환합니다.
- `schema_generator`
  deal 기준 `effective_schema` 와 FN 리뷰 입력 파일을 생성합니다.
- `qa_review_ui`
  후보/모델 출력/FN 후보를 한 화면에서 검토하는 Streamlit UI입니다.

## 작업 흐름

1. `agent_a` 로 후보 풀 생성
2. `schema_generator` 로 `effective_schema` 생성
3. `schema_generator` 로 `fn_review_input` 생성
4. `qa_review_ui` 에서 휴먼 QA 진행

세부 실행 방법은 각 하위 프로젝트 `README.md` 를 기준으로 봅니다.
