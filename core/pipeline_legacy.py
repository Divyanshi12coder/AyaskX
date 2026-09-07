from dataclasses import dataclass

import pandas as pd

from core.models.candidates import ModelCandidateGenerator
from core.models.trainer import ModelTrainer
from core.models.splitters import ValidationSplitter


@dataclass(frozen=True)
class PipelineResult:
    target: str
    task_type: str
    validation_strategy: str
    candidates: tuple[str, ...]
    evaluations: tuple
    best_model_name: str | None
    best_score: float | None


class AyaskPipeline:

    def __init__(self):

        self.candidate_generator = (
            ModelCandidateGenerator()
        )

        self.trainer = ModelTrainer()

        self.splitter = ValidationSplitter()

    def run(
        self,
        df: pd.DataFrame,
        target: str,
        task_type: str,
        validation_strategy: str = "random_holdout",
        group_column: str | None = None,
        time_column: str | None = None,
        latitude_column: str | None = None,
        longitude_column: str | None = None,
    ) -> PipelineResult:

        # ======================================================
        # BASIC VALIDATION
        # ======================================================

        if df.empty:
            raise ValueError(
                "Cannot run pipeline on an empty dataset."
            )

        if target not in df.columns:
            raise ValueError(
                f"Target column not found: {target}"
            )

        # ======================================================
        # 1. GENERATE MODEL CANDIDATES
        # ======================================================

        candidate_report = (
            self.candidate_generator.generate(
                df=df,
                target=target,
                task_type=task_type,
            )
        )

        candidates = tuple(
            candidate.name
            for candidate in candidate_report.candidates
        )

        if not candidates:
            raise ValueError(
                "No suitable model candidates generated."
            )

        # ======================================================
        # 2. REMOVE ROWS WITH MISSING TARGET
        # ======================================================

        clean_df = df.dropna(
            subset=[target]
        ).copy()

        if clean_df.empty:
            raise ValueError(
                "No rows remain after removing "
                "missing target values."
            )

        X = clean_df.drop(
            columns=[target]
        )

        y = clean_df[target]

        # ======================================================
        # 3. CREATE THE SELECTED VALIDATION SPLIT
        # ======================================================
        #
        # IMPORTANT:
        #
        # This is the ONLY split performed by the pipeline.
        #
        # The selected strategy must be respected:
        #
        # random_holdout
        # group_holdout
        # temporal_holdout
        # spatial_holdout
        # stratified_holdout
        #
        # Metadata such as mine_id is still available here
        # because it may be required to construct the split.
        # ======================================================

        split = self.splitter.split(
            X=X,
            y=y,
            strategy=validation_strategy,
            group_column=group_column,
            time_column=time_column,
            latitude_column=latitude_column,
            longitude_column=longitude_column,
        )

        # ======================================================
        # 4. TRAIN AND EVALUATE ON THE EXACT SAME SPLIT
        # ======================================================
        #
        # DO NOT call train_and_evaluate() here.
        #
        # train_and_evaluate() creates a new split.
        #
        # Instead, pass the already-created split directly to
        # train_on_split().
        # ======================================================

        training_result = (
            self.trainer.train_on_split(
                split=split,
                task_type=task_type,
                candidates=candidates,
            )
        )

        # ======================================================
        # 5. RETURN PIPELINE RESULT
        # ======================================================

        return PipelineResult(
            target=target,
            task_type=task_type,
            validation_strategy=validation_strategy,
            candidates=candidates,
            evaluations=training_result.evaluations,
            best_model_name=(
                training_result.best_model_name
            ),
            best_score=training_result.best_score,
        )