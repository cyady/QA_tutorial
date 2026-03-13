from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

from slackbot_for_web.config import Settings, load_settings


ISSUE_PREFIX_RE = re.compile(r"^\s*(\d{1,3})\s*([./)|-])\s*")
SECTION_HINT_RE = re.compile(r"^\s*(.+?)\s*>\s*")
MENTION_RE = re.compile(r"<@[A-Z0-9]+>")
LINK_RE = re.compile(r"<https?://[^|>]+(?:\|[^>]+)?>")
THREAD_LINK_RE = re.compile(r"<(https?://[^|>]+)(?:\|([^>]+))?>")
CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
MULTISPACE_RE = re.compile(r"\s+")

ISSUE_SEVERITY_DEFAULTS: dict[str, str] = {
    "animation_replay": "P2",
    "flicker": "P1",
    "mobile_alignment": "P2",
    "text_wrap": "P3",
    "share_preview": "P2",
    "mobile_overlay_depth": "P1",
    "mobile_media_render": "P2",
    "spacing_layout": "P2",
    "footer_alignment": "P3",
    "performance_motion": "P1",
    "close_button": "P1",
    "broken_link": "P1",
    "image_render": "P2",
    "menu_consistency": "P3",
    "click_affordance": "P2",
    "click_feedback": "P2",
    "responsive_overflow": "P2",
    "branding_render": "P3",
    "favicon_missing": "P3",
}

EXPECTED_BEHAVIOR_BY_ISSUE: dict[str, str] = {
    "animation_replay": "스크롤 재진입 여부와 무관하게 애니메이션은 최초 1회만 재생되어야 합니다.",
    "flicker": "스크롤 경계 구간에서도 애니메이션과 배경은 깜빡임 없이 안정적으로 유지되어야 합니다.",
    "mobile_alignment": "모바일 뷰에서는 텍스트와 장식 요소의 정렬이 의도한 기준선에 맞아야 합니다.",
    "text_wrap": "문장 줄바꿈은 가독성을 해치지 않도록 자연스럽게 배치되어야 합니다.",
    "share_preview": "공유 링크 미리보기에는 대표 이미지와 기본 메타 정보가 정상 노출되어야 합니다.",
    "mobile_overlay_depth": "플로팅 CTA와 폼 오버레이는 배경과 버튼 위 레이어에서 선명하게 보여야 합니다.",
    "mobile_media_render": "모바일에서 동영상 플레이어와 미디어 프레임은 중복 렌더링 없이 안정적으로 보여야 합니다.",
    "spacing_layout": "여백과 간격은 웹/모바일 의도에 맞게 일관되게 유지되어야 합니다.",
    "footer_alignment": "푸터/하단 브랜딩 요소는 지정된 정렬선에 맞아야 합니다.",
    "performance_motion": "애니메이션과 배경 효과는 과부하 없이 부드럽게 동작해야 합니다.",
    "close_button": "닫기 버튼은 시각적으로 보일 뿐 아니라 실제로 모달을 닫아야 합니다.",
    "broken_link": "링크와 버튼은 의도한 목적지나 상태 변화로 정확히 이어져야 합니다.",
    "image_render": "이미지와 카드 배경은 잘림이나 비정상 겹침 없이 렌더링되어야 합니다.",
    "menu_consistency": "서로 대응되는 메뉴명과 정보 구조는 섹션 간에 일관되어야 합니다.",
    "click_affordance": "클릭 가능한 커서/hover affordance는 실제 클릭 가능 요소에만 제공되어야 합니다.",
    "click_feedback": "클릭 액션 이후에는 상태 변화나 포커싱 등 명확한 피드백이 보여야 합니다.",
    "responsive_overflow": "작은 뷰포트에서도 주요 버튼과 입력 요소가 가려지지 않아야 합니다.",
    "branding_render": "브랜딩 요소는 시각적 의도대로 자연스럽게 렌더링되어야 합니다.",
    "favicon_missing": "페이지와 서비스에 맞는 파비콘이 노출되어야 합니다.",
}


@dataclass(frozen=True)
class IssueRule:
    issue_type: str
    match_any: tuple[str, ...]
    match_all: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class PatternRule:
    value: str
    match_any: tuple[str, ...]
    match_all: tuple[tuple[str, ...], ...] = ()


ISSUE_RULES: tuple[IssueRule, ...] = (
    IssueRule(
        issue_type="animation_replay",
        match_any=("재실행", "재생", "최초만", "한번만 노출", "한 번만 노출", "왔다갔다", "다시 진행"),
        match_all=(("애니메이션", "스크롤"),),
    ),
    IssueRule(
        issue_type="flicker",
        match_any=("깜빡", "깜빡임", "flicker"),
        match_all=(("애니메이션", "걸쳐"), ("스크롤", "깜빡")),
    ),
    IssueRule(
        issue_type="mobile_alignment",
        match_any=("정렬", "안맞", "안 맞", "쏠림", "치우침"),
        match_all=(("모바일", "정렬"), ("도트", "정렬")),
    ),
    IssueRule(
        issue_type="text_wrap",
        match_any=("줄바꿈", "줄 바꿈", "가독성", "텍스트에서", "\\n"),
    ),
    IssueRule(
        issue_type="share_preview",
        match_any=("공유 링크", "미리보기", "preview"),
        match_all=(("공유", "이미지"),),
    ),
    IssueRule(
        issue_type="mobile_overlay_depth",
        match_any=("depth", "z-index", "overlay"),
        match_all=(("플로팅 cta", "아래"), ("cta", "아래 depth"), ("폼", "아래 depth")),
    ),
    IssueRule(
        issue_type="mobile_media_render",
        match_any=("동영상 플레이어", "플레이어 이미지", "다다닥", "중복 렌더"),
        match_all=(("모바일", "플레이어"),),
    ),
    IssueRule(
        issue_type="spacing_layout",
        match_any=("여백", "padding", "margin", "간격"),
    ),
    IssueRule(
        issue_type="footer_alignment",
        match_any=("footer",),
        match_all=(("하단", "ci"), ("알파키 ci", "좌측"), ("푸터", "쏠림")),
    ),
    IssueRule(
        issue_type="performance_motion",
        match_any=("과부하", "버벅", "끊기", "이상하게 움직", "성능"),
    ),
    IssueRule(
        issue_type="close_button",
        match_any=("닫기버튼", "닫기 버튼", "[x]", "x 버튼", "닫기 미동작"),
        match_all=(("닫기", "미동작"),),
    ),
    IssueRule(
        issue_type="broken_link",
        match_any=("미동작", "링크", "현재창", "새창", "새 창"),
        match_all=(("클릭", "안"), ("목적지", "다름"), ("링크", "이동")),
    ),
    IssueRule(
        issue_type="image_render",
        match_any=("짤림", "잘림", "이미지 영역 콘텐츠 없음", "이미지가", "도트가 텍스트"),
        match_all=(("이미지", "콘텐츠 없음"), ("텍스트", "위에 찍혀"), ("이미지", "짤부")),
    ),
    IssueRule(
        issue_type="menu_consistency",
        match_any=("lnb", "메뉴명", "일치"),
        match_all=(("lnb", "푸터"),),
    ),
    IssueRule(
        issue_type="click_affordance",
        match_any=("hover", "커서", "손가락 모양", "클리커블"),
        match_all=(("hover", "클릭"), ("커서", "콘텐츠가 아니라면")),
    ),
    IssueRule(
        issue_type="click_feedback",
        match_any=("피드백", "색상이 변경되지", "포커싱", "완료되었습니다"),
        match_all=(("클릭", "피드백"), ("버튼", "색상")),
    ),
    IssueRule(
        issue_type="responsive_overflow",
        match_any=("가려짐", "좁아져", "작아서", "화면이 작아", "항목이 가려짐"),
    ),
    IssueRule(
        issue_type="branding_render",
        match_any=("브랜딩", "브랜드 소개", "브랜드 소개", "도트"),
    ),
    IssueRule(
        issue_type="favicon_missing",
        match_any=("파비콘", "favicon"),
    ),
)

PAGE_ROLE_RULES: tuple[PatternRule, ...] = (
    PatternRule("landing", ("home", "homepage", "메인", "랜딩", "hero", "first view")),
    PatternRule("pricing", ("pricing", "price", "prices", "요금", "가격", "플랜")),
    PatternRule("product", ("product", "products", "solution", "solutions", "service", "services", "feature")),
    PatternRule("about", ("about", "company", "회사", "브랜드 소개", "브랜드")),
    PatternRule("contact", ("contact", "문의", "상담", "consult", "demo request", "문의하기")),
    PatternRule("faq", ("faq", "자주 묻는", "질문", "accordion")),
    PatternRule("blog", ("blog", "news", "article", "post", "insight", "stories")),
    PatternRule("docs", ("docs", "documentation", "guide", "help", "문서", "가이드")),
    PatternRule("careers", ("careers", "career", "jobs", "job", "채용", "join us")),
    PatternRule("form_page", ("form", "input", "신청", "접수", "상담폼", "문의폼", "lead form")),
    PatternRule("policy", ("privacy", "terms", "policy", "개인정보", "이용약관")),
)

COMPONENT_TYPE_RULES: tuple[PatternRule, ...] = (
    PatternRule("header_nav", ("header", "gnb", "lnb", "nav", "menu", "메뉴")),
    PatternRule("footer_nav", ("footer", "푸터", "하단", "ci")),
    PatternRule("hero_cta", ("hero", "kv", "메인 비주얼", "퍼스트뷰")),
    PatternRule("primary_cta", ("cta", "문의", "상담", "demo", "trial", "download", "리포트", "자료")),
    PatternRule("floating_cta", ("floating cta", "플로팅 cta", "sticky cta", "sticky", "floating")),
    PatternRule("lead_form", ("form", "input", "placeholder", "label", "문의폼", "상담폼", "신청폼")),
    PatternRule("modal", ("modal", "popup", "팝업", "overlay", "drawer")),
    PatternRule("accordion", ("accordion", "faq", "토글", "접힘", "펼침")),
    PatternRule("card_grid", ("card", "cards", "카드")),
    PatternRule("carousel", ("carousel", "slider", "슬라이더", "swiper")),
    PatternRule("video_player", ("video", "동영상", "player", "플레이어", "youtube")),
    PatternRule("share_meta", ("공유 링크", "preview", "og image", "미리보기", "thumbnail")),
    PatternRule("tabs", ("tab", "tabs", "탭")),
    PatternRule("close_control", ("닫기", "close", "x 버튼", "[x]")),
)

INTERACTION_KIND_RULES: tuple[PatternRule, ...] = (
    PatternRule("scroll_triggered_animation", ("스크롤", "scroll", "애니메이션", "animation")),
    PatternRule("hover_navigation", ("hover", "dropdown", "popover", "tooltip", "menu hover")),
    PatternRule("click_navigation", ("클릭", "click", "버튼", "cta", "링크")),
    PatternRule("external_navigation", ("새창", "새 창", "현재창", "external", "외부 링크")),
    PatternRule("modal_toggle", ("modal", "popup", "drawer", "닫기", "close")),
    PatternRule("form_interaction", ("form", "input", "label", "placeholder", "validation", "신청", "문의")),
    PatternRule("accordion_toggle", ("faq", "accordion", "toggle", "접힘", "펼침")),
    PatternRule("media_playback", ("video", "player", "play", "동영상")),
    PatternRule("share_preview", ("공유", "preview", "og", "meta")),
)

LAYOUT_SIGNAL_RULES: tuple[PatternRule, ...] = (
    PatternRule("overlay_depth", ("depth", "z-index", "overlay")),
    PatternRule("alignment", ("정렬", "안맞", "안 맞", "쏠림", "치우침", "기준선")),
    PatternRule("spacing", ("여백", "간격", "spacing", "padding", "margin")),
    PatternRule("text_wrap", ("줄바꿈", "줄 바꿈", "가독성", "말풍선")),
    PatternRule("image_crop", ("잘림", "짤림", "겹쳐", "이미지 영역 콘텐츠 없음")),
    PatternRule("viewport_overflow", ("가려짐", "좁아", "작아", "overflow", "responsive")),
    PatternRule("animation_stability", ("깜빡", "재실행", "버벅", "끊기", "성능")),
    PatternRule("visibility", ("안 보", "안보", "미노출", "숨겨", "노출되지")),
)

FRAMEWORK_HINT_RULES: tuple[PatternRule, ...] = (
    PatternRule("framer", ("framer", "framer.app", ".framer.")),
    PatternRule("webflow", ("webflow", "webflow.io")),
    PatternRule("shopify", ("shopify", "myshopify")),
    PatternRule("wordpress", ("wordpress", "wp-content", "wp-admin")),
    PatternRule("nextjs", ("_next", "next.js", "nextjs")),
)

ISSUE_COMPONENT_TYPE_HINTS: dict[str, tuple[str, ...]] = {
    "mobile_overlay_depth": ("floating_cta", "lead_form", "modal"),
    "mobile_media_render": ("video_player",),
    "menu_consistency": ("header_nav", "footer_nav"),
    "share_preview": ("share_meta",),
    "close_button": ("modal", "close_control"),
    "click_affordance": ("primary_cta",),
    "click_feedback": ("primary_cta",),
    "footer_alignment": ("footer_nav",),
    "branding_render": ("footer_nav", "card_grid"),
    "broken_link": ("primary_cta",),
}

ISSUE_INTERACTION_KIND_HINTS: dict[str, tuple[str, ...]] = {
    "animation_replay": ("scroll_triggered_animation",),
    "flicker": ("scroll_triggered_animation",),
    "performance_motion": ("scroll_triggered_animation",),
    "broken_link": ("click_navigation", "external_navigation"),
    "close_button": ("modal_toggle",),
    "menu_consistency": ("hover_navigation", "click_navigation"),
    "click_affordance": ("hover_navigation", "click_navigation"),
    "click_feedback": ("click_navigation",),
    "share_preview": ("share_preview",),
    "mobile_media_render": ("media_playback",),
    "mobile_overlay_depth": ("click_navigation", "form_interaction"),
}

ISSUE_LAYOUT_SIGNAL_HINTS: dict[str, tuple[str, ...]] = {
    "mobile_overlay_depth": ("overlay_depth",),
    "mobile_alignment": ("alignment",),
    "spacing_layout": ("spacing",),
    "text_wrap": ("text_wrap",),
    "image_render": ("image_crop",),
    "responsive_overflow": ("viewport_overflow",),
    "animation_replay": ("animation_stability",),
    "flicker": ("animation_stability",),
    "performance_motion": ("animation_stability",),
    "footer_alignment": ("alignment",),
}

ISSUE_TYPE_PRIORITY: tuple[str, ...] = (
    "close_button",
    "broken_link",
    "mobile_overlay_depth",
    "animation_replay",
    "flicker",
    "performance_motion",
    "mobile_alignment",
    "responsive_overflow",
    "click_feedback",
    "click_affordance",
    "share_preview",
    "mobile_media_render",
    "image_render",
    "spacing_layout",
    "footer_alignment",
    "menu_consistency",
    "branding_render",
    "favicon_missing",
    "text_wrap",
)

ISSUE_KEYWORD_HITS: dict[str, tuple[str, ...]] = {
    "animation_replay": ("애니메이션", "재실행", "최초", "스크롤"),
    "flicker": ("깜빡임", "스크롤", "애니메이션"),
    "mobile_alignment": ("모바일", "정렬", "도트", "안맞"),
    "text_wrap": ("줄바꿈", "가독성", "텍스트"),
    "share_preview": ("공유 링크", "미리보기", "이미지"),
    "mobile_overlay_depth": ("모바일", "depth", "cta", "폼"),
    "mobile_media_render": ("모바일", "동영상", "플레이어"),
    "spacing_layout": ("여백", "간격"),
    "footer_alignment": ("하단", "ci", "푸터"),
    "performance_motion": ("성능", "버벅", "끊기"),
    "close_button": ("닫기", "x", "미동작"),
    "broken_link": ("링크", "클릭", "이동"),
    "image_render": ("이미지", "잘림", "콘텐츠 없음"),
    "menu_consistency": ("lnb", "메뉴명", "푸터"),
    "click_affordance": ("hover", "커서", "손가락"),
    "click_feedback": ("클릭", "피드백", "색상"),
    "responsive_overflow": ("가려짐", "좁아", "작아"),
    "branding_render": ("브랜딩", "도트", "브랜드"),
    "favicon_missing": ("파비콘",),
}

PLATFORM_KEYWORDS: dict[str, tuple[str, ...]] = {
    "real_mobile": ("실제 모바일", "실제모바일", "실제 기기", "실기기", "iphone", "iphone se", "z플립", "갤럭시"),
    "mobile": ("모바일뷰", "모바일 뷰", "모바일", "모바일&실제모바일"),
    "tablet": ("태블릿", "tablet", "테블릿"),
    "desktop": ("(pc)", "pc", "desktop", "웹에서", "웹 뷰"),
}

SEVERITY_HINTS: dict[str, tuple[str, ...]] = {
    "P1": ("미동작", "안 열", "안나오", "안 나오", "클릭이 안", "가려짐", "depth", "버벅", "끊기"),
    "P2": ("정렬", "깜빡", "잘림", "줄바꿈", "공유 링크"),
    "P3": ("좋을듯", "좋을 듯", "같아요", "제안"),
}

ISSUE_CUES: tuple[str, ...] = (
    "정렬",
    "안맞",
    "안 맞",
    "깜빡",
    "미동작",
    "잘림",
    "짤림",
    "가려짐",
    "줄바꿈",
    "가독성",
    "여백",
    "파비콘",
    "공유 링크",
    "미리보기",
    "hover",
    "depth",
    "z-index",
    "버벅",
    "끊기",
    "손가락 모양",
)


@dataclass(frozen=True)
class MemoryPaths:
    memory_dir: Path
    manifest_path: Path
    messages_path: Path
    files_manifest_path: Path
    files_path: Path
    output_cards_path: Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract issue memory cards from saved Slack QA thread archives.")
    parser.add_argument("--memory-id", help="Memory archive id under artifacts/_memory, e.g. MEM-fb9c644c")
    parser.add_argument("--memory-dir", help="Absolute or relative path to a specific memory archive directory")
    parser.add_argument("--all", action="store_true", help="Extract cards for all memory archives")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
    settings = load_settings(require_slack_tokens=False)

    targets = _resolve_targets(settings, memory_id=args.memory_id, memory_dir=args.memory_dir, all_archives=args.all)
    if not targets:
        raise SystemExit("No memory archive target found.")

    for memory_paths in targets:
        summary = extract_issue_memory_cards(memory_paths)
        print(
            f"{summary['memory_id']}: cards={summary['card_count']} "
            f"issue_messages={summary['issue_message_count']} output={summary['output_path']}"
        )


def extract_issue_memory_cards(memory_paths: MemoryPaths) -> dict[str, Any]:
    manifest = _read_json(memory_paths.manifest_path)
    messages = _read_json(memory_paths.messages_path)
    file_manifest = _read_json(memory_paths.files_manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError(f"Invalid manifest at {memory_paths.manifest_path}")
    if not isinstance(messages, list):
        raise ValueError(f"Invalid thread messages at {memory_paths.messages_path}")
    if not isinstance(file_manifest, list):
        file_manifest = []

    manifest, messages, file_manifest = _repair_memory_archive(
        manifest=manifest,
        messages=messages,
        file_manifest=file_manifest,
        memory_paths=memory_paths,
    )

    cards = _build_cards(manifest=manifest, messages=messages)
    payload = {
        "schema_version": 1,
        "memory_id": str(manifest.get("memory_id", "")).strip(),
        "thread_key": str(manifest.get("thread_key", "")).strip(),
        "captured_at": str(manifest.get("last_captured_at") or manifest.get("captured_at") or "").strip(),
        "card_count": len(cards),
        "cards": cards,
    }
    memory_paths.output_cards_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "memory_id": payload["memory_id"],
        "card_count": len(cards),
        "issue_message_count": len([m for m in messages if _is_issue_message(m)]),
        "output_path": str(memory_paths.output_cards_path),
    }


def _resolve_targets(settings: Settings, memory_id: str | None, memory_dir: str | None, all_archives: bool) -> list[MemoryPaths]:
    memory_root = Path(settings.artifact_root) / "_memory"
    targets: list[Path] = []
    if memory_dir:
        targets = [Path(memory_dir).resolve()]
    elif memory_id:
        targets = [(memory_root / str(memory_id).strip()).resolve()]
    elif all_archives:
        if memory_root.exists():
            targets = sorted([path.resolve() for path in memory_root.iterdir() if path.is_dir() and path.name.startswith("MEM-")])
    else:
        raise SystemExit("Provide --memory-id, --memory-dir, or --all")

    resolved: list[MemoryPaths] = []
    for directory in targets:
        manifest_path = directory / "thread_manifest.json"
        messages_path = directory / "thread_messages.json"
        files_manifest_path = directory / "file_manifest.json"
        files_path = directory / "files"
        if not manifest_path.exists() or not messages_path.exists():
            continue
        resolved.append(
            MemoryPaths(
                memory_dir=directory,
                manifest_path=manifest_path,
                messages_path=messages_path,
                files_manifest_path=files_manifest_path,
                files_path=files_path,
                output_cards_path=directory / "issue_memory_cards.json",
            )
        )
    return resolved


def _repair_memory_archive(
    *,
    manifest: dict[str, Any],
    messages: list[dict[str, Any]],
    file_manifest: list[dict[str, Any]],
    memory_paths: MemoryPaths,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_manifest = dict(manifest)
    normalized_manifest["thread_key"] = _thread_key(
        str(normalized_manifest.get("channel_id", "")).strip(),
        str(normalized_manifest.get("thread_ts", "")).strip(),
    )

    normalized_file_manifest: list[dict[str, Any]] = []
    file_records_by_id: dict[str, dict[str, Any]] = {}
    file_manifest_changed = False
    for record in file_manifest:
        if not isinstance(record, dict):
            file_manifest_changed = True
            continue
        normalized_record, changed = _normalize_file_record(record)
        file_manifest_changed = file_manifest_changed or changed
        file_id = str(normalized_record.get("id", "")).strip()
        if file_id:
            file_records_by_id[file_id] = normalized_record
        normalized_file_manifest.append(normalized_record)

    normalized_messages: list[dict[str, Any]] = []
    message_changed = False
    for message in messages:
        if not isinstance(message, dict):
            message_changed = True
            continue
        normalized_message, changed = _normalize_message_record(message, file_records_by_id)
        normalized_messages.append(normalized_message)
        message_changed = message_changed or changed

    if normalized_manifest != manifest:
        memory_paths.manifest_path.write_text(json.dumps(normalized_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if file_manifest_changed:
        memory_paths.files_manifest_path.write_text(
            json.dumps(normalized_file_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if message_changed:
        memory_paths.messages_path.write_text(json.dumps(normalized_messages, ensure_ascii=False, indent=2), encoding="utf-8")

    return normalized_manifest, normalized_messages, normalized_file_manifest


def _normalize_message_record(message: dict[str, Any], file_records_by_id: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    normalized = dict(message)
    changed = False
    for key in ("ts", "thread_ts", "user", "subtype", "text"):
        raw_value = str(normalized.get(key, "") or "")
        fixed = _normalize_unicode(raw_value).strip()
        if normalized.get(key) != fixed:
            normalized[key] = fixed
            changed = True
    raw_files = normalized.get("files")
    if isinstance(raw_files, list):
        new_files: list[dict[str, Any]] = []
        for file_info in raw_files:
            if not isinstance(file_info, dict):
                changed = True
                continue
            file_id = str(file_info.get("id", "")).strip()
            canonical = file_records_by_id.get(file_id, {})
            merged = dict(file_info)
            if canonical:
                for key in ("name", "local_path", "status", "download_error", "permalink", "mimetype", "filetype"):
                    canonical_value = canonical.get(key)
                    if canonical_value is not None:
                        merged[key] = canonical_value
            for key in ("id", "name", "mimetype", "filetype", "permalink", "local_path", "status", "download_error"):
                raw_value = str(merged.get(key, "") or "")
                fixed = _normalize_unicode(raw_value).strip()
                if merged.get(key) != fixed:
                    merged[key] = fixed
                    changed = True
            new_files.append(merged)
        if raw_files != new_files:
            normalized["files"] = new_files
            changed = True
    return normalized, changed


def _normalize_file_record(record: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    normalized = dict(record)
    changed = False
    for key in ("id", "name", "status", "error"):
        raw_value = str(normalized.get(key, "") or "")
        fixed = _normalize_unicode(raw_value).strip()
        if normalized.get(key) != fixed:
            normalized[key] = fixed
            changed = True

    raw_path = str(normalized.get("local_path", "") or "").strip()
    fixed_path, path_changed = _normalize_local_path(raw_path)
    if raw_path != fixed_path:
        normalized["local_path"] = fixed_path
        changed = True
    changed = changed or path_changed
    return normalized, changed


def _normalize_local_path(raw_path: str) -> tuple[str, bool]:
    path = Path(raw_path) if raw_path else None
    if path is None or not raw_path:
        return raw_path, False
    normalized_name = _normalize_unicode(path.name)
    if normalized_name == path.name:
        return str(path), False
    target = path.with_name(normalized_name)
    try:
        if path.exists() and not target.exists():
            path.rename(target)
            return str(target), True
        if target.exists():
            return str(target), True
    except Exception:
        pass
    return str(path), False


def _build_cards(manifest: dict[str, Any], messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    sequence_by_issue_number: dict[int, int] = defaultdict(int)
    seen_message_keys: set[str] = set()
    thread_key = _thread_key(str(manifest.get("channel_id", "")).strip(), str(manifest.get("thread_ts", "")).strip())
    thread_context = _extract_thread_context(messages)
    for message in messages:
        if not isinstance(message, dict):
            continue
        if not _is_issue_message(message):
            continue

        message_key = f"{thread_key}:{str(message.get('ts', '')).strip()}"
        if message_key in seen_message_keys:
            continue
        seen_message_keys.add(message_key)

        issue_number = _extract_issue_number(str(message.get("text", "")))
        if issue_number is not None:
            sequence_by_issue_number[issue_number] += 1
            ordinal = sequence_by_issue_number[issue_number]
        else:
            ordinal = len(cards) + 1

        cards.append(
            _message_to_card(
                manifest=manifest,
                message=message,
                issue_number=issue_number,
                ordinal=ordinal,
                thread_context=thread_context,
            )
        )
    return cards


def _message_to_card(
    manifest: dict[str, Any],
    message: dict[str, Any],
    issue_number: int | None,
    ordinal: int,
    thread_context: dict[str, Any],
) -> dict[str, Any]:
    raw_text = str(message.get("text", "") or "")
    clean_text = _normalize_text(raw_text)
    body_text = _strip_issue_prefix(clean_text)
    section_hint = _extract_section_hint(body_text)
    platform = _detect_platform(body_text)
    issue_types = _classify_issue_types(body_text, platform=platform, section_hint=section_hint)
    severity_hint = _detect_severity(body_text, issue_types)
    evidence_refs = _build_evidence_refs(message)
    summary = _build_summary(body_text)
    expected_behavior = _infer_expected_behavior(body_text, issue_types)
    page_roles = _infer_page_roles(body_text, section_hint=section_hint, thread_context=thread_context)
    framework_hints = _infer_framework_hints(body_text, thread_context=thread_context)
    component_types = _infer_component_types(
        body_text,
        issue_types=issue_types,
        section_hint=section_hint,
        thread_context=thread_context,
    )
    interaction_kinds = _infer_interaction_kinds(
        body_text,
        issue_types=issue_types,
        component_types=component_types,
        thread_context=thread_context,
    )
    layout_signals = _infer_layout_signals(body_text, issue_types=issue_types, platform=platform)
    pattern_tags = _build_pattern_tags(
        page_roles=page_roles,
        component_types=component_types,
        interaction_kinds=interaction_kinds,
        layout_signals=layout_signals,
        framework_hints=framework_hints,
        platform=platform,
    )
    keywords = _extract_keywords(
        body_text,
        issue_types=issue_types,
        platform=platform,
        section_hint=section_hint,
        page_roles=page_roles,
        component_types=component_types,
        interaction_kinds=interaction_kinds,
        layout_signals=layout_signals,
        framework_hints=framework_hints,
    )
    vector_text = _build_vector_text(
        summary=summary,
        observation=body_text,
        issue_types=issue_types,
        platform=platform,
        section_hint=section_hint,
        expected_behavior=expected_behavior,
        thread_context=thread_context,
        page_roles=page_roles,
        component_types=component_types,
        interaction_kinds=interaction_kinds,
        layout_signals=layout_signals,
        framework_hints=framework_hints,
        pattern_tags=pattern_tags,
    )

    if issue_number is not None:
        issue_label = f"{issue_number:02d}" if ordinal == 1 else f"{issue_number:02d}-{ordinal:02d}"
    else:
        issue_label = f"U{ordinal:02d}"
    message_ts = str(message.get("ts", "")).strip()
    memory_id = str(manifest.get("memory_id", "")).strip()
    thread_key = str(
        manifest.get("thread_key") or _thread_key(str(manifest.get("channel_id", "")).strip(), str(manifest.get("thread_ts", "")).strip())
    )
    message_identity = f"{thread_key}:{message_ts}"
    dedupe_key = hashlib.sha1(message_identity.encode("utf-8")).hexdigest()[:16]
    return {
        "card_id": f"{memory_id}-I{issue_label}",
        "memory_id": memory_id,
        "job_id": str(manifest.get("job_id", "")).strip(),
        "thread_ts": str(manifest.get("thread_ts", "")).strip(),
        "thread_key": thread_key,
        "channel_id": str(manifest.get("channel_id", "")).strip(),
        "source_message_ts": message_ts,
        "message_identity": message_identity,
        "dedupe_key": dedupe_key,
        "capture_count": int(manifest.get("capture_count") or 1),
        "source_user": str(message.get("user", "")).strip(),
        "created_at": _coerce_created_at(message_ts, fallback=str(manifest.get("captured_at", "")).strip()),
        "platform": platform,
        "issue_number": issue_number,
        "section_hint": section_hint,
        "issue_types": issue_types,
        "page_roles": page_roles,
        "component_types": component_types,
        "interaction_kinds": interaction_kinds,
        "layout_signals": layout_signals,
        "framework_hints": framework_hints,
        "pattern_tags": pattern_tags,
        "severity_hint": severity_hint,
        "summary": summary,
        "observation": body_text,
        "expected_behavior": expected_behavior,
        "keywords": keywords,
        "evidence_refs": evidence_refs,
        "raw_text": raw_text.strip(),
        "vector_text": vector_text,
        "confidence": _estimate_confidence(message=message, issue_number=issue_number, issue_types=issue_types),
        "thread_context": thread_context,
    }


def _is_issue_message(message: dict[str, Any]) -> bool:
    text = _normalize_text(str(message.get("text", "") or ""))
    if not text:
        return False
    if ISSUE_PREFIX_RE.match(text):
        return True
    if message.get("files"):
        lowered = text.lower()
        return any(cue in lowered for cue in [cue.lower() for cue in ISSUE_CUES])
    return False


def _extract_issue_number(text: str) -> int | None:
    match = ISSUE_PREFIX_RE.match(_normalize_text(text))
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _strip_issue_prefix(text: str) -> str:
    normalized = _normalize_text(text)
    return ISSUE_PREFIX_RE.sub("", normalized, count=1).strip()


def _extract_section_hint(text: str) -> str | None:
    match = SECTION_HINT_RE.match(text)
    if match:
        value = match.group(1).strip()
        if 1 <= len(value) <= 80:
            return value
    return None


def _classify_issue_types(text: str, *, platform: str, section_hint: str | None) -> list[str]:
    normalized = _normalize_match_text(text)
    matches: set[str] = set()
    for rule in ISSUE_RULES:
        if _matches_issue_rule(normalized, rule):
            matches.add(rule.issue_type)

    if "도트" in normalized and ("정렬" in normalized or "텍스트 위" in normalized or "텍스트 위에" in normalized):
        if platform in {"mobile", "real_mobile", "tablet", "cross_viewport"}:
            matches.add("mobile_alignment")
        else:
            matches.add("image_render")
    if "ci" in normalized and ("좌측" in normalized or "쏠림" in normalized):
        matches.add("footer_alignment")
    if "플로팅 cta" in normalized and ("폼" in normalized or "depth" in normalized):
        matches.add("mobile_overlay_depth")
    if "실제 모바일" in normalized and "여백" in normalized:
        matches.add("spacing_layout")
    if "손가락 모양" in normalized or ("hover" in normalized and "클릭 가능한 콘텐츠가 아니라면" in normalized):
        matches.add("click_affordance")
    if ("현재창" in normalized or "새창" in normalized or "새 창" in normalized) and "링크" in normalized:
        matches.add("broken_link")
    if "이미지 영역 콘텐츠 없음" in normalized:
        matches.add("image_render")
    if "파비콘" in normalized:
        matches.add("favicon_missing")

    ordered = [issue_type for issue_type in ISSUE_TYPE_PRIORITY if issue_type in matches]
    if not ordered:
        ordered.append("general_ui_issue")
    return ordered


def _matches_issue_rule(text: str, rule: IssueRule) -> bool:
    any_hit = any(keyword in text for keyword in rule.match_any)
    all_hit = any(all(keyword in text for keyword in group) for group in rule.match_all) if rule.match_all else False
    return any_hit or all_hit


def _detect_platform(text: str) -> str:
    normalized = _normalize_match_text(text)
    matches: list[str] = []
    for platform, keywords in PLATFORM_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            matches.append(platform)
    if {"desktop", "mobile"} <= set(matches) or {"desktop", "real_mobile"} <= set(matches):
        return "cross_viewport"
    if "real_mobile" in matches:
        return "real_mobile"
    if "mobile" in matches:
        return "mobile"
    if "tablet" in matches:
        return "tablet"
    if "desktop" in matches:
        return "desktop"
    return "unspecified"


def _detect_severity(text: str, issue_types: list[str]) -> str:
    normalized = _normalize_match_text(text)
    severity_rank = {"P1": 1, "P2": 2, "P3": 3}
    issue_default = "P3"
    for issue_type in issue_types:
        if issue_type in ISSUE_SEVERITY_DEFAULTS:
            issue_default = ISSUE_SEVERITY_DEFAULTS[issue_type]
            break
    rule_based = "P3"
    for severity, keywords in SEVERITY_HINTS.items():
        if any(keyword in normalized for keyword in keywords):
            rule_based = severity
            break
    return issue_default if severity_rank[issue_default] < severity_rank[rule_based] else rule_based


def _build_summary(text: str) -> str:
    base = SECTION_HINT_RE.sub("", text, count=1).strip()
    first_line = base.splitlines()[0].strip() if base else ""
    first_sentence = re.split(r"(?<=[.!?])\s+|,\s*", first_line, maxsplit=1)[0].strip()
    summary = first_sentence or first_line or base
    if len(summary) > 180:
        summary = summary[:177].rstrip() + "..."
    return summary


def _infer_expected_behavior(text: str, issue_types: list[str]) -> str:
    for issue_type in issue_types:
        expected = EXPECTED_BEHAVIOR_BY_ISSUE.get(issue_type)
        if expected:
            return expected
    if "좋을듯" in _normalize_match_text(text) or "좋을 듯" in _normalize_match_text(text):
        return "해당 UI는 제안된 방향처럼 더 자연스럽고 일관된 상태로 동작해야 합니다."
    return ""


def _infer_page_roles(text: str, *, section_hint: str | None, thread_context: dict[str, Any]) -> list[str]:
    context_text = _pattern_context_text(text, section_hint=section_hint, thread_context=thread_context)
    route_tokens = _extract_route_tokens(thread_context)
    page_roles: list[str] = []
    for rule in PAGE_ROLE_RULES:
        if _matches_pattern_rule(context_text, rule):
            page_roles.append(rule.value)
            continue
        if any(token in rule.match_any for token in route_tokens):
            page_roles.append(rule.value)
    if not page_roles and _looks_like_landing_context(context_text, thread_context):
        page_roles.append("landing")
    return _dedupe_strings(page_roles, limit=6)


def _infer_framework_hints(text: str, *, thread_context: dict[str, Any]) -> list[str]:
    context_text = _pattern_context_text(text, section_hint=None, thread_context=thread_context)
    framework_hints: list[str] = []
    for rule in FRAMEWORK_HINT_RULES:
        if _matches_pattern_rule(context_text, rule):
            framework_hints.append(rule.value)
    return _dedupe_strings(framework_hints, limit=4)


def _infer_component_types(
    text: str,
    *,
    issue_types: list[str],
    section_hint: str | None,
    thread_context: dict[str, Any],
) -> list[str]:
    context_text = _pattern_context_text(text, section_hint=section_hint, thread_context=thread_context)
    component_types: list[str] = []
    for issue_type in issue_types:
        component_types.extend(ISSUE_COMPONENT_TYPE_HINTS.get(issue_type, ()))
    for rule in COMPONENT_TYPE_RULES:
        if _matches_pattern_rule(context_text, rule):
            component_types.append(rule.value)
    return _dedupe_strings(component_types, limit=8)


def _infer_interaction_kinds(
    text: str,
    *,
    issue_types: list[str],
    component_types: list[str],
    thread_context: dict[str, Any],
) -> list[str]:
    context_text = _pattern_context_text(text, section_hint=None, thread_context=thread_context)
    interaction_kinds: list[str] = []
    for issue_type in issue_types:
        interaction_kinds.extend(ISSUE_INTERACTION_KIND_HINTS.get(issue_type, ()))
    for rule in INTERACTION_KIND_RULES:
        if _matches_pattern_rule(context_text, rule):
            interaction_kinds.append(rule.value)
    if any(component in {"modal", "close_control"} for component in component_types):
        interaction_kinds.append("modal_toggle")
    if any(component in {"lead_form"} for component in component_types):
        interaction_kinds.append("form_interaction")
    if any(component in {"accordion"} for component in component_types):
        interaction_kinds.append("accordion_toggle")
    if any(component in {"share_meta"} for component in component_types):
        interaction_kinds.append("share_preview")
    return _dedupe_strings(interaction_kinds, limit=8)


def _infer_layout_signals(text: str, *, issue_types: list[str], platform: str) -> list[str]:
    normalized = _normalize_match_text(text)
    layout_signals: list[str] = []
    for issue_type in issue_types:
        layout_signals.extend(ISSUE_LAYOUT_SIGNAL_HINTS.get(issue_type, ()))
    for rule in LAYOUT_SIGNAL_RULES:
        if _matches_pattern_rule(normalized, rule):
            layout_signals.append(rule.value)
    if platform in {"mobile", "real_mobile", "tablet", "cross_viewport"}:
        layout_signals.append("mobile_surface")
    if platform in {"desktop", "cross_viewport"}:
        layout_signals.append("desktop_surface")
    return _dedupe_strings(layout_signals, limit=8)


def _build_pattern_tags(
    *,
    page_roles: list[str],
    component_types: list[str],
    interaction_kinds: list[str],
    layout_signals: list[str],
    framework_hints: list[str],
    platform: str,
) -> list[str]:
    tags: list[str] = []
    tags.extend(f"role:{value}" for value in page_roles)
    tags.extend(f"component:{value}" for value in component_types)
    tags.extend(f"interaction:{value}" for value in interaction_kinds)
    tags.extend(f"layout:{value}" for value in layout_signals)
    tags.extend(f"framework:{value}" for value in framework_hints)
    if platform and platform != "unspecified":
        tags.append(f"platform:{platform}")
    return _dedupe_strings(tags, limit=24)


def _extract_keywords(
    text: str,
    issue_types: list[str],
    platform: str,
    section_hint: str | None,
    page_roles: list[str],
    component_types: list[str],
    interaction_kinds: list[str],
    layout_signals: list[str],
    framework_hints: list[str],
) -> list[str]:
    normalized = _normalize_match_text(text)
    tokens: list[str] = []
    if section_hint:
        tokens.append(section_hint)
    tokens.extend(issue_types)
    tokens.extend(page_roles)
    tokens.extend(component_types)
    tokens.extend(interaction_kinds)
    tokens.extend(layout_signals)
    tokens.extend(framework_hints)
    if platform != "unspecified":
        tokens.append(platform)
    for issue_type in issue_types:
        tokens.extend(ISSUE_KEYWORD_HITS.get(issue_type, ()))
    for keyword in ("모바일", "실제 모바일", "태블릿", "pc", "cta", "depth", "hover", "faq", "ci"):
        if keyword in normalized:
            tokens.append(keyword)
    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        cleaned = token.strip()
        if cleaned and cleaned not in seen:
            deduped.append(cleaned)
            seen.add(cleaned)
    return deduped[:24]


def _build_vector_text(
    summary: str,
    observation: str,
    issue_types: list[str],
    platform: str,
    section_hint: str | None,
    expected_behavior: str,
    thread_context: dict[str, Any],
    page_roles: list[str],
    component_types: list[str],
    interaction_kinds: list[str],
    layout_signals: list[str],
    framework_hints: list[str],
    pattern_tags: list[str],
) -> str:
    parts = [
        summary,
        observation,
        f"issue_types: {', '.join(issue_types)}",
        f"platform: {platform}",
    ]
    if section_hint:
        parts.append(f"section: {section_hint}")
    if page_roles:
        parts.append(f"page_roles: {', '.join(page_roles)}")
    if component_types:
        parts.append(f"component_types: {', '.join(component_types)}")
    if interaction_kinds:
        parts.append(f"interaction_kinds: {', '.join(interaction_kinds)}")
    if layout_signals:
        parts.append(f"layout_signals: {', '.join(layout_signals)}")
    if framework_hints:
        parts.append(f"framework_hints: {', '.join(framework_hints)}")
    if pattern_tags:
        parts.append(f"pattern_tags: {', '.join(pattern_tags)}")
    if expected_behavior:
        parts.append(f"expected: {expected_behavior}")
    context_summary = str(thread_context.get("summary") or "").strip()
    if context_summary:
        parts.append(f"thread_context: {context_summary}")
    context_urls = _dedupe_strings(list(thread_context.get("urls") or []), limit=8)
    if context_urls:
        parts.append("thread_urls: " + ", ".join(context_urls))
    context_labels = _dedupe_strings(list(thread_context.get("labels") or []), limit=8)
    if context_labels:
        parts.append("thread_labels: " + ", ".join(context_labels))
    return "\n".join(part for part in parts if part).strip()


def _pattern_context_text(text: str, *, section_hint: str | None, thread_context: dict[str, Any]) -> str:
    fragments: list[str] = [text]
    if section_hint:
        fragments.append(section_hint)
    fragments.append(str(thread_context.get("summary") or ""))
    fragments.extend(_dedupe_strings(list(thread_context.get("labels") or []), limit=8))
    fragments.extend(_dedupe_strings(list(thread_context.get("urls") or []), limit=8))
    return _normalize_match_text("\n".join(fragment for fragment in fragments if fragment))


def _extract_route_tokens(thread_context: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    for raw_url in _dedupe_strings(list(thread_context.get("urls") or []), limit=8):
        parsed = urlparse(raw_url)
        for chunk in re.split(r"[/_\-.]+", parsed.path.lower()):
            cleaned = chunk.strip()
            if len(cleaned) >= 2:
                tokens.append(cleaned)
    return _dedupe_strings(tokens, limit=20)


def _matches_pattern_rule(text: str, rule: PatternRule) -> bool:
    any_hit = any(keyword in text for keyword in rule.match_any)
    all_hit = any(all(keyword in text for keyword in group) for group in rule.match_all) if rule.match_all else False
    return any_hit or all_hit


def _looks_like_landing_context(context_text: str, thread_context: dict[str, Any]) -> bool:
    if any(keyword in context_text for keyword in ("랜딩", "메인", "hero", "homepage", "home")):
        return True
    for raw_url in _dedupe_strings(list(thread_context.get("urls") or []), limit=8):
        parsed = urlparse(raw_url)
        path = parsed.path.strip()
        if not path or path == "/":
            return True
    return False


def _extract_thread_context(messages: list[dict[str, Any]]) -> dict[str, Any]:
    if not messages:
        return {"summary": "", "urls": [], "labels": []}
    root_message = None
    for message in messages:
        if not isinstance(message, dict):
            continue
        if str(message.get("ts") or "").strip() == str(message.get("thread_ts") or "").strip():
            root_message = message
            break
    if root_message is None:
        root_message = messages[0] if messages else {}

    raw_text = str((root_message or {}).get("text") or "")
    urls: list[str] = []
    labels: list[str] = []
    for url, label in THREAD_LINK_RE.findall(raw_text):
        url_text = str(url or "").strip()
        label_text = _normalize_text(str(label or "")).strip()
        if url_text:
            urls.append(url_text)
        if label_text:
            labels.append(label_text)

    summary = _normalize_text(raw_text)
    summary = LINK_RE.sub("", summary)
    summary = MENTION_RE.sub("", summary)
    summary = _build_summary(summary)
    return {
        "summary": summary,
        "urls": _dedupe_strings(urls, limit=8),
        "labels": _dedupe_strings(labels, limit=8),
    }


def _build_evidence_refs(message: dict[str, Any]) -> list[dict[str, Any]]:
    raw_files = message.get("files")
    if not isinstance(raw_files, list):
        return []
    refs: list[dict[str, Any]] = []
    for file_info in raw_files:
        if not isinstance(file_info, dict):
            continue
        refs.append(
            {
                "id": str(file_info.get("id", "")).strip(),
                "name": _normalize_unicode(str(file_info.get("name", "")).strip()),
                "mimetype": str(file_info.get("mimetype", "")).strip(),
                "local_path": _normalize_unicode(str(file_info.get("local_path", "")).strip()),
                "permalink": str(file_info.get("permalink", "")).strip(),
                "status": str(file_info.get("status", "")).strip(),
            }
        )
    return refs


def _estimate_confidence(message: dict[str, Any], issue_number: int | None, issue_types: list[str]) -> float:
    score = 0.45
    if issue_number is not None:
        score += 0.2
    if message.get("files"):
        score += 0.2
    if issue_types and issue_types != ["general_ui_issue"]:
        score += 0.1
    if len(str(message.get("text", "")).strip()) >= 20:
        score += 0.05
    return round(min(score, 0.95), 2)


def _coerce_created_at(message_ts: str, fallback: str) -> str:
    try:
        seconds = float(message_ts)
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    except Exception:
        return fallback


def _thread_key(channel_id: str, thread_ts: str) -> str:
    if not channel_id or not thread_ts:
        return ""
    return f"{channel_id}:{thread_ts}"


def _normalize_text(raw: str) -> str:
    text = _normalize_unicode(raw or "")
    text = CODE_BLOCK_RE.sub(lambda match: match.group(0).replace("\n", "\\n"), text)
    text = MENTION_RE.sub("", text)
    text = LINK_RE.sub("", text)
    text = text.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
    lines = [MULTISPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _normalize_match_text(raw: str) -> str:
    text = _normalize_text(raw).lower()
    replacements = {
        "`": " ",
        "•": " ",
        "[x ]": " x ",
        "[x]": " x ",
        "x]": " x ",
        "<->": " ",
        "&": " and ",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = text.replace("/", " ")
    text = text.replace("|", " ")
    text = MULTISPACE_RE.sub(" ", text)
    return text.strip()


def _normalize_unicode(raw: str) -> str:
    return unicodedata.normalize("NFC", str(raw or ""))


def _dedupe_strings(values: list[str], *, limit: int) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _normalize_unicode(str(value or "")).strip()
        lowered = cleaned.lower()
        if cleaned and lowered not in seen:
            deduped.append(cleaned)
            seen.add(lowered)
        if len(deduped) >= limit:
            break
    return deduped


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
