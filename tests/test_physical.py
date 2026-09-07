import pandas as pd

from data.validation.physical import PhysicalValidator


def test_invalid_borehole_depth():

    df = pd.DataFrame({
        "depth_from_m": [0, 20],
        "depth_to_m": [10, 150],
        "total_depth_m": [100, 100],
    })

    validator = PhysicalValidator()

    issues = validator.validate_boreholes(df)

    assert len(issues) == 1
    assert issues[0].code == "INVALID_BOREHOLE_DEPTH"


def test_negative_production():

    df = pd.DataFrame({
        "actual_production_t": [100, -5],
        "ore_available_t": [200, 300],
    })

    validator = PhysicalValidator()

    issues = validator.validate_production(df)

    assert len(issues) == 1
    assert issues[0].code == "NEGATIVE_PRODUCTION"


def test_invalid_grade():

    df = pd.DataFrame({
        "mn_grade_pct": [30, 45, 120],
    })

    validator = PhysicalValidator()

    issues = validator.validate_grade(df)

    assert len(issues) == 1
    assert issues[0].code == "INVALID_GRADE"