import pandas as pd

from core.pipeline import AyaskPipeline


def test_pipeline_end_to_end_regression():

    df = pd.DataFrame({
        "mine_id": [
            "M1", "M1", "M1",
            "M2", "M2", "M2",
            "M3", "M3", "M3",
            "M4", "M4", "M4",
            "M5", "M5", "M5",
            "M6", "M6", "M6",
        ],
        "latitude": [
            21.1, 21.1, 21.2,
            21.3, 21.3, 21.4,
            21.5, 21.5, 21.6,
            21.7, 21.7, 21.8,
            21.9, 21.9, 22.0,
            22.1, 22.1, 22.2,
        ],
        "longitude": [
            85.1, 85.2, 85.2,
            85.3, 85.4, 85.4,
            85.5, 85.6, 85.6,
            85.7, 85.8, 85.8,
            85.9, 86.0, 86.0,
            86.1, 86.2, 86.2,
        ],
        "ore_grade_mn_pct": [
            28.0, 29.0, 30.0,
            31.0, 32.0, 33.0,
            34.0, 35.0, 36.0,
            37.0, 38.0, 39.0,
            40.0, 41.0, 42.0,
            43.0, 44.0, 45.0,
        ],
        "ore_available_t": [
            100, 105, 110,
            115, 120, 125,
            130, 135, 140,
            145, 150, 155,
            160, 165, 170,
            175, 180, 185,
        ],
        "rainfall_24h_mm": [
            10, 20, 15,
            12, 18, 22,
            8, 14, 19,
            11, 17, 21,
            7, 13, 16,
            9, 15, 20,
        ],
        "production": [
            50, 55, 60,
            65, 70, 75,
            80, 85, 90,
            95, 100, 105,
            110, 115, 120,
            125, 130, 135,
        ],
    })

    pipeline = AyaskPipeline()

    result = pipeline.run(
        df=df,
        target="production",
        task_type="regression",
        validation_strategy="group_holdout",
        group_column="mine_id",
    )

    assert result.target == "production"

    assert result.task_type == "regression"

    assert (
        result.validation_strategy
        == "group_holdout"
    )

    assert len(result.candidates) > 0

    assert len(result.evaluations) > 0

    assert result.best_model_name is not None

    assert result.best_score is not None