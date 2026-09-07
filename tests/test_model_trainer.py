import pandas as pd

from core.models.trainer import (
    ModelTrainer,
)


def test_trains_regression_models():

    df = pd.DataFrame({
        "grade": [
            20, 22, 25, 28, 30,
            32, 35, 37, 40, 42,
            45, 47, 50, 52, 55,
        ],
        "rainfall": [
            5, 8, 10, 12, 15,
            18, 20, 22, 25, 28,
            30, 32, 35, 38, 40,
        ],
        "production": [
            50, 55, 60, 65, 70,
            75, 80, 85, 90, 95,
            100, 105, 110, 115, 120,
        ],
    })

    trainer = ModelTrainer()

    result = trainer.train_and_evaluate(
        df=df,
        target="production",
        task_type="regression",
        candidates=[
            "linear_regression",
            "random_forest_regressor",
        ],
    )

    assert len(result.evaluations) == 2
    assert result.best_model_name is not None
    assert result.best_score is not None


def test_trains_classification_models():

    df = pd.DataFrame({
        "grade": [
            20, 21, 22, 23, 30,
            31, 32, 33, 40, 41,
            42, 43, 50, 51, 52,
            53,
        ],
        "rainfall": [
            5, 6, 7, 8, 10,
            11, 12, 13, 15, 16,
            17, 18, 20, 21, 22,
            23,
        ],
        "risk": [
            0, 0, 0, 0,
            1, 1, 1, 1,
            0, 0, 0, 0,
            1, 1, 1, 1,
        ],
    })

    trainer = ModelTrainer()

    result = trainer.train_and_evaluate(
        df=df,
        target="risk",
        task_type="classification",
        candidates=[
            "logistic_regression",
            "random_forest_classifier",
        ],
        validation_strategy="stratified_holdout",
    )

    assert len(result.evaluations) == 2
    assert result.best_model_name is not None


def test_group_holdout():

    df = pd.DataFrame({
        "mine_id": [
            "M1", "M1", "M1",
            "M2", "M2", "M2",
            "M3", "M3", "M3",
            "M4", "M4", "M4",
        ],
        "grade": [
            20, 21, 22,
            30, 31, 32,
            40, 41, 42,
            50, 51, 52,
        ],
        "production": [
            50, 55, 60,
            70, 75, 80,
            90, 95, 100,
            110, 115, 120,
        ],
    })

    result = ModelTrainer().train_and_evaluate(
        df=df,
        target="production",
        task_type="regression",
        candidates=[
            "random_forest_regressor",
        ],
        validation_strategy="group_holdout",
        group_column="mine_id",
    )

    assert len(result.evaluations) == 1


def test_missing_target_fails():

    df = pd.DataFrame({
        "feature": [1, 2, 3, 4],
        "target": [10, 20, 30, 40],
    })

    try:

        ModelTrainer().train_and_evaluate(
            df=df,
            target="missing",
            task_type="regression",
            candidates=[
                "linear_regression",
            ],
        )

        assert False

    except ValueError:
        assert True