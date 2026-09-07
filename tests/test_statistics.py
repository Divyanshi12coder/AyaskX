import pandas as pd

from eda.statistics import StatisticalAnalyzer


def test_numeric_statistics():

    df = pd.DataFrame({
        "grade": [
            20.0,
            25.0,
            30.0,
            35.0,
            100.0,
        ]
    })

    analyzer = StatisticalAnalyzer()

    report = analyzer.analyze(df)

    assert len(report.numeric) == 1

    stats = report.numeric[0]

    assert stats.column == "grade"
    assert stats.count == 5
    assert stats.minimum == 20.0
    assert stats.maximum == 100.0
    assert stats.outlier_count > 0


def test_categorical_statistics():

    df = pd.DataFrame({
        "mine": [
            "M1",
            "M1",
            "M1",
            "M2",
        ]
    })

    analyzer = StatisticalAnalyzer()

    report = analyzer.analyze(df)

    assert len(report.categorical) == 1

    stats = report.categorical[0]

    assert stats.column == "mine"
    assert stats.unique_count == 2
    assert stats.most_frequent == "M1"
    assert stats.most_frequent_count == 3


def test_constant_column():

    df = pd.DataFrame({
        "constant": [1, 1, 1, 1],
        "value": [1, 2, 3, 4],
    })

    analyzer = StatisticalAnalyzer()

    report = analyzer.analyze(df)

    assert "constant" in report.constant_columns