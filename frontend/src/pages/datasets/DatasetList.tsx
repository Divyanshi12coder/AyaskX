/**
 * src/pages/datasets/DatasetList.tsx
 * Dataset registry — list, upload, filter.
 */

import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, Database, RefreshCw } from 'lucide-react';
import { datasetsApi } from '../../api/endpoints';
import type { DatasetRecord } from '../../types';
import { useApi } from '../../hooks/useApi';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { LoadingState } from '../../components/ui/LoadingState';
import { ErrorState } from '../../components/ui/ErrorState';
import { EmptyState } from '../../components/ui/EmptyState';
import { PageHeader } from '../../components/ui/PageHeader';

function fmtBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 ** 2) return `${(b / 1024).toFixed(1)} KB`;
  if (b < 1024 ** 3) return `${(b / 1024 ** 2).toFixed(1)} MB`;
  return `${(b / 1024 ** 3).toFixed(2)} GB`;
}

export default function DatasetList() {
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  const { data, loading, error, refetch } = useApi(() => datasetsApi.list());

  const datasets: DatasetRecord[] = data ?? [];
  const filtered = datasets.filter(
    (d) =>
      !search ||
      d.original_filename.toLowerCase().includes(search.toLowerCase()) ||
      d.dataset_id.toLowerCase().includes(search.toLowerCase())
  );

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadProgress(0);
    setUploadError(null);
    try {
      await datasetsApi.upload(file, setUploadProgress);
      refetch();
    } catch (err) {
      setUploadError(String(err));
    } finally {
      setUploading(false);
      setUploadProgress(0);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader
        title="Dataset Registry"
        subtitle={`${datasets.length} dataset${datasets.length !== 1 ? 's' : ''} registered`}
        breadcrumbs={[{ label: 'AyaskX' }, { label: 'Datasets' }]}
        actions={
          <>
            <button className="btn btn-ghost btn-sm" onClick={refetch}>
              <RefreshCw size={13} />
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.tsv,.parquet"
              style={{ display: 'none' }}
              onChange={handleUpload}
            />
            <button
              className="btn btn-primary btn-sm"
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
            >
              <Upload size={13} />
              {uploading ? `Uploading ${uploadProgress}%` : 'Upload Dataset'}
            </button>
          </>
        }
      />

      {/* Filter bar */}
      <div className="filter-bar">
        <div className="filter-search">
          <Database size={14} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            className="input"
            style={{ paddingLeft: 32 }}
            placeholder="Search datasets..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <span style={{ fontSize: '0.77rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>
          Accepts: CSV, TSV, Parquet (max 200MB)
        </span>
      </div>

      {uploadError && (
        <div
          style={{
            padding: '8px 20px',
            background: 'var(--status-error-dim)',
            borderBottom: '1px solid rgba(239,68,68,0.25)',
            fontSize: '0.83rem',
            color: 'var(--status-error)',
          }}
        >
          Upload failed: {uploadError}
          <button
            className="btn btn-ghost btn-sm"
            style={{ marginLeft: 8 }}
            onClick={() => setUploadError(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      <div style={{ flex: 1, overflow: 'auto' }}>
        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState
            title="Unable to load datasets"
            message={error}
            onRetry={refetch}
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No datasets found"
            message={
              search
                ? 'No datasets match your search.'
                : 'Upload a CSV, TSV, or Parquet file to get started.'
            }
            action={
              !search && (
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => fileRef.current?.click()}
                >
                  <Upload size={13} />
                  Upload Dataset
                </button>
              )
            }
          />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Dataset ID</th>
                <th>Filename</th>
                <th>Size</th>
                <th>Uploaded</th>
                <th>Type</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((ds) => (
                <tr
                  key={ds.dataset_id}
                  onClick={() => navigate(`/datasets/${ds.dataset_id}`)}
                >
                  <td className="mono">{ds.dataset_id.slice(0, 16)}…</td>
                  <td className="text-primary">{ds.original_filename}</td>
                  <td className="mono">{fmtBytes(ds.file_size_bytes ?? 0)}</td>
                  <td className="mono" style={{ fontSize: '0.77rem' }}>
                    {ds.uploaded_at
                      ? new Date(ds.uploaded_at).toLocaleString()
                      : '—'}
                  </td>
                  <td>
                    <StatusBadge
                      value={
                        ds.original_filename?.endsWith('.parquet')
                          ? 'parquet'
                          : 'csv'
                      }
                      variant="neutral"
                      dot={false}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
