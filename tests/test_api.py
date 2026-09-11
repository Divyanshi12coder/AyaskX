"""
tests/test_api.py
-----------------
Comprehensive API tests for AyaskX FastAPI layer (Phase N).

Tests cover:
- /health and /ready
- Dataset upload (valid, too large, wrong type)
- Dataset metadata, profile, feature-roles, leakage
- Pipeline run (submit → queued)
- Pipeline listing, lookup, status, nodes, checkpoints
- Model endpoints (candidates, model, metrics, strategy)
- Inference endpoint (requires succeeded status)
- Recovery/fault endpoints (before/after self-healing trigger)
- Audit endpoints
- Error envelope shape on all 4xx/5xx responses
- CORS configuration

Does NOT retest frozen core logic — that is covered by existing 483 tests.
"""

from __future__ import annotations

import io
import os
import tempfile
import warnings
from pathlib import Path

import pandas as pd
import pytest

# Suppress starlette/httpx deprecation warning in test output
warnings.filterwarnings("ignore", category=DeprecationWarning, module="fastapi")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tmp_store(tmp_path_factory):
    """Isolated filesystem store for the API under test."""
    return tmp_path_factory.mktemp("api_store")


@pytest.fixture(scope="module")
def client(tmp_store):
    """TestClient with isolated store/upload dirs."""
    os.environ["AYASKX_STORE_ROOT"] = str(tmp_store / "store")
    os.environ["AYASKX_UPLOAD_TMP"] = str(tmp_store / "uploads")
    os.environ["AYASKX_CHECKPOINT_ROOT"] = str(tmp_store / "checkpoints")
    os.environ["AYASKX_ARTIFACT_ROOT"] = str(tmp_store / "artifacts")
    os.environ["AYASKX_CORS_ORIGINS"] = "http://localhost:3000"
    os.environ["AYASKX_MAX_UPLOAD_MB"] = "1"

    # Reset singletons so fresh settings are picked up
    from api import config
    config.get_settings.cache_clear()
    from api import dependencies
    dependencies.reset_singletons()

    from api.main import create_app
    from fastapi.testclient import TestClient
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture(scope="module")
def small_csv_bytes():
    """A small valid CSV dataset."""
    df = pd.DataFrame({
        "age": [25, 30, 35, 40, 45, 50],
        "income": [50000, 60000, 70000, 80000, 90000, 100000],
        "label": [0, 1, 0, 1, 0, 1],
    })
    return df.to_csv(index=False).encode()


@pytest.fixture(scope="module")
def uploaded_dataset_id(client, small_csv_bytes):
    """Upload a dataset and return its dataset_id."""
    resp = client.post(
        "/v1/datasets/upload",
        files={"file": ("test_data.csv", io.BytesIO(small_csv_bytes), "text/csv")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "success"
    return data["data"]["dataset_id"]


@pytest.fixture(scope="module")
def queued_execution_id(client, uploaded_dataset_id):
    """Submit a pipeline run and return execution_id."""
    resp = client.post(
        "/v1/pipelines/run",
        json={"dataset_id": uploaded_dataset_id, "target": "label"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "success"
    return data["data"]["execution_id"]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def assert_envelope(resp, *, status: str = "success"):
    """Assert response has standard AyaskX envelope shape."""
    assert "status" in resp.json(), f"Missing 'status' in response: {resp.json()}"
    assert resp.json()["status"] == status, \
        f"Expected status={status!r}, got {resp.json()['status']!r}: {resp.json()}"
    assert "timestamp" in resp.json()
    assert "errors" in resp.json() or status == "success"


# ---------------------------------------------------------------------------
# Health / Ready
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["service"] == "ayaskx-api"
        assert "started_at" in body
        assert "timestamp" in body

    def test_ready_initializes_and_verifies_database(self, client):
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
        assert response.json()["database"] == "ready"

    def test_ready_200(self, client):
        r = client.get("/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ready"

    def test_system_status_reports_real_dependencies(self, client):
        response = client.get("/v1/system/status")
        assert response.status_code == 200
        assert_envelope(response)
        data = response.json()["data"]
        assert data["api"]["status"] == "ready"
        assert data["database"]["status"] == "ready"
        assert data["storage"]["uploads_ready"] is True
        assert data["runtime"]["authentication"] == "not_configured"

    def test_observability_and_integrity_endpoints(self, client):
        summary = client.get("/v1/observability/summary")
        assert summary.status_code == 200
        assert_envelope(summary)
        assert "total_executions" in summary.json()["data"]

        events = client.get("/v1/observability/events?limit=1")
        assert events.status_code == 200
        assert_envelope(events)

        integrity = client.get("/v1/integrity/artifacts")
        assert integrity.status_code == 200
        assert_envelope(integrity)


# ---------------------------------------------------------------------------
# Dataset upload
# ---------------------------------------------------------------------------

class TestDatasetUpload:
    def test_upload_valid_csv(self, client, small_csv_bytes):
        r = client.post(
            "/v1/datasets/upload",
            files={"file": ("upload.csv", io.BytesIO(small_csv_bytes), "text/csv")},
        )
        assert r.status_code == 201
        assert_envelope(r, status="success")
        data = r.json()["data"]
        assert "dataset_id" in data
        assert data["rows"] == 6
        assert data["columns"] == 3
        assert "age" in data["column_names"]
        assert "fingerprint" in data

    def test_upload_parquet(self, client):
        pytest.importorskip("pyarrow", reason="pyarrow not installed")
        df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)
        r = client.post(
            "/v1/datasets/upload",
            files={"file": ("data.parquet", buf, "application/octet-stream")},
        )
        assert r.status_code == 201
        assert r.json()["data"]["rows"] == 2

    def test_upload_wrong_extension(self, client):
        r = client.post(
            "/v1/datasets/upload",
            files={"file": ("evil.exe", io.BytesIO(b"bad"), "application/octet-stream")},
        )
        assert r.status_code == 415
        assert_envelope(r, status="error")
        assert len(r.json()["errors"]) > 0

    def test_upload_too_large(self, client):
        # max is 1MB; send >1MB
        big = b"x,y\n" + b"1,2\n" * 600_000  # ~7MB
        r = client.post(
            "/v1/datasets/upload",
            files={"file": ("big.csv", io.BytesIO(big), "text/csv")},
        )
        assert r.status_code == 413
        assert_envelope(r, status="error")

    def test_upload_tsv(self, client):
        tsv = b"a\tb\n1\t2\n3\t4\n"
        r = client.post(
            "/v1/datasets/upload",
            files={"file": ("data.tsv", io.BytesIO(tsv), "text/tab-separated-values")},
        )
        assert r.status_code == 201
        assert r.json()["data"]["columns"] == 2

    def test_upload_malformed_csv_is_rejected(self, client):
        r = client.post(
            "/v1/datasets/upload",
            files={"file": ("bad.csv", io.BytesIO(b'column\n"unterminated'), "text/csv")},
        )
        assert r.status_code == 422
        assert_envelope(r, status="error")


# ---------------------------------------------------------------------------
# Dataset retrieval
# ---------------------------------------------------------------------------

class TestDatasetRetrieval:
    def test_list_datasets(self, client, uploaded_dataset_id):
        r = client.get("/v1/datasets")
        assert r.status_code == 200
        assert_envelope(r)
        ids = [d["dataset_id"] for d in r.json()["data"]]
        assert uploaded_dataset_id in ids

    def test_get_dataset(self, client, uploaded_dataset_id):
        r = client.get(f"/v1/datasets/{uploaded_dataset_id}")
        assert r.status_code == 200
        assert_envelope(r)
        assert r.json()["data"]["dataset_id"] == uploaded_dataset_id

    def test_get_dataset_404(self, client):
        r = client.get("/v1/datasets/nonexistent-id")
        assert r.status_code == 404
        assert_envelope(r, status="error")

    def test_get_profile(self, client, uploaded_dataset_id):
        r = client.get(f"/v1/datasets/{uploaded_dataset_id}/profile")
        assert r.status_code == 200
        assert_envelope(r)
        profile = r.json()["data"]
        assert profile["n_rows"] == 6
        assert profile["n_cols"] == 3
        assert isinstance(profile["columns"], list)
        assert profile["duplicate_rows"] == 0
        assert profile["target"] == "label"

    def test_get_feature_roles(self, client, uploaded_dataset_id):
        r = client.get(f"/v1/datasets/{uploaded_dataset_id}/feature-roles")
        assert r.status_code == 200
        assert_envelope(r)
        assert r.json()["data"]["roles"]["age"] == "numeric"

    def test_get_leakage(self, client, uploaded_dataset_id):
        r = client.get(f"/v1/datasets/{uploaded_dataset_id}/leakage")
        assert r.status_code == 200
        assert_envelope(r)
        assert r.json()["data"]["leakage_risk"] == "none"

    def test_profile_404(self, client):
        r = client.get("/v1/datasets/no-such/profile")
        assert r.status_code == 404
        assert_envelope(r, status="error")

    def test_feature_roles_404(self, client):
        r = client.get("/v1/datasets/no-such/feature-roles")
        assert r.status_code == 404
        assert_envelope(r, status="error")

    def test_leakage_404(self, client):
        r = client.get("/v1/datasets/no-such/leakage")
        assert r.status_code == 404
        assert_envelope(r, status="error")


# ---------------------------------------------------------------------------
# Pipeline run submission
# ---------------------------------------------------------------------------

class TestPipelineRun:
    def test_run_pipeline_queued(self, client, uploaded_dataset_id):
        r = client.post(
            "/v1/pipelines/run",
            json={"dataset_id": uploaded_dataset_id, "target": "label"},
        )
        assert r.status_code == 202
        assert_envelope(r)
        data = r.json()["data"]
        assert "execution_id" in data
        assert data["status"] == "queued"
        assert r.json()["execution_id"] == data["execution_id"]

    def test_run_pipeline_unknown_dataset(self, client):
        r = client.post(
            "/v1/pipelines/run",
            json={"dataset_id": "does-not-exist"},
        )
        assert r.status_code == 404
        assert_envelope(r, status="error")

    def test_run_pipeline_no_body(self, client):
        r = client.post("/v1/pipelines/run", json={})
        assert r.status_code == 422
        assert_envelope(r, status="error")


# ---------------------------------------------------------------------------
# Pipeline lookup
# ---------------------------------------------------------------------------

class TestPipelineLookup:
    def test_list_pipelines(self, client, queued_execution_id):
        r = client.get("/v1/pipelines")
        assert r.status_code == 200
        assert_envelope(r)
        ids = [e["execution_id"] for e in r.json()["data"]]
        assert queued_execution_id in ids

    def test_get_pipeline(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}")
        assert r.status_code == 200
        assert_envelope(r)
        assert r.json()["data"]["execution_id"] == queued_execution_id

    def test_get_pipeline_404(self, client):
        r = client.get("/v1/pipelines/nope")
        assert r.status_code == 404
        assert_envelope(r, status="error")

    def test_get_status_queued_or_later(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/status")
        assert r.status_code == 200
        assert_envelope(r)
        st = r.json()["data"]["status"]
        assert st in ("queued", "running", "succeeded", "failed")

    def test_get_status_404(self, client):
        r = client.get("/v1/pipelines/nope/status")
        assert r.status_code == 404
        assert_envelope(r, status="error")

    def test_get_nodes(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/nodes")
        assert r.status_code == 200
        assert_envelope(r)
        assert isinstance(r.json()["data"], list)

    def test_get_nodes_404(self, client):
        r = client.get("/v1/pipelines/nope/nodes")
        assert r.status_code == 404

    def test_get_node_404(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/nodes/nonexistent-node")
        assert r.status_code == 404
        assert_envelope(r, status="error")

    def test_get_checkpoints(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/checkpoints")
        assert r.status_code == 200
        assert_envelope(r)
        assert isinstance(r.json()["data"], list)

    def test_get_checkpoints_404(self, client):
        r = client.get("/v1/pipelines/nope/checkpoints")
        assert r.status_code == 404

    def test_get_checkpoint_404(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/checkpoints/ckpt-999")
        assert r.status_code == 404
        assert_envelope(r, status="error")


# ---------------------------------------------------------------------------
# Model endpoints
# ---------------------------------------------------------------------------

class TestModelEndpoints:
    def test_get_candidates(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/candidates")
        assert r.status_code == 200
        assert_envelope(r)

    def test_get_model(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/model")
        assert r.status_code == 200
        assert_envelope(r)

    def test_get_metrics(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/model/metrics")
        assert r.status_code == 200
        assert_envelope(r)

    def test_get_validation_strategy(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/model/validation-strategy")
        assert r.status_code == 200
        assert_envelope(r)

    def test_model_endpoints_404(self, client):
        for path in ("candidates", "model", "model/metrics", "model/validation-strategy"):
            r = client.get(f"/v1/pipelines/nope/{path}")
            assert r.status_code == 404, f"Expected 404 for /v1/pipelines/nope/{path}"
            assert_envelope(r, status="error")


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

class TestInference:
    def test_predict_on_non_succeeded_returns_422(self, client, queued_execution_id):
        # Execution is queued/running, not succeeded yet
        r = client.post(
            f"/v1/pipelines/{queued_execution_id}/predict",
            json={"rows": [{"age": 30, "income": 65000}]},
        )
        # Should be 422 (not succeeded) or 200 if it finished fast
        assert r.status_code in (200, 422, 404)

    def test_predict_unknown_execution(self, client):
        r = client.post(
            "/v1/pipelines/nope/predict",
            json={"rows": [{"age": 30}]},
        )
        assert r.status_code == 404
        assert_envelope(r, status="error")

    def test_predict_bad_body(self, client, queued_execution_id):
        r = client.post(
            f"/v1/pipelines/{queued_execution_id}/predict",
            json={"not_rows": "wrong"},
        )
        assert r.status_code == 422
        assert_envelope(r, status="error")


# ---------------------------------------------------------------------------
# Recovery / Fault endpoints
# ---------------------------------------------------------------------------

class TestRecoveryEndpoints:
    def test_get_fault_returns_200_or_none(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/fault")
        assert r.status_code == 200
        assert_envelope(r)

    def test_get_localization(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/fault/localization")
        assert r.status_code == 200
        assert_envelope(r)

    def test_get_root_cause(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/fault/root-cause")
        assert r.status_code == 200
        assert_envelope(r)

    def test_get_recovery_decision(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/recovery/decision")
        assert r.status_code == 200
        assert_envelope(r)

    def test_get_repair_plan(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/recovery/plan")
        assert r.status_code == 200
        assert_envelope(r)

    def test_get_recovery_result(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/recovery/result")
        assert r.status_code == 200
        assert_envelope(r)

    def test_get_self_healing(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/self-healing")
        assert r.status_code == 200
        assert_envelope(r)

    def test_fault_endpoints_404(self, client):
        for path in (
            "fault",
            "fault/localization",
            "fault/root-cause",
            "recovery/decision",
            "recovery/plan",
            "recovery/result",
            "self-healing",
        ):
            r = client.get(f"/v1/pipelines/nope/{path}")
            assert r.status_code == 404, f"Expected 404 for {path}"
            assert_envelope(r, status="error")

    def test_trigger_self_healing(self, client, queued_execution_id):
        r = client.post(
            f"/v1/pipelines/{queued_execution_id}/self-healing/trigger",
            json={"auto_approve_low_risk": False},
        )
        # Should return 202 with a self-healing result dict
        assert r.status_code in (200, 202, 404)
        if r.status_code in (200, 202):
            assert_envelope(r)

    def test_trigger_self_healing_404(self, client):
        r = client.post(
            "/v1/pipelines/nope/self-healing/trigger",
            json={"auto_approve_low_risk": False},
        )
        assert r.status_code == 404
        assert_envelope(r, status="error")


# ---------------------------------------------------------------------------
# Audit endpoints
# ---------------------------------------------------------------------------

class TestAuditEndpoints:
    def test_list_audit_events(self, client):
        r = client.get("/v1/audit/events")
        assert r.status_code == 200
        assert_envelope(r)
        assert isinstance(r.json()["data"], list)

    def test_list_audit_events_filtered(self, client, queued_execution_id):
        r = client.get(f"/v1/audit/events?execution_id={queued_execution_id}")
        assert r.status_code == 200
        assert_envelope(r)

    def test_get_audit_event_404(self, client):
        r = client.get("/v1/audit/events/nonexistent-event-id")
        assert r.status_code == 404
        assert_envelope(r, status="error")

    def test_get_execution_audit(self, client, queued_execution_id):
        r = client.get(f"/v1/pipelines/{queued_execution_id}/audit")
        assert r.status_code == 200
        assert_envelope(r)
        assert isinstance(r.json()["data"], list)

    def test_get_execution_audit_404(self, client):
        r = client.get("/v1/pipelines/nope/audit")
        assert r.status_code == 404
        assert_envelope(r, status="error")


# ---------------------------------------------------------------------------
# Error envelope shape
# ---------------------------------------------------------------------------

class TestErrorEnvelopeShape:
    def test_404_has_correct_shape(self, client):
        r = client.get("/v1/pipelines/no-such-exec")
        assert r.status_code == 404
        body = r.json()
        assert body["status"] == "error"
        assert isinstance(body["errors"], list)
        assert len(body["errors"]) > 0
        assert "timestamp" in body
        assert body["data"] is None

    def test_422_has_correct_shape(self, client):
        r = client.post("/v1/pipelines/run", json={})
        assert r.status_code == 422
        body = r.json()
        assert body["status"] == "error"
        assert isinstance(body["errors"], list)

    def test_415_on_bad_file_type(self, client):
        r = client.post(
            "/v1/datasets/upload",
            files={"file": ("script.py", io.BytesIO(b"import os"), "text/x-python")},
        )
        assert r.status_code == 415
        body = r.json()
        assert body["status"] == "error"

    def test_413_on_oversized_upload(self, client):
        big = b"x,y\n" + b"1,2\n" * 600_000
        r = client.post(
            "/v1/datasets/upload",
            files={"file": ("huge.csv", io.BytesIO(big), "text/csv")},
        )
        assert r.status_code == 413
        body = r.json()
        assert body["status"] == "error"


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

class TestCORS:
    def test_cors_header_present(self, client):
        r = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )
        assert r.status_code == 200
        assert "access-control-allow-origin" in r.headers
