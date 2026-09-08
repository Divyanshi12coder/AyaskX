/**
 * src/api/endpoints.ts
 * All typed API call functions.
 * Never duplicate these outside this file.
 */

import type { AxiosResponse } from 'axios';
import { apiClient } from './client';
import type {
  ApiResponse,
  AuditEvent,
  CheckpointRecord,
  DatasetProfile,
  DatasetRecord,
  ExecutionRecord,
  FaultInfo,
  FeatureRoles,
  HealthStatus,
  LeakageReport,
  LocalizationInfo,
  ModelCandidate,
  PredictResult,
  ReadyStatus,
  RecoveryDecision,
  RecoveryPlan,
  RecoveryResult,
  RootCauseInfo,
  SelfHealingReport,
} from '../types';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function data<T>(res: AxiosResponse<ApiResponse<T>>): T {
  return res.data.data;
}

// ─── Health ──────────────────────────────────────────────────────────────────

export const healthApi = {
  get: () => apiClient.get<HealthStatus>('/health').then((r) => r.data),
  ready: () => apiClient.get<ReadyStatus>('/ready').then((r) => r.data),
};

// ─── Datasets ────────────────────────────────────────────────────────────────

export const datasetsApi = {
  list: () =>
    apiClient
      .get<ApiResponse<DatasetRecord[]>>('/v1/datasets')
      .then(data),

  get: (datasetId: string) =>
    apiClient
      .get<ApiResponse<DatasetRecord>>(`/v1/datasets/${datasetId}`)
      .then(data),

  upload: (file: File, onProgress?: (pct: number) => void) => {
    const fd = new FormData();
    fd.append('file', file);
    return apiClient
      .post<ApiResponse<DatasetRecord>>('/v1/datasets/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (evt) => {
          if (onProgress && evt.total) {
            onProgress(Math.round((evt.loaded / evt.total) * 100));
          }
        },
      })
      .then(data);
  },

  profile: (datasetId: string) =>
    apiClient
      .get<ApiResponse<DatasetProfile>>(`/v1/datasets/${datasetId}/profile`)
      .then(data),

  featureRoles: (datasetId: string) =>
    apiClient
      .get<ApiResponse<FeatureRoles>>(`/v1/datasets/${datasetId}/feature-roles`)
      .then(data),

  leakage: (datasetId: string) =>
    apiClient
      .get<ApiResponse<LeakageReport>>(`/v1/datasets/${datasetId}/leakage`)
      .then(data),
};

// ─── Pipelines ───────────────────────────────────────────────────────────────

export interface RunRequest {
  dataset_id: string;
  target?: string;
  task_type?: string;
  max_candidates?: number;
}

export const pipelinesApi = {
  run: (req: RunRequest) =>
    apiClient
      .post<ApiResponse<{ execution_id: string; status: string }>>('/v1/pipelines/run', req)
      .then(data),

  list: () =>
    apiClient
      .get<ApiResponse<ExecutionRecord[]>>('/v1/pipelines')
      .then(data),

  get: (executionId: string) =>
    apiClient
      .get<ApiResponse<ExecutionRecord>>(`/v1/pipelines/${executionId}`)
      .then(data),

  status: (executionId: string) =>
    apiClient
      .get<ApiResponse<{ status: string }>>(`/v1/pipelines/${executionId}/status`)
      .then(data),

  nodes: (executionId: string) =>
    apiClient
      .get<ApiResponse<unknown[]>>(`/v1/pipelines/${executionId}/nodes`)
      .then(data),

  node: (executionId: string, nodeId: string) =>
    apiClient
      .get<ApiResponse<unknown>>(`/v1/pipelines/${executionId}/nodes/${nodeId}`)
      .then(data),

  checkpoints: (executionId: string) =>
    apiClient
      .get<ApiResponse<CheckpointRecord[]>>(`/v1/pipelines/${executionId}/checkpoints`)
      .then(data),

  checkpoint: (executionId: string, checkpointId: string) =>
    apiClient
      .get<ApiResponse<CheckpointRecord>>(`/v1/pipelines/${executionId}/checkpoints/${checkpointId}`)
      .then(data),
};

// ─── Models ──────────────────────────────────────────────────────────────────

export const modelsApi = {
  candidates: (executionId: string) =>
    apiClient
      .get<ApiResponse<ModelCandidate[]>>(`/v1/pipelines/${executionId}/candidates`)
      .then(data),

  best: (executionId: string) =>
    apiClient
      .get<ApiResponse<{ best_model?: string; best_score?: number; training_result?: unknown }>>(
        `/v1/pipelines/${executionId}/model`
      )
      .then(data),

  metrics: (executionId: string) =>
    apiClient
      .get<ApiResponse<{ metrics?: unknown; best_score?: number }>>(
        `/v1/pipelines/${executionId}/model/metrics`
      )
      .then(data),

  validationStrategy: (executionId: string) =>
    apiClient
      .get<ApiResponse<{ validation_strategy?: string; detail?: unknown }>>(
        `/v1/pipelines/${executionId}/model/validation-strategy`
      )
      .then(data),
};

// ─── Inference ───────────────────────────────────────────────────────────────

export const inferenceApi = {
  predict: (executionId: string, rows: Record<string, unknown>[]) =>
    apiClient
      .post<ApiResponse<PredictResult>>(`/v1/pipelines/${executionId}/predict`, { rows })
      .then(data),
};

// ─── Recovery / Self-Healing ─────────────────────────────────────────────────

export const recoveryApi = {
  fault: (executionId: string) =>
    apiClient
      .get<ApiResponse<FaultInfo>>(`/v1/pipelines/${executionId}/fault`)
      .then(data),

  localization: (executionId: string) =>
    apiClient
      .get<ApiResponse<LocalizationInfo>>(`/v1/pipelines/${executionId}/fault/localization`)
      .then(data),

  rootCause: (executionId: string) =>
    apiClient
      .get<ApiResponse<RootCauseInfo>>(`/v1/pipelines/${executionId}/fault/root-cause`)
      .then(data),

  decision: (executionId: string) =>
    apiClient
      .get<ApiResponse<RecoveryDecision>>(`/v1/pipelines/${executionId}/recovery/decision`)
      .then(data),

  plan: (executionId: string) =>
    apiClient
      .get<ApiResponse<RecoveryPlan>>(`/v1/pipelines/${executionId}/recovery/plan`)
      .then(data),

  result: (executionId: string) =>
    apiClient
      .get<ApiResponse<RecoveryResult>>(`/v1/pipelines/${executionId}/recovery/result`)
      .then(data),

  selfHealing: (executionId: string) =>
    apiClient
      .get<ApiResponse<SelfHealingReport>>(`/v1/pipelines/${executionId}/self-healing`)
      .then(data),

  trigger: (executionId: string, autoApproveLowRisk = false) =>
    apiClient
      .post<ApiResponse<unknown>>(`/v1/pipelines/${executionId}/self-healing/trigger`, {
        auto_approve_low_risk: autoApproveLowRisk,
      })
      .then(data),
};

// ─── Audit ────────────────────────────────────────────────────────────────────

export const auditApi = {
  events: (executionId?: string) => {
    const params = executionId ? { execution_id: executionId } : {};
    return apiClient
      .get<ApiResponse<AuditEvent[]>>('/v1/audit/events', { params })
      .then(data);
  },

  event: (eventId: string) =>
    apiClient
      .get<ApiResponse<AuditEvent>>(`/v1/audit/events/${eventId}`)
      .then(data),

  executionAudit: (executionId: string) =>
    apiClient
      .get<ApiResponse<AuditEvent[]>>(`/v1/pipelines/${executionId}/audit`)
      .then(data),
};
