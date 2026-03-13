import { Agentation } from "agentation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchRunDetail, fetchRuns } from "./api";
import type { ArtifactFile, PipelineStage, QaFinding, RunDetail, RunsResponse } from "./types";

type TestCaseView = {
  caseId: string;
  title: string;
  reason: string;
  status: string;
  tier: string;
  stepsExecuted: number;
  evidenceRefs: string[];
  targetUrl: string;
  priority: string;
  objective: string;
  expectedResult: string;
  severityHint: string;
  plannedSteps: string[];
  plannedProbeKinds: string[];
  memoryHitCount: number;
  memoryIssueTypes: string[];
  memoryPageRoles: string[];
  memoryComponentTypes: string[];
  memoryInteractionKinds: string[];
  memoryLayoutSignals: string[];
  memoryFrameworkHints: string[];
  memoryCardIds: string[];
};

type ProbeRectView = {
  left: number;
  top: number;
  width: number;
  height: number;
};

type ProbeViewportView = {
  width: number;
  height: number;
  scrollX: number;
  scrollY: number;
  devicePixelRatio: number;
};

type VisualProbeAnnotationView = {
  screenshotNote: string;
  phase: string;
  kind: string;
  label: string;
  color: string;
  rect: ProbeRectView;
  viewport: ProbeViewportView;
};

type VisualProbeScreenshotView = {
  id: string;
  note: string;
  path: string;
  pageUrl: string;
};

type VisualProbeItemView = {
  probeKind: string;
  status: string;
  reason: string;
  observations: string[];
  evidenceRefs: string[];
  candidateLabel: string;
  overlayAnnotations: VisualProbeAnnotationView[];
};

type VisualProbeCaseView = {
  caseId: string;
  title: string;
  pageUrl: string;
  plannedProbeKinds: string[];
  summary: {
    total: number;
    pass: number;
    fail: number;
    needsReview: number;
    skipped: number;
  };
  probes: VisualProbeItemView[];
  executionLog: string[];
  evidenceScreenshots: VisualProbeScreenshotView[];
};

type VisualProbeSummaryView = {
  caseCount: number;
  probeCount: number;
  pass: number;
  fail: number;
  needsReview: number;
  skipped: number;
};

type ResolvedEvidence = {
  label: string;
  source: string;
  url: string | null;
  isImage: boolean;
};

type ResolvedProbeEvidence = ResolvedEvidence & {
  note: string;
  pageUrl: string;
};

type VisualProbePreviewSelection = {
  probeCase: VisualProbeCaseView;
  probe: VisualProbeItemView;
};

type WorkflowNode = {
  label: string;
  agent: string;
  role: string;
  outputs: string[];
  caption: string;
  state: string;
};

type MemoryQueryHintsView = {
  platform: string;
  pageRoles: string[];
  componentTypes: string[];
  interactionKinds: string[];
  layoutSignals: string[];
  frameworkHints: string[];
};

type MemoryRetrievalHitView = {
  cardId: string;
  memoryId: string;
  score: number;
  baseScore: number;
  metadataBoost: number;
  summary: string;
  issueTypes: string[];
  pageRoles: string[];
  componentTypes: string[];
  interactionKinds: string[];
  layoutSignals: string[];
  frameworkHints: string[];
  sectionHint: string;
  severityHint: string;
  scoreBreakdown: Record<string, number>;
  observation: string;
  expectedBehavior: string;
};

type MemoryRetrievalView = {
  enabled: boolean;
  backend: string;
  queryText: string;
  topK: number;
  totalHits: number;
  issueTypeCounts: Array<[string, number]>;
  queryHints: MemoryQueryHintsView;
  hits: MemoryRetrievalHitView[];
  reason: string;
};

const PASS_CASES_PER_PAGE = 5;
const TEXT_ARTIFACT_EXTENSIONS = new Set(["json", "txt", "log", "md", "csv", "yml", "yaml", "html"]);

function fmtNumber(value: number | string | null | undefined): string {
  return Number(value ?? 0).toLocaleString("en-US");
}

function fmtScore(value: number | string | null | undefined): string {
  const number = Number(value ?? 0);
  return Number.isFinite(number) ? number.toFixed(3) : "0.000";
}

function fmtSignedScore(value: number | string | null | undefined): string {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) {
    return "0.000";
  }
  return `${number >= 0 ? "+" : ""}${number.toFixed(3)}`;
}

function fmtTime(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("ko-KR", { hour12: false });
}

function fmtDuration(startedAt: string | null | undefined, completedAt: string | null | undefined): string {
  if (!startedAt || !completedAt) {
    return "-";
  }
  const started = new Date(startedAt).getTime();
  const completed = new Date(completedAt).getTime();
  if (Number.isNaN(started) || Number.isNaN(completed) || completed < started) {
    return "-";
  }
  const totalSeconds = Math.floor((completed - started) / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m ${seconds}s`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

function statusClass(value: string | null | undefined): string {
  const status = String(value ?? "").toLowerCase();
  if (status === "pass") return "status-pass";
  if (status === "fail") return "status-fail";
  if (status === "needs_review") return "status-review";
  if (status === "skipped") return "status-review";
  if (status === "error") return "status-error";
  return "status-running";
}

function diffDirectionClass(value: string | null | undefined): string {
  const direction = String(value ?? "").toLowerCase();
  if (direction === "improved") return "status-pass";
  if (direction === "regressed") return "status-fail";
  if (direction === "unchanged") return "status-running";
  return "status-review";
}

function asObject(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value
        .map((item) => String(item ?? "").trim())
        .filter(Boolean)
    : [];
}

function asNumber(value: unknown): number {
  const number = Number(value ?? 0);
  return Number.isFinite(number) ? number : 0;
}

function asNumberRecord(value: unknown): Record<string, number> {
  if (typeof value !== "object" || value === null) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .map(([key, raw]) => [String(key).trim(), asNumber(raw)] as const)
      .filter(([key]) => key.length > 0),
  );
}

function countItems(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

function extensionOf(name: string): string {
  const clean = name.split("?")[0];
  const dot = clean.lastIndexOf(".");
  return dot >= 0 ? clean.slice(dot + 1).toLowerCase() : "";
}

function isImageRef(value: string): boolean {
  return ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"].includes(extensionOf(value));
}

function shouldDisplayArtifact(file: ArtifactFile): boolean {
  if (file.is_image) {
    return false;
  }
  if (file.is_json) {
    return true;
  }
  return TEXT_ARTIFACT_EXTENSIONS.has(extensionOf(file.name));
}

function asFindings(runDetail: RunDetail | null): QaFinding[] {
  if (!runDetail) {
    return [];
  }
  const qaReport = asObject(runDetail.artifacts.qa_report);
  const result = asObject(runDetail.artifacts.result);
  if (Array.isArray(qaReport.findings)) {
    return qaReport.findings.filter((item): item is QaFinding => typeof item === "object" && item !== null);
  }
  if (Array.isArray(result.findings)) {
    return result.findings.filter((item): item is QaFinding => typeof item === "object" && item !== null);
  }
  return [];
}

function asMemoryRetrieval(runDetail: RunDetail | null): MemoryRetrievalView | null {
  if (!runDetail) {
    return null;
  }
  const payload = asObject(runDetail.artifacts.memory_retrieval);
  if (Object.keys(payload).length === 0) {
    return null;
  }
  const queryHints = asObject(payload.query_hints);
  const issueTypeCounts = Object.entries(asNumberRecord(payload.issue_type_counts)).sort((left, right) => right[1] - left[1]);
  const hits = Array.isArray(payload.hits)
    ? payload.hits
        .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
        .map((item) => ({
          cardId: String(item.card_id ?? "").trim(),
          memoryId: String(item.memory_id ?? "").trim(),
          score: asNumber(item.score),
          baseScore: asNumber(item.base_score),
          metadataBoost: asNumber(item.metadata_boost),
          summary: String(item.summary ?? "").trim(),
          issueTypes: asStringList(item.issue_types),
          pageRoles: asStringList(item.page_roles),
          componentTypes: asStringList(item.component_types),
          interactionKinds: asStringList(item.interaction_kinds),
          layoutSignals: asStringList(item.layout_signals),
          frameworkHints: asStringList(item.framework_hints),
          sectionHint: String(item.section_hint ?? "").trim(),
          severityHint: String(item.severity_hint ?? "").trim(),
          scoreBreakdown: asNumberRecord(item.score_breakdown),
          observation: String(item.observation ?? "").trim(),
          expectedBehavior: String(item.expected_behavior ?? "").trim(),
        }))
    : [];

  return {
    enabled: Boolean(payload.enabled),
    backend: String(payload.backend ?? "").trim(),
    queryText: String(payload.query_text ?? "").trim(),
    topK: asNumber(payload.top_k),
    totalHits: asNumber(payload.total_hits),
    issueTypeCounts,
    queryHints: {
      platform: String(queryHints.platform ?? "").trim(),
      pageRoles: asStringList(queryHints.page_roles),
      componentTypes: asStringList(queryHints.component_types),
      interactionKinds: asStringList(queryHints.interaction_kinds),
      layoutSignals: asStringList(queryHints.layout_signals),
      frameworkHints: asStringList(queryHints.framework_hints),
    },
    hits,
    reason: String(payload.reason ?? "").trim(),
  };
}

function asTestCases(resultsValue: unknown, planValue: unknown): TestCaseView[] {
  const planRows = Array.isArray(planValue)
    ? planValue.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    : [];
  const resultsRows = Array.isArray(resultsValue)
    ? resultsValue.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    : [];

  const planByCaseId = new Map<string, Record<string, unknown>>();
  planRows.forEach((item, index) => {
    const caseId = String(item.case_id ?? `TC-${String(index + 1).padStart(4, "0")}`).trim();
    planByCaseId.set(caseId, item);
  });

  const mergedCases: TestCaseView[] = resultsRows.map((item, index) => {
    const caseId = String(item.case_id ?? `TC-${String(index + 1).padStart(4, "0")}`).trim();
    const plan = asObject(planByCaseId.get(caseId));
    const memoryHints = asObject(plan.memory_hints);
    const visualProbePlan = asObject(plan.visual_probe_plan);
    const memoryHits = Array.isArray(memoryHints.hits)
      ? memoryHints.hits.filter((hit): hit is Record<string, unknown> => typeof hit === "object" && hit !== null)
      : [];

    return {
      caseId,
      title: String(plan.title ?? item.title ?? "-"),
      reason: String(item.status_reason ?? plan.reason ?? "-"),
      status: String(item.status ?? ""),
      tier: String(plan.execution_tier ?? item.execution_tier ?? item.tier ?? "-"),
      stepsExecuted: asNumber(item.steps_executed),
      evidenceRefs: asStringList(item.evidence_refs),
      targetUrl: String(plan.target_url ?? item.target_url ?? ""),
      priority: String(plan.priority ?? "-"),
      objective: String(plan.objective ?? ""),
      expectedResult: String(plan.expected_result ?? ""),
      severityHint: String(plan.severity_hint ?? ""),
      plannedSteps: asStringList(plan.steps),
      plannedProbeKinds: asStringList(visualProbePlan.probe_kinds),
      memoryHitCount: asNumber(memoryHints.hit_count),
      memoryIssueTypes: asStringList(memoryHints.issue_types),
      memoryPageRoles: asStringList(memoryHints.page_roles),
      memoryComponentTypes: asStringList(memoryHints.component_types),
      memoryInteractionKinds: asStringList(memoryHints.interaction_kinds),
      memoryLayoutSignals: asStringList(memoryHints.layout_signals),
      memoryFrameworkHints: asStringList(memoryHints.framework_hints),
      memoryCardIds: memoryHits.map((hit) => String(hit.card_id ?? "").trim()).filter(Boolean),
    };
  });

  const seenCaseIds = new Set(mergedCases.map((item) => item.caseId));
  planRows.forEach((item, index) => {
    const caseId = String(item.case_id ?? `TC-${String(index + 1).padStart(4, "0")}`).trim();
    if (seenCaseIds.has(caseId)) {
      return;
    }
    const memoryHints = asObject(item.memory_hints);
    const visualProbePlan = asObject(item.visual_probe_plan);
    const memoryHits = Array.isArray(memoryHints.hits)
      ? memoryHints.hits.filter((hit): hit is Record<string, unknown> => typeof hit === "object" && hit !== null)
      : [];
    mergedCases.push({
      caseId,
      title: String(item.title ?? "-"),
      reason: String(item.reason ?? "-"),
      status: "planned",
      tier: String(item.execution_tier ?? item.tier ?? "-"),
      stepsExecuted: 0,
      evidenceRefs: [],
      targetUrl: String(item.target_url ?? ""),
      priority: String(item.priority ?? "-"),
      objective: String(item.objective ?? ""),
      expectedResult: String(item.expected_result ?? ""),
      severityHint: String(item.severity_hint ?? ""),
      plannedSteps: asStringList(item.steps),
      plannedProbeKinds: asStringList(visualProbePlan.probe_kinds),
      memoryHitCount: asNumber(memoryHints.hit_count),
      memoryIssueTypes: asStringList(memoryHints.issue_types),
      memoryPageRoles: asStringList(memoryHints.page_roles),
      memoryComponentTypes: asStringList(memoryHints.component_types),
      memoryInteractionKinds: asStringList(memoryHints.interaction_kinds),
      memoryLayoutSignals: asStringList(memoryHints.layout_signals),
      memoryFrameworkHints: asStringList(memoryHints.framework_hints),
      memoryCardIds: memoryHits.map((hit) => String(hit.card_id ?? "").trim()).filter(Boolean),
    });
  });

  return mergedCases;
}

function asProbeRect(value: unknown): ProbeRectView | null {
  const rect = asObject(value);
  const width = Number(rect.width ?? 0);
  const height = Number(rect.height ?? 0);
  if (width <= 0 || height <= 0) {
    return null;
  }
  return {
    left: Number(rect.left ?? 0),
    top: Number(rect.top ?? 0),
    width,
    height,
  };
}

function asProbeViewport(value: unknown): ProbeViewportView | null {
  const viewport = asObject(value);
  const width = Number(viewport.width ?? 0);
  const height = Number(viewport.height ?? 0);
  if (width <= 0 || height <= 0) {
    return null;
  }
  return {
    width,
    height,
    scrollX: Number(viewport.scroll_x ?? viewport.scrollX ?? 0),
    scrollY: Number(viewport.scroll_y ?? viewport.scrollY ?? 0),
    devicePixelRatio: Number(viewport.device_pixel_ratio ?? viewport.devicePixelRatio ?? 1),
  };
}

function asVisualProbeAnnotations(value: unknown): VisualProbeAnnotationView[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    .map((item) => {
      const rect = asProbeRect(item.rect);
      const viewport = asProbeViewport(item.viewport);
      if (!rect || !viewport) {
        return null;
      }
      return {
        screenshotNote: String(item.screenshot_note ?? ""),
        phase: String(item.phase ?? ""),
        kind: String(item.kind ?? ""),
        label: String(item.label ?? ""),
        color: String(item.color ?? "#ff3b30"),
        rect,
        viewport,
      };
    })
    .filter((item): item is VisualProbeAnnotationView => Boolean(item));
}

function asVisualProbeScreenshots(value: unknown): VisualProbeScreenshotView[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    .map((item, index) => ({
      id: String(item.id ?? `VP-S-${index + 1}`),
      note: String(item.note ?? ""),
      path: String(item.path ?? ""),
      pageUrl: String(item.page_url ?? ""),
    }))
    .filter((item) => item.path.trim().length > 0);
}

function prettifyProbeKind(value: string): string {
  return value
    .replace(/_/g, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function asVisualProbeCases(value: unknown): VisualProbeCaseView[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    .map((item, index) => {
      const probePlan = asObject(item.probe_plan);
      const summary = asObject(item.summary);
      const probes = Array.isArray(item.probes)
        ? item.probes
            .filter((probe): probe is Record<string, unknown> => typeof probe === "object" && probe !== null)
            .map((probe) => ({
              probeKind: String(probe.probe_kind ?? "-"),
              status: String(probe.status ?? "-"),
              reason: String(probe.status_reason ?? "-"),
              observations: asStringList(probe.observations),
              evidenceRefs: asStringList(probe.evidence_refs),
              candidateLabel: String(asObject(probe.candidate).label ?? asObject(probe.candidate).selector ?? "-"),
              overlayAnnotations: asVisualProbeAnnotations(probe.overlay_annotations),
            }))
        : [];

      return {
        caseId: String(item.case_id ?? `TC-${String(index + 1).padStart(4, "0")}`),
        title: String(item.case_title ?? item.title ?? "-"),
        pageUrl: String(item.page_url ?? item.target_url ?? "-"),
        plannedProbeKinds: asStringList(probePlan.probe_kinds),
        summary: {
          total: Number(summary.total ?? probes.length),
          pass: Number(summary.pass ?? 0),
          fail: Number(summary.fail ?? 0),
          needsReview: Number(summary.needs_review ?? 0),
          skipped: Number(summary.skipped ?? 0),
        },
        probes,
        executionLog: asStringList(item.execution_log),
        evidenceScreenshots: asVisualProbeScreenshots(item.evidence_screenshots),
      };
    });
}

function pickVisualProbeSummary(rawSummary: Record<string, unknown>, probeCases: VisualProbeCaseView[]): VisualProbeSummaryView {
  if (Object.keys(rawSummary).length > 0) {
    return {
      caseCount: Number(rawSummary.case_count ?? probeCases.length),
      probeCount: Number(rawSummary.probe_count ?? 0),
      pass: Number(rawSummary.pass ?? 0),
      fail: Number(rawSummary.fail ?? 0),
      needsReview: Number(rawSummary.needs_review ?? 0),
      skipped: Number(rawSummary.skipped ?? 0),
    };
  }

  return probeCases.reduce(
    (accumulator, probeCase) => {
      accumulator.caseCount += 1;
      accumulator.probeCount += probeCase.probes.length;
      accumulator.pass += probeCase.summary.pass;
      accumulator.fail += probeCase.summary.fail;
      accumulator.needsReview += probeCase.summary.needsReview;
      accumulator.skipped += probeCase.summary.skipped;
      return accumulator;
    },
    { caseCount: 0, probeCount: 0, pass: 0, fail: 0, needsReview: 0, skipped: 0 },
  );
}

function buildPageButtons(totalPages: number, currentPage: number): Array<number | "ellipsis" | "eof"> {
  if (totalPages <= 1) {
    return [1];
  }
  if (totalPages <= 4) {
    return Array.from({ length: totalPages }, (_unused, index) => index + 1);
  }
  const pages = new Set<number>([1, Math.max(1, currentPage - 1), currentPage, Math.min(totalPages, currentPage + 1)]);
  const ordered = Array.from(pages)
    .filter((page) => page >= 1 && page <= totalPages)
    .sort((a, b) => a - b);
  const buttons: Array<number | "ellipsis" | "eof"> = [];
  ordered.forEach((page, index) => {
    const previous = ordered[index - 1];
    if (previous && page - previous > 1) {
      buttons.push("ellipsis");
    }
    buttons.push(page);
  });
  if (buttons[buttons.length - 1] !== totalPages) {
    buttons.push("eof");
  }
  return buttons;
}

function resolveOutputUrl(output: string, files: ArtifactFile[]): string | null {
  const normalized = output.replace(/\\/g, "/").split("/").pop()?.toLowerCase();
  const match = files.find((file) => file.name.toLowerCase() === output.toLowerCase() || file.name.toLowerCase() === normalized);
  return match?.url ?? null;
}

function resolveEvidenceRef(evidenceRef: string, files: ArtifactFile[]): ResolvedEvidence {
  const normalized = evidenceRef.replace(/\\/g, "/");
  const label = normalized.split("/").pop() ?? evidenceRef;
  const loweredLabel = label.toLowerCase();
  const matchedFile = files.find((file) => file.name.toLowerCase() === loweredLabel || file.url.toLowerCase().includes(loweredLabel));
  const url = /^https?:\/\//i.test(evidenceRef) ? evidenceRef : matchedFile?.url ?? null;
  return {
    label,
    source: evidenceRef,
    url,
    isImage: matchedFile?.is_image ?? isImageRef(label),
  };
}

function normalizeArtifactPath(value: string): string {
  return String(value ?? "").replace(/\\/g, "/").trim().toLowerCase();
}

function sameArtifactPath(left: string, right: string): boolean {
  const normalizedLeft = normalizeArtifactPath(left);
  const normalizedRight = normalizeArtifactPath(right);
  if (!normalizedLeft || !normalizedRight) {
    return false;
  }
  if (normalizedLeft === normalizedRight) {
    return true;
  }
  return normalizedLeft.split("/").pop() === normalizedRight.split("/").pop();
}

function extractCaseSteps(events: string[], caseId: string): string[] {
  const exact = events.filter((event) => event.includes(caseId));
  if (exact.length > 0) {
    return exact;
  }
  return events.filter((event) => event.toLowerCase().includes(caseId.toLowerCase()));
}

function extractProbeSteps(events: string[], probeKind: string): string[] {
  const patternsByKind: Record<string, string[]> = {
    scroll_probe: ["probe-scroll", "browser_scroll"],
    hover_probe: ["probe-hover", "browser_hover"],
    clickability_probe: ["probe-click", "browser_click", "browser_get_url"],
  };
  const patterns = patternsByKind[probeKind] ?? [probeKind.replace(/_/g, "-"), probeKind];
  const matched = events.filter((event) => patterns.some((pattern) => event.toLowerCase().includes(pattern.toLowerCase())));
  if (matched.length > 0) {
    return matched;
  }
  return events.slice(0, 20);
}

function resolveProbeEvidenceEntries(
  probeCase: VisualProbeCaseView,
  probe: VisualProbeItemView,
  files: ArtifactFile[],
): ResolvedProbeEvidence[] {
  const matchedScreenshots = probeCase.evidenceScreenshots.filter((item) =>
    probe.evidenceRefs.some((ref) => sameArtifactPath(ref, item.path)),
  );
  if (matchedScreenshots.length > 0) {
    return matchedScreenshots.map((item) => {
      const resolved = resolveEvidenceRef(item.path, files);
      return {
        ...resolved,
        note: item.note,
        pageUrl: item.pageUrl,
      };
    });
  }

  return probe.evidenceRefs.map((ref) => {
    const resolved = resolveEvidenceRef(ref, files);
    return {
      ...resolved,
      note: "",
      pageUrl: probeCase.pageUrl,
    };
  });
}

function findProbeImageByPhase(images: ResolvedProbeEvidence[], phase: "before" | "after"): ResolvedProbeEvidence | null {
  const matched = images.find((item) => (item.note || item.label).toLowerCase().includes(phase));
  return matched ?? null;
}

function annotationsForProbeNote(
  selection: VisualProbePreviewSelection | null,
  image: ResolvedProbeEvidence | null,
): VisualProbeAnnotationView[] {
  if (!selection || !image) {
    return [];
  }
  return selection.probe.overlayAnnotations.filter((item) => item.screenshotNote === image.note);
}

function workflowNodeState(stage: PipelineStage | undefined): string {
  if (!stage) {
    return "warning";
  }
  return stage.ready ? "ready" : "warning";
}

function pickCaseSummary(allCases: TestCaseView[], rawSummary: Record<string, unknown>): Record<string, number> {
  if (Object.keys(rawSummary).length > 0) {
    return {
      total: Number(rawSummary.total ?? allCases.length),
      pass: Number(rawSummary.pass ?? 0),
      fail: Number(rawSummary.fail ?? 0),
      needs_review: Number(rawSummary.needs_review ?? 0),
    };
  }
  return allCases.reduce(
    (accumulator, item) => {
      accumulator.total += 1;
      const status = item.status.toLowerCase();
      if (status === "pass") accumulator.pass += 1;
      else if (status === "fail") accumulator.fail += 1;
      else if (status === "needs_review") accumulator.needs_review += 1;
      return accumulator;
    },
    { total: 0, pass: 0, fail: 0, needs_review: 0 },
  );
}

export default function App(): JSX.Element {
  const [runsResponse, setRunsResponse] = useState<RunsResponse | null>(null);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [query, setQuery] = useState("");
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [passCasePage, setPassCasePage] = useState(1);
  const [isPassCaseBrowserOpen, setIsPassCaseBrowserOpen] = useState(false);
  const [selectedPassCase, setSelectedPassCase] = useState<TestCaseView | null>(null);
  const [selectedEvidenceIndex, setSelectedEvidenceIndex] = useState(0);
  const [imageZoom, setImageZoom] = useState(1);
  const [selectedProbePreview, setSelectedProbePreview] = useState<VisualProbePreviewSelection | null>(null);
  const [selectedProbeEvidenceIndex, setSelectedProbeEvidenceIndex] = useState(0);
  const [probeImageZoom, setProbeImageZoom] = useState(1);
  const selectedRunIdRef = useRef("");
  const runDetailRequestRef = useRef(0);

  const pathname = typeof window === "undefined" ? "/review" : window.location.pathname;
  const currentView = pathname.startsWith("/workflow") ? "workflow" : "review";

  const loadRun = useCallback(async (runId: string) => {
    const requestId = runDetailRequestRef.current + 1;
    runDetailRequestRef.current = requestId;
    setSelectedRunId(runId);
    setRunDetail(null);
    setLoadingDetail(true);
    setErrorMessage("");
    try {
      const detail = await fetchRunDetail(runId);
      if (runDetailRequestRef.current !== requestId) {
        return;
      }
      setRunDetail(detail);
    } catch (error) {
      if (runDetailRequestRef.current !== requestId) {
        return;
      }
      setRunDetail(null);
      setErrorMessage(error instanceof Error ? error.message : String(error));
    } finally {
      if (runDetailRequestRef.current === requestId) {
        setLoadingDetail(false);
      }
    }
  }, []);

  const refreshRuns = useCallback(
    async (keepSelection = true) => {
      setLoadingRuns(true);
      setErrorMessage("");
      try {
        const response = await fetchRuns(300);
        setRunsResponse(response);
        const currentRunId = selectedRunIdRef.current;
        if (keepSelection && currentRunId && response.runs.some((run) => run.run_id === currentRunId)) {
          await loadRun(currentRunId);
        } else if (response.runs.length > 0) {
          await loadRun(response.runs[0].run_id);
        } else {
          runDetailRequestRef.current += 1;
          setRunDetail(null);
          setSelectedRunId("");
          setLoadingDetail(false);
        }
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : String(error));
      } finally {
        setLoadingRuns(false);
      }
    },
    [loadRun],
  );

  useEffect(() => {
    void refreshRuns(false);
  }, [refreshRuns]);

  useEffect(() => {
    selectedRunIdRef.current = selectedRunId;
  }, [selectedRunId]);

  useEffect(() => {
    setPassCasePage(1);
    setIsPassCaseBrowserOpen(false);
    setSelectedPassCase(null);
    setSelectedProbePreview(null);
  }, [selectedRunId]);

  useEffect(() => {
    setSelectedEvidenceIndex(0);
    setImageZoom(1);
  }, [selectedPassCase?.caseId]);

  useEffect(() => {
    setSelectedProbeEvidenceIndex(0);
    setProbeImageZoom(1);
  }, [selectedProbePreview?.probeCase.caseId, selectedProbePreview?.probe.probeKind]);

  const filteredRuns = useMemo(() => {
    const runs = runsResponse?.runs ?? [];
    const keyword = query.trim().toLowerCase();
    if (!keyword) {
      return runs;
    }
    return runs.filter((run) =>
      [run.run_id, run.url, run.agent, run.mode_label, run.mode_key, run.status].some((value) =>
        value.toLowerCase().includes(keyword),
      ),
    );
  }, [query, runsResponse]);

  const selectedSummary = runDetail?.summary ?? null;
  const artifacts = runDetail?.artifacts ?? {};
  const qaReport = asObject(artifacts.qa_report);
  const regressionDiff = asObject(artifacts.regression_diff);
  const coverageSummary = asObject(qaReport.coverage_summary ?? qaReport.coverage);
  const tokenUsage = asObject(qaReport.token_usage);
  const testCaseResults = asObject(artifacts.test_case_results);
  const testCasePlan = asObject(artifacts.test_cases);
  const visualProbes = asObject(artifacts.visual_probes);
  const executionLog = asObject(artifacts.execution_log);
  const memoryRetrieval = asMemoryRetrieval(runDetail);
  const rawExecutionEvents = Array.isArray(executionLog.raw_events)
    ? executionLog.raw_events.map((item) => String(item ?? ""))
    : [];
  const allTestCases = asTestCases(testCaseResults.results, testCasePlan.test_cases);
  const caseSummary = pickCaseSummary(allTestCases, asObject(testCaseResults.summary));
  const visualProbeCases = asVisualProbeCases(visualProbes.results);
  const visualProbeSummary = pickVisualProbeSummary(asObject(qaReport.visual_probe_summary ?? visualProbes.summary), visualProbeCases);
  const passCases = allTestCases.filter((item) => item.status.toLowerCase() === "pass");
  const passCasePageCount = Math.max(1, Math.ceil(passCases.length / PASS_CASES_PER_PAGE));
  const safePassCasePage = Math.min(passCasePage, passCasePageCount);
  const visiblePassCases = passCases.slice((safePassCasePage - 1) * PASS_CASES_PER_PAGE, safePassCasePage * PASS_CASES_PER_PAGE);
  const passCaseButtons = buildPageButtons(passCasePageCount, safePassCasePage);
  const displayArtifacts = (runDetail?.files ?? []).filter(shouldDisplayArtifact);
  const findings = useMemo(() => asFindings(runDetail), [runDetail]);
  const reportFindings = Array.isArray(qaReport.findings) ? qaReport.findings : [];
  const unresolvedItems = Array.isArray(qaReport.unresolved_items) ? qaReport.unresolved_items : [];
  const selfHealingAttempts = Array.isArray(qaReport.self_healing_attempts) ? qaReport.self_healing_attempts : [];
  const deepDiveCandidates = asStringList(qaReport.top3_deep_dive_candidates);
  const unresolvedReasons = unresolvedItems
    .map((item) => String(asObject(item).reason ?? "").trim())
    .filter(Boolean)
    .join(", ");
  const pipelineTrace = runDetail?.pipeline_trace ?? [];
  const traceMap = useMemo(() => new Map(pipelineTrace.map((stage) => [stage.stage.toLowerCase(), stage])), [pipelineTrace]);
  const selectedPassCaseSteps = selectedPassCase ? extractCaseSteps(rawExecutionEvents, selectedPassCase.caseId) : [];
  const selectedPassCaseStepList =
    selectedPassCase && selectedPassCaseSteps.length === 0 ? selectedPassCase.plannedSteps : selectedPassCaseSteps;
  const selectedPassCaseEvidence = selectedPassCase
    ? selectedPassCase.evidenceRefs.map((ref) => resolveEvidenceRef(ref, runDetail?.files ?? []))
    : [];
  const selectedPassCaseImages = selectedPassCaseEvidence.filter((item) => item.isImage && item.url);
  const selectedImageEvidence = selectedPassCaseImages[selectedEvidenceIndex] ?? null;
  const hasVisualProbeData = visualProbeCases.length > 0 || visualProbeSummary.probeCount > 0;
  const visualProbeRegression = asObject(regressionDiff.visual_probe_diff);
  const visualProbeRegressionPrevious = asObject(visualProbeRegression.previous_summary);
  const visualProbeRegressionCurrent = asObject(visualProbeRegression.current_summary);
  const visualProbeRegressionDelta = asObject(visualProbeRegression.delta);
  const visualProbeBreakdownDelta = asObject(visualProbeRegression.breakdown_delta);
  const selectedProbeSteps = selectedProbePreview
    ? extractProbeSteps(selectedProbePreview.probeCase.executionLog, selectedProbePreview.probe.probeKind)
    : [];
  const selectedProbeEvidence = selectedProbePreview
    ? resolveProbeEvidenceEntries(selectedProbePreview.probeCase, selectedProbePreview.probe, runDetail?.files ?? [])
    : [];
  const selectedProbeImages = selectedProbeEvidence.filter((item) => item.isImage && item.url);
  const selectedProbeImage = selectedProbeImages[selectedProbeEvidenceIndex] ?? null;
  const selectedProbeAnnotations = annotationsForProbeNote(selectedProbePreview, selectedProbeImage);
  const selectedProbeBeforeImage = findProbeImageByPhase(selectedProbeImages, "before");
  const selectedProbeAfterImage = findProbeImageByPhase(selectedProbeImages, "after");
  const hasProbeCompareView = Boolean(selectedProbeBeforeImage && selectedProbeAfterImage);

  const workflowNodes: WorkflowNode[] = useMemo(
    () => [
      {
        label: "Request",
        agent: "Intake / Job Orchestrator",
        role: "Accept the requested URL and initialize the run workspace in fixed Full QA (E2E) mode.",
        outputs: ["started.json"],
        caption: selectedSummary?.mode_label || selectedSummary?.agent || "Queued",
        state: selectedSummary ? "ready" : "warning",
      },
      {
        label: "Map",
        agent: "Domain Context Mapping Agent",
        role: "Collect the domain context, global navigation, CTA candidates, forms, and representative page structure.",
        outputs: ["domain_context_map.json"],
        caption: traceMap.get("map")?.artifact ?? "domain_context_map.json",
        state: workflowNodeState(traceMap.get("map")),
      },
      {
        label: "Plan",
        agent: "Coverage Planning Agent",
        role: "Transform the map into coverage decisions and executable test cases.",
        outputs: ["coverage_plan.json", "test_cases.json"],
        caption: traceMap.get("plan")?.artifact ?? "coverage_plan.json / test_cases.json",
        state: workflowNodeState(traceMap.get("plan")),
      },
      {
        label: "Execute",
        agent: "Execution Agent",
        role: "Run deterministic visual probes and test cases with self-healing, then collect evidence and execution logs.",
        outputs: ["execution_log.json", "test_case_results.json", "visual_probes.json"],
        caption: traceMap.get("execute")?.artifact ?? "execution_log.json / test_case_results.json / visual_probes.json",
        state: workflowNodeState(traceMap.get("execute")),
      },
      {
        label: "Report",
        agent: "Report Agent",
        role: "Assemble the QA report, result summary, and regression comparison artifacts.",
        outputs: ["qa_report.json", "result.json", "regression_diff.json"],
        caption: traceMap.get("report")?.artifact ?? "qa_report.json / result.json",
        state: workflowNodeState(traceMap.get("report")),
      },
    ],
    [selectedSummary, traceMap],
  );

  return (
    <div className="page">
      <header className="topbar">
        <div className="topbar-main">
          <h1>Web QA Review</h1>
          <nav className="page-nav" aria-label="Primary">
            <a href="/review" className={`nav-link ${currentView === "review" ? "active" : ""}`}>
              Review
            </a>
            <a href="/workflow" className={`nav-link ${currentView === "workflow" ? "active" : ""}`}>
              Workflow
            </a>
            <a href="/api" className={`nav-link ${pathname.startsWith("/api") ? "active" : ""}`}>
              Python API
            </a>
          </nav>
        </div>
        <button type="button" className="button" onClick={() => void refreshRuns(true)} disabled={loadingRuns || loadingDetail}>
          Refresh
        </button>
      </header>

      <section className="layout">
        <aside className="panel run-panel">
          <div className="panel-head">
            <h2>Runs</h2>
            <input
              className="input"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
              }}
              placeholder="Search run id / url / mode"
            />
          </div>

          {errorMessage ? <p className="error-text">{errorMessage}</p> : null}

          <div className="run-list">
            {filteredRuns.map((run) => (
              <button
                key={run.run_id}
                type="button"
                className={`run-item ${run.run_id === selectedRunId ? "active" : ""}`}
                onClick={() => {
                  void loadRun(run.run_id);
                }}
              >
                <div className="run-item-title">{run.run_id}</div>
                <div className="run-item-sub">
                  <span className={`pill ${statusClass(run.status)}`}>{run.status}</span>
                  <span>{run.agent || "-"}</span>
                  <span>{run.mode_label || run.mode_key || "-"}</span>
                  {run.visual_probe_direction ? (
                    <span className={`pill ${diffDirectionClass(run.visual_probe_direction)}`}>interaction {run.visual_probe_direction}</span>
                  ) : null}
                </div>
                <div className="run-item-url">{run.url || "-"}</div>
                <div className="run-item-meta">
                  tokens {fmtNumber(run.token_total)} / findings {fmtNumber(run.finding_count)}
                  {run.visual_probe_fail_delta !== 0 || run.visual_probe_review_delta !== 0
                    ? ` / probe fail ${run.visual_probe_fail_delta >= 0 ? "+" : ""}${fmtNumber(run.visual_probe_fail_delta)} / review ${run.visual_probe_review_delta >= 0 ? "+" : ""}${fmtNumber(run.visual_probe_review_delta)}`
                    : ""}
                </div>
              </button>
            ))}

            {filteredRuns.length === 0 ? <div className="empty">No runs matched the current search.</div> : null}
          </div>
        </aside>

        <main className="panel detail-panel">
          {selectedSummary ? (
            currentView === "workflow" ? (
              <>
                <section className="detail-section">
                  <h2>Run Overview</h2>
                  <div className="overview-grid">
                    <article className="overview-card">
                      <span>Status</span>
                      <strong className={statusClass(selectedSummary.status)}>{selectedSummary.status}</strong>
                    </article>
                    <article className="overview-card">
                      <span>Target URL</span>
                      <strong>{selectedSummary.url || "-"}</strong>
                    </article>
                    <article className="overview-card">
                      <span>Duration</span>
                      <strong>{fmtDuration(selectedSummary.started_at, selectedSummary.completed_at)}</strong>
                    </article>
                    <article className="overview-card">
                      <span>Token Total</span>
                      <strong>{fmtNumber(selectedSummary.token_total)}</strong>
                    </article>
                    <article className="overview-card">
                      <span>Finding Count</span>
                      <strong>{fmtNumber(selectedSummary.finding_count)}</strong>
                    </article>
                    <article className="overview-card">
                      <span>Completed At</span>
                      <strong>{fmtTime(selectedSummary.completed_at)}</strong>
                    </article>
                  </div>
                  <div className="overview-actions">
                    <button
                      type="button"
                      className="overview-action-button"
                      onClick={() => {
                        setIsPassCaseBrowserOpen(true);
                      }}
                      disabled={passCases.length === 0}
                    >
                      Browse Passed Cases
                    </button>
                    <span className="hint">{fmtNumber(passCases.length)} pass cases available</span>
                  </div>
                </section>

                <section className="detail-section">
                  <h2>Workflow Map</h2>
                  <p className="hint">Each step shows the responsible agent, what it does, and which artifacts it should produce.</p>
                  <div className="workflow-stack">
                    {workflowNodes.map((node, index) => (
                      <div key={`${node.label}-row`} className="workflow-row">
                        <div className="workflow-step-column">
                          <article className={`workflow-node ${node.state}`}>
                            <span>{node.label}</span>
                            <strong>{node.agent}</strong>
                            <p className="workflow-summary">{node.role}</p>
                            <small>{node.caption}</small>
                          </article>
                          {index < workflowNodes.length - 1 ? <div className="workflow-down-arrow">↓</div> : null}
                        </div>
                        <div className="workflow-arrow workflow-arrow-side">→</div>
                        <article className={`workflow-output-card ${node.state}`}>
                          <div className="workflow-output-head">
                            <div>
                              <span className="pill">{node.label} Outputs</span>
                              <strong>{node.caption}</strong>
                            </div>
                          </div>
                          <ul className="workflow-output-list">
                            {node.outputs.map((output) => {
                              const outputUrl = resolveOutputUrl(output, runDetail?.files ?? []);
                              return (
                                <li key={`${node.label}-${output}`}>
                                  {outputUrl ? (
                                    <a href={outputUrl} target="_blank" rel="noreferrer">
                                      {output}
                                    </a>
                                  ) : (
                                    <span>{output}</span>
                                  )}
                                </li>
                              );
                            })}
                          </ul>
                        </article>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="detail-section">
                  <h2>Stage Trace</h2>
                  {pipelineTrace.length === 0 ? (
                    <div className="empty">No stage trace was recorded for this run.</div>
                  ) : (
                    <div className="trace-grid">
                      {pipelineTrace.map((stage) => (
                        <article key={stage.stage} className="trace-card">
                          <strong>{stage.stage}</strong>
                          <p>{stage.artifact}</p>
                          <span className={`pill ${stage.ready ? "status-pass" : "status-review"}`}>
                            {stage.ready ? "ready" : "pending"}
                          </span>
                          <a href={stage.url} target="_blank" rel="noreferrer">
                            Open artifact
                          </a>
                        </article>
                      ))}
                    </div>
                  )}
                </section>
              </>
            ) : (
              <>
                <section className="detail-section">
                  <h2>Run Overview</h2>
                  <div className="overview-grid">
                    <article className="overview-card">
                      <span>Status</span>
                      <strong className={statusClass(selectedSummary.status)}>{selectedSummary.status}</strong>
                    </article>
                    <article className="overview-card">
                      <span>Target URL</span>
                      <strong>{selectedSummary.url || "-"}</strong>
                    </article>
                    <article className="overview-card">
                      <span>Duration</span>
                      <strong>{fmtDuration(selectedSummary.started_at, selectedSummary.completed_at)}</strong>
                    </article>
                    <article className="overview-card">
                      <span>Token Total</span>
                      <strong>{fmtNumber(selectedSummary.token_total)}</strong>
                    </article>
                    <article className="overview-card">
                      <span>Finding Count</span>
                      <strong>{fmtNumber(selectedSummary.finding_count)}</strong>
                    </article>
                    <article className="overview-card">
                      <span>Completed At</span>
                      <strong>{fmtTime(selectedSummary.completed_at)}</strong>
                    </article>
                  </div>
                  <div className="overview-actions">
                    <button
                      type="button"
                      className="overview-action-button"
                      onClick={() => {
                        setIsPassCaseBrowserOpen(true);
                      }}
                      disabled={passCases.length === 0}
                    >
                      Browse Passed Cases
                    </button>
                    <span className="hint">{fmtNumber(passCases.length)} pass cases available</span>
                  </div>
                </section>
                <section className="detail-section split">
                  <div>
                    <h2>QA Report</h2>
                    {Object.keys(qaReport).length === 0 ? (
                      <div className="empty">qa_report.json is missing or empty.</div>
                    ) : (
                      <div className="report-preview">
                        <div className="report-grid">
                          <section className="report-card">
                            <div className="report-card-header">
                              <h3>Execution Results</h3>
                              <span className={`pill ${statusClass(String(qaReport.overall_status ?? selectedSummary.status))}`}>
                                {String(qaReport.overall_status ?? selectedSummary.status)}
                              </span>
                            </div>
                            <table className="report-table">
                              <tbody>
                                <tr>
                                  <th>Total Cases</th>
                                  <td>{fmtNumber(caseSummary.total)}</td>
                                </tr>
                                <tr>
                                  <th>Pass</th>
                                  <td>{fmtNumber(caseSummary.pass)}</td>
                                </tr>
                                <tr>
                                  <th>Fail</th>
                                  <td>{fmtNumber(caseSummary.fail)}</td>
                                </tr>
                                <tr>
                                  <th>Needs Review</th>
                                  <td>{fmtNumber(caseSummary.needs_review)}</td>
                                </tr>
                              </tbody>
                            </table>
                            <p className="report-note">{String(qaReport.status_reason ?? selectedSummary.status_reason ?? "-")}</p>
                          </section>

                          <section className="report-card">
                            <h3>Coverage</h3>
                            <table className="report-table">
                              <tbody>
                                <tr>
                                  <th>Canonical Host</th>
                                  <td>{String(coverageSummary.canonical_host ?? coverageSummary.final_host ?? "-")}</td>
                                </tr>
                                <tr>
                                  <th>Visited Count</th>
                                  <td>{fmtNumber(Number(coverageSummary.visited_count ?? 0))}</td>
                                </tr>
                                <tr>
                                  <th>Visited URLs</th>
                                  <td>{fmtNumber(countItems(coverageSummary.visited_urls))}</td>
                                </tr>
                                <tr>
                                  <th>External Events</th>
                                  <td>{fmtNumber(countItems(coverageSummary.external_navigation_events))}</td>
                                </tr>
                                <tr>
                                  <th>Stop Reason</th>
                                  <td>{String(coverageSummary.map_stop_reason ?? coverageSummary.stop_reason ?? "-")}</td>
                                </tr>
                              </tbody>
                            </table>
                          </section>

                          <section className="report-card">
                            <h3>Token Usage</h3>
                            <table className="report-table">
                              <tbody>
                                <tr>
                                  <th>Total Tokens</th>
                                  <td>{fmtNumber(Number(tokenUsage.total_tokens ?? selectedSummary.token_total ?? 0))}</td>
                                </tr>
                                <tr>
                                  <th>Prompt Tokens</th>
                                  <td>{fmtNumber(Number(tokenUsage.prompt_tokens ?? 0))}</td>
                                </tr>
                                <tr>
                                  <th>Completion Tokens</th>
                                  <td>{fmtNumber(Number(tokenUsage.completion_tokens ?? 0))}</td>
                                </tr>
                                <tr>
                                  <th>Self-healing Cases</th>
                                  <td>{fmtNumber(selfHealingAttempts.length)}</td>
                                </tr>
                                <tr>
                                  <th>Unresolved</th>
                                  <td>{unresolvedReasons || "-"}</td>
                                </tr>
                              </tbody>
                            </table>
                          </section>
                        </div>

                        <section className="report-card">
                          <h3>Key Findings</h3>
                          {reportFindings.length === 0 ? (
                            <div className="empty">No findings were recorded in qa_report.json.</div>
                          ) : (
                            <table className="report-finding-table">
                              <thead>
                                <tr>
                                  <th>ID</th>
                                  <th>Severity</th>
                                  <th>Type</th>
                                  <th>Observation</th>
                                  <th>Next Check</th>
                                </tr>
                              </thead>
                              <tbody>
                                {reportFindings.map((item, index) => {
                                  const finding = asObject(item);
                                  return (
                                    <tr key={String(finding.id ?? index)}>
                                      <td>{String(finding.id ?? `F-${index + 1}`)}</td>
                                      <td>{String(finding.severity ?? "-")}</td>
                                      <td>{String(finding.type ?? "-")}</td>
                                      <td>{String(finding.observation ?? "-")}</td>
                                      <td>{String(finding.next_check ?? "-")}</td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          )}
                        </section>
                      </div>
                    )}
                  </div>

                  <div>
                    <h2>Deep Dive & Debug</h2>
                    <div className="report-preview">
                      <section className="report-card">
                        <h3>Deep Dive Candidates</h3>
                        {deepDiveCandidates.length === 0 ? (
                          <div className="empty">No deep dive candidates were recorded for this run.</div>
                        ) : (
                          <ul className="tag-list">
                            {deepDiveCandidates.map((candidate) => (
                              <li key={candidate}>{candidate}</li>
                            ))}
                          </ul>
                        )}
                      </section>

                      <section className="report-card log-card">
                        <details className="log-details">
                          <summary>Debug Log</summary>
                          <div className="log-frame">
                            <pre className="log-preview">{runDetail?.text_previews["runner.log"] ?? "runner.log not found"}</pre>
                          </div>
                        </details>
                      </section>
                    </div>
                  </div>
                </section>

                <section className="detail-section">
                  <h2>Memory Retrieval</h2>
                  <p className="hint">
                    Pattern-aware retrieval shows which past QA memories were pulled into planning and how much metadata reranking changed
                    the final ordering.
                  </p>
                  {!memoryRetrieval ? (
                    <div className="empty">memory_retrieval.json is missing or empty.</div>
                  ) : (
                    <div className="report-preview">
                      <div className="report-grid">
                        <section className="report-card">
                          <div className="report-card-header">
                            <h3>Retrieval Summary</h3>
                            <span className={`pill ${memoryRetrieval.enabled ? "status-pass" : "status-review"}`}>
                              {memoryRetrieval.enabled ? "enabled" : "disabled"}
                            </span>
                          </div>
                          <table className="report-table">
                            <tbody>
                              <tr>
                                <th>Backend</th>
                                <td>{memoryRetrieval.backend || "-"}</td>
                              </tr>
                              <tr>
                                <th>Top K</th>
                                <td>{fmtNumber(memoryRetrieval.topK)}</td>
                              </tr>
                              <tr>
                                <th>Total Hits</th>
                                <td>{fmtNumber(memoryRetrieval.totalHits)}</td>
                              </tr>
                              <tr>
                                <th>Issue Patterns</th>
                                <td>{fmtNumber(memoryRetrieval.issueTypeCounts.length)}</td>
                              </tr>
                            </tbody>
                          </table>
                          <p className="report-note">{memoryRetrieval.reason || "No retrieval warning was recorded."}</p>
                        </section>

                        <section className="report-card">
                          <h3>Query Text</h3>
                          <p className="memory-query-text">{memoryRetrieval.queryText || "-"}</p>
                        </section>

                        <section className="report-card">
                          <h3>Query Hints</h3>
                          <div className="memory-hint-groups">
                            {memoryRetrieval.queryHints.platform ? (
                              <div className="memory-hint-group">
                                <span>Platform</span>
                                <ul className="tag-list">
                                  <li>{memoryRetrieval.queryHints.platform}</li>
                                </ul>
                              </div>
                            ) : null}

                            {memoryRetrieval.queryHints.pageRoles.length > 0 ? (
                              <div className="memory-hint-group">
                                <span>Page Roles</span>
                                <ul className="tag-list">
                                  {memoryRetrieval.queryHints.pageRoles.map((value) => (
                                    <li key={`query-role-${value}`}>{value}</li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}

                            {memoryRetrieval.queryHints.componentTypes.length > 0 ? (
                              <div className="memory-hint-group">
                                <span>Components</span>
                                <ul className="tag-list">
                                  {memoryRetrieval.queryHints.componentTypes.map((value) => (
                                    <li key={`query-component-${value}`}>{value}</li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}

                            {memoryRetrieval.queryHints.interactionKinds.length > 0 ? (
                              <div className="memory-hint-group">
                                <span>Interactions</span>
                                <ul className="tag-list">
                                  {memoryRetrieval.queryHints.interactionKinds.map((value) => (
                                    <li key={`query-interaction-${value}`}>{value}</li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}

                            {memoryRetrieval.queryHints.layoutSignals.length > 0 ? (
                              <div className="memory-hint-group">
                                <span>Layout Signals</span>
                                <ul className="tag-list">
                                  {memoryRetrieval.queryHints.layoutSignals.map((value) => (
                                    <li key={`query-layout-${value}`}>{value}</li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}

                            {memoryRetrieval.queryHints.frameworkHints.length > 0 ? (
                              <div className="memory-hint-group">
                                <span>Framework</span>
                                <ul className="tag-list">
                                  {memoryRetrieval.queryHints.frameworkHints.map((value) => (
                                    <li key={`query-framework-${value}`}>{value}</li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}

                            {memoryRetrieval.issueTypeCounts.length > 0 ? (
                              <div className="memory-hint-group">
                                <span>Retrieved Issue Patterns</span>
                                <ul className="tag-list">
                                  {memoryRetrieval.issueTypeCounts.map(([issueType, count]) => (
                                    <li key={`issue-type-${issueType}`}>
                                      {issueType} · {fmtNumber(count)}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}

                            {!memoryRetrieval.queryHints.platform &&
                            memoryRetrieval.queryHints.pageRoles.length === 0 &&
                            memoryRetrieval.queryHints.componentTypes.length === 0 &&
                            memoryRetrieval.queryHints.interactionKinds.length === 0 &&
                            memoryRetrieval.queryHints.layoutSignals.length === 0 &&
                            memoryRetrieval.queryHints.frameworkHints.length === 0 &&
                            memoryRetrieval.issueTypeCounts.length === 0 ? (
                              <div className="empty">No query hints were recorded for this run.</div>
                            ) : null}
                          </div>
                        </section>
                      </div>

                      <section className="report-card">
                        <div className="report-card-header">
                          <h3>Top Memory Hits</h3>
                          <span className="pill">top {fmtNumber(memoryRetrieval.hits.length)}</span>
                        </div>
                        {memoryRetrieval.hits.length === 0 ? (
                          <div className="empty">No memory hits were returned for this run.</div>
                        ) : (
                          <div className="memory-hit-list">
                            {memoryRetrieval.hits.map((hit) => {
                              const scoreBreakdown = Object.entries(hit.scoreBreakdown).filter(([, value]) => Math.abs(Number(value)) > 0);
                              return (
                                <article key={hit.cardId || `${hit.memoryId}-${hit.summary}`} className="memory-hit-card">
                                  <div className="memory-hit-head">
                                    <div className="memory-hit-title">
                                      <div className="memory-hit-pills">
                                        <span className="pill">{hit.cardId || "-"}</span>
                                        {hit.memoryId ? <span className="pill">{hit.memoryId}</span> : null}
                                        {hit.severityHint ? <span className="pill">{hit.severityHint}</span> : null}
                                      </div>
                                      <strong>{hit.summary || hit.observation || "Untitled memory hit"}</strong>
                                    </div>
                                    <div className="memory-hit-scores">
                                      <span className="pill">score {fmtScore(hit.score)}</span>
                                      <span className="pill">vector {fmtScore(hit.baseScore)}</span>
                                      <span className={`pill ${hit.metadataBoost > 0 ? "status-pass" : ""}`}>
                                        boost {fmtSignedScore(hit.metadataBoost)}
                                      </span>
                                    </div>
                                  </div>

                                  {hit.sectionHint ? <p className="memory-hit-section">Section: {hit.sectionHint}</p> : null}
                                  {hit.observation ? <p className="memory-hit-copy">{hit.observation}</p> : null}
                                  {hit.expectedBehavior ? <p className="memory-hit-note">Expected: {hit.expectedBehavior}</p> : null}

                                  <div className="memory-hit-meta">
                                    {hit.issueTypes.length > 0 ? (
                                      <div className="memory-meta-group">
                                        <span>Issue Types</span>
                                        <ul className="tag-list">
                                          {hit.issueTypes.map((value) => (
                                            <li key={`${hit.cardId}-issue-${value}`}>{value}</li>
                                          ))}
                                        </ul>
                                      </div>
                                    ) : null}

                                    {hit.pageRoles.length > 0 ? (
                                      <div className="memory-meta-group">
                                        <span>Page Roles</span>
                                        <ul className="tag-list">
                                          {hit.pageRoles.map((value) => (
                                            <li key={`${hit.cardId}-role-${value}`}>{value}</li>
                                          ))}
                                        </ul>
                                      </div>
                                    ) : null}

                                    {hit.componentTypes.length > 0 ? (
                                      <div className="memory-meta-group">
                                        <span>Components</span>
                                        <ul className="tag-list">
                                          {hit.componentTypes.map((value) => (
                                            <li key={`${hit.cardId}-component-${value}`}>{value}</li>
                                          ))}
                                        </ul>
                                      </div>
                                    ) : null}

                                    {hit.interactionKinds.length > 0 ? (
                                      <div className="memory-meta-group">
                                        <span>Interactions</span>
                                        <ul className="tag-list">
                                          {hit.interactionKinds.map((value) => (
                                            <li key={`${hit.cardId}-interaction-${value}`}>{value}</li>
                                          ))}
                                        </ul>
                                      </div>
                                    ) : null}

                                    {hit.layoutSignals.length > 0 ? (
                                      <div className="memory-meta-group">
                                        <span>Layout Signals</span>
                                        <ul className="tag-list">
                                          {hit.layoutSignals.map((value) => (
                                            <li key={`${hit.cardId}-layout-${value}`}>{value}</li>
                                          ))}
                                        </ul>
                                      </div>
                                    ) : null}

                                    {hit.frameworkHints.length > 0 ? (
                                      <div className="memory-meta-group">
                                        <span>Framework</span>
                                        <ul className="tag-list">
                                          {hit.frameworkHints.map((value) => (
                                            <li key={`${hit.cardId}-framework-${value}`}>{value}</li>
                                          ))}
                                        </ul>
                                      </div>
                                    ) : null}

                                    {scoreBreakdown.length > 0 ? (
                                      <div className="memory-meta-group">
                                        <span>Metadata Boost Breakdown</span>
                                        <ul className="tag-list">
                                          {scoreBreakdown.map(([label, value]) => (
                                            <li key={`${hit.cardId}-boost-${label}`}>
                                              {label} {fmtSignedScore(value)}
                                            </li>
                                          ))}
                                        </ul>
                                      </div>
                                    ) : null}
                                  </div>
                                </article>
                              );
                            })}
                          </div>
                        )}
                      </section>
                    </div>
                  )}
                </section>

                <section className="detail-section">
                  <h2>Test Case Plan</h2>
                  <p className="hint">
                    Each card merges planned case data with execution results so you can see why a case was assigned to deep, hover, or
                    clickability-oriented checks.
                  </p>
                  {allTestCases.length === 0 ? (
                    <div className="empty">No merged test case plan was available for this run.</div>
                  ) : (
                    <div className="test-case-plan-grid">
                      {allTestCases.map((testCase) => (
                        <article key={testCase.caseId} className="test-case-plan-card">
                          <div className="test-case-plan-head">
                            <div className="test-case-plan-title">
                              <div className="test-case-plan-pills">
                                <span className="pill">{testCase.caseId}</span>
                                <span className={`pill ${statusClass(testCase.status)}`}>{testCase.status || "-"}</span>
                                <span className="pill">{testCase.tier || "-"}</span>
                                {testCase.priority && testCase.priority !== "-" ? <span className="pill">{testCase.priority}</span> : null}
                                {testCase.severityHint ? <span className="pill">{testCase.severityHint}</span> : null}
                              </div>
                              <strong>{testCase.title}</strong>
                            </div>
                            <div className="test-case-plan-meta">
                              <span className="pill">planned probes {fmtNumber(testCase.plannedProbeKinds.length)}</span>
                              <span className="pill">memory hits {fmtNumber(testCase.memoryHitCount)}</span>
                            </div>
                          </div>

                          {testCase.targetUrl ? <p className="test-case-plan-url">{testCase.targetUrl}</p> : null}
                          {testCase.objective ? <p className="test-case-plan-copy">{testCase.objective}</p> : null}

                          {testCase.plannedProbeKinds.length > 0 ? (
                            <div className="memory-meta-group">
                              <span>Planned Probes</span>
                              <ul className="tag-list">
                                {testCase.plannedProbeKinds.map((value) => (
                                  <li key={`${testCase.caseId}-probe-${value}`}>{prettifyProbeKind(value)}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null}

                          {testCase.memoryIssueTypes.length > 0 ? (
                            <div className="memory-meta-group">
                              <span>Memory Issue Types</span>
                              <ul className="tag-list">
                                {testCase.memoryIssueTypes.map((value) => (
                                  <li key={`${testCase.caseId}-memory-issue-${value}`}>{value}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null}

                          {testCase.memoryPageRoles.length > 0 ? (
                            <div className="memory-meta-group">
                              <span>Memory Page Roles</span>
                              <ul className="tag-list">
                                {testCase.memoryPageRoles.map((value) => (
                                  <li key={`${testCase.caseId}-memory-role-${value}`}>{value}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null}

                          {testCase.memoryComponentTypes.length > 0 ? (
                            <div className="memory-meta-group">
                              <span>Memory Components</span>
                              <ul className="tag-list">
                                {testCase.memoryComponentTypes.map((value) => (
                                  <li key={`${testCase.caseId}-memory-component-${value}`}>{value}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null}

                          {testCase.memoryInteractionKinds.length > 0 ? (
                            <div className="memory-meta-group">
                              <span>Memory Interactions</span>
                              <ul className="tag-list">
                                {testCase.memoryInteractionKinds.map((value) => (
                                  <li key={`${testCase.caseId}-memory-interaction-${value}`}>{value}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null}

                          {testCase.memoryLayoutSignals.length > 0 ? (
                            <div className="memory-meta-group">
                              <span>Memory Layout Signals</span>
                              <ul className="tag-list">
                                {testCase.memoryLayoutSignals.map((value) => (
                                  <li key={`${testCase.caseId}-memory-layout-${value}`}>{value}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null}

                          {testCase.memoryFrameworkHints.length > 0 ? (
                            <div className="memory-meta-group">
                              <span>Memory Framework</span>
                              <ul className="tag-list">
                                {testCase.memoryFrameworkHints.map((value) => (
                                  <li key={`${testCase.caseId}-memory-framework-${value}`}>{value}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null}

                          {testCase.memoryCardIds.length > 0 ? (
                            <div className="memory-meta-group">
                              <span>Retrieved Cards</span>
                              <ul className="tag-list">
                                {testCase.memoryCardIds.slice(0, 4).map((value) => (
                                  <li key={`${testCase.caseId}-memory-card-${value}`}>{value}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null}

                          <div className="test-case-plan-actions">
                            <button
                              type="button"
                              className="page-button"
                              onClick={() => {
                                setSelectedPassCase(testCase);
                              }}
                            >
                              Open Case Detail
                            </button>
                          </div>
                        </article>
                      ))}
                    </div>
                  )}
                </section>

                <section className="detail-section">
                  <h2>Visual Probes</h2>
                  <p className="hint">
                    Deterministic scroll, hover, and clickability probes run alongside the execution agent to verify visible interaction
                    states before they are reduced into the final QA verdict.
                  </p>
                  {!hasVisualProbeData ? (
                    <div className="empty">No visual probe artifact was recorded for this run.</div>
                  ) : (
                    <div className="report-preview">
                      {Object.keys(visualProbeRegression).length > 0 ? (
                        <section className="report-card visual-probe-regression-card">
                          <div className="report-card-header">
                            <h3>Interaction Regression</h3>
                            <span className={`pill ${statusClass(String(visualProbeRegression.direction ?? "running"))}`}>
                              {String(visualProbeRegression.direction ?? "-")}
                            </span>
                          </div>
                          <table className="report-table">
                            <tbody>
                              <tr>
                                <th>Previous Run</th>
                                <td>{String(regressionDiff.previous_job_id ?? "-")}</td>
                              </tr>
                              <tr>
                                <th>Probe Count</th>
                                <td>
                                  {fmtNumber(Number(visualProbeRegressionPrevious.probe_count ?? 0))} →{" "}
                                  {fmtNumber(Number(visualProbeRegressionCurrent.probe_count ?? 0))} (
                                  {Number(visualProbeRegressionDelta.probe_count ?? 0) >= 0 ? "+" : ""}
                                  {fmtNumber(Number(visualProbeRegressionDelta.probe_count ?? 0))})
                                </td>
                              </tr>
                              <tr>
                                <th>Pass Delta</th>
                                <td>
                                  {Number(visualProbeRegressionDelta.pass ?? 0) >= 0 ? "+" : ""}
                                  {fmtNumber(Number(visualProbeRegressionDelta.pass ?? 0))}
                                </td>
                              </tr>
                              <tr>
                                <th>Fail Delta</th>
                                <td>
                                  {Number(visualProbeRegressionDelta.fail ?? 0) >= 0 ? "+" : ""}
                                  {fmtNumber(Number(visualProbeRegressionDelta.fail ?? 0))}
                                </td>
                              </tr>
                              <tr>
                                <th>Needs Review Delta</th>
                                <td>
                                  {Number(visualProbeRegressionDelta.needs_review ?? 0) >= 0 ? "+" : ""}
                                  {fmtNumber(Number(visualProbeRegressionDelta.needs_review ?? 0))}
                                </td>
                              </tr>
                            </tbody>
                          </table>
                          {Object.keys(visualProbeBreakdownDelta).length > 0 ? (
                            <div className="visual-probe-breakdown-row">
                              {Object.entries(visualProbeBreakdownDelta).map(([kind, deltaValue]) => {
                                const deltaRow = asObject(deltaValue);
                                return (
                                  <span key={kind} className="pill">
                                    {prettifyProbeKind(kind)}: fail {Number(deltaRow.fail ?? 0) >= 0 ? "+" : ""}
                                    {fmtNumber(Number(deltaRow.fail ?? 0))} / review {Number(deltaRow.needs_review ?? 0) >= 0 ? "+" : ""}
                                    {fmtNumber(Number(deltaRow.needs_review ?? 0))}
                                  </span>
                                );
                              })}
                            </div>
                          ) : null}
                        </section>
                      ) : null}

                      <div className="visual-probe-summary-grid">
                        <article className="overview-card">
                          <span>Cases</span>
                          <strong>{fmtNumber(visualProbeSummary.caseCount)}</strong>
                        </article>
                        <article className="overview-card">
                          <span>Total Probes</span>
                          <strong>{fmtNumber(visualProbeSummary.probeCount)}</strong>
                        </article>
                        <article className="overview-card">
                          <span>Pass</span>
                          <strong className="status-pass">{fmtNumber(visualProbeSummary.pass)}</strong>
                        </article>
                        <article className="overview-card">
                          <span>Fail</span>
                          <strong className="status-fail">{fmtNumber(visualProbeSummary.fail)}</strong>
                        </article>
                        <article className="overview-card">
                          <span>Needs Review</span>
                          <strong className="status-review">{fmtNumber(visualProbeSummary.needsReview)}</strong>
                        </article>
                        <article className="overview-card">
                          <span>Skipped</span>
                          <strong>{fmtNumber(visualProbeSummary.skipped)}</strong>
                        </article>
                      </div>

                      <div className="visual-probe-list">
                        {visualProbeCases.map((probeCase) => (
                          <article key={probeCase.caseId} className="visual-probe-card">
                            <div className="visual-probe-head">
                              <div className="visual-probe-title-block">
                                <div className="visual-probe-title-row">
                                  <span className="pill">{probeCase.caseId}</span>
                                  <strong>{probeCase.title}</strong>
                                </div>
                                <small>{probeCase.pageUrl}</small>
                              </div>
                              <div className="visual-probe-case-stats">
                                <span className="pill">planned {fmtNumber(probeCase.plannedProbeKinds.length)}</span>
                                <span className="pill status-pass">pass {fmtNumber(probeCase.summary.pass)}</span>
                                <span className="pill status-fail">fail {fmtNumber(probeCase.summary.fail)}</span>
                                <span className="pill status-review">review {fmtNumber(probeCase.summary.needsReview)}</span>
                                <span className="pill">skipped {fmtNumber(probeCase.summary.skipped)}</span>
                              </div>
                            </div>

                            <div className="visual-probe-plan-row">
                              <span className="visual-probe-label">Planned Probes</span>
                              <ul className="tag-list">
                                {probeCase.plannedProbeKinds.length > 0 ? (
                                  probeCase.plannedProbeKinds.map((kind) => <li key={`${probeCase.caseId}-${kind}`}>{prettifyProbeKind(kind)}</li>)
                                ) : (
                                  <li>No planned probes</li>
                                )}
                              </ul>
                            </div>

                            {probeCase.probes.length === 0 ? (
                              <div className="empty">No probe result rows were recorded for this case.</div>
                            ) : (
                              <div className="visual-probe-item-list">
                                {probeCase.probes.map((probe, index) => {
                                  const resolvedEvidence = probe.evidenceRefs.map((ref) => resolveEvidenceRef(ref, runDetail?.files ?? []));
                                  return (
                                    <article key={`${probeCase.caseId}-${probe.probeKind}-${index}`} className="visual-probe-item">
                                      <div className="visual-probe-item-head">
                                        <strong>{prettifyProbeKind(probe.probeKind)}</strong>
                                        <span className={`pill ${statusClass(probe.status)}`}>{probe.status}</span>
                                      </div>
                                      <p className="visual-probe-reason">{probe.reason}</p>

                                      {probe.observations.length > 0 ? (
                                        <ul className="visual-probe-observations">
                                          {probe.observations.map((observation) => (
                                            <li key={`${probeCase.caseId}-${probe.probeKind}-${observation}`}>{observation}</li>
                                          ))}
                                        </ul>
                                      ) : null}

                                      <div className="visual-probe-evidence-row">
                                        <span className="visual-probe-label">Evidence</span>
                                        {resolvedEvidence.length === 0 ? (
                                          <span className="visual-probe-empty">No evidence refs</span>
                                        ) : (
                                          <div className="visual-probe-evidence-list">
                                            {resolvedEvidence.map((evidence, evidenceIndex) =>
                                              evidence.url ? (
                                                <a
                                                  key={`${probeCase.caseId}-${probe.probeKind}-${evidence.label}-${evidenceIndex}`}
                                                  href={evidence.url}
                                                  target="_blank"
                                                  rel="noreferrer"
                                                >
                                                  {evidence.label}
                                                </a>
                                              ) : (
                                                <span key={`${probeCase.caseId}-${probe.probeKind}-${evidence.label}-${evidenceIndex}`}>
                                                  {evidence.label}
                                                </span>
                                              ),
                                            )}
                                          </div>
                                        )}
                                      </div>

                                      <div className="visual-probe-item-actions">
                                        <button
                                          type="button"
                                          className="page-button"
                                          onClick={() => {
                                            setSelectedProbePreview({ probeCase, probe });
                                          }}
                                        >
                                          Open Probe Preview
                                        </button>
                                      </div>
                                    </article>
                                  );
                                })}
                              </div>
                            )}
                          </article>
                        ))}
                      </div>
                    </div>
                  )}
                </section>

                <section className="detail-section">
                  <h2>Artifacts</h2>
                  <p className="hint">Only structured and text artifacts are shown here. Image files stay inside case-level evidence preview.</p>
                  {displayArtifacts.length === 0 ? (
                    <div className="empty">No structured artifacts were recorded for this run.</div>
                  ) : (
                    <div className="artifact-grid">
                      {displayArtifacts.map((file) => (
                        <article key={file.name} className="artifact-card">
                          <strong>{file.name}</strong>
                          <span>{fmtNumber(file.size)} bytes</span>
                          <span>{fmtTime(file.modified_at)}</span>
                          <a href={file.url} target="_blank" rel="noreferrer">
                            Open artifact
                          </a>
                        </article>
                      ))}
                    </div>
                  )}
                </section>

                <section className="detail-section">
                  <h2>Findings</h2>
                  {findings.length === 0 ? (
                    <div className="empty">No findings were recorded for this run.</div>
                  ) : (
                    <div className="finding-table">
                      {findings.map((finding, index) => (
                        <article key={finding.id ?? `${index}`} className="finding-row">
                          <div>
                            <strong>{finding.id ?? `F-${index + 1}`}</strong>
                            <span className="pill">{finding.severity ?? "-"}</span>
                            <span className="pill">{finding.type ?? "-"}</span>
                          </div>
                          <p>{finding.observation ?? "-"}</p>
                          <small>{finding.page_url ?? finding.location ?? "-"}</small>
                        </article>
                      ))}
                    </div>
                  )}
                </section>
              </>
            )
          ) : (
            <div className="empty">No run selected.</div>
          )}

          {loadingDetail ? <div className="loading">Loading run details...</div> : null}
        </main>
      </section>

      <Agentation />
      {isPassCaseBrowserOpen ? (
        <div className="quicklook-backdrop" onClick={() => setIsPassCaseBrowserOpen(false)}>
          <section
            className="quicklook-panel pass-browser-panel"
            role="dialog"
            aria-modal="true"
            aria-label="Passed test cases"
            onClick={(event) => {
              event.stopPropagation();
            }}
          >
            <div className="quicklook-head">
              <div>
                <span className="pill">{fmtNumber(passCases.length)} pass cases</span>
                <h2>Passed Test Cases</h2>
              </div>
              <button type="button" className="quicklook-close" onClick={() => setIsPassCaseBrowserOpen(false)}>
                Close
              </button>
            </div>

            {passCases.length === 0 ? (
              <div className="empty">No passed test cases were recorded for this run.</div>
            ) : (
              <div className="pass-browser-body">
                <p className="hint">Open a case to inspect steps and evidences without keeping every detail on the main page.</p>
                <div className="pass-case-shell">
                  <div className="pass-case-list">
                    {visiblePassCases.map((testCase) => (
                      <article key={testCase.caseId} className="pass-case-card">
                        <div className="pass-case-head">
                          <strong>{testCase.caseId}</strong>
                          <div className="pass-case-meta">
                            <span className="pill">{testCase.tier}</span>
                            <span className="pill">{fmtNumber(testCase.stepsExecuted)} steps</span>
                            <span className="pill">{fmtNumber(testCase.evidenceRefs.length)} evidences</span>
                            <span className="pill">{fmtNumber(testCase.plannedProbeKinds.length)} probes</span>
                            <span className="pill">{fmtNumber(testCase.memoryHitCount)} memory hits</span>
                          </div>
                        </div>
                        <div className="pass-case-body">
                          <div>
                            <dt>Validated Item</dt>
                            <dd>{testCase.title}</dd>
                          </div>
                          <div>
                            <dt>Why It Passed</dt>
                            <dd>{testCase.reason}</dd>
                          </div>
                        </div>
                        <div className="pass-case-actions">
                          <button
                            type="button"
                            className="page-button"
                            onClick={() => {
                              setIsPassCaseBrowserOpen(false);
                              setSelectedPassCase(testCase);
                            }}
                          >
                            Open Steps & Evidences
                          </button>
                        </div>
                      </article>
                    ))}
                  </div>

                  <div className="pass-pagination" aria-label="pass case pagination">
                    <button
                      type="button"
                      className="page-button"
                      onClick={() => {
                        setPassCasePage((current) => Math.max(1, current - 1));
                      }}
                      disabled={safePassCasePage <= 1}
                    >
                      {"<"}
                    </button>

                    {passCaseButtons.map((button, index) => {
                      if (button === "ellipsis") {
                        return (
                          <span key={`ellipsis-${index}`} className="page-ellipsis">
                            ...
                          </span>
                        );
                      }

                      if (button === "eof") {
                        return (
                          <button
                            key="eof"
                            type="button"
                            className={`page-button ${safePassCasePage === passCasePageCount ? "active" : ""}`}
                            onClick={() => {
                              setPassCasePage(passCasePageCount);
                            }}
                          >
                            EOF
                          </button>
                        );
                      }

                      return (
                        <button
                          key={button}
                          type="button"
                          className={`page-button ${safePassCasePage === button ? "active" : ""}`}
                          onClick={() => {
                            setPassCasePage(button);
                          }}
                        >
                          {button}
                        </button>
                      );
                    })}

                    <button
                      type="button"
                      className="page-button"
                      onClick={() => {
                        setPassCasePage((current) => Math.min(passCasePageCount, current + 1));
                      }}
                      disabled={safePassCasePage >= passCasePageCount}
                    >
                      {">"}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>
      ) : null}

      {selectedPassCase ? (
        <div className="quicklook-backdrop" onClick={() => setSelectedPassCase(null)}>
          <section
            className="quicklook-panel"
            role="dialog"
            aria-modal="true"
            aria-label={`Pass case preview ${selectedPassCase.caseId}`}
            onClick={(event) => {
              event.stopPropagation();
            }}
          >
            <div className="quicklook-head">
              <div>
                <div className="memory-hit-pills">
                  <span className="pill">{selectedPassCase.caseId}</span>
                  <span className={`pill ${statusClass(selectedPassCase.status)}`}>{selectedPassCase.status || "-"}</span>
                  <span className="pill">{selectedPassCase.tier}</span>
                </div>
                <h2>{selectedPassCase.title}</h2>
              </div>
              <button type="button" className="quicklook-close" onClick={() => setSelectedPassCase(null)}>
                Close
              </button>
            </div>

            <div className="quicklook-grid">
              <section className="quicklook-card">
                <h3>Case Summary</h3>
                <dl className="quicklook-meta">
                  <div>
                    <dt>Tier</dt>
                    <dd>{selectedPassCase.tier}</dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>{selectedPassCase.status || "-"}</dd>
                  </div>
                  <div>
                    <dt>Status Reason</dt>
                    <dd>{selectedPassCase.reason}</dd>
                  </div>
                  <div>
                    <dt>Priority</dt>
                    <dd>{selectedPassCase.priority || "-"}</dd>
                  </div>
                  <div>
                    <dt>Step Count</dt>
                    <dd>{fmtNumber(selectedPassCase.stepsExecuted)}</dd>
                  </div>
                  <div>
                    <dt>Evidence Count</dt>
                    <dd>{fmtNumber(selectedPassCase.evidenceRefs.length)}</dd>
                  </div>
                  <div>
                    <dt>Target URL</dt>
                    <dd>{selectedPassCase.targetUrl || "-"}</dd>
                  </div>
                </dl>
              </section>

              <section className="quicklook-card">
                <h3>Steps</h3>
                {selectedPassCaseStepList.length === 0 ? (
                  <div className="empty">No execution or planned steps were recorded for this test case.</div>
                ) : (
                  <ol className="quicklook-list">
                    {selectedPassCaseStepList.map((step, index) => (
                      <li key={`${selectedPassCase.caseId}-step-${index}`}>{step}</li>
                    ))}
                  </ol>
                )}
              </section>

              <section className="quicklook-card">
                <h3>Planning & Memory</h3>
                <dl className="quicklook-meta">
                  <div>
                    <dt>Objective</dt>
                    <dd>{selectedPassCase.objective || "-"}</dd>
                  </div>
                  <div>
                    <dt>Expected Result</dt>
                    <dd>{selectedPassCase.expectedResult || "-"}</dd>
                  </div>
                  <div>
                    <dt>Severity Hint</dt>
                    <dd>{selectedPassCase.severityHint || "-"}</dd>
                  </div>
                  <div>
                    <dt>Memory Hit Count</dt>
                    <dd>{fmtNumber(selectedPassCase.memoryHitCount)}</dd>
                  </div>
                </dl>

                {selectedPassCase.plannedProbeKinds.length > 0 ? (
                  <div className="memory-meta-group">
                    <span>Planned Probes</span>
                    <ul className="tag-list">
                      {selectedPassCase.plannedProbeKinds.map((value) => (
                        <li key={`${selectedPassCase.caseId}-modal-probe-${value}`}>{prettifyProbeKind(value)}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {selectedPassCase.memoryIssueTypes.length > 0 ? (
                  <div className="memory-meta-group">
                    <span>Memory Issue Types</span>
                    <ul className="tag-list">
                      {selectedPassCase.memoryIssueTypes.map((value) => (
                        <li key={`${selectedPassCase.caseId}-modal-memory-issue-${value}`}>{value}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {selectedPassCase.memoryPageRoles.length > 0 ? (
                  <div className="memory-meta-group">
                    <span>Page Roles</span>
                    <ul className="tag-list">
                      {selectedPassCase.memoryPageRoles.map((value) => (
                        <li key={`${selectedPassCase.caseId}-modal-role-${value}`}>{value}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {selectedPassCase.memoryComponentTypes.length > 0 ? (
                  <div className="memory-meta-group">
                    <span>Components</span>
                    <ul className="tag-list">
                      {selectedPassCase.memoryComponentTypes.map((value) => (
                        <li key={`${selectedPassCase.caseId}-modal-component-${value}`}>{value}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {selectedPassCase.memoryInteractionKinds.length > 0 ? (
                  <div className="memory-meta-group">
                    <span>Interactions</span>
                    <ul className="tag-list">
                      {selectedPassCase.memoryInteractionKinds.map((value) => (
                        <li key={`${selectedPassCase.caseId}-modal-interaction-${value}`}>{value}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {selectedPassCase.memoryLayoutSignals.length > 0 ? (
                  <div className="memory-meta-group">
                    <span>Layout Signals</span>
                    <ul className="tag-list">
                      {selectedPassCase.memoryLayoutSignals.map((value) => (
                        <li key={`${selectedPassCase.caseId}-modal-layout-${value}`}>{value}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {selectedPassCase.memoryFrameworkHints.length > 0 ? (
                  <div className="memory-meta-group">
                    <span>Framework</span>
                    <ul className="tag-list">
                      {selectedPassCase.memoryFrameworkHints.map((value) => (
                        <li key={`${selectedPassCase.caseId}-modal-framework-${value}`}>{value}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {selectedPassCase.memoryCardIds.length > 0 ? (
                  <div className="memory-meta-group">
                    <span>Retrieved Cards</span>
                    <ul className="tag-list">
                      {selectedPassCase.memoryCardIds.map((value) => (
                        <li key={`${selectedPassCase.caseId}-modal-memory-card-${value}`}>{value}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </section>

              <section className="quicklook-card evidence-card">
                <h3>Evidences</h3>
                {selectedPassCaseEvidence.length === 0 ? (
                  <div className="empty">No evidence references were recorded for this test case.</div>
                ) : (
                  <div className="quicklook-image-viewer">
                    <ul className="quicklook-list">
                      {selectedPassCaseEvidence.map((evidence, index) => (
                        <li key={`${evidence.label}-${index}`}>
                          {evidence.url ? (
                            <a href={evidence.url} target="_blank" rel="noreferrer">
                              {evidence.label}
                            </a>
                          ) : (
                            <span>{evidence.label}</span>
                          )}
                          <small>{evidence.source}</small>
                        </li>
                      ))}
                    </ul>

                    {selectedPassCaseImages.length > 0 && selectedImageEvidence ? (
                      <>
                        <div className="quicklook-image-toolbar">
                          <div className="quicklook-image-meta">
                            <span>{selectedEvidenceIndex + 1}</span>
                            <span>/</span>
                            <span>{selectedPassCaseImages.length}</span>
                            <span>{selectedImageEvidence.label}</span>
                          </div>
                          <div className="quicklook-image-actions">
                            <button
                              type="button"
                              className="page-button"
                              onClick={() => {
                                setImageZoom((current) => Math.max(0.5, Number((current - 0.1).toFixed(2))));
                              }}
                            >
                              -
                            </button>
                            <button
                              type="button"
                              className="page-button"
                              onClick={() => {
                                setImageZoom(1);
                              }}
                            >
                              100%
                            </button>
                            <button
                              type="button"
                              className="page-button"
                              onClick={() => {
                                setImageZoom((current) => Math.min(3, Number((current + 0.1).toFixed(2))));
                              }}
                            >
                              +
                            </button>
                          </div>
                        </div>

                        <div className="quicklook-image-stage">
                          <img
                            className="quicklook-image"
                            src={selectedImageEvidence.url ?? undefined}
                            alt={selectedImageEvidence.label}
                            style={{ transform: `scale(${imageZoom})` }}
                          />
                        </div>

                        {selectedPassCaseImages.length > 1 ? (
                          <div className="quicklook-thumb-row">
                            {selectedPassCaseImages.map((image, index) => (
                              <button
                                key={`${image.label}-${index}`}
                                type="button"
                                className={`quicklook-thumb ${selectedEvidenceIndex === index ? "active" : ""}`}
                                onClick={() => {
                                  setSelectedEvidenceIndex(index);
                                }}
                              >
                                <img src={image.url ?? undefined} alt={image.label} />
                                <span>{image.label}</span>
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </>
                    ) : null}
                  </div>
                )}
              </section>
            </div>
          </section>
        </div>
      ) : null}

      {selectedProbePreview ? (
        <div className="quicklook-backdrop" onClick={() => setSelectedProbePreview(null)}>
          <section
            className="quicklook-panel"
            role="dialog"
            aria-modal="true"
            aria-label={`Visual probe preview ${selectedProbePreview.probeCase.caseId} ${selectedProbePreview.probe.probeKind}`}
            onClick={(event) => {
              event.stopPropagation();
            }}
          >
            <div className="quicklook-head">
              <div>
                <span className="pill">{selectedProbePreview.probeCase.caseId}</span>
                <h2>
                  {prettifyProbeKind(selectedProbePreview.probe.probeKind)} · {selectedProbePreview.probe.candidateLabel}
                </h2>
              </div>
              <button type="button" className="quicklook-close" onClick={() => setSelectedProbePreview(null)}>
                Close
              </button>
            </div>

            <div className="quicklook-grid">
              <section className="quicklook-card">
                <h3>Probe Summary</h3>
                <dl className="quicklook-meta">
                  <div>
                    <dt>Status</dt>
                    <dd className={statusClass(selectedProbePreview.probe.status)}>{selectedProbePreview.probe.status}</dd>
                  </div>
                  <div>
                    <dt>Reason</dt>
                    <dd>{selectedProbePreview.probe.reason}</dd>
                  </div>
                  <div>
                    <dt>Target Page</dt>
                    <dd>{selectedProbePreview.probeCase.pageUrl}</dd>
                  </div>
                  <div>
                    <dt>Evidence Count</dt>
                    <dd>{fmtNumber(selectedProbePreview.probe.evidenceRefs.length)}</dd>
                  </div>
                </dl>
              </section>

              <section className="quicklook-card">
                <h3>Probe Steps</h3>
                {selectedProbeSteps.length === 0 ? (
                  <div className="empty">No probe execution steps were recorded for this item.</div>
                ) : (
                  <ol className="quicklook-list">
                    {selectedProbeSteps.map((step, index) => (
                      <li key={`${selectedProbePreview.probeCase.caseId}-${selectedProbePreview.probe.probeKind}-step-${index}`}>{step}</li>
                    ))}
                  </ol>
                )}
              </section>

              <section className="quicklook-card evidence-card">
                <h3>Probe Evidences</h3>
                {selectedProbeEvidence.length === 0 ? (
                  <div className="empty">No evidence references were recorded for this probe.</div>
                ) : (
                  <div className="quicklook-image-viewer">
                    <ul className="quicklook-list">
                      {selectedProbeEvidence.map((evidence, index) => (
                        <li key={`${evidence.label}-${evidence.note}-${index}`}>
                          {evidence.url ? (
                            <a href={evidence.url} target="_blank" rel="noreferrer">
                              {evidence.label}
                            </a>
                          ) : (
                            <span>{evidence.label}</span>
                          )}
                          <small>{evidence.note || evidence.source}</small>
                        </li>
                      ))}
                    </ul>

                    {selectedProbeImages.length > 0 && (hasProbeCompareView || selectedProbeImage) ? (
                      <>
                        <div className="quicklook-image-toolbar">
                          <div className="quicklook-image-meta">
                            {hasProbeCompareView ? (
                              <>
                                <span>before / after compare</span>
                                <span>{selectedProbePreview.probe.reason}</span>
                              </>
                            ) : (
                              <>
                                <span>{selectedProbeEvidenceIndex + 1}</span>
                                <span>/</span>
                                <span>{selectedProbeImages.length}</span>
                                <span>{selectedProbeImage?.note || selectedProbeImage?.label}</span>
                              </>
                            )}
                          </div>
                          <div className="quicklook-image-actions">
                            <button
                              type="button"
                              className="page-button"
                              onClick={() => {
                                setProbeImageZoom((current) => Math.max(0.5, Number((current - 0.1).toFixed(2))));
                              }}
                            >
                              -
                            </button>
                            <button
                              type="button"
                              className="page-button"
                              onClick={() => {
                                setProbeImageZoom(1);
                              }}
                            >
                              100%
                            </button>
                            <button
                              type="button"
                              className="page-button"
                              onClick={() => {
                                setProbeImageZoom((current) => Math.min(3, Number((current + 0.1).toFixed(2))));
                              }}
                            >
                              +
                            </button>
                          </div>
                        </div>

                        {hasProbeCompareView && selectedProbeBeforeImage && selectedProbeAfterImage ? (
                          <div className="probe-compare-grid">
                            {[selectedProbeBeforeImage, selectedProbeAfterImage].map((image) => {
                              const imageAnnotations = annotationsForProbeNote(selectedProbePreview, image);
                              return (
                                <section key={`${image.label}-${image.note}`} className="probe-compare-card">
                                  <div className="probe-compare-head">
                                    <strong>{image.note || image.label}</strong>
                                    <span className="pill">{image.pageUrl || selectedProbePreview.probeCase.pageUrl}</span>
                                  </div>
                                  <div className="quicklook-image-stage">
                                    <div className="probe-image-canvas" style={{ transform: `scale(${probeImageZoom})` }}>
                                      <img className="quicklook-image probe-preview-image" src={image.url ?? undefined} alt={image.label} />
                                      {imageAnnotations.map((annotation, index) => {
                                        const left = (annotation.rect.left / annotation.viewport.width) * 100;
                                        const top = (annotation.rect.top / annotation.viewport.height) * 100;
                                        const width = (annotation.rect.width / annotation.viewport.width) * 100;
                                        const height = (annotation.rect.height / annotation.viewport.height) * 100;
                                        return (
                                          <div
                                            key={`${annotation.screenshotNote}-${annotation.kind}-${index}`}
                                            className={`probe-overlay-box probe-overlay-${annotation.kind}`}
                                            style={{
                                              left: `${left}%`,
                                              top: `${top}%`,
                                              width: `${width}%`,
                                              height: `${height}%`,
                                              borderColor: annotation.color,
                                            }}
                                          >
                                            <span style={{ backgroundColor: annotation.color }}>{annotation.label}</span>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  </div>
                                </section>
                              );
                            })}
                          </div>
                        ) : selectedProbeImage ? (
                          <>
                            <div className="quicklook-image-stage">
                              <div className="probe-image-canvas" style={{ transform: `scale(${probeImageZoom})` }}>
                                <img
                                  className="quicklook-image probe-preview-image"
                                  src={selectedProbeImage.url ?? undefined}
                                  alt={selectedProbeImage.label}
                                />
                                {selectedProbeAnnotations.map((annotation, index) => {
                                  const left = (annotation.rect.left / annotation.viewport.width) * 100;
                                  const top = (annotation.rect.top / annotation.viewport.height) * 100;
                                  const width = (annotation.rect.width / annotation.viewport.width) * 100;
                                  const height = (annotation.rect.height / annotation.viewport.height) * 100;
                                  return (
                                    <div
                                      key={`${annotation.screenshotNote}-${annotation.kind}-${index}`}
                                      className={`probe-overlay-box probe-overlay-${annotation.kind}`}
                                      style={{
                                        left: `${left}%`,
                                        top: `${top}%`,
                                        width: `${width}%`,
                                        height: `${height}%`,
                                        borderColor: annotation.color,
                                      }}
                                    >
                                      <span style={{ backgroundColor: annotation.color }}>{annotation.label}</span>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>

                            {selectedProbeImages.length > 1 ? (
                              <div className="quicklook-thumb-row">
                                {selectedProbeImages.map((image, index) => (
                                  <button
                                    key={`${image.label}-${image.note}-${index}`}
                                    type="button"
                                    className={`quicklook-thumb ${selectedProbeEvidenceIndex === index ? "active" : ""}`}
                                    onClick={() => {
                                      setSelectedProbeEvidenceIndex(index);
                                    }}
                                  >
                                    <img src={image.url ?? undefined} alt={image.label} />
                                    <span>{image.note || image.label}</span>
                                  </button>
                                ))}
                              </div>
                            ) : null}
                          </>
                        ) : null}

                      </>
                    ) : null}
                  </div>
                )}
              </section>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
