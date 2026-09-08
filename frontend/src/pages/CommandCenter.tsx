/**
 * src/pages/CommandCenter.tsx
 * Main operational dashboard — Command Center.
 *
 * Shows: active/recent pipeline executions, execution graph of most recent,
 * and live system event stream (audit events).
 * All data sourced from real API endpoints.
 */

import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Clock, Play, RefreshCw, XCircle } from 'lucide-react';
import { pipelinesApi, auditApi } from '../api/endpoints';
import type { AuditEvent, ExecutionRecord } from '../types';
import { StatusBadge } from '../components/ui/StatusBadge';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { PageHeader } from '../components/ui/PageHeader';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtDuration(start?: string | null, end?: string | null): string {
  if (!start) return '—';
  const s = new Date(start).getTime();
  const e = end ? new Date(end).getTime() : Date.now();
  const diff = Math.round((e - s) / 1000);
  if (diff < 60) return `${diff}s`;
  const m = Math.floor(diff / 60);
  const sec = diff % 60;
  return `${m}m ${sec}s`;
}

function fmtTime(ts?: string): string {
  if (!ts) return '—';
  return new Date(ts).toLocaleTimeString();
}

function fmtDateTime(ts?: string): string {
  if (!ts) return '—';
  const d = new Date(ts);
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
}

// ─── Pipeline Execution Mini-Graph ───────────────────────────────────────────

const PIPELINE_STAGES = [
  'characterization',
  'task_detection',
  'feature_roles',
  'leakage_detection',
  'preprocessing',
  'validation_strategy',
  'model_candidates',
  'training',
  'inference',
];

function MiniPipelineGraph({ execution }: { execution: ExecutionRecord }) {
  const nodes = execution.nodes ?? [];
  const nodeMap = new Map(nodes.map((n) => [n.node_id, n]));

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: 0,
        padding: '12px 0',
        maxHeight: 420,
        overflowY: 'auto',
      }}
    >
      {PIPELINE_STAGES.map((stage, i) => {
        const node = nodeMap.get(stage) ?? nodes.find((n) => n.node_id?.includes(stage));
        const status = node?.status ?? 'queued';
        const label = stage.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

        const color =
          status === 'success'
            ? 'var(--status-success)'
            : status === 'failed'
            ? 'var(--status-error)'
            : status === 'running'
            ? 'var(--status-info)'
            : status === 'recovered'
            ? 'var(--status-warning)'
            : 'var(--text-muted)';

        return (
          <div key={stage} style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '6px 8px',
                borderRadius: 4,
                background: 'var(--bg-elevated)',
                border: `1px solid ${color}33`,
                minWidth: 220,
              }}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: color,
                  flexShrink: 0,
                  boxShadow: status === 'running' ? `0 0 6px ${color}` : undefined,
                }}
              />
              <span style={{ fontSize: '0.83rem', color: 'var(--text-secondary)', flex: 1 }}>
                {label}
              </span>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                {node?.started_at ? fmtDuration(node.started_at, node.finished_at) : '—'}
              </span>
            </div>
            {i < PIPELINE_STAGES.length - 1 && (
              <div
                style={{
                  width: 1,
                  height: 12,
                  background: 'var(--border)',
                  marginLeft: 22,
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Recent Executions Table ──────────────────────────────────────────────────

function RecentExecutions({
  executions,
  onSelect,
}: {
  executions: ExecutionRecord[];
  onSelect: (id: string) => void;
}) {
  if (executions.length === 0) {
    return (
      <EmptyState
        title="No executions yet"
        message="Run a pipeline from the Datasets or Pipelines page."
      />
    );
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="data-table">
        <thead>
          <tr>
            <th>Execution ID</th>
            <th>Dataset</th>
            <th>Task</th>
            <th>Started</th>
            <th>Duration</th>
            <th>Status</th>
            <th>Best Model</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {executions.slice(0, 20).map((ex) => (
            <tr key={ex.execution_id} onClick={() => onSelect(ex.execution_id)}>
              <td className="mono">{ex.execution_id.slice(0, 12)}…</td>
              <td>{ex.dataset_path ?? ex.dataset_id}</td>
              <td>{ex.task_type ?? '—'}</td>
              <td className="mono" style={{ fontSize: '0.77rem' }}>
                {fmtDateTime(ex.started_at ?? ex.created_at)}
              </td>
              <td className="mono">{fmtDuration(ex.started_at, ex.completed_at)}</td>
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
    </div>
  );
}

// ─── Event Stream ─────────────────────────────────────────────────────────────

function EventStream({ events }: { events: AuditEvent[] }) {
  if (events.length === 0) {
    return (
      <EmptyState title="No events" message="Events will appear here as the system runs." />
    );
  }

  const sevColor = (sev?: string) => {
    switch (sev) {
      case 'error': return 'var(--status-error)';
      case 'warning': return 'var(--status-warning)';
      case 'critical': return 'var(--status-error)';
      default: return 'var(--status-info)';
    }
  };

  return (
    <div style={{ overflowY: 'auto', maxHeight: 260 }}>
      {events.slice(0, 30).map((ev, idx) => (
        <div
          key={ev.event_id ?? idx}
          className="timeline-item"
          style={{ padding: '6px 0' }}
        >
          <div
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: sevColor(ev.severity),
              marginTop: 5,
              flexShrink: 0,
            }}
          />
          <div style={{ flex: 1, minWidth: 0, paddingLeft: 8 }}>
            <div className="flex items-center gap-2">
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.72rem',
                  color: 'var(--text-muted)',
                  flexShrink: 0,
                }}
              >
                {fmtTime(ev.timestamp)}
              </span>
              <span
                style={{
                  fontSize: '0.83rem',
                  color: 'var(--text-secondary)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {ev.action ?? ev.event_id}
              </span>
              {ev.severity && ev.severity !== 'info' && (
                <StatusBadge value={ev.severity} dot={false} />
              )}
            </div>
            {ev.resource && (
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 1 }}>
                {ev.resource}
                {ev.execution_id && ` · ${ev.execution_id.slice(0, 8)}…`}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function CommandCenter() {
  const navigate = useNavigate();
  const [executions, setExecutions] = useState<ExecutionRecord[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  async function load() {
    try {
      const [execs, evts] = await Promise.all([
        pipelinesApi.list(),
        auditApi.events(),
      ]);
      setExecutions(
        [...(execs ?? [])].sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        )
      );
      setEvents(
        [...(evts ?? [])].sort(
          (a, b) =>
            new Date(b.timestamp ?? 0).getTime() -
            new Date(a.timestamp ?? 0).getTime()
        )
      );
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  function refresh() {
    setRefreshing(true);
    void load();
  }

  const mostRecent = executions[0] ?? null;
  const running = executions.filter((e) => e.status === 'running');
  const failed = executions.filter((e) => e.status === 'failed');
  const succeeded = executions.filter((e) => e.status === 'succeeded');

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Command Center"
        subtitle="Operational overview — all data live from backend"
        breadcrumbs={[{ label: 'AyaskX' }, { label: 'Command Center' }]}
        actions={
          <button className="btn btn-ghost btn-sm" onClick={refresh} disabled={refreshing}>
            <RefreshCw size={13} className={refreshing ? 'spin' : ''} />
            Refresh
          </button>
        }
      />

      <div className="page-body">
        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState
            title="Unable to retrieve data"
            message={error}
            onRetry={refresh}
          />
        ) : (
          <>
            {/* Summary metrics */}
            <div className="metric-grid mb-4">
              <div className="metric-card">
                <div className="metric-card-label">Total Executions</div>
                <div className="metric-card-value">{executions.length}</div>
              </div>
              <div className="metric-card">
                <div className="metric-card-label">Running</div>
                <div
                  className="metric-card-value"
                  style={{ color: running.length > 0 ? 'var(--status-info)' : undefined }}
                >
                  {running.length}
                </div>
              </div>
              <div className="metric-card">
                <div className="metric-card-label">Succeeded</div>
                <div
                  className="metric-card-value"
                  style={{ color: 'var(--status-success)' }}
                >
                  {succeeded.length}
                </div>
              </div>
              <div className="metric-card">
                <div className="metric-card-label">Failed</div>
                <div
                  className="metric-card-value"
                  style={{ color: failed.length > 0 ? 'var(--status-error)' : undefined }}
                >
                  {failed.length}
                </div>
              </div>
            </div>

            {/* Main two-column layout */}
            <div className="grid-2" style={{ alignItems: 'start' }}>
              {/* Active Pipeline Graph */}
              <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
                <div
                  style={{
                    padding: '10px 14px',
                    borderBottom: '1px solid var(--border)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <span className="section-title">Active Pipeline</span>
                  {mostRecent && (
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => navigate(`/pipelines/${mostRecent.execution_id}`)}
                    >
                      View →
                    </button>
                  )}
                </div>
                <div style={{ padding: '0 14px' }}>
                  {mostRecent ? (
                    <>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          padding: '8px 0',
                          borderBottom: '1px solid var(--border)',
                          marginBottom: 4,
                          fontSize: '0.8rem',
                          color: 'var(--text-muted)',
                        }}
                      >
                        <span className="mono">{mostRecent.execution_id.slice(0, 16)}…</span>
                        <StatusBadge value={mostRecent.status} />
                        {mostRecent.dataset_path && (
                          <span style={{ color: 'var(--text-secondary)' }}>
                            {mostRecent.dataset_path}
                          </span>
                        )}
                      </div>
                      <MiniPipelineGraph execution={mostRecent} />
                    </>
                  ) : (
                    <EmptyState
                      title="No pipeline executions"
                      message="Start a run from the Datasets page"
                    />
                  )}
                </div>
              </div>

              {/* Right column */}
              <div className="flex flex-col gap-4">
                {/* Failed executions alert */}
                {failed.length > 0 && (
                  <div
                    style={{
                      background: 'var(--status-error-dim)',
                      border: '1px solid rgba(239,68,68,0.25)',
                      borderRadius: 'var(--radius)',
                      padding: '10px 14px',
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 10,
                    }}
                  >
                    <AlertTriangle size={16} color="var(--status-error)" style={{ flexShrink: 0, marginTop: 1 }} />
                    <div>
                      <div
                        style={{ fontSize: '0.83rem', fontWeight: 600, color: 'var(--status-error)' }}
                      >
                        {failed.length} failed execution{failed.length > 1 ? 's' : ''}
                      </div>
                      <div style={{ fontSize: '0.77rem', color: 'var(--text-muted)', marginTop: 2 }}>
                        Check Self-Healing for recovery options.
                      </div>
                    </div>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => navigate('/self-healing')}
                      style={{ marginLeft: 'auto' }}
                    >
                      View →
                    </button>
                  </div>
                )}

                {/* System events */}
                <div className="panel" style={{ padding: 0 }}>
                  <div
                    style={{
                      padding: '10px 14px',
                      borderBottom: '1px solid var(--border)',
                    }}
                  >
                    <span className="section-title">System Events</span>
                  </div>
                  <div style={{ padding: '8px 14px' }}>
                    <EventStream events={events} />
                  </div>
                </div>
              </div>
            </div>

            {/* Recent Executions Table */}
            <div className="section" style={{ marginTop: 20 }}>
              <div className="section-header">
                <span className="section-title">Recent Executions</span>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => navigate('/pipelines')}
                >
                  View all →
                </button>
              </div>
              <div className="panel" style={{ padding: 0 }}>
                <RecentExecutions
                  executions={executions}
                  onSelect={(id) => navigate(`/pipelines/${id}`)}
                />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
