/**
 * src/pages/Models.tsx
 * Model Lab — compare candidates, view metrics, validation strategy.
 * All data sourced from real execution records.
 */

import React, { useState } from 'react';
import { FlaskConical } from 'lucide-react';
import { pipelinesApi, modelsApi } from '../api/endpoints';
import type { ExecutionRecord, ModelCandidate } from '../types';
import { useApi } from '../hooks/useApi';
import { StatusBadge } from '../components/ui/StatusBadge';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { PageHeader } from '../components/ui/PageHeader';

function CandidatesTable({ candidates }: { candidates: ModelCandidate[] }) {
  if (!candidates.length)
    return <EmptyState title="No candidates" message="No model candidates recorded for this execution." />;

  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="data-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Model</th>
            <th>Type</th>
            <th>CV Score</th>
            <th>Score</th>
            <th>Train Time</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {candidates
            .slice()
            .sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99))
            .map((c, i) => (
              <tr key={i}>
                <td className="mono" style={{ color: i === 0 ? 'var(--accent)' : undefined }}>
                  #{(c.rank ?? i + 1)}
                </td>
                <td
                  className="text-primary"
                  style={{ fontWeight: i === 0 ? 600 : undefined }}
                >
                  {c.model_name ?? c.model_type ?? '—'}
                </td>
                <td>{c.model_type ?? '—'}</td>
                <td className="mono">
                  {c.cv_score != null ? Number(c.cv_score).toFixed(4) : '—'}
                </td>
                <td className="mono">
                  {c.score != null ? Number(c.score).toFixed(4) : '—'}
                </td>
                <td className="mono">
                  {c.train_time_seconds != null
                    ? `${Number(c.train_time_seconds).toFixed(1)}s`
                    : '—'}
                </td>
                <td>
                  <StatusBadge value={c.status ?? 'unknown'} />
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}

function ExecutionModelDetail({ executionId }: { executionId: string }) {
  const { data: modelData, loading } = useApi(
    () => modelsApi.best(executionId),
    [executionId]
  );
  const { data: candidates, loading: cLoading } = useApi(
    () => modelsApi.candidates(executionId),
    [executionId]
  );
  const { data: strategy, loading: sLoading } = useApi(
    () => modelsApi.validationStrategy(executionId),
    [executionId]
  );

  if (loading || cLoading || sLoading) return <LoadingState />;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Best model summary */}
      <div className="panel" style={{ padding: 16 }}>
        <h4 style={{ marginBottom: 12 }}>Best Model</h4>
        <div className="kv-grid">
          <div className="kv-key">Model</div>
          <div className="kv-val">
            {modelData?.best_model ? (
              <StatusBadge value={modelData.best_model} variant="accent" dot={false} />
            ) : (
              '—'
            )}
          </div>
          <div className="kv-key">Best Score</div>
          <div className="kv-val mono">
            {modelData?.best_score != null ? Number(modelData.best_score).toFixed(6) : '—'}
          </div>
          <div className="kv-key">Validation</div>
          <div className="kv-val">{strategy?.validation_strategy ?? '—'}</div>
        </div>

        {/* SHAP note */}
        <div
          style={{
            marginTop: 12,
            padding: '8px 12px',
            background: 'var(--bg-elevated)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.77rem',
            color: 'var(--text-muted)',
          }}
        >
          Feature importance (SHAP): Not available for this execution.
        </div>
      </div>

      {/* Candidates */}
      <div className="panel" style={{ padding: 0 }}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
          <span className="section-title">Model Candidates</span>
        </div>
        <CandidatesTable candidates={candidates ?? []} />
      </div>

      {/* Validation detail */}
      {!!strategy?.detail && (
        <div className="panel" style={{ padding: 16 }}>
          <h4 style={{ marginBottom: 12 }}>Validation Strategy Detail</h4>
          <div className="code-block">
            {JSON.stringify(strategy!.detail, null, 2)}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Models() {
  const [selectedExecId, setSelectedExecId] = useState<string | null>(null);

  const { data, loading, error, refetch } = useApi(() => pipelinesApi.list());

  const executions: ExecutionRecord[] = (data ?? [])
    .filter((e) => e.status === 'succeeded' || e.best_model)
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Model Lab"
        subtitle="Compare model candidates across pipeline executions"
        breadcrumbs={[{ label: 'AyaskX' }, { label: 'Models' }]}
      />

      <div style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>
        {/* Execution list */}
        <div
          style={{
            width: 280,
            borderRight: '1px solid var(--border)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            flexShrink: 0,
          }}
        >
          <div
            style={{
              padding: '10px 14px',
              borderBottom: '1px solid var(--border)',
              fontSize: '0.77rem',
              color: 'var(--text-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              fontWeight: 600,
            }}
          >
            Executions with Models
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {loading ? (
              <LoadingState />
            ) : error ? (
              <ErrorState message={error} onRetry={refetch} />
            ) : executions.length === 0 ? (
              <EmptyState
                title="No model results"
                message="Complete a pipeline run to see model results."
              />
            ) : (
              executions.map((ex) => (
                <div
                  key={ex.execution_id}
                  onClick={() => setSelectedExecId(ex.execution_id)}
                  style={{
                    padding: '10px 14px',
                    borderBottom: '1px solid var(--border-subtle)',
                    cursor: 'pointer',
                    background:
                      selectedExecId === ex.execution_id
                        ? 'var(--accent-dim)'
                        : undefined,
                    borderLeft:
                      selectedExecId === ex.execution_id
                        ? '2px solid var(--accent)'
                        : '2px solid transparent',
                  }}
                >
                  <div
                    style={{
                      fontSize: '0.8rem',
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--text-secondary)',
                      marginBottom: 4,
                    }}
                  >
                    {ex.execution_id.slice(0, 14)}…
                  </div>
                  <div style={{ fontSize: '0.77rem', color: 'var(--text-muted)' }}>
                    {ex.best_model ?? '—'}
                  </div>
                  <div
                    style={{
                      fontSize: '0.72rem',
                      color: 'var(--accent)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {ex.best_score != null
                      ? `score: ${ex.best_score.toFixed(4)}`
                      : ''}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Detail area */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          {selectedExecId ? (
            <ExecutionModelDetail executionId={selectedExecId} />
          ) : (
            <EmptyState
              title="Select an execution"
              message="Click an execution on the left to view model candidates and metrics."
              icon={<FlaskConical size={40} />}
            />
          )}
        </div>
      </div>
    </div>
  );
}
