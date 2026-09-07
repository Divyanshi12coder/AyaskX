import pandas as pd

from core.models.candidates import (
    ModelCandidateGenerator,
)


def test_generates_regression_candidates():

    df = pd.DataFrame({
        "grade": [28, 30, 32, 35, 37],
        "rainfall": [10, 20, 15, 5, 12],
        "production": [100, 120, 130, 150, 160],
    })

    report = ModelCandidateGenerator().generate(
        df,
        target="production",
    )

    assert report.task == "regression"

    names = {
        candidate.name
        for candidate in report.candidates
    }

    assert "linear_regression" in names
    assert "random_forest_regressor" in names
    assert "gradient_boosting_regressor" in names


def test_generates_classification_candidates():

    df = pd.DataFrame({
        "grade": [28, 30, 32, 35, 37],
        "rainfall": [10, 20, 15, 5, 12],
        "risk": [0, 1, 0, 1, 1],
    })

    report = ModelCandidateGenerator().generate(
        df,
        target="risk",
    )

    assert report.task == "classification"

    names = {
        candidate.name
        for candidate in report.candidates
    }

    assert "logistic_regression" in names
    assert "random_forest_classifier" in names
    assert "gradient_boosting_classifier" in names


def test_string_target_is_classification():

    df = pd.DataFrame({
        "grade": [28, 30, 32, 35],
        "prospectivity": [
            "low",
            "high",
            "medium",
            "high",
        ],
    })

    report = ModelCandidateGenerator().generate(
        df,
        target="prospectivity",
    )

    assert report.task == "classification"


def test_large_dataset_gets_extra_candidate():

    df = pd.DataFrame({
        "feature": range(500),
        "target": range(500),
    })

    report = ModelCandidateGenerator().generate(
        df,
        target="target",
    )

    names = {
        candidate.name
        for candidate in report.candidates
    }

    assert (
        "hist_gradient_boosting_regressor"
        in names
    )


def test_missing_target_fails():

    df = pd.DataFrame({
        "feature": [1, 2, 3],
    })

    try:
        ModelCandidateGenerator().generate(
            df,
            target="missing",
        )
        assert False
    except ValueError:
        assert True