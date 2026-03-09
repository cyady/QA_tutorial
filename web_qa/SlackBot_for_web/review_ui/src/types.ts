export type RunStatus = "pass" | "fail" | "needs_review" | "error" | "running" | "completed";

export type RunSummary = {
  run_id: string;
  run_type: string;
  status: RunStatus;
  agent: string;
  mode_key: string;
  mode_label: string;
  url: string;
  started_at: string;
  completed_at: string;
  token_total: number;
  finding_count: number;
  image_count: number;
  has_error: boolean;
  has_qa_report: boolean;
  has_regression_diff: boolean;
  has_batch_report: boolean;
  status_reason: string;
  visual_probe_direction: string;
  visual_probe_fail_delta: number;
  visual_probe_review_delta: number;
  mtime: string;
};

export type RunsResponse = {
  artifact_root: string;
  generated_at: string;
  summary: {
    run_count: number;
    status_counts: Record<string, number>;
    token_total_sum: number;
    finding_total_sum: number;
  };
  runs: RunSummary[];
};

export type PipelineStage = {
  stage: string;
  artifact: string;
  ready: boolean;
  url: string;
};

export type ArtifactFile = {
  name: string;
  size: number;
  modified_at: string;
  is_image: boolean;
  is_json: boolean;
  url: string;
};

export type RunDetail = {
  summary: RunSummary;
  pipeline_trace: PipelineStage[];
  artifacts: Record<string, unknown>;
  text_previews: Record<string, string>;
  files: ArtifactFile[];
  generated_at: string;
};

export type QaFinding = {
  id?: string;
  severity?: string;
  page_url?: string;
  location?: string;
  type?: string;
  observation?: string;
  why_it_matters?: string;
  next_check?: string;
  screenshot_refs?: string[];
  evidence_refs?: string[];
};

export type AnnotationEvent = {
  id: string;
  kind: "add" | "update" | "delete" | "clear" | "copy" | "submit";
  at: string;
  comment?: string;
  element?: string;
  path?: string;
  output?: string;
  count?: number;
};
