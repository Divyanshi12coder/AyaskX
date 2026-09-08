/**
 * src/pages/pipelines/PipelineDetail.tsx
 * Full pipeline execution workspace with:
 * - Execution graph (left/center)
 * - Node detail drawer (right)
 * - Bottom: logs / checkpoints
 * - Live polling for running executions
 */

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, RefreshCw, ChevronRight } from 'lucide-react';
import { pipelinesApi } from '../../api/endpoints';
import type { ExecutionRecord, PipelineNode } from '../../types';
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

// ─── Pipeline Execution Graph ─────────────────────────────────────────────────

function PipelineGraph({
  execution,
  selectedNode,
  onSelectNode,
}: {
  execution: ExecutionRecord;
  selectedNode: PipelineNode | null;
  onSelectNode: (n: PipelineNode | null) => void;
}) {
  const nodes: PipelineNode[] = execution.nodes ?? [];

  // If we have node data, show it. Otherwise show stage template with execution status.
  const displayNodes =
    nodes.length > 0
      ? nodes
      : [];

  if (displayNodes.length === 0) {
    return (
      <EmptyState
        title="No node data"
        message="Node-level detail is populated once the pipeline completes or reaches a checkpoint."
      />
    );
  }

  return (
    <div className="pipeline-graph">
      {displayNodes.map((node, i) => {
        const status = node.status ?? 'queued';
        const isSelected = selectedNode?.node_id === node.node_id;
        const hasFailed = status === 'failed';

        return (
          <div key={node.node_id} className="pipeline-node">
            <div
              className={`pipeline-node-box status-${status}${isSelected ? ' selected' : ''}`}
              onClick={() => onSelectNode(isSelected ? null : node)}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      flexShrink: 0,
                      background:
                        status === 'success'
                          ? 'var(--status-success)'
                          : status === 'failed'
                          ? 'var(--status-error)'
                          : status === 'running'
                          ? 'var(--status-info)'
                          : status === 'recovered'
                          ? 'var(--status-warning)'
                          : 'var(--text-muted)',
                      boxShadow:
                        status === 'running'
                          ? '0 0 6px var(--status-info)'
                          : undefined,
                      animation: status === 'running' ? 'pulse 2s infinite' : undefined,
                    }}
                  />
                  <span
                    style={{
                      fontSize: '0.85rem',
                      fontWeight: 500,
                      color: 'var(--text-primary)',
                    }}
                  >
                    {node.node_id
                      .replace(/_/g, ' ')
                      .replace(/\b\w/g, (c) => c.toUpperCase())}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.72rem',
                      color: 'var(--text-muted)',
                    }}
                  >
                    {fmtDuration(node.started_at, node.finished_at)}
                  </span>
                  {node.checkpoint_id && (
                    <span
                      style={{
                        fontSize: '0.68rem',
                        padding: '1px 5px',
                        borderRadius: 2,
                        background: 'var(--accent-dim)',
                        color: 'var(--accent)',
                        border: '1px solid var(--accent-border)',
                      }}
                    >
                      CKPT
                    </span>
                  )}
                  <ChevronRight size={12} style={{ color: 'var(--text-muted)' }} />
                </div>
              </div>

              {hasFailed && node.error_message && (
                <div
                  style={{
                    marginTop: 6,
                    padding: '4px 8px',
                    background: 'var(--status-error-dim)',
                    borderRadius: 3,
                    fontSize: '0.75rem',
                    color: 'var(--status-error)',
                    fontFamily: 'var(--font-mono)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {node.error_type}: {node.error_message}
                </div>
              )}
            </div>

            {i < displayNodes.length - 1 && (
              <div className="pipeline-connector" />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Node Detail Panel ────────────────────────────────────────────────────────

function NodeDetail({ node }: { node: PipelineNode }) {
  return (
    <div>
      <div
        style={{
          padding: '12px 16px',
          background: 'var(--bg-elevated)',
          borderRadius: 'var(--radius)',
          marginBottom: 16,
          borderLeft: `3px solid ${
            node.status === 'success'
              ? 'var(--status-success)'
              : node.status === 'failed'
              ? 'var(--status-error)'
              : 'var(--status-info)'
          }`,
        }}
      >
        <div
          style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}
        >
          {node.node_id.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
        </div>
        <StatusBadge value={node.status} />
      </div>

      <div className="kv-grid">
        <div className="kv-key">Node ID</div>
        <div className="kv-val mono">{node.node_id}</div>
        <div className="kv-key">Status</div>
        <div className="kv-val">
          <StatusBadge value={node.status} />
        </div>
        <div className="kv-key">Started</div>
        <div className="kv-val mono" style={{ fontSize: '0.77rem' }}>
          {node.started_at ? new Date(node.started_at).toLocaleString() : '—'}
        </div>
        <div className="kv-key">Finished</div>
        <div className="kv-val mono" style={{ fontSize: '0.77rem' }}>
          {node.finished_at ? new Date(node.finished_at).toLocaleString() : '—'}
        </div>
        <div className="kv-key">Duration</div>
        <div className="kv-val mono">
          {fmtDuration(node.started_at, node.finished_at)}
        </div>
        <div className="kv-key">Checkpoint</div>
        <div className="kv-val mono">{node.checkpoint_id ?? 'None'}</div>
      </div>

      {node.status === 'failed' && (
        <div style={{ marginTop: 16 }}>
          <div className="section-title" style={{ marginBottom: 8 }}>Error Detail</div>
          {node.error_type && (
            <div
              style={{
                fontSize: '0.83rem',
                fontWeight: 600,
                color: 'var(--status-error)',
                marginBottom: 4,
              }}
            >
              {node.error_type}
            </div>
          )}
          {node.error_message && (
            <div className="code-block">{node.error_message}</div>
          )}
        </div>
      )}

      {node.output_metadata && Object.keys(node.output_metadata).length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="section-title" style={{ marginBottom: 8 }}>Output Metadata</div>
          <div className="code-block">
            {JSON.stringify(node.output_metadata, null, 2)}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Checkpoints Table ────────────────────────────────────────────────────────

function CheckpointsTable({ executionId }: { executionId: string }) {
  const { data, loading, error } = useApi(
    () => pipelinesApi.checkpoints(executionId),
    [executionId]
  );

  if (loading) return <LoadingState inline />;
  if (error) return <p className="text-xs text-muted">{error}</p>;
  if (!data?.length) return <EmptyState title="No checkpoints" />;

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Checkpoint ID</th>
          <th>Node</th>
          <th>Created</th>
          <th>Validation</th>
          <th>Hash</th>
        </tr>
      </thead>
      <tbody>
        {data.map((ckpt) => (
          <tr key={ckpt.checkpoint_id}>
            <td className="mono">{ckpt.checkpoint_id?.slice(0, 16)}…</td>
            <td>{ckpt.node_id}</td>
            <td className="mono" style={{ fontSize: '0.77rem' }}>
              {ckpt.created_at ? new Date(ckpt.created_at).toLocaleString() : '—'}
            </td>
            <td>
              <StatusBadge
                value={ckpt.validation_status ?? 'unknown'}
              />
            </td>
            <td className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
              {ckpt.data_hash?.slice(0, 16) ?? '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function PipelineDetail() {
  const { executionId } = useParams<{ executionId: string }>();
  const navigate = useNavigate();
  const [selectedNode, setSelectedNode] = useState<PipelineNode | null>(null);
  const [activeTab, setActiveTab] = useState('graph');

  const { data: execution, loading, error, refetch } = useApi(
    () => pipelinesApi.get(executionId!),
    [executionId]
  );

  // Auto-poll while running
  useEffect(() => {
    if (!execution) return;
    if (execution.status !== 'running' && execution.status !== 'queued') return;
    const id = setInterval(refetch, 3000);
    return () => clearInterval(id);
  }, [execution?.status, refetch]);

  if (loading && !execution) return <LoadingState />;
  if (error || !execution)
    return (
      <ErrorState
        title="Execution not found"
        message={error ?? 'Unknown error'}
        onRetry={refetch}
      />
    );

  const TABS = ['graph', 'checkpoints', 'summary', 'audit'];

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title={`Execution ${execution.execution_id.slice(0, 16)}…`}
        subtitle={`${execution.dataset_path ?? execution.dataset_id} · ${execution.task_type ?? 'auto'}`}
        breadcrumbs={[
          { label: 'Pipelines', href: '/pipelines' },
          { label: execution.execution_id.slice(0, 16) },
        ]}
        actions={
          <div className="flex items-center gap-2">
            <StatusBadge value={execution.status} />
            <button className="btn btn-ghost btn-sm" onClick={refetch}>
              <RefreshCw
                size={13}
                className={
                  execution.status === 'running' || execution.status === 'queued'
                    ? 'spin'
                    : ''
                }
              />
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/pipelines')}>
              <ArrowLeft size={13} />
              Back
            </button>
          </div>
        }
      />

      {/* Tabs */}
      <div className="tabs">
        {TABS.map((t) => (
          <div
            key={t}
            className={`tab${activeTab === t ? ' active' : ''}`}
            onClick={() => setActiveTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </div>
        ))}
      </div>

      <div style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>
        {activeTab === 'graph' && (
          <>
            {/* Graph panel */}
            <div
              style={{
                flex: 1,
                overflowY: 'auto',
                padding: 20,
                borderRight: selectedNode ? '1px solid var(--border)' : undefined,
              }}
            >
              <PipelineGraph
                execution={execution}
                selectedNode={selectedNode}
                onSelectNode={setSelectedNode}
              />
            </div>

            {/* Node detail panel */}
            {selectedNode && (
              <div
                style={{
                  width: 360,
                  overflowY: 'auto',
                  padding: 16,
                  background: 'var(--bg-surface)',
                  flexShrink: 0,
                }}
              >
                <div
                  className="flex items-center justify-between"
                  style={{ marginBottom: 12 }}
                >
                  <span style={{ fontSize: '0.83rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    NODE DETAIL
                  </span>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => setSelectedNode(null)}
                  >
                    ✕
                  </button>
                </div>
                <NodeDetail node={selectedNode} />
              </div>
            )}
          </>
        )}

        {activeTab === 'checkpoints' && (
          <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
            <CheckpointsTable executionId={executionId!} />
          </div>
        )}

        {activeTab === 'summary' && (
          <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
            <div className="grid-2" style={{ alignItems: 'start' }}>
              <div className="panel" style={{ padding: 16 }}>
                <h4 style={{ marginBottom: 12 }}>Execution Summary</h4>
                <div className="kv-grid">
                  <div className="kv-key">Execution ID</div>
                  <div className="kv-val mono">{execution.execution_id}</div>
                  <div className="kv-key">Dataset</div>
                  <div className="kv-val">{execution.dataset_path ?? execution.dataset_id}</div>
                  <div className="kv-key">Task Type</div>
                  <div className="kv-val">{execution.task_type ?? '—'}</div>
                  <div className="kv-key">Target</div>
                  <div className="kv-val">{execution.target ?? '—'}</div>
                  <div className="kv-key">Status</div>
                  <div className="kv-val">
                    <StatusBadge value={execution.status} />
                  </div>
                  <div className="kv-key">Created</div>
                  <div className="kv-val mono">{new Date(execution.created_at).toLocaleString()}</div>
                  <div className="kv-key">Started</div>
                  <div className="kv-val mono">
                    {execution.started_at ? new Date(execution.started_at).toLocaleString() : '—'}
                  </div>
                  <div className="kv-key">Completed</div>
                  <div className="kv-val mono">
                    {execution.completed_at
                      ? new Date(execution.completed_at).toLocaleString()
                      : '—'}
                  </div>
                  <div className="kv-key">Best Model</div>
                  <div className="kv-val">{execution.best_model ?? '—'}</div>
                  <div className="kv-key">Best Score</div>
                  <div className="kv-val mono">
                    {execution.best_score != null ? execution.best_score.toFixed(6) : '—'}
                  </div>
                  <div className="kv-key">Validation</div>
                  <div className="kv-val">{execution.validation_strategy ?? '—'}</div>
                </div>
              </div>

              <div className="panel" style={{ padding: 16 }}>
                <h4 style={{ marginBottom: 12 }}>Messages</h4>
                {execution.message && (
                  <div className="code-block" style={{ marginBottom: 12 }}>
                    {execution.message}
                  </div>
                )}
                {execution.warnings && execution.warnings.length > 0 && (
                  <>
                    <div className="section-title" style={{ marginBottom: 6 }}>Warnings</div>
                    {execution.warnings.map((w, i) => (
                      <div
                        key={i}
                        style={{
                          fontSize: '0.8rem',
                          color: 'var(--status-warning)',
                          padding: '4px 0',
                          borderBottom: '1px solid var(--border-subtle)',
                        }}
                      >
                        {w}
                      </div>
                    ))}
                  </>
                )}
                {!execution.message && (!execution.warnings || execution.warnings.length === 0) && (
                  <EmptyState title="No messages" />
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'audit' && (
          <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
            <ExecutionAuditTab executionId={executionId!} />
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Execution Audit Tab ─────────────────────────────────────────────────────

import { auditApi } from '../../api/endpoints';

function ExecutionAuditTab({ executionId }: { executionId: string }) {
  const { data, loading, error } = useApi(
    () => auditApi.executionAudit(executionId),
    [executionId]
  );

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;
  if (!data?.length)
    return <EmptyState title="No audit events" message="No audit events for this execution" />;

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Timestamp</th>
          <th>Action</th>
          <th>Resource</th>
          <th>Result</th>
          <th>Severity</th>
        </tr>
      </thead>
      <tbody>
        {data.map((ev, i) => (
          <tr key={ev.event_id ?? i}>
            <td className="mono" style={{ fontSize: '0.77rem' }}>
              {ev.timestamp ? new Date(ev.timestamp).toLocaleString() : '—'}
            </td>
            <td>{ev.action ?? '—'}</td>
            <td>{ev.resource ?? '—'}</td>
            <td>{ev.result ?? '—'}</td>
            <td>
              <StatusBadge
                value={ev.severity ?? 'info'}
                variant={
                  ev.severity === 'error' || ev.severity === 'critical'
                    ? 'error'
                    : ev.severity === 'warning'
                    ? 'warning'
                    : 'info'
                }
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
