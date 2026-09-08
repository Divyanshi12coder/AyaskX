/**
 * src/pages/SelfHealing.tsx
 * Self-Healing Center — Engineering incident-resolution console.
 *
 * Shows: incident list (failed executions), full healing chain detail,
 * fault detection → localization → root cause → decision → execution → validation.
 * All data from real API endpoints. Never fakes recovery status.
 */

import React, { useState } from 'react';
import { Heart, RefreshCw } from 'lucide-react';
import { pipelinesApi, recoveryApi } from '../api/endpoints';
import type {
  ExecutionRecord,
  FaultInfo,
  LocalizationInfo,
  RootCauseInfo,
  RecoveryDecision,
  RecoveryResult,
} from '../types';
import { useApi } from '../hooks/useApi';
import { StatusBadge } from '../components/ui/StatusBadge';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { PageHeader } from '../components/ui/PageHeader';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';

// ─── Healing Chain Step ───────────────────────────────────────────────────────

interface StepProps {
  num: number;
  title: string;
  color: string;
  children: React.ReactNode;
  isLast?: boolean;
}

function HealingStep({ num, title, color, children, isLast }: StepProps) {
  return (
    <div className="healing-step">
      <div className="healing-step-connector">
        <div
          className="healing-step-icon"
          style={{ background: `${color}22`, border: `1px solid ${color}44`, color }}
        >
          {num}
        </div>
        {!isLast && <div className="healing-step-line" />}
      </div>
      <div className="healing-step-content">
        <div className="healing-step-title" style={{ color }}>
          {title}
        </div>
        {children}
      </div>
    </div>
  );
}

// ─── Healing Chain ─────────────────────────────────────────────────────────

function HealingChain({ executionId }: { executionId: string }) {
  const { data: report, loading, error, refetch } = useApi(
    () => recoveryApi.selfHealing(executionId),
    [executionId]
  );

  const [triggerOpen, setTriggerOpen] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [triggerResult, setTriggerResult] = useState<string | null>(null);

  async function doTrigger() {
    setTriggering(true);
    setTriggerOpen(false);
    try {
      const r = await recoveryApi.trigger(executionId, true);
      setTriggerResult(`Self-healing triggered: ${JSON.stringify(r)}`);
      refetch();
    } catch (e) {
      setTriggerResult(`Error: ${e}`);
    } finally {
      setTriggering(false);
    }
  }

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  const fault = report?.fault as FaultInfo | undefined;
  const loc = report?.localization as LocalizationInfo | undefined;
  const rc = report?.root_cause as RootCauseInfo | undefined;
  const dec = report?.decision as RecoveryDecision | undefined;
  const res = report?.result as RecoveryResult | undefined;

  return (
    <div>
      <div className="flex items-center justify-between" style={{ marginBottom: 20 }}>
        <h4>Self-Healing Chain</h4>
        <button
          className="btn btn-secondary btn-sm"
          disabled={triggering}
          onClick={() => setTriggerOpen(true)}
        >
          <Heart size={13} />
          {triggering ? 'Triggering…' : 'Trigger Healing'}
        </button>
      </div>

      {triggerResult && (
        <div
          style={{
            padding: '8px 12px',
            marginBottom: 16,
            background: 'var(--bg-elevated)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.8rem',
            fontFamily: 'var(--font-mono)',
            color: 'var(--text-secondary)',
          }}
        >
          {triggerResult}
        </div>
      )}

      <div className="healing-chain">
        {/* Step 1: Failure */}
        <HealingStep num={1} title="FAILURE" color="var(--status-error)">
          <div className="panel" style={{ padding: 14, marginBottom: 4 }}>
            <div className="kv-grid">
              <div className="kv-key">Failed Node</div>
              <div className="kv-val">{fault?.failed_node ?? '—'}</div>
              <div className="kv-key">Error Type</div>
              <div className="kv-val mono">{fault?.error_type ?? '—'}</div>
              <div className="kv-key">Error Message</div>
              <div className="kv-val">{fault?.error_message ?? '—'}</div>
            </div>
          </div>
        </HealingStep>

        {/* Step 2: Detection */}
        <HealingStep num={2} title="FAULT DETECTION" color="var(--status-warning)">
          <div className="panel" style={{ padding: 14, marginBottom: 4 }}>
            <div className="kv-grid">
              <div className="kv-key">Detected</div>
              <div className="kv-val">
                <StatusBadge
                  value={fault?.detected ? 'YES' : 'NO'}
                  variant={fault?.detected ? 'success' : 'neutral'}
                  dot={false}
                />
              </div>
              <div className="kv-key">Fault Type</div>
              <div className="kv-val">{fault?.fault_type ?? '—'}</div>
            </div>
          </div>
        </HealingStep>

        {/* Step 3: Localization */}
        <HealingStep num={3} title="LOCALIZATION" color="var(--status-info)">
          <div className="panel" style={{ padding: 14, marginBottom: 4 }}>
            <div className="kv-grid">
              <div className="kv-key">Observed Node</div>
              <div className="kv-val">{loc?.observed_node ?? '—'}</div>
              <div className="kv-key">Fault Boundary</div>
              <div className="kv-val">{loc?.fault_boundary ?? '—'}</div>
              <div className="kv-key">Downstream Impact</div>
              <div className="kv-val">
                {loc?.downstream_impact?.join(', ') ?? '—'}
              </div>
            </div>
          </div>
        </HealingStep>

        {/* Step 4: Root Cause */}
        <HealingStep num={4} title="ROOT CAUSE ANALYSIS" color="var(--accent)">
          <div className="panel" style={{ padding: 14, marginBottom: 4 }}>
            <div className="kv-grid">
              <div className="kv-key">Root Cause</div>
              <div className="kv-val">{rc?.root_cause ?? '—'}</div>
              <div className="kv-key">Explanation</div>
              <div className="kv-val">{rc?.explanation ?? '—'}</div>
            </div>
            {rc?.contributing_factors && rc.contributing_factors.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <div className="section-title" style={{ marginBottom: 6 }}>Contributing Factors</div>
                {rc.contributing_factors.map((f, i) => (
                  <div
                    key={i}
                    style={{
                      fontSize: '0.8rem',
                      color: 'var(--text-secondary)',
                      padding: '3px 0',
                      borderBottom: '1px solid var(--border-subtle)',
                    }}
                  >
                    · {f}
                  </div>
                ))}
              </div>
            )}
          </div>
        </HealingStep>

        {/* Step 5: Recovery Decision */}
        <HealingStep num={5} title="RECOVERY DECISION" color="var(--status-warning)">
          <div className="panel" style={{ padding: 14, marginBottom: 4 }}>
            <div className="kv-grid">
              <div className="kv-key">Decision</div>
              <div className="kv-val">{dec?.decision ?? '—'}</div>
              <div className="kv-key">Strategy</div>
              <div className="kv-val">{dec?.strategy ?? '—'}</div>
              <div className="kv-key">Last Good Checkpoint</div>
              <div className="kv-val mono">{dec?.checkpoint_id ?? '—'}</div>
              <div className="kv-key">Last Good Node</div>
              <div className="kv-val">{dec?.last_good_node ?? '—'}</div>
              <div className="kv-key">Risk Level</div>
              <div className="kv-val">
                {dec?.risk_level ? (
                  <StatusBadge
                    value={dec.risk_level}
                    variant={dec.risk_level === 'low' ? 'success' : dec.risk_level === 'high' ? 'error' : 'warning'}
                  />
                ) : '—'}
              </div>
            </div>
          </div>
        </HealingStep>

        {/* Step 6: Validation */}
        <HealingStep num={6} title="RECOVERY VALIDATION" color="var(--status-success)" isLast>
          <div className="panel" style={{ padding: 14 }}>
            <div className="kv-grid">
              <div className="kv-key">Validation Status</div>
              <div className="kv-val">
                {res?.validation_status ? (
                  <StatusBadge value={res.validation_status} />
                ) : (
                  <StatusBadge value="pending" variant="neutral" />
                )}
              </div>
              <div className="kv-key">Recovery Success</div>
              <div className="kv-val">
                {res?.success != null ? (
                  <StatusBadge
                    value={res.success ? 'YES' : 'NO'}
                    variant={res.success ? 'success' : 'error'}
                    dot={false}
                  />
                ) : (
                  '—'
                )}
              </div>
              <div className="kv-key">Message</div>
              <div className="kv-val">{res?.message ?? '—'}</div>
              <div className="kv-key">Recovered At</div>
              <div className="kv-val mono">
                {res?.recovered_at ? new Date(res.recovered_at).toLocaleString() : '—'}
              </div>
            </div>
          </div>
        </HealingStep>
      </div>

      <ConfirmDialog
        open={triggerOpen}
        title="Trigger Self-Healing"
        message={`Run the self-healing pipeline for execution ${executionId.slice(0, 16)}…? This will attempt fault recovery from the last known good checkpoint.`}
        confirmLabel="Trigger"
        onConfirm={doTrigger}
        onCancel={() => setTriggerOpen(false)}
      />
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function SelfHealing() {
  const [selectedExecId, setSelectedExecId] = useState<string | null>(null);

  const { data, loading, error, refetch } = useApi(() => pipelinesApi.list());

  const allExecs: ExecutionRecord[] = [...(data ?? [])].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Self-Healing Center"
        subtitle="Autonomous fault detection, root-cause analysis, and recovery"
        breadcrumbs={[{ label: 'AyaskX' }, { label: 'Self-Healing' }]}
        actions={
          <button className="btn btn-ghost btn-sm" onClick={refetch}>
            <RefreshCw size={13} />
          </button>
        }
      />

      <div style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>
        {/* Incident list */}
        <div
          style={{
            width: 320,
            borderRight: '1px solid var(--border)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            flexShrink: 0,
          }}
        >
          <div
            style={{
              padding: '8px 14px',
              borderBottom: '1px solid var(--border)',
              fontSize: '0.77rem',
              color: 'var(--text-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              fontWeight: 600,
            }}
          >
            All Executions ({allExecs.length})
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {loading ? (
              <LoadingState />
            ) : error ? (
              <ErrorState message={error} onRetry={refetch} />
            ) : allExecs.length === 0 ? (
              <EmptyState title="No executions" />
            ) : (
              allExecs.map((ex) => (
                <div
                  key={ex.execution_id}
                  onClick={() => setSelectedExecId(ex.execution_id)}
                  style={{
                    padding: '10px 14px',
                    borderBottom: '1px solid var(--border-subtle)',
                    cursor: 'pointer',
                    background:
                      selectedExecId === ex.execution_id
                        ? 'var(--accent-dim)'
                        : undefined,
                    borderLeft:
                      selectedExecId === ex.execution_id
                        ? '2px solid var(--accent)'
                        : '2px solid transparent',
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.78rem',
                        color: 'var(--text-secondary)',
                      }}
                    >
                      {ex.execution_id.slice(0, 14)}…
                    </span>
                    <StatusBadge value={ex.status} />
                  </div>
                  <div
                    style={{
                      fontSize: '0.72rem',
                      color: 'var(--text-muted)',
                      marginTop: 3,
                    }}
                  >
                    {ex.dataset_path ?? ex.dataset_id}
                  </div>
                  {ex.status === 'failed' && ex.message && (
                    <div
                      style={{
                        fontSize: '0.72rem',
                        color: 'var(--status-error)',
                        marginTop: 2,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {ex.message}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Detail */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          {selectedExecId ? (
            <HealingChain executionId={selectedExecId} />
          ) : (
            <EmptyState
              title="Select an execution"
              message="Select any execution on the left to view its self-healing chain."
              icon={<Heart size={40} />}
            />
          )}
        </div>
      </div>
    </div>
  );
}
