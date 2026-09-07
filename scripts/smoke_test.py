"""
Phase O: Real Dataset Smoke Test
---------------------------------
Uses SIH26009_DATA datasets to verify AyaskXOrchestrator
operates without any hardcoded dataset-specific assumptions.
Sampling is used; full production-scale training is NOT required.
"""
import sys
sys.path.insert(0, r"c:\Users\HP\Desktop\AyasK\Ayask_Foundation_v0_1")

import pandas as pd
import tempfile
from pathlib import Path

from core.platform.orchestrator import AyaskXOrchestrator

DATA_ROOT = Path(r"c:\Users\HP\Desktop\AyasK\Ayask_Foundation_v0_1\source_friend_v1\SIH26009_DATA\ml_ready")

DATASETS = [
    # (filename, target, task_type)
    ("prospectivity_train.csv", None, None),           # auto-detect: prospectivity_label / classification
    ("production_train.csv", "actual_production_t", "regression"),   # explicit: regression target
    ("equipment_train.csv", "failure_next_24h", "classification"),   # explicit: binary classification
]


SAMPLE_N = 500  # keep tests fast; max rows per dataset


def run_smoke(path: Path, target=None, task_type=None, label=""):
    print(f"\n{'='*60}")
    print(f"  DATASET: {label or path.name}")
    print(f"{'='*60}")

    df = pd.read_csv(path, nrows=SAMPLE_N)
    print(f"  Shape: {df.shape}")
    print(f"  Columns: {list(df.columns)}")

    with tempfile.TemporaryDirectory() as td:
        orch = AyaskXOrchestrator(checkpoint_root=td+"/c", artifact_root=td+"/a")
        result = orch.run(df, dataset_path=str(path), target=target, task_type=task_type, save_artifact=False)

    summary = result.to_summary()
    print(f"  Execution ID:        {summary['execution_id']}")
    print(f"  Fingerprint:         {summary['dataset_fingerprint']}")
    print(f"  Task type:           {summary['task_type']}")
    print(f"  Target:              {summary['target']}")
    print(f"  Validation strategy: {summary['validation_strategy']}")
    print(f"  Candidates:          {summary['candidates']}")
    print(f"  Best model:          {summary['best_model']}")
    print(f"  Best score:          {summary['best_score']}")
    print(f"  Success:             {summary['success']}")
    if summary['warnings']:
        print(f"  Warnings ({len(summary['warnings'])}):")
        for w in summary['warnings'][:5]:
            print(f"    - {w}")
    print(f"  Alerts:              {summary['alerts']}")

    # Structural checks
    errors = []
    if not summary['execution_id']:
        errors.append("No execution ID")
    if not summary['dataset_fingerprint'].startswith("sha:"):
        errors.append("Bad fingerprint")
    if result.characterization is None:
        errors.append("No characterization")
    if result.task_detection is None:
        errors.append("No task detection")
    if result.feature_roles is None:
        errors.append("No feature roles")
    if result.leakage_report is None:
        errors.append("No leakage report")
    if result.preprocessing_plan is None:
        errors.append("No preprocessing plan")
    if result.validation_strategy is None:
        errors.append("No validation strategy")
    if result.candidate_report is None:
        errors.append("No candidate report")
    if errors:
        raise AssertionError("; ".join(errors))
    print("  [OK] All structural assertions passed")
    return result


if __name__ == "__main__":
    results = []
    for filename, target, task_type in DATASETS:
        path = DATA_ROOT / filename
        if not path.exists():
            print(f"\nSKIPPED (not found): {filename}")
            continue
        try:
            r = run_smoke(path, target=target, task_type=task_type, label=filename)
            results.append((filename, "PASSED", r.to_summary()))
        except Exception as exc:
            import traceback
            print(f"\nFAILED: {filename}")
            traceback.print_exc()
            results.append((filename, "FAILED", str(exc)))

    print(f"\n{'='*60}")
    print("  SMOKE TEST SUMMARY")
    print(f"{'='*60}")
    for name, status, _ in results:
        print(f"  {status:8s}  {name}")
    passed = sum(1 for _, s, _ in results if s == "PASSED")
    print(f"\n  {passed}/{len(results)} datasets processed successfully")
