/**
 * src/pages/Inference.tsx
 * Inference panel — run predictions against a completed execution.
 */

import React, { useState } from 'react';
import { pipelinesApi, inferenceApi } from '../api/endpoints';
import type { ExecutionRecord } from '../types';
import { useApi } from '../hooks/useApi';
import { StatusBadge } from '../components/ui/StatusBadge';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { PageHeader } from '../components/ui/PageHeader';

export default function Inference() {
  const [selectedExecId, setSelectedExecId] = useState('');
  const [inputJson, setInputJson] = useState('[\n  {}\n]');
  const [result, setResult] = useState<unknown>(null);
  const [inferring, setInferring] = useState(false);
  const [inferError, setInferError] = useState<string | null>(null);

  const { data, loading, error } = useApi(() => pipelinesApi.list());

  const succeeded: ExecutionRecord[] = (data ?? [])
    .filter((e) => e.status === 'succeeded')
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

  async function runInference() {
    setInferError(null);
    setResult(null);
    let rows: Record<string, unknown>[];
    try {
      rows = JSON.parse(inputJson);
      if (!Array.isArray(rows)) throw new Error('Input must be a JSON array of objects');
    } catch (e) {
      setInferError(`JSON parse error: ${e}`);
      return;
    }
    setInferring(true);
    try {
      const res = await inferenceApi.predict(selectedExecId, rows);
      setResult(res);
    } catch (e) {
      setInferError(String(e));
    } finally {
      setInferring(false);
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Inference"
        subtitle="Run predictions against a completed pipeline execution"
        breadcrumbs={[{ label: 'AyaskX' }, { label: 'Inference' }]}
      />

      <div className="page-body">
        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState message={error} />
        ) : succeeded.length === 0 ? (
          <EmptyState
            title="No succeeded executions"
            message="Complete a pipeline run before running inference."
          />
        ) : (
          <div className="grid-2" style={{ alignItems: 'start' }}>
            {/* Input panel */}
            <div className="flex flex-col gap-4">
              <div className="panel" style={{ padding: 16 }}>
                <h4 style={{ marginBottom: 12 }}>Select Execution</h4>
                <select
                  className="input"
                  value={selectedExecId}
                  onChange={(e) => setSelectedExecId(e.target.value)}
                >
                  <option value="">— Select an execution —</option>
                  {succeeded.map((ex) => (
                    <option key={ex.execution_id} value={ex.execution_id}>
                      {ex.execution_id.slice(0, 20)}… · {ex.best_model ?? 'model'} ·{' '}
                      {ex.best_score != null ? ex.best_score.toFixed(4) : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div className="panel" style={{ padding: 16 }}>
                <h4 style={{ marginBottom: 4 }}>Input Data</h4>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 10 }}>
                  JSON array of objects. Each object is one row with feature columns.
                </p>
                <textarea
                  className="input"
                  style={{
                    minHeight: 220,
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.82rem',
                    resize: 'vertical',
                    lineHeight: 1.6,
                  }}
                  value={inputJson}
                  onChange={(e) => setInputJson(e.target.value)}
                  spellCheck={false}
                />
                {inferError && (
                  <div
                    style={{
                      marginTop: 8,
                      fontSize: '0.8rem',
                      color: 'var(--status-error)',
                    }}
                  >
                    {inferError}
                  </div>
                )}
                <button
                  className="btn btn-primary"
                  style={{ marginTop: 12, width: '100%', justifyContent: 'center' }}
                  disabled={!selectedExecId || inferring}
                  onClick={runInference}
                >
                  {inferring ? 'Running inference…' : 'Run Inference'}
                </button>
              </div>
            </div>

            {/* Output panel */}
            <div className="panel" style={{ padding: 16 }}>
              <h4 style={{ marginBottom: 12 }}>Results</h4>
              {result ? (
                <div>
                  <div className="kv-grid" style={{ marginBottom: 16 }}>
                    <div className="kv-key">Request ID</div>
                    <div className="kv-val mono">
                      {String((result as Record<string, unknown>).request_id ?? '—')}
                    </div>
                    <div className="kv-key">Model</div>
                    <div className="kv-val">
                      <StatusBadge
                        value={
                          String((result as Record<string, unknown>).model_name ?? '—')
                        }
                        variant="accent"
                        dot={false}
                      />
                    </div>
                    <div className="kv-key">Samples</div>
                    <div className="kv-val mono">
                      {String((result as Record<string, unknown>).n_samples ?? '—')}
                    </div>
                  </div>
                  <div className="section-title" style={{ marginBottom: 6 }}>
                    Predictions
                  </div>
                  <div className="code-block">
                    {JSON.stringify(
                      (result as Record<string, unknown>).predictions,
                      null,
                      2
                    )}
                  </div>
                </div>
              ) : (
                <EmptyState
                  title="No results yet"
                  message="Select an execution, provide input data, and click Run Inference."
                />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
