/**
 * src/types/index.ts
 * All TypeScript types for the AyaskX API layer.
 */

// ─── API Envelope ────────────────────────────────────────────────────────────

export interface ApiResponse<T = unknown> {
  status: 'success' | 'error';
  execution_id?: string | null;
  data: T;
  errors: string[];
  timestamp: string;
}

// ─── Health ──────────────────────────────────────────────────────────────────

export interface HealthStatus {
  status: string;
  service: string;
  started_at: string;
  timestamp: string;
}

export interface ReadyStatus {
  status: string;
  database?: string;
  timestamp: string;
}

// ─── Datasets ────────────────────────────────────────────────────────────────

export interface DatasetRecord {
  dataset_id: string;
  original_filename: string;
  safe_filename: string;
  file_path: string;
  file_size_bytes: number;
  uploaded_at: string;
  content_type?: string;
}

export interface ColumnProfile {
  name: string;
  dtype: string;
  missing_count?: number;
  missing_pct?: number;
  unique_count?: number;
  mean?: number;
  std?: number;
  min?: number;
  max?: number;
  sample_values?: unknown[];
}

export interface DatasetProfile {
  dataset_id?: string;
  n_rows?: number;
  n_cols?: number;
  columns?: ColumnProfile[];
  missing_total?: number;
  duplicate_rows?: number;
  task_type?: string;
  target?: string;
  [key: string]: unknown;
}

export interface FeatureRoles {
  target?: string;
  features?: string[];
  id_columns?: string[];
  dropped_columns?: string[];
  roles?: Record<string, string>;
  [key: string]: unknown;
}

export interface LeakageReport {
  dataset_id?: string;
  leakage_risk?: 'none' | 'low' | 'medium' | 'high';
  leaky_columns?: string[];
  details?: string;
  [key: string]: unknown;
}

// ─── Pipeline Executions ─────────────────────────────────────────────────────

export type ExecutionStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'recovered';

export type NodeStatus =
  | 'queued'
  | 'running'
  | 'success'
  | 'failed'
  | 'skipped'
  | 'recovered';

export interface PipelineNode {
  node_id: string;
  status: NodeStatus;
  started_at?: string;
  finished_at?: string;
  error_type?: string | null;
  error_message?: string | null;
  checkpoint_id?: string | null;
  output_metadata?: Record<string, unknown>;
}

export interface CheckpointRecord {
  checkpoint_id: string;
  execution_id: string;
  node_id: string;
  created_at: string;
  validation_status?: string;
  artifact_path?: string;
  data_hash?: string;
}

export interface ModelCandidate {
  model_name?: string;
  model_type?: string;
  rank?: number;
  score?: number;
  cv_score?: number;
  train_time_seconds?: number;
  status?: string;
  [key: string]: unknown;
}

export interface ExecutionRecord {
  execution_id: string;
  dataset_id: string;
  dataset_path: string;
  status: ExecutionStatus;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  success?: boolean | null;
  message?: string;
  warnings?: string[];
  task_type?: string;
  target?: string;
  best_model?: string;
  best_score?: number;
  validation_strategy?: string;
  candidates?: ModelCandidate[];
  nodes?: PipelineNode[];
  checkpoints?: CheckpointRecord[];
  summary?: Record<string, unknown>;
  characterization?: Record<string, unknown>;
  feature_roles?: Record<string, unknown>;
  leakage_report?: Record<string, unknown>;
  preprocessing_plan?: Record<string, unknown>;
  candidate_report?: Record<string, unknown>;
  training_result?: Record<string, unknown>;
  validation_strategy_detail?: Record<string, unknown>;
}

// ─── Recovery / Self-Healing ──────────────────────────────────────────────────

export interface FaultInfo {
  detected?: boolean;
  fault_type?: string;
  failed_node?: string;
  error_message?: string;
  error_type?: string;
  [key: string]: unknown;
}

export interface LocalizationInfo {
  observed_node?: string;
  fault_boundary?: string;
  upstream_nodes?: string[];
  downstream_impact?: string[];
  [key: string]: unknown;
}

export interface RootCauseInfo {
  root_cause?: string;
  explanation?: string;
  contributing_factors?: string[];
  [key: string]: unknown;
}

export interface RecoveryDecision {
  decision?: string;
  strategy?: string;
  checkpoint_id?: string;
  last_good_node?: string;
  risk_level?: string;
  [key: string]: unknown;
}

export interface RecoveryPlan {
  steps?: string[];
  estimated_cost?: string;
  [key: string]: unknown;
}

export interface RecoveryResult {
  success?: boolean;
  validation_status?: 'passed' | 'failed' | 'pending';
  recovered_at?: string;
  message?: string;
  [key: string]: unknown;
}

export interface SelfHealingReport {
  execution_id?: string;
  fault?: FaultInfo;
  localization?: LocalizationInfo;
  root_cause?: RootCauseInfo;
  decision?: RecoveryDecision;
  plan?: RecoveryPlan;
  result?: RecoveryResult;
  [key: string]: unknown;
}

// ─── Audit ────────────────────────────────────────────────────────────────────

export interface AuditEvent {
  event_id?: string;
  execution_id?: string;
  timestamp?: string;
  actor?: string;
  action?: string;
  resource?: string;
  resource_id?: string;
  result?: string;
  severity?: 'info' | 'warning' | 'error' | 'critical';
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

// ─── Inference ────────────────────────────────────────────────────────────────

export interface PredictResult {
  predictions: unknown[];
  request_id: string;
  model_name: string;
  n_samples: number;
}

// ─── System Status (derived, not from single endpoint) ───────────────────────

export interface SystemStatus {
  api: { status: string; version: string };
  database: { status: string; dialect: string | null };
  storage: {
    uploads_ready: boolean;
    artifacts_ready: boolean;
    checkpoints_ready: boolean;
    execution_store_ready: boolean;
  };
  counts: { datasets: number; executions: number };
  runtime: { execution_mode: string; authentication: string };
  timestamp: string;
}

export interface IntegrityArtifact {
  artifact_name: string;
  artifact_path: string;
  execution_id: string;
  status: string;
  valid: boolean;
  reason: string;
  expected_checksum?: string | null;
  actual_checksum?: string | null;
}

export interface ObservabilitySummary {
  total_executions: number;
  status_counts: Record<string, number>;
  latest_execution_at: string | null;
  generated_at: string;
}
