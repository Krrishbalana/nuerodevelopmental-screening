// Mirrors backend/scoring/models.py. snake_case on purpose: sent to the API as-is.

import type { GazeParams, SplitRules } from "./cv/gaze";

export interface Frame {
  t: number;
  face: boolean;
  iris_x?: number;
  iris_y?: number;
  yaw?: number;
  pitch?: number;
  roll?: number;
  face_x?: number;
  face_y?: number;
  face_w?: number;
  blink: number;
  smile: number;
}

export interface AudioSample {
  t: number;
  rms: number;
}

export interface BrightnessSample {
  t: number;
  luma: number;
}

export interface CalibrationPoint {
  x: number;
  y: number;
  phase: "fit" | "validate";
  t_start: number;
  t_end: number;
}

export type Side = "left" | "right";

export interface SplitScreenTrial {
  index: number;
  social_side: Side;
  clip: number;
  t_start: number;
  t_end: number;
}

export interface NameCallTrial {
  index: number;
  t_start: number;
  cue_t: number;
  t_end: number;
}

export interface VoiceCheck {
  quiet_start: number;
  quiet_end: number;
  speak_start: number;
  speak_end: number;
}

export interface SessionUpload {
  child: { dob: string; session_date: string };
  viewport: { width: number; height: number };
  frames: Frame[];
  audio: AudioSample[];
  brightness: BrightnessSample[];
  calibration_points: CalibrationPoint[];
  split_screen_trials: SplitScreenTrial[];
  name_call_trials: NameCallTrial[];
  voice_check: VoiceCheck | null;
  recording_consent: boolean;
  stimulus_set: string;
  client: Record<string, string>;
}

export interface CalibrationSummary {
  passed: boolean;
  quality: "good" | "fair" | "poor";
  fit_points_used: number;
  validation_samples: number;
  mean_abs_err_x: number | null;
  side_accuracy: number | null;
  reason: string | null;
  yaw_gain?: number | null;
  yaw_gain_source?: "fitted" | "bounded" | "default" | null;
  yaw_spread_deg?: number | null;
  model?: GazeParams | null; // only from the live calibration endpoint
  rules?: SplitRules;
}

export type Outcome = "refer" | "hearing_check" | "incomplete" | "no_signs";
export type MetricStatus = "flagged" | "not_flagged" | "insufficient";

export interface MetricResult {
  key: string;
  label: string;
  status: MetricStatus;
  confidence: "high" | "medium" | "low" | null;
  value: number | null;
  unit: string;
  summary: string;
  reasons: string[];
  trials: Record<string, unknown>[];
  thresholds: Record<string, unknown>;
  reference: string;
  details: Record<string, unknown>;
}

export interface WindowQuality {
  frames: number;
  face_ratio: number;
  median_luma: number | null;
  median_face_w: number | null;
  flags: string[];
}

export interface Source {
  key: string;
  citation: string;
  url: string;
}

export interface Finding {
  key: string;
  title: string;
  status: MetricStatus | null; // null for Tier B (reported, never flagged)
  confidence: "high" | "medium" | "low" | null;
  measured: string;
  meaning: string | null;
  tier: "A" | "B";
  used_in_likelihood?: boolean;
  age_note?: string | null;
  sources: Source[];
}

export interface Likelihood {
  condition: string;
  available: boolean;
  prior: number;
  prior_note: string;
  prior_sources: Source[];
  posterior: number | null;
  per_100?: number;
  times_population?: number;
  evidence_used: { key: string; result: MetricStatus; lr: number; derivation: string; sources: Source[] }[];
  evidence_excluded: { key: string; reason: string }[];
  assumption: string;
}

export interface ProfileArea {
  key: string;
  label: string;
  tier: "A" | "B" | null;
  value: number | null; // share of the session showing the autism-linked pattern, 0..1
  status: "flagged" | "not_flagged" | "reported" | "insufficient" | "not_assessed";
  measured: string;
  cutoff: number | null;
  cutoff_label?: string;
  markers: { value: number; label: string }[];
  sources: Source[];
}

export interface Recommendation {
  action: string;
  why: string;
  sources: Source[];
}

export interface Report {
  parent: {
    outcome: Outcome;
    title: string;
    message: string;
    findings: { title: string; status: MetricStatus | null; text: string }[];
    profile: ProfileArea[];
    likelihood: string | null;
    next_steps: string[];
    not_checked: string[];
    tips: string[];
    note: string;
  };
  clinician: {
    outcome: Outcome;
    outcome_rule: string;
    findings: Finding[];
    profile: ProfileArea[];
    likelihood: Likelihood;
    recommendations: Recommendation[];
    not_assessed: { area: string; detail: string; how: string }[];
    age_months: number;
    scoring_version: string;
    stimulus_set: string;
    thresholds_provisional: boolean;
    calibration: CalibrationSummary;
    quality: Record<string, WindowQuality>;
    metrics: MetricResult[];
    viewport: { width: number; height: number };
    frame_count: number;
    median_frame_interval_ms: number;
  };
}

// --- Saathi parent questionnaire (backend/app/questionnaire.py) ---

export type AnswerKey = "y" | "py" | "dk" | "pn" | "n";

export interface Intake {
  sex: "boy" | "girl" | "na";
  born: "term" | "32_36" | "lt32";
  familyFactors: string[];
}

export interface QuestionStep {
  type: "question" | "urgent" | "pattern" | "done";
  number: number | null;
  question: { id: string; domain: string; type: string; question: string; typical: string; is_urgent: boolean } | null;
  reason_kind: string | null;
  reason_conditions: string[];
  urgent_question_ids: string[];
  pattern_condition: string | null;
  pattern_probability: number | null;
}

export interface ObservationApplied {
  id: string;
  label: string | null;
  outcome: string;
  confidence: number;
  terms: { condition: string; lr: number; delta: number; source: string; ref: string }[];
}

export interface QuestionnaireMeta {
  dataset_version: string;
  dataset_hash: string;
  family_factors: { factor: string; label: string }[];
  domains: { key: string; name: string }[];
  conditions: { key: string; name: string; short_name: string }[];
}

export interface QuestionnaireResults {
  action: "urgent" | "refer" | "watch" | "on_track";
  title: string;
  steps: string[];
  hearing_test: boolean;
  recheck: string;
  conditions: {
    key: string;
    probability: number;
    band: "strong" | "likely" | "possible" | "unlikely";
    eligibility: string;
    evidence: { question_id: string; delta: number }[];
  }[];
  sharpen: { question_id: string; text?: string }[];
  questions_asked: number;
}

export interface SessionQuestionnaire {
  questionnaire_id: string;
  results: QuestionnaireResults | null;
  observations: ObservationApplied[];
  answers: { question_id: string; key: AnswerKey; answered_at_step: number }[];
}

// --- Adaptive report (backend/app/full_report.py) ---

export interface WheelSlice {
  key: string;
  label: string;
  domains: string[];
  value: number | null; // share of checked signs reported/seen, 0..1
  checked: number;
  signs: string[];
  status: "concern" | "some" | "clear" | "not_assessed";
}

export interface EvidenceLine {
  text: string;
  source: "camera" | "parent";
  delta: number;
  id: string;
}

export interface ConditionSection {
  key: string;
  name: string;
  short_name: string;
  group: string;
  band: "strong" | "likely" | "possible" | "unlikely";
  probability: number;
  eligibility: string;
  about: string;
  clinical_note: string;
  dx_age: string;
  refer: string;
  for: EvidenceLine[];
  against: EvidenceLine[];
}

/** How many DSM-5-TR criteria in a group show signs; social needs all 3 (A1-A3), repetitive 2 of 4 (B1-B4). */
export interface CriterionCount {
  with_signs: number;
  checked: number;
  total: number;
  dsm_needs: number;
}

export interface AutismWheel {
  slices: WheelSlice[];
  social: CriterionCount;
  repetitive: CriterionCount;
}

export interface FullReport {
  has_questionnaire: boolean;
  questionnaire_id: string | null;
  questions_asked: number;
  age_months: number;
  action: "urgent" | "refer" | "watch" | "on_track";
  title: string;
  message: string;
  steps: string[];
  hearing_test: boolean;
  recheck: string;
  red_flags: string[];
  wheel: WheelSlice[];
  autism_wheel: AutismWheel;
  conditions: ConditionSection[];
  all_conditions: { key: string; name: string; probability: number; prior: number; eligibility: string }[];
  observations: ObservationApplied[];
  answers: { question_id: string; question: string; clinical_name: string; domain: string; answer: string }[];
  provenance: { dataset_version: string; model_version: string; dataset_hash: string; note: string };
  camera: Report;
}
