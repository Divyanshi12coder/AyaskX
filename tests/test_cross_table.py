import pandas as pd

from data.validation.cross_table import CrossDatasetValidator


def test_key_coverage():

    parent = pd.DataFrame({
        "mine_id": ["M1", "M2", "M3"]
    })

    child = pd.DataFrame({
        "mine_id": ["M1", "M2", "M4"]
    })

    validator = CrossDatasetValidator()

    issues = validator.check_key_coverage(
        parent,
        child,
        "mine_id",
        "mines",
        "production",
    )

    assert len(issues) == 1
    assert issues[0].code == "ORPHAN_KEYS"