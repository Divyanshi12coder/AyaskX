/**
 * src/pages/pipelines/PipelineList.tsx
 * List of all pipeline executions with filtering and status.
 */

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { pipelinesApi } from '../../api/endpoints';
import type { ExecutionRecord } from '../../types';
import { useApi } from '../../hooks/useApi';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { PageHeader } from '../../components/ui/PageHeader';

function fmtDuration(start?: string | null, end?: string | null): string {
  if (!start) return '—';
  const s = new Date(start).getTime();
  const e = end ? new Date(end).getTime() : Date.now();
  const diff = Math.round((e - s) / 1000);
  if (diff < 60) return `${diff}s`;
  return `${Math.floor(diff / 60)}m ${diff % 60}s`;
}

const STATUS_FILTERS = ['all', 'queued', 'running', 'succeeded', 'failed', 'recovered'];

export default function PipelineList() {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState('all');
  const [search, setSearch] = useState('');
  const { data, loading, error, refetch } = useApi(() => pipelinesApi.list());

  const executions: ExecutionRecord[] = [...(data ?? [])].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  const filtered = executions.filter((e) => {
    if (statusFilter !== 'all' && e.status !== statusFilter) return false;
    if (
      search &&
      !e.execution_id.includes(search) &&
      !(e.dataset_path ?? '').toLowerCase().includes(search.toLowerCase()) &&
      !(e.task_type ?? '').toLowerCase().includes(search.toLowerCase())
    )
      return false;
    return true;
  });

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Pipeline Executions"
        subtitle={`${executions.length} total executions`}
        breadcrumbs={[{ label: 'AyaskX' }, { label: 'Pipelines' }]}
        actions={
          <button className="btn btn-ghost btn-sm" onClick={refetch}>
            <RefreshCw size={13} />
            Refresh
          </button>
        }
      />

      {/* Filters */}
      <div className="filter-bar">
        <div style={{ display: 'flex', gap: 4 }}>
          {STATUS_FILTERS.map((f) => (
            <button
              key={f}
              className={`btn btn-sm ${statusFilter === f ? 'btn-secondary' : 'btn-ghost'}`}
              onClick={() => setStatusFilter(f)}
              style={{ textTransform: 'capitalize' }}
            >
              {f}
            </button>
          ))}
        </div>
        <input
          className="input"
          style={{ maxWidth: 240 }}
          placeholder="Search by ID, dataset, task…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <span style={{ marginLeft: 'auto', fontSize: '0.77rem', color: 'var(--text-muted)' }}>
          {filtered.length} result{filtered.length !== 1 ? 's' : ''}
        </span>
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No pipeline executions"
            message="Start a pipeline from the Datasets page."
          />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Execution ID</th>
                <th>Dataset</th>
                <th>Task</th>
                <th>Target</th>
                <th>Started</th>
                <th>Duration</th>
                <th>Status</th>
                <th>Best Model</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((ex) => (
                <tr key={ex.execution_id} onClick={() => navigate(`/pipelines/${ex.execution_id}`)}>
                  <td className="mono">{ex.execution_id.slice(0, 16)}…</td>
                  <td>{ex.dataset_path ?? ex.dataset_id}</td>
                  <td>{ex.task_type ?? '—'}</td>
                  <td>{ex.target ?? '—'}</td>
                  <td className="mono" style={{ fontSize: '0.77rem' }}>
                    {ex.started_at
                      ? new Date(ex.started_at).toLocaleString()
                      : new Date(ex.created_at).toLocaleString()}
                  </td>
                  <td className="mono">
                    {fmtDuration(ex.started_at, ex.completed_at)}
                  </td>
                  <td>
                    <StatusBadge value={ex.status} />
                  </td>
                  <td>{ex.best_model ?? '—'}</td>
                  <td className="mono">
                    {ex.best_score != null ? ex.best_score.toFixed(4) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
