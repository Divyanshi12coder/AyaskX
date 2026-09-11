/**
 * src/pages/admin/AdminOverview.tsx
 */

import React from 'react';
import { healthApi, systemApi } from '../../api/endpoints';
import { useApi } from '../../hooks/useApi';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { LoadingState } from '../../components/ui/LoadingState';
import { PageHeader } from '../../components/ui/PageHeader';

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <>
      <div className="kv-key">{k}</div>
      <div className="kv-val">{v ?? '—'}</div>
    </>
  );
}

export default function AdminOverview() {
  const { data: health, loading } = useApi(() => healthApi.get());
  const { data: ready } = useApi(() => healthApi.ready().catch(() => null));
  const { data: system } = useApi(() => systemApi.status().catch(() => null));

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Administration Overview"
        subtitle="System status and environment information"
        breadcrumbs={[{ label: 'Admin' }, { label: 'Overview' }]}
      />
      <div className="page-body">
        <div className="grid-2" style={{ alignItems: 'start' }}>
          <div className="panel" style={{ padding: 16 }}>
            <h4 style={{ marginBottom: 12 }}>System</h4>
            {loading ? (
              <LoadingState inline />
            ) : (
              <div className="kv-grid">
                <KV k="API Version" v={system?.api.version ?? 'â€”'} />
                <KV k="Service" v={health?.service ?? '—'} />
                <KV
                  k="Backend Status"
                  v={<StatusBadge value={health ? 'connected' : 'disconnected'} />}
                />
                <KV
                  k="Ready Status"
                  v={<StatusBadge value={ready ? 'ready' : 'not ready'} />}
                />
                <KV
                  k="Started At"
                  v={
                    health?.started_at
                      ? new Date(health.started_at).toLocaleString()
                      : '—'
                  }
                />
                <KV k="Last Health Check" v={health?.timestamp ? new Date(health.timestamp).toLocaleString() : '—'} />
              </div>
            )}
          </div>

          <div className="panel" style={{ padding: 16 }}>
            <h4 style={{ marginBottom: 12 }}>Backend Dependencies</h4>
            <div className="kv-grid">
              <KV k="Database" v={<StatusBadge value={system?.database.status ?? 'unknown'} />} />
              <KV k="Database Dialect" v={system?.database.dialect ?? 'â€”'} />
              <KV k="Upload Storage" v={<StatusBadge value={system?.storage.uploads_ready ? 'ready' : 'unavailable'} />} />
              <KV k="Artifact Storage" v={<StatusBadge value={system?.storage.artifacts_ready ? 'ready' : 'unavailable'} />} />
              <KV k="Checkpoint Storage" v={<StatusBadge value={system?.storage.checkpoints_ready ? 'ready' : 'unavailable'} />} />
              <KV k="Datasets" v={system?.counts.datasets ?? 'â€”'} />
              <KV k="Executions" v={system?.counts.executions ?? 'â€”'} />
            </div>
          </div>

          <div className="panel" style={{ padding: 16 }}>
            <h4 style={{ marginBottom: 8 }}>Access Control</h4>
            <div
              style={{
                padding: '10px 12px',
                background: 'var(--status-warning-dim)',
                border: '1px solid rgba(245,158,11,0.2)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.8rem',
                color: 'var(--status-warning)',
              }}
            >
              Authentication is currently {system?.runtime.authentication ?? 'not configured'}.
              All endpoints remain open until a server-side authentication provider is configured.
            </div>
          </div>

          <div className="panel" style={{ padding: 16 }}>
            <h4 style={{ marginBottom: 8 }}>Pipeline Engine</h4>
            <div className="kv-grid">
              <KV
                k="Status"
                v={<StatusBadge value={ready ? 'ready' : 'unknown'} />}
              />
              <KV k="Executor" v={system?.runtime.execution_mode ?? 'â€”'} />
              <KV k="Parallelism" v="Sequential per execution" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
