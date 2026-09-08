/**
 * src/components/Topbar.tsx
 * System status bar at the top of every page.
 */

import React, { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { healthApi } from '../api/endpoints';
import type { SystemStatus } from '../types';

function Dot({ ok }: { ok: boolean | null }) {
  if (ok === null) return <span className="dot dot-gray" />;
  return <span className={`dot ${ok ? 'dot-green' : 'dot-red'}`} />;
}

interface Chip {
  label: string;
  value: string;
  ok: boolean | null;
}

export function Topbar() {
  const [status, setStatus] = useState<SystemStatus>({
    system: 'unknown',
    backend: 'disconnected',
    database: 'unknown',
    pipeline_engine: 'unknown',
    self_healing: 'unknown',
  });
  const [checking, setChecking] = useState(false);

  async function check() {
    setChecking(true);
    try {
      await healthApi.get();
      let readyOk = false;
      try {
        await healthApi.ready();
        readyOk = true;
      } catch {
        readyOk = false;
      }
      setStatus({
        system: readyOk ? 'healthy' : 'degraded',
        backend: 'connected',
        database: readyOk ? 'connected' : 'error',
        pipeline_engine: readyOk ? 'ready' : 'failed',
        self_healing: readyOk ? 'operational' : 'degraded',
      });
    } catch {
      setStatus({
        system: 'critical',
        backend: 'disconnected',
        database: 'error',
        pipeline_engine: 'failed',
        self_healing: 'degraded',
      });
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => {
    void check();
    const id = setInterval(check, 30_000);
    return () => clearInterval(id);
  }, []);

  const chips: Chip[] = [
    {
      label: 'System',
      value: status.system,
      ok: status.system === 'healthy' ? true : status.system === 'critical' ? false : null,
    },
    {
      label: 'Backend',
      value: status.backend,
      ok: status.backend === 'connected',
    },
    {
      label: 'Pipeline Engine',
      value: status.pipeline_engine,
      ok: status.pipeline_engine === 'ready' || status.pipeline_engine === 'running',
    },
    {
      label: 'Self-Healing',
      value: status.self_healing,
      ok: status.self_healing === 'operational',
    },
  ];

  return (
    <div className="topbar">
      {chips.map((chip) => (
        <div key={chip.label} className="topbar-status-chip">
          <Dot ok={chip.ok} />
          <span style={{ color: 'var(--text-muted)', marginRight: 4 }}>{chip.label}:</span>
          <span
            style={{
              color:
                chip.ok === true
                  ? 'var(--status-success)'
                  : chip.ok === false
                  ? 'var(--status-error)'
                  : 'var(--text-secondary)',
              fontWeight: 500,
              textTransform: 'capitalize',
            }}
          >
            {chip.value}
          </span>
        </div>
      ))}

      <div style={{ flex: 1 }} />

      <button
        className="btn btn-ghost btn-icon"
        onClick={() => void check()}
        disabled={checking}
        title="Refresh status"
      >
        <RefreshCw size={14} className={checking ? 'spin' : ''} />
      </button>

      <div
        style={{
          fontSize: '0.77rem',
          color: 'var(--text-muted)',
          fontFamily: 'var(--font-mono)',
        }}
      >
        {new Date().toLocaleTimeString()}
      </div>
    </div>
  );
}
