/**
 * src/components/Topbar.tsx
 * System status bar at the top of every page.
 */

import React, { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { systemApi } from '../api/endpoints';
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
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [checking, setChecking] = useState(false);

  async function check() {
    setChecking(true);
    try {
      setStatus(await systemApi.status());
    } catch {
      setStatus(null);
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
      value: status?.api.status ?? 'unavailable',
      ok: status?.api.status === 'ready' ? true : status ? false : null,
    },
    {
      label: 'Backend',
      value: status ? 'connected' : 'disconnected',
      ok: status ? true : false,
    },
    {
      label: 'Pipeline Engine',
      value: status?.runtime.execution_mode.replace(/_/g, ' ') ?? 'unavailable',
      ok: status ? true : null,
    },
    {
      label: 'Database',
      value: status?.database.status ?? 'unavailable',
      ok: status?.database.status === 'ready' ? true : status ? false : null,
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
