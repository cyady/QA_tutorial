from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import re
import subprocess
import sys

import streamlit as st


APP_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = APP_DIR.parent
REPO_ROOT = WORKSPACE_DIR.parent
AGENT_A_DIR = WORKSPACE_DIR / "agent_a"
SCHEMA_GENERATOR_DIR = WORKSPACE_DIR / "schema_generator"
DATA_DIR = APP_DIR / "data"
DECISIONS_DIR = DATA_DIR / "decisions"
DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
LAST_INPUTS_PATH = DATA_DIR / "last_inputs.json"
WS_RE = re.compile(r"\s+")


def repo_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except Exception:
        return str(path)


def resolve_user_path(path: str, prefer_base: Path | None = None) -> Path:
    raw = (path or "").strip()
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p

    bases: list[Path] = []
    for base in (Path.cwd(), prefer_base, WORKSPACE_DIR, REPO_ROOT):
        if base is None or base in bases:
            continue
        bases.append(base)

    for base in bases:
        candidate = (base / p).resolve()
        if candidate.exists():
            return candidate

    return ((prefer_base or WORKSPACE_DIR) / p).resolve()


def read_json(path: str) -> Any:
    p = resolve_user_path(path)
    return json.loads(p.read_text(encoding="utf-8-sig"))


def read_json_or_jsonl(path: str) -> Any:
    p = resolve_user_path(path)
    text = p.read_text(encoding="utf-8-sig").strip()
    if not text:
        return None
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _hangul_count(s: str) -> int:
    return sum(1 for ch in s if "\uac00" <= ch <= "\ud7a3")


def _latin_noise_count(s: str) -> int:
    return sum(1 for ch in s if "\u00c0" <= ch <= "\u024f")


def fix_mojibake_text(s: str) -> str:
    if not isinstance(s, str) or not s:
        return s
    try:
        repaired = s.encode("latin1").decode("utf-8")
    except Exception:
        return s
    before_score = _hangul_count(s) - _latin_noise_count(s)
    after_score = _hangul_count(repaired) - _latin_noise_count(repaired)
    return repaired if after_score > before_score else s


def fix_mojibake_obj(v: Any) -> Any:
    if isinstance(v, str):
        return fix_mojibake_text(v)
    if isinstance(v, list):
        return [fix_mojibake_obj(x) for x in v]
    if isinstance(v, dict):
        return {k: fix_mojibake_obj(val) for k, val in v.items()}
    return v


def flatten_model_output(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        out: list[dict[str, Any]] = []
        for x in payload:
            if isinstance(x, dict):
                out.append(x)
            elif isinstance(x, list):
                out.extend(flatten_model_output(x))
        return out
    return []


def load_candidate_pool(path: str) -> dict[str, Any]:
    payload = read_json_or_jsonl(path)
    if isinstance(payload, list):
        if not payload:
            return {"memo_id": "UNKNOWN", "candidates": []}
        return payload[0]
    return payload


def load_fn_candidates(path: str) -> list[dict[str, Any]]:
    payload = read_json_or_jsonl(path)
    if isinstance(payload, list):
        return payload
    return [payload]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_field_map(effective_schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fields = effective_schema.get("effective_fields", [])
    return {str(f.get("id")): fix_mojibake_obj(f) for f in fields}


def option_value_to_label_map(field_def: dict[str, Any]) -> dict[str, str]:
    attrs = field_def.get("attributes") or {}
    opts = attrs.get("options") if isinstance(attrs, dict) else None
    if not isinstance(opts, list):
        return {}
    out: dict[str, str] = {}
    for o in opts:
        if not isinstance(o, dict):
            continue
        ov = o.get("value")
        label = o.get("label")
        if ov is None:
            continue
        out[str(ov)] = fix_mojibake_text(str(label)) if label is not None else str(ov)
    return out


def format_extracted_value(item: dict[str, Any], field_map: dict[str, dict[str, Any]]) -> str:
    fd = fix_mojibake_obj(item.get("field_definition") or {})
    extracted = fix_mojibake_obj(item.get("extracted_value"))
    field_id = str(fd.get("id")) if fd.get("id") is not None else ""
    field_type = str(fd.get("type") or "")

    ref_def = field_map.get(field_id, {})
    ov_map = option_value_to_label_map(fd)
    if not ov_map and ref_def:
        ov_map = option_value_to_label_map(ref_def)

    if field_type in ("select", "multi-select"):
        labels: list[str] = []
        if isinstance(extracted, list):
            for x in extracted:
                if isinstance(x, dict) and "value" in x:
                    key = str(x["value"])
                    labels.append(f"{ov_map.get(key, key)} ({key})")
                else:
                    key = str(x)
                    labels.append(f"{ov_map.get(key, key)} ({key})")
        elif isinstance(extracted, dict) and "value" in extracted:
            key = str(extracted["value"])
            labels.append(f"{ov_map.get(key, key)} ({key})")
        else:
            key = str(extracted)
            labels.append(f"{ov_map.get(key, key)} ({key})")
        return ", ".join(labels)

    return json.dumps(extracted, ensure_ascii=False, indent=2) if isinstance(extracted, (list, dict)) else str(extracted)


def char_to_line_no(text: str, char_idx: Any) -> int | None:
    if not isinstance(char_idx, int):
        return None
    if char_idx < 0:
        return None
    if char_idx > len(text):
        char_idx = len(text)
    return text.count("\n", 0, char_idx) + 1


def get_line_text(text: str, line_no: int | None) -> str | None:
    if line_no is None:
        return None
    lines = text.splitlines()
    if line_no <= 0 or line_no > len(lines):
        return None
    return lines[line_no - 1]


def field_option_label(field_id: str, field_map: dict[str, dict[str, Any]]) -> str:
    if not field_id:
        return "(unassigned)"
    f = field_map.get(str(field_id)) or {}
    label = fix_mojibake_text(str(f.get("label") or "UNKNOWN"))
    ftype = str(f.get("type") or "-")
    return f"{field_id} | {label} | {ftype}"


def suggest_fn_output_path(candidate_pool_path: str) -> str:
    p = resolve_user_path(candidate_pool_path)
    stem = p.stem
    return repo_rel(SCHEMA_GENERATOR_DIR / "output" / f"{stem}_fn_review_input.json")


def _path_ok(path_str: str) -> bool:
    s = (path_str or "").strip()
    return bool(s) and resolve_user_path(s).exists()


def load_last_inputs() -> dict[str, str]:
    if not LAST_INPUTS_PATH.exists():
        return {}
    try:
        data = json.loads(LAST_INPUTS_PATH.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def save_last_inputs(data: dict[str, str]) -> None:
    LAST_INPUTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_INPUTS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def decision_file(memo_id: str) -> Path:
    return DECISIONS_DIR / f"{memo_id}.json"


def load_existing_decisions(memo_id: str) -> dict[str, Any]:
    fp = decision_file(memo_id)
    if fp.exists():
        return json.loads(fp.read_text(encoding="utf-8-sig"))
    return {"memo_id": memo_id, "updated_at": None, "model_decisions": [], "fn_decisions": []}


def save_decisions(payload: dict[str, Any]) -> None:
    fp = decision_file(payload["memo_id"])
    fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def aggregate_counts(field_map: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    field_map = field_map or {}
    for fp in DECISIONS_DIR.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        for row in data.get("model_decisions", []):
            field_id = str(row.get("field_id") or "UNASSIGNED")
            default_label = ""
            if field_id in field_map:
                default_label = fix_mojibake_text(str(field_map[field_id].get("label") or ""))
            elif row.get("field_label"):
                default_label = fix_mojibake_text(str(row.get("field_label")))
            bucket = counts.setdefault(
                field_id, {"field_id": field_id, "label": default_label, "tp": 0, "fp": 0, "fn": 0}
            )
            if not bucket.get("label"):
                bucket["label"] = default_label
            decision = row.get("decision")
            if decision == "TP":
                bucket["tp"] += 1
            elif decision == "FP":
                bucket["fp"] += 1
        for row in data.get("fn_decisions", []):
            if row.get("decision") != "FN":
                continue
            field_id = str(row.get("assigned_field_id") or "UNASSIGNED")
            default_label = ""
            if field_id in field_map:
                default_label = fix_mojibake_text(str(field_map[field_id].get("label") or ""))
            bucket = counts.setdefault(
                field_id, {"field_id": field_id, "label": default_label, "tp": 0, "fp": 0, "fn": 0}
            )
            if not bucket.get("label"):
                bucket["label"] = default_label
            bucket["fn"] += 1
    return sorted(
        counts.values(),
        key=lambda x: (-(x["tp"] + x["fp"] + x["fn"]), x["field_id"]),
    )


def app() -> None:
    st.set_page_config(page_title="QA Review UI", layout="wide")
    st.title("QA Review UI")
    st.caption("Review memo + model_output + FN candidates in one place, and track field TP/FP/FN.")

    remembered = load_last_inputs()
    path_defaults = {
        "memo_text_path": remembered.get("memo_text_path", repo_rel(AGENT_A_DIR / "data_w" / "memo_w1.txt")),
        "candidate_pool_path": remembered.get(
            "candidate_pool_path",
            repo_rel(AGENT_A_DIR / "outputs" / "runs_merged" / "w1" / "candidate_pool.jsonl"),
        ),
        "model_output_path": remembered.get(
            "model_output_path",
            repo_rel(AGENT_A_DIR / "model_output" / "w1_model_output.json"),
        ),
        "fn_input_path_input": remembered.get(
            "fn_input_path_input",
            repo_rel(SCHEMA_GENERATOR_DIR / "output" / "w1_fn_review_input.json"),
        ),
        "effective_schema_path_input": remembered.get(
            "effective_schema_path_input",
            repo_rel(SCHEMA_GENERATOR_DIR / "output" / "effective_schema_566552.json"),
        ),
        "deal_id_for_schema": remembered.get("deal_id_for_schema", "566552"),
    }
    for k, v in path_defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if "pending_effective_schema_path" in st.session_state:
        st.session_state["effective_schema_path_input"] = st.session_state.pop("pending_effective_schema_path")
    if "pending_fn_input_path" in st.session_state:
        st.session_state["fn_input_path_input"] = st.session_state.pop("pending_fn_input_path")

    with st.sidebar:
        st.subheader("Input Files")
        memo_text_path = st.text_input("Memo text (.txt)", key="memo_text_path")
        candidate_pool_path = st.text_input("candidate_pool (.json/.jsonl)", key="candidate_pool_path")
        model_output_path = st.text_input("model_output (.json/.jsonl)", key="model_output_path")
        fn_input_path = st.text_input("FN review input (.json/.jsonl)", key="fn_input_path_input")
        effective_schema_path = st.text_input("effective_schema (.json)", key="effective_schema_path_input")

        memo_ok = _path_ok(memo_text_path)
        cp_ok = _path_ok(candidate_pool_path)
        mo_ok = _path_ok(model_output_path)
        es_ok = _path_ok(effective_schema_path)

        st.markdown("---")
        st.subheader("Required Inputs")
        st.caption("memo_text / candidate_pool / model_output are required for this workflow.")
        st.write(f"- memo_text: {'OK' if memo_ok else 'MISSING'}")
        st.write(f"- candidate_pool: {'OK' if cp_ok else 'MISSING'}")
        st.write(f"- model_output: {'OK' if mo_ok else 'MISSING'}")
        st.write(f"- effective_schema: {'OK' if es_ok else 'MISSING'}")

        st.markdown("---")
        st.subheader("Auto Generate effective_schema")
        deal_id_for_schema = st.text_input("deal_id", key="deal_id_for_schema")
        api_token = st.text_input("Bearer token (RECATCH_FB_TOKEN)", value="", type="password", key="api_token")
        generate_schema_btn = st.button(
            "Generate effective_schema from deal_id",
            help="Validates required inputs when clicked, then runs schema generation.",
        )

        st.markdown("---")
        st.subheader("Auto Generate fn_review_input")
        top_k_for_fn = st.number_input("Suggested fields top-k", min_value=1, max_value=20, value=5, step=1)
        generate_fn_btn = st.button(
            "Generate fn_review_input from candidate_pool",
            help="Validates required inputs when clicked, then runs FN input generation.",
        )
        st.caption(
            "top-k controls how many suggested fields are attached to each FN candidate. "
            "Higher values increase recall but add review noise."
        )
        auto_reload_files = st.checkbox("Auto reload files", value=True)
        load_btn = st.button("Load", type="primary")

        if generate_schema_btn:
            missing = []
            if not memo_ok:
                missing.append("memo_text path")
            if not cp_ok:
                missing.append("candidate_pool path")
            if not mo_ok:
                missing.append("model_output path")
            deal_id_text = (deal_id_for_schema or "").strip()
            if missing:
                st.error(f"Missing/invalid required inputs: {', '.join(missing)}")
            elif not deal_id_text.isdigit():
                st.error("deal_id must be numeric.")
            elif not api_token.strip():
                st.error("Enter Bearer token.")
            else:
                out_path = SCHEMA_GENERATOR_DIR / "output" / f"effective_schema_{deal_id_text}.json"
                cmd = [
                    sys.executable,
                    str(SCHEMA_GENERATOR_DIR / "build_effective_schema_from_deal.py"),
                    "--deal-id",
                    deal_id_text,
                    "--token",
                    api_token.strip(),
                    "--output",
                    str(out_path),
                ]
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
                    st.session_state["pending_effective_schema_path"] = repo_rel(out_path)
                    st.success(f"Generated: {repo_rel(out_path)}")
                    if proc.stdout.strip():
                        st.caption(proc.stdout.strip())
                    st.rerun()
                except subprocess.CalledProcessError as e:
                    st.error("effective_schema generation failed.")
                    msg = (e.stderr or "") + ("\n" if e.stderr and e.stdout else "") + (e.stdout or "")
                    st.code(msg if msg.strip() else "no error output")

        if generate_fn_btn:
            cp = (candidate_pool_path or "").strip()
            mo = (model_output_path or "").strip()
            es = (effective_schema_path or "").strip()
            missing = []
            if not memo_ok:
                missing.append("memo_text path")
            if not cp or not resolve_user_path(cp).exists():
                missing.append("candidate_pool path")
            if not mo or not resolve_user_path(mo).exists():
                missing.append("model_output path")
            if not es or not resolve_user_path(es).exists():
                missing.append("effective_schema path")

            if missing:
                st.error(f"Missing/invalid required inputs: {', '.join(missing)}")
            else:
                out_path = resolve_user_path(suggest_fn_output_path(cp), prefer_base=REPO_ROOT)
                cmd = [
                    sys.executable,
                    str(SCHEMA_GENERATOR_DIR / "build_fn_review_input.py"),
                    "--candidate-pool",
                    str(resolve_user_path(cp)),
                    "--model-output",
                    str(resolve_user_path(mo)),
                    "--effective-schema",
                    str(resolve_user_path(es)),
                    "--output",
                    str(out_path),
                    "--top-k",
                    str(int(top_k_for_fn)),
                ]
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
                    st.session_state["pending_fn_input_path"] = repo_rel(out_path)
                    st.success(f"Generated: {repo_rel(out_path)}")
                    if proc.stdout.strip():
                        st.caption(proc.stdout.strip())
                    st.rerun()
                except subprocess.CalledProcessError as e:
                    st.error("fn_review_input generation failed.")
                    if e.stderr:
                        st.code(e.stderr)
                    elif e.stdout:
                        st.code(e.stdout)

    save_last_inputs(
        {
            "memo_text_path": st.session_state.get("memo_text_path", ""),
            "candidate_pool_path": st.session_state.get("candidate_pool_path", ""),
            "model_output_path": st.session_state.get("model_output_path", ""),
            "fn_input_path_input": st.session_state.get("fn_input_path_input", ""),
            "effective_schema_path_input": st.session_state.get("effective_schema_path_input", ""),
            "deal_id_for_schema": st.session_state.get("deal_id_for_schema", ""),
        }
    )

    if "loaded" not in st.session_state:
        st.session_state.loaded = False

    if load_btn or (not st.session_state.loaded) or auto_reload_files:
        try:
            memo_text = resolve_user_path(memo_text_path).read_text(encoding="utf-8-sig")
            model_output = fix_mojibake_obj(flatten_model_output(read_json_or_jsonl(model_output_path)))
            fn_rows = load_fn_candidates(fn_input_path)
            effective_schema = read_json(effective_schema_path)
            memo_id = fn_rows[0].get("memo_id") if fn_rows else "UNKNOWN"
            field_map = get_field_map(effective_schema)
            st.session_state.loaded = True
            st.session_state.memo_text = memo_text
            st.session_state.model_output = model_output
            st.session_state.fn_rows = fn_rows
            st.session_state.effective_schema = effective_schema
            st.session_state.memo_id = memo_id
            st.session_state.field_map = field_map
        except Exception as e:
            st.error(f"Load failed: {e}")
            st.stop()

    memo_text = st.session_state.memo_text
    model_output = st.session_state.model_output
    fn_rows = fix_mojibake_obj(st.session_state.fn_rows)
    field_map = st.session_state.field_map
    memo_id = st.session_state.memo_id
    existing = load_existing_decisions(memo_id)

    bad_signals = 0
    for x in model_output:
        fd = x.get("field_definition") or {}
        txt = " ".join([str(fd.get("label", "")), str(x.get("reasoning", ""))])
        if "??" in txt:
            bad_signals += 1
    if bad_signals > 0:
        st.warning(
            f"Detected {bad_signals} suspicious mojibake signals in model_output text. "
            "UI-level repair is limited if source data is already broken."
        )

    st.subheader("Memo Text")
    st.text_area("memo", memo_text, height=260)

    st.subheader("Field TP/FP/FN Aggregate")
    agg = aggregate_counts(field_map=field_map)
    agg_display = [
        {
            "field_id": x.get("field_id", ""),
            "label": x.get("label", ""),
            "tp": x.get("tp", 0),
            "fp": x.get("fp", 0),
            "fn": x.get("fn", 0),
            "precision": round(
                (x.get("tp", 0) / (x.get("tp", 0) + x.get("fp", 0)))
                if (x.get("tp", 0) + x.get("fp", 0)) > 0
                else 0.0,
                4,
            ),
            "recall": round(
                (x.get("tp", 0) / (x.get("tp", 0) + x.get("fn", 0)))
                if (x.get("tp", 0) + x.get("fn", 0)) > 0
                else 0.0,
                4,
            ),
            "f1_score": round(
                (
                    (
                        2
                        * (
                            (x.get("tp", 0) / (x.get("tp", 0) + x.get("fp", 0)))
                            if (x.get("tp", 0) + x.get("fp", 0)) > 0
                            else 0.0
                        )
                        * (
                            (x.get("tp", 0) / (x.get("tp", 0) + x.get("fn", 0)))
                            if (x.get("tp", 0) + x.get("fn", 0)) > 0
                            else 0.0
                        )
                    )
                    / (
                        (
                            (x.get("tp", 0) / (x.get("tp", 0) + x.get("fp", 0)))
                            if (x.get("tp", 0) + x.get("fp", 0)) > 0
                            else 0.0
                        )
                        + (
                            (x.get("tp", 0) / (x.get("tp", 0) + x.get("fn", 0)))
                            if (x.get("tp", 0) + x.get("fn", 0)) > 0
                            else 0.0
                        )
                    )
                )
                if (
                    (
                        (x.get("tp", 0) / (x.get("tp", 0) + x.get("fp", 0)))
                        if (x.get("tp", 0) + x.get("fp", 0)) > 0
                        else 0.0
                    )
                    + (
                        (x.get("tp", 0) / (x.get("tp", 0) + x.get("fn", 0)))
                        if (x.get("tp", 0) + x.get("fn", 0)) > 0
                        else 0.0
                    )
                )
                > 0
                else 0.0,
                4,
            ),
        }
        for x in agg
    ]
    st.dataframe(agg_display, use_container_width=True, height=220)

    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Model Output Review (TP/FP)")
        prev_model = {(x.get("item_idx")): x for x in existing.get("model_decisions", [])}
        model_decisions: list[dict[str, Any]] = []

        for i, item in enumerate(model_output):
            fd = fix_mojibake_obj(item.get("field_definition") or {})
            field_id = str(fd.get("id")) if fd.get("id") is not None else None
            field_label = fix_mojibake_text(str(fd.get("label") or ""))
            with st.expander(f"[{i}] {field_id} | {field_label}", expanded=False):
                st.write("type:", fd.get("type"), "| category:", fd.get("category"))
                st.write("extracted_value:", format_extracted_value(item, field_map))
                st.write("reasoning:", fix_mojibake_text(str(item.get("reasoning") or "")))
                prev = prev_model.get(i, {})
                decision = st.selectbox(
                    "Decision",
                    ["SKIP", "TP", "FP"],
                    index=["SKIP", "TP", "FP"].index(prev.get("decision", "SKIP")),
                    key=f"model_decision_{i}",
                )
                note = st.text_input("Note", value=prev.get("note", ""), key=f"model_note_{i}")
                model_decisions.append(
                    {
                        "item_idx": i,
                        "field_id": field_id,
                        "field_label": field_label,
                        "decision": decision,
                        "note": note,
                    }
                )

    with col2:
        st.subheader("FN Candidate Review (FN/NOT_FN)")
        prev_fn = {x.get("candidate_id"): x for x in existing.get("fn_decisions", [])}
        fn_decisions: list[dict[str, Any]] = []

        all_field_ids = sorted(field_map.keys(), key=lambda x: (len(x), x))
        for i, row in enumerate(fn_rows):
            cid = row.get("candidate_id")
            with st.expander(f"[{i}] {cid} | {row.get('semantic_type')} | {row.get('raw_text')}", expanded=False):
                ev = row.get("evidence") or {}
                st.write("evidence:", fix_mojibake_text(str(ev.get("exact_quote") or "")))
                st.write("section:", ev.get("section_path"))
                st.write("offset:", ev.get("start_char"), "~", ev.get("end_char"))
                line_no = char_to_line_no(memo_text, ev.get("start_char"))
                line_text = get_line_text(memo_text, line_no)
                st.write("line:", line_no if line_no is not None else "-")
                if line_text:
                    st.code(line_text, language="text")
                st.write("suggested_fields:", row.get("suggested_fields"))

                prev = prev_fn.get(cid, {})
                decision = st.selectbox(
                    "Decision",
                    ["SKIP", "FN", "NOT_FN"],
                    index=["SKIP", "FN", "NOT_FN"].index(prev.get("decision", "SKIP")),
                    key=f"fn_decision_{cid}",
                )

                suggested = [x.get("field_id") for x in (row.get("suggested_fields") or []) if x.get("field_id")]
                default_field = str(prev.get("assigned_field_id")) if prev.get("assigned_field_id") else ""
                field_options = [""] + list(dict.fromkeys(suggested + all_field_ids))
                if default_field not in field_options and default_field:
                    field_options.append(default_field)
                assigned_field_id = st.selectbox(
                    "Assign field_id",
                    field_options,
                    index=field_options.index(default_field) if default_field in field_options else 0,
                    format_func=lambda x: field_option_label(x, field_map),
                    key=f"fn_field_{cid}",
                )
                note = st.text_input("Note", value=prev.get("note", ""), key=f"fn_note_{cid}")
                assigned_field_label = None
                if assigned_field_id:
                    assigned_field_label = fix_mojibake_text(
                        str((field_map.get(str(assigned_field_id)) or {}).get("label") or "")
                    )
                fn_decisions.append(
                    {
                        "candidate_id": cid,
                        "semantic_type": row.get("semantic_type"),
                        "value_type": row.get("value_type"),
                        "raw_text": row.get("raw_text"),
                        "normalized": row.get("normalized"),
                        "evidence_segment_id": ev.get("segment_id"),
                        "evidence_section_path": ev.get("section_path"),
                        "evidence_quote": ev.get("exact_quote"),
                        "start_char": ev.get("start_char"),
                        "end_char": ev.get("end_char"),
                        "line_no": line_no,
                        "line_text": line_text,
                        "suggested_fields_snapshot": row.get("suggested_fields"),
                        "decision": decision,
                        "assigned_field_id": assigned_field_id or None,
                        "assigned_field_label": assigned_field_label,
                        "note": note,
                    }
                )

    if st.button("Save Decisions", type="primary"):
        payload = {
            "memo_id": memo_id,
            "updated_at": utc_now_iso(),
            "model_decisions": model_decisions,
            "fn_decisions": fn_decisions,
        }
        save_decisions(payload)
        st.success(f"Saved: {decision_file(memo_id)}")
        st.rerun()


if __name__ == "__main__":
    app()
