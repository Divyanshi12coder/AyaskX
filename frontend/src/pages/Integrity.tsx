/**
 * src/pages/Integrity.tsx
 * Integrity monitoring — derived from checkpoint and dataset data.
 * No dedicated backend integrity API endpoint.
 */

import React from 'react';
import { integrityApi, pipelinesApi } from '../api/endpoints';
import type { CheckpointRecord, ExecutionRecord, IntegrityArtifact } from '../types';
import { useApi } from '../hooks/useApi';
import { StatusBadge } from '../components/ui/StatusBadge';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { PageHeader } from '../components/ui/PageHeader';

export default function Integrity() {
  const { data, loading, error, refetch } = useApi(() => pipelinesApi.list());
  const { data: artifacts, loading: artifactsLoading } = useApi(() => integrityApi.artifacts());

  const allCheckpoints: (CheckpointRecord & { dataset_path?: string })[] = (data ?? []).flatMap(
    (ex: ExecutionRecord) =>
      (ex.checkpoints ?? []).map((ckpt) => ({
        ...ckpt,
        dataset_path: ex.dataset_path ?? ex.dataset_id,
      }))
  );

  const validated = allCheckpoints.filter((c) => c.validation_status === 'valid' || c.validation_status === 'passed');
  const failed = allCheckpoints.filter((c) => c.validation_status === 'failed' || c.validation_status === 'invalid');
  const pending = allCheckpoints.filter(
    (c) => !c.validation_status || c.validation_status === 'unknown' || c.validation_status === 'pending'
  );

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Integrity"
        subtitle="Artifact and checkpoint integrity monitoring"
        breadcrumbs={[{ label: 'AyaskX' }, { label: 'Integrity' }]}
      />

      <div className="page-body">
        <div
          style={{
            padding: '8px 12px',
            marginBottom: 16,
            background: 'var(--status-info-dim)',
            border: '1px solid rgba(59,130,246,0.2)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.77rem',
            color: 'var(--status-info)',
          }}
        >
          Artifact checks are verified by the backend against server-managed integrity manifests.
          Checkpoint validation records are shown separately below.
        </div>

        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : (
          <>
            <div className="metric-grid mb-4">
              <div className="metric-card">
                <div className="metric-card-label">Total Checkpoints</div>
                <div className="metric-card-value">{allCheckpoints.length}</div>
              </div>
              <div className="metric-card">
                <div className="metric-card-label">Validated</div>
                <div className="metric-card-value" style={{ color: 'var(--status-success)' }}>
                  {validated.length}
                </div>
              </div>
              <div className="metric-card">
                <div className="metric-card-label">Failed Validation</div>
                <div
                  className="metric-card-value"
                  style={{ color: failed.length > 0 ? 'var(--status-error)' : undefined }}
                >
                  {failed.length}
                </div>
              </div>
              <div className="metric-card">
                <div className="metric-card-label">Pending</div>
                <div className="metric-card-value">{pending.length}</div>
              </div>
            </div>

            <div className="section">
              <div className="section-header">
                <span className="section-title">Model Artifact Verification</span>
              </div>
              <div className="panel" style={{ padding: 0, marginBottom: 20 }}>
                {artifactsLoading ? (
                  <LoadingState inline />
                ) : !(artifacts as IntegrityArtifact[] | undefined)?.length ? (
                  <EmptyState title="No model artifacts" message="Verified artifacts appear after a successful pipeline run." />
                ) : (
                  <table className="data-table">
                    <thead><tr><th>Artifact</th><th>Execution</th><th>Status</th><th>Reason</th></tr></thead>
                    <tbody>
                      {(artifacts as IntegrityArtifact[]).map((artifact) => (
                        <tr key={artifact.artifact_name}>
                          <td className="mono">{artifact.artifact_name}</td>
                          <td className="mono">{artifact.execution_id.slice(0, 14)}â€¦</td>
                          <td><StatusBadge value={artifact.status} /></td>
                          <td>{artifact.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              <div className="section-header">
                <span className="section-title">Checkpoint Integrity Records</span>
              </div>
              <div className="panel" style={{ padding: 0 }}>
                {allCheckpoints.length === 0 ? (
                  <EmptyState
                    title="No checkpoint records"
                    message="Checkpoints appear once pipeline executions complete."
                  />
                ) : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Checkpoint ID</th>
                        <th>Execution</th>
                        <th>Node</th>
                        <th>Created</th>
                        <th>Validation</th>
                        <th>Data Hash</th>
                      </tr>
                    </thead>
                    <tbody>
                      {allCheckpoints.map((c) => (
                        <tr key={c.checkpoint_id}>
                          <td className="mono">{c.checkpoint_id?.slice(0, 16)}…</td>
                          <td className="mono">{c.execution_id?.slice(0, 14)}…</td>
                          <td>{c.node_id}</td>
                          <td className="mono" style={{ fontSize: '0.77rem' }}>
                            {c.created_at ? new Date(c.created_at).toLocaleString() : '—'}
                          </td>
                          <td>
                            <StatusBadge value={c.validation_status ?? 'unknown'} />
                          </td>
                          <td
                            className="mono"
                            style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}
                          >
                            {c.data_hash?.slice(0, 20) ?? '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
