/**
 * src/pages/Checkpoints.tsx
 * Checkpoint registry — all checkpoints across all executions.
 */

import React, { useState } from 'react';
import { pipelinesApi } from '../api/endpoints';
import type { ExecutionRecord, CheckpointRecord } from '../types';
import { useApi } from '../hooks/useApi';
import { StatusBadge } from '../components/ui/StatusBadge';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { PageHeader } from '../components/ui/PageHeader';
import { DetailDrawer } from '../components/ui/DetailDrawer';

export default function Checkpoints() {
  const [selectedCkpt, setSelectedCkpt] = useState<CheckpointRecord | null>(null);
  const [search, setSearch] = useState('');

  const { data, loading, error, refetch } = useApi(() => pipelinesApi.list());

  // Aggregate all checkpoints from all executions
  const allCheckpoints: (CheckpointRecord & { dataset_path?: string })[] = (data ?? []).flatMap(
    (ex: ExecutionRecord) =>
      (ex.checkpoints ?? []).map((ckpt) => ({
        ...ckpt,
        dataset_path: ex.dataset_path ?? ex.dataset_id,
      }))
  );

  const filtered = allCheckpoints.filter(
    (c) =>
      !search ||
      c.checkpoint_id?.includes(search) ||
      c.node_id?.includes(search) ||
      c.execution_id?.includes(search)
  );

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Checkpoint Registry"
        subtitle={`${allCheckpoints.length} checkpoint${allCheckpoints.length !== 1 ? 's' : ''} across all executions`}
        breadcrumbs={[{ label: 'AyaskX' }, { label: 'Checkpoints' }]}
      />

      <div className="filter-bar">
        <input
          className="input"
          style={{ maxWidth: 280 }}
          placeholder="Search by ID, node, execution…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No checkpoints"
            message="Checkpoints are created during pipeline execution at each successful node."
          />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Checkpoint ID</th>
                <th>Execution ID</th>
                <th>Dataset</th>
                <th>Node</th>
                <th>Created</th>
                <th>Validation</th>
                <th>Data Hash</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((ckpt) => (
                <tr key={ckpt.checkpoint_id} onClick={() => setSelectedCkpt(ckpt)}>
                  <td className="mono">{ckpt.checkpoint_id?.slice(0, 16)}…</td>
                  <td className="mono">{ckpt.execution_id?.slice(0, 14)}…</td>
                  <td>{ckpt.dataset_path ?? '—'}</td>
                  <td>{ckpt.node_id}</td>
                  <td className="mono" style={{ fontSize: '0.77rem' }}>
                    {ckpt.created_at ? new Date(ckpt.created_at).toLocaleString() : '—'}
                  </td>
                  <td>
                    <StatusBadge value={ckpt.validation_status ?? 'unknown'} />
                  </td>
                  <td className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    {ckpt.data_hash?.slice(0, 16) ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <DetailDrawer
        open={!!selectedCkpt}
        onClose={() => setSelectedCkpt(null)}
        title="Checkpoint Detail"
      >
        {selectedCkpt && (
          <div>
            <div className="kv-grid">
              <div className="kv-key">Checkpoint ID</div>
              <div className="kv-val mono">{selectedCkpt.checkpoint_id}</div>
              <div className="kv-key">Execution ID</div>
              <div className="kv-val mono">{selectedCkpt.execution_id}</div>
              <div className="kv-key">Node</div>
              <div className="kv-val">{selectedCkpt.node_id}</div>
              <div className="kv-key">Created</div>
              <div className="kv-val mono">
                {selectedCkpt.created_at
                  ? new Date(selectedCkpt.created_at).toLocaleString()
                  : '—'}
              </div>
              <div className="kv-key">Validation Status</div>
              <div className="kv-val">
                <StatusBadge value={selectedCkpt.validation_status ?? 'unknown'} />
              </div>
              <div className="kv-key">Artifact Path</div>
              <div className="kv-val mono" style={{ wordBreak: 'break-all' }}>
                {selectedCkpt.artifact_path ?? 'N/A'}
              </div>
              <div className="kv-key">Data Hash</div>
              <div className="kv-val mono" style={{ wordBreak: 'break-all' }}>
                {selectedCkpt.data_hash ?? '—'}
              </div>
            </div>

            <div
              style={{
                marginTop: 20,
                padding: '10px 12px',
                background: 'var(--bg-elevated)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.77rem',
                color: 'var(--text-muted)',
              }}
            >
              Restore/recovery controls: not yet exposed by backend API.
            </div>
          </div>
        )}
      </DetailDrawer>
    </div>
  );
}
