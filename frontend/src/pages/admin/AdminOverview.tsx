/**
 * src/pages/admin/AdminOverview.tsx
 */

import React from 'react';
import { healthApi } from '../../api/endpoints';
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
                <KV k="API Version" v="1.0.0" />
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
            <h4 style={{ marginBottom: 12 }}>Environment</h4>
            <div className="kv-grid">
              <KV k="API Host" v={<span className="mono">0.0.0.0:8000</span>} />
              <KV k="Checkpoint Root" v={<span className="mono">.ayask_checkpoints/</span>} />
              <KV k="Artifact Root" v={<span className="mono">.ayask_artifacts/</span>} />
              <KV k="Upload Root" v={<span className="mono">.ayask_uploads/</span>} />
              <KV k="Store Root" v={<span className="mono">.ayask_store/</span>} />
              <KV k="Max Upload" v="200 MB" />
              <KV k="DB" v={<span className="mono">ayaskx.db (SQLite)</span>} />
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
              Authentication and RBAC are not implemented in the current backend.
              All endpoints are open. Implement AYASKX_SECRET_KEY and JWT middleware
              to enforce access control.
            </div>
          </div>

          <div className="panel" style={{ padding: 16 }}>
            <h4 style={{ marginBottom: 8 }}>Pipeline Engine</h4>
            <div className="kv-grid">
              <KV
                k="Status"
                v={<StatusBadge value={ready ? 'ready' : 'unknown'} />}
              />
              <KV k="Executor" v="Background thread (daemon)" />
              <KV k="Parallelism" v="Sequential (per execution)" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
