/**
 * src/components/ui/ErrorState.tsx
 */

import React from 'react';
import { AlertTriangle } from 'lucide-react';

interface Props {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export function ErrorState({
  title = 'Unable to load data',
  message,
  onRetry,
}: Props) {
  return (
    <div className="state-container">
      <AlertTriangle size={36} color="var(--status-error)" style={{ opacity: 0.7 }} />
      <p className="state-title">{title}</p>
      <p className="state-sub" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.77rem' }}>
        {message}
      </p>
      {onRetry && (
        <button className="btn btn-secondary btn-sm" onClick={onRetry} style={{ marginTop: 4 }}>
          Retry
        </button>
      )}
    </div>
  );
}
