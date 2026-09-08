/**
 * src/pages/Observability.tsx
 * Operational observability — derived from execution data.
 * No dedicated backend API endpoint; visualizes from pipeline execution records.
 */

import React from 'react';
import { pipelinesApi } from '../api/endpoints';
import type { ExecutionRecord } from '../types';
import { useApi } from '../hooks/useApi';
import { StatusBadge } from '../components/ui/StatusBadge';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { PageHeader } from '../components/ui/PageHeader';

function fmtDuration(start?: string | null, end?: string | null): string {
  if (!start || !end) return '—';
  const diff = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 1000);
  if (diff < 60) return `${diff}s`;
  return `${Math.floor(diff / 60)}m ${diff % 60}s`;
}

export default function Observability() {
  const { data, loading, error, refetch } = useApi(() => pipelinesApi.list());

  const executions: ExecutionRecord[] = [...(data ?? [])].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  const total = executions.length;
  const succeeded = executions.filter((e) => e.status === 'succeeded').length;
  const failed = executions.filter((e) => e.status === 'failed').length;
  const running = executions.filter((e) => e.status === 'running').length;
  const successRate = total > 0 ? ((succeeded / total) * 100).toFixed(1) : '—';

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Observability"
        subtitle="Operational metrics derived from pipeline execution records"
        breadcrumbs={[{ label: 'AyaskX' }, { label: 'Observability' }]}
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
          Note: No dedicated observability API endpoint exists in the current backend.
          Metrics below are computed from pipeline execution records.
        </div>

        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : (
          <>
            <div className="metric-grid mb-4">
              <div className="metric-card">
                <div className="metric-card-label">Total Executions</div>
                <div className="metric-card-value">{total}</div>
              </div>
              <div className="metric-card">
                <div className="metric-card-label">Success Rate</div>
                <div
                  className="metric-card-value"
                  style={{ color: 'var(--status-success)' }}
                >
                  {successRate}%
                </div>
                <div className="metric-card-sub">from actual data</div>
              </div>
              <div className="metric-card">
                <div className="metric-card-label">Failed</div>
                <div
                  className="metric-card-value"
                  style={{ color: failed > 0 ? 'var(--status-error)' : undefined }}
                >
                  {failed}
                </div>
              </div>
              <div className="metric-card">
                <div className="metric-card-label">Currently Running</div>
                <div
                  className="metric-card-value"
                  style={{ color: running > 0 ? 'var(--status-info)' : undefined }}
                >
                  {running}
                </div>
              </div>
            </div>

            {/* Execution timeline table */}
            <div className="section">
              <div className="section-header">
                <span className="section-title">Execution Timeline</span>
              </div>
              <div className="panel" style={{ padding: 0 }}>
                {executions.length === 0 ? (
                  <EmptyState title="No executions" />
                ) : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Execution ID</th>
                        <th>Dataset</th>
                        <th>Task</th>
                        <th>Started</th>
                        <th>Duration</th>
                        <th>Status</th>
                        <th>Model</th>
                        <th>Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {executions.map((ex) => (
                        <tr key={ex.execution_id}>
                          <td className="mono">{ex.execution_id.slice(0, 14)}…</td>
                          <td>{ex.dataset_path ?? ex.dataset_id}</td>
                          <td>{ex.task_type ?? '—'}</td>
                          <td className="mono" style={{ fontSize: '0.77rem' }}>
                            {ex.started_at
                              ? new Date(ex.started_at).toLocaleString()
                              : '—'}
                          </td>
                          <td className="mono">
                            {fmtDuration(ex.started_at, ex.completed_at)}
                          </td>
                          <td>
                            <StatusBadge value={ex.status} />
                          </td>
                          <td>{ex.best_model ?? '—'}</td>
                          <td className="mono">
                            {ex.best_score != null
                              ? ex.best_score.toFixed(4)
                              : '—'}
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
