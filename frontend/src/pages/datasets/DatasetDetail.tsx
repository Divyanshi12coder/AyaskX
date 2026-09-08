/**
 * src/pages/datasets/DatasetDetail.tsx
 * Dataset detail — overview, profile, feature roles, leakage analysis.
 */

import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Play, ArrowLeft } from 'lucide-react';
import { datasetsApi, pipelinesApi } from '../../api/endpoints';
import { useApi } from '../../hooks/useApi';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { PageHeader } from '../../components/ui/PageHeader';

function fmtBytes(_b: number): string {
  return '';
}

function KVRow({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <>
      <div className="kv-key">{k}</div>
      <div className="kv-val">{v ?? '—'}</div>
    </>
  );
}

// ─── Column Stats Table ───────────────────────────────────────────────────────

function ColumnStatsTable({ columns }: { columns: Record<string, unknown>[] }) {
  if (!columns?.length) return <EmptyState title="No column data" />;
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="data-table">
        <thead>
          <tr>
            <th>Column</th>
            <th>Type</th>
            <th>Missing</th>
            <th>Missing %</th>
            <th>Unique</th>
            <th>Mean</th>
            <th>Std</th>
            <th>Min</th>
            <th>Max</th>
          </tr>
        </thead>
        <tbody>
          {columns.map((col: Record<string, unknown>, i) => (
            <tr key={String(col.name ?? i)}>
              <td className="text-primary">{String(col.name ?? '—')}</td>
              <td>
                <StatusBadge value={String(col.dtype ?? 'unknown')} variant="neutral" dot={false} />
              </td>
              <td className="mono">{String(col.missing_count ?? '—')}</td>
              <td className="mono">
                {col.missing_pct != null
                  ? `${(Number(col.missing_pct) * 100).toFixed(1)}%`
                  : '—'}
              </td>
              <td className="mono">{String(col.unique_count ?? '—')}</td>
              <td className="mono">{col.mean != null ? Number(col.mean).toFixed(3) : '—'}</td>
              <td className="mono">{col.std != null ? Number(col.std).toFixed(3) : '—'}</td>
              <td className="mono">{col.min != null ? String(col.min) : '—'}</td>
              <td className="mono">{col.max != null ? String(col.max) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Feature Roles Panel ──────────────────────────────────────────────────────

function FeatureRolesPanel({ data }: { data: Record<string, unknown> }) {
  const roles = data?.roles as Record<string, string> | undefined;
  const target = String(data?.target ?? '—');
  const features = data?.features as string[] | undefined;
  const dropped = data?.dropped_columns as string[] | undefined;

  return (
    <div>
      <div className="kv-grid mb-4">
        <KVRow k="Target" v={<span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>{target}</span>} />
        <KVRow k="Features" v={features?.length ?? 0} />
        <KVRow k="Dropped" v={dropped?.length ?? 0} />
      </div>

      {roles && Object.keys(roles).length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Column</th>
                <th>Role</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(roles).map(([col, role]) => (
                <tr key={col}>
                  <td className="text-primary">{col}</td>
                  <td>
                    <StatusBadge
                      value={role}
                      variant={
                        role === 'target'
                          ? 'accent'
                          : role === 'feature'
                          ? 'info'
                          : 'neutral'
                      }
                      dot={false}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Leakage Panel ───────────────────────────────────────────────────────────

function LeakagePanel({ data }: { data: Record<string, unknown> }) {
  const risk = String(data?.leakage_risk ?? 'unknown');
  const leaky = data?.leaky_columns as string[] | undefined;

  return (
    <div>
      <div className="kv-grid mb-4">
        <KVRow
          k="Leakage Risk"
          v={
            <StatusBadge
              value={risk}
              variant={
                risk === 'none' || risk === 'low'
                  ? 'success'
                  : risk === 'medium'
                  ? 'warning'
                  : 'error'
              }
            />
          }
        />
        <KVRow k="Leaky Columns" v={leaky?.length ?? 0} />
        {!!data?.details && <KVRow k="Details" v={<span>{String(data.details)}</span>} />}
      </div>
      {leaky && leaky.length > 0 && (
        <div>
          <p style={{ fontSize: '0.83rem', color: 'var(--text-muted)', marginBottom: 8 }}>
            Potential leakage columns:
          </p>
          <div className="flex" style={{ flexWrap: 'wrap', gap: 6 }}>
            {leaky.map((col) => (
              <StatusBadge key={col} value={col} variant="warning" dot={false} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Run Pipeline Modal ───────────────────────────────────────────────────────

function RunPipelinePanel({
  datasetId,
}: {
  datasetId: string;
}) {
  const navigate = useNavigate();
  const [target, setTarget] = useState('');
  const [taskType, setTaskType] = useState('');
  const [maxCandidates, setMaxCandidates] = useState('5');
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setRunning(true);
    setErr(null);
    try {
      const result = await pipelinesApi.run({
        dataset_id: datasetId,
        target: target || undefined,
        task_type: taskType || undefined,
        max_candidates: maxCandidates ? parseInt(maxCandidates) : undefined,
      });
      navigate(`/pipelines/${result.execution_id}`);
    } catch (e) {
      setErr(String(e));
      setRunning(false);
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <label style={{ fontSize: '0.77rem', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
          Target Column (optional — auto-detected if blank)
        </label>
        <input
          className="input"
          placeholder="e.g. target, label, y"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
        />
      </div>
      <div>
        <label style={{ fontSize: '0.77rem', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
          Task Type (optional)
        </label>
        <select
          className="input"
          value={taskType}
          onChange={(e) => setTaskType(e.target.value)}
        >
          <option value="">Auto-detect</option>
          <option value="classification">Classification</option>
          <option value="regression">Regression</option>
          <option value="clustering">Clustering</option>
        </select>
      </div>
      <div>
        <label style={{ fontSize: '0.77rem', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
          Max Model Candidates
        </label>
        <input
          className="input"
          type="number"
          min={1}
          max={20}
          value={maxCandidates}
          onChange={(e) => setMaxCandidates(e.target.value)}
        />
      </div>
      {err && (
        <div style={{ fontSize: '0.8rem', color: 'var(--status-error)' }}>
          {err}
        </div>
      )}
      <button
        className="btn btn-primary"
        disabled={running}
        onClick={submit}
        style={{ marginTop: 4 }}
      >
        <Play size={13} />
        {running ? 'Starting…' : 'Run Pipeline'}
      </button>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function DatasetDetail() {
  const { datasetId } = useParams<{ datasetId: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('overview');

  const { data: dataset, loading: dsLoading, error: dsError } = useApi(
    () => datasetsApi.get(datasetId!),
    [datasetId]
  );

  const { data: profile, loading: profLoading, error: profError } = useApi(
    () => datasetsApi.profile(datasetId!),
    [datasetId]
  );

  const { data: featureRoles } = useApi(
    () => datasetsApi.featureRoles(datasetId!),
    [datasetId]
  );

  const { data: leakage } = useApi(
    () => datasetsApi.leakage(datasetId!),
    [datasetId]
  );

  if (dsLoading) return <LoadingState />;
  if (dsError || !dataset)
    return (
      <ErrorState
        title="Dataset not found"
        message={dsError ?? 'Unknown error'}
        onRetry={() => navigate('/datasets')}
      />
    );

  const TABS = ['overview', 'schema', 'feature-roles', 'leakage', 'run'];

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title={dataset.original_filename}
        subtitle={`Dataset ID: ${dataset.dataset_id}`}
        breadcrumbs={[
          { label: 'Datasets', href: '/datasets' },
          { label: dataset.original_filename },
        ]}
        actions={
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/datasets')}>
            <ArrowLeft size={13} />
            Back
          </button>
        }
      />

      {/* Tabs */}
      <div className="tabs">
        {TABS.map((t) => (
          <div
            key={t}
            className={`tab${activeTab === t ? ' active' : ''}`}
            onClick={() => setActiveTab(t)}
          >
            {t === 'feature-roles' ? 'Feature Roles' : t.charAt(0).toUpperCase() + t.slice(1)}
          </div>
        ))}
      </div>

      <div className="page-body">
        {/* Overview */}
        {activeTab === 'overview' && (
          <div className="grid-2" style={{ alignItems: 'start' }}>
            <div className="panel" style={{ padding: 16 }}>
              <h4 style={{ marginBottom: 12 }}>File Information</h4>
              <div className="kv-grid">
                <KVRow k="Dataset ID" v={<span className="mono">{dataset.dataset_id}</span>} />
                <KVRow k="Filename" v={dataset.original_filename} />
                <KVRow k="Safe Filename" v={<span className="mono">{dataset.safe_filename}</span>} />
                <KVRow k="Size" v={`${((dataset.file_size_bytes ?? 0) / 1024).toFixed(1)} KB`} />
                <KVRow
                  k="Uploaded"
                  v={dataset.uploaded_at ? new Date(dataset.uploaded_at).toLocaleString() : '—'}
                />
              </div>
            </div>

            <div className="panel" style={{ padding: 16 }}>
              <h4 style={{ marginBottom: 12 }}>Dataset Characterization</h4>
              {profLoading ? (
                <LoadingState inline message="Profiling…" />
              ) : profError ? (
                <p className="text-xs text-muted">{profError}</p>
              ) : profile ? (
                <div className="kv-grid">
                  <KVRow k="Rows" v={profile.n_rows != null ? String(profile.n_rows) : '—'} />
                  <KVRow k="Columns" v={profile.n_cols != null ? String(profile.n_cols) : '—'} />
                  <KVRow k="Task Type" v={profile.task_type ?? '—'} />
                  <KVRow k="Target" v={profile.target ?? '—'} />
                  <KVRow k="Missing Values" v={profile.missing_total != null ? String(profile.missing_total) : '—'} />
                  <KVRow k="Duplicate Rows" v={profile.duplicate_rows != null ? String(profile.duplicate_rows) : '—'} />
                </div>
              ) : (
                <EmptyState title="No profile data" message="Profile not yet computed" />
              )}
            </div>
          </div>
        )}

        {/* Schema */}
        {activeTab === 'schema' && (
          profLoading ? (
            <LoadingState />
          ) : profError ? (
            <ErrorState title="Unable to load schema" message={profError} />
          ) : (
            <div className="panel" style={{ padding: 0 }}>
              <ColumnStatsTable columns={(profile?.columns as unknown as Record<string, unknown>[]) ?? []} />
            </div>
          )
        )}

        {/* Feature Roles */}
        {activeTab === 'feature-roles' && (
          <div className="panel" style={{ padding: 16 }}>
            <h4 style={{ marginBottom: 12 }}>Feature Role Detection</h4>
            {featureRoles ? (
              <FeatureRolesPanel data={featureRoles as Record<string, unknown>} />
            ) : (
              <EmptyState title="No feature role data" message="Run a pipeline to compute roles" />
            )}
          </div>
        )}

        {/* Leakage */}
        {activeTab === 'leakage' && (
          <div className="panel" style={{ padding: 16 }}>
            <h4 style={{ marginBottom: 12 }}>Leakage Analysis</h4>
            {leakage ? (
              <LeakagePanel data={leakage as Record<string, unknown>} />
            ) : (
              <EmptyState title="No leakage data" message="Run a pipeline to detect leakage" />
            )}
          </div>
        )}

        {/* Run */}
        {activeTab === 'run' && (
          <div style={{ maxWidth: 480 }}>
            <div className="panel" style={{ padding: 20 }}>
              <h4 style={{ marginBottom: 4 }}>Run Pipeline</h4>
              <p
                style={{ fontSize: '0.83rem', color: 'var(--text-muted)', marginBottom: 16 }}
              >
                Start an autonomous ML pipeline on this dataset. The run will
                execute asynchronously.
              </p>
              <RunPipelinePanel
                datasetId={dataset.dataset_id}

              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
