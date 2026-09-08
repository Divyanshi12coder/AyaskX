/**
 * src/components/ui/LoadingState.tsx
 */

import React from 'react';
import { Loader2 } from 'lucide-react';

interface Props {
  message?: string;
  inline?: boolean;
}

export function LoadingState({ message = 'Loading...', inline }: Props) {
  if (inline) {
    return (
      <span className="flex items-center gap-2 text-muted text-sm">
        <Loader2 size={14} className="spin" />
        {message}
      </span>
    );
  }
  return (
    <div className="state-container">
      <Loader2 size={32} className="spin" color="var(--accent)" />
      <p className="state-sub">{message}</p>
    </div>
  );
}
