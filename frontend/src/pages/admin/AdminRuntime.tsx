/**
 * src/pages/admin/AdminRuntime.tsx
 */
import React from 'react';
import { PageHeader } from '../../components/ui/PageHeader';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { useApi } from '../../hooks/useApi';
import { healthApi } from '../../api/endpoints';

export default function AdminRuntime() {
  const { data: health } = useApi(() => healthApi.get());

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader title="Runtime" subtitle="Pipeline engine and worker status" breadcrumbs={[{ label: 'Admin' }, { label: 'Runtime' }]} />
      <div className="page-body">
        <div style={{ maxWidth: 680 }}>
          <div className="panel" style={{ padding: 16 }}>
            <h4 style={{ marginBottom: 12 }}>Runtime Configuration</h4>
            <div className="kv-grid">
              <div className="kv-key">Pipeline Executor</div>
              <div className="kv-val">Python threading (daemon threads)</div>
              <div className="kv-key">Parallelism</div>
              <div className="kv-val">Sequential per execution, concurrent across executions</div>
              <div className="kv-key">Background Tasks</div>
              <div className="kv-val"><StatusBadge value="operational" variant="success" /></div>
              <div className="kv-key">API Framework</div>
              <div className="kv-val">FastAPI + Uvicorn</div>
              <div className="kv-key">Service Started</div>
              <div className="kv-val mono">{health?.started_at ? new Date(health.started_at).toLocaleString() : '—'}</div>
            </div>
          </div>
          <div style={{ marginTop: 12, fontSize: '0.77rem', color: 'var(--text-muted)', padding: '10px 12px', background: 'var(--bg-elevated)', borderRadius: 'var(--radius-sm)' }}>
            Worker management, distributed execution, and queue monitoring are not implemented in the current backend.
          </div>
        </div>
      </div>
    </div>
  );
}
