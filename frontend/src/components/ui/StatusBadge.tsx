/**
 * src/components/ui/StatusBadge.tsx
 */

import React from 'react';

type Variant = 'success' | 'error' | 'warning' | 'info' | 'neutral' | 'accent';

const VARIANT_MAP: Record<string, Variant> = {
  // Execution statuses
  succeeded: 'success',
  success: 'success',
  failed: 'error',
  error: 'error',
  running: 'info',
  queued: 'neutral',
  skipped: 'neutral',
  recovered: 'warning',
  // Health
  ok: 'success',
  ready: 'success',
  healthy: 'success',
  connected: 'success',
  operational: 'success',
  degraded: 'warning',
  critical: 'error',
  disconnected: 'error',
  // Leakage
  none: 'success',
  low: 'success',
  medium: 'warning',
  high: 'error',
  // Severity
  info: 'info',
  warning: 'warning',
  critical_sev: 'error',
  // Validation
  passed: 'success',
  pending: 'neutral',
};

interface Props {
  value: string;
  variant?: Variant;
  dot?: boolean;
}

export function StatusBadge({ value, variant, dot = true }: Props) {
  const v = variant ?? VARIANT_MAP[value?.toLowerCase?.()] ?? 'neutral';
  return (
    <span className={`badge badge-${v}`}>
      {dot && <span className="badge-dot" style={{ background: 'currentColor' }} />}
      {value}
    </span>
  );
}
