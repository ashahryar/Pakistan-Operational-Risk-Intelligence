"""Task 33 -- baselines and the lightweight ML candidates (scikit-learn only; no new infrastructure).

Baselines (predict the value at origin + horizon from the features at the origin; no fitting):
    persistence       : the last observed value (lag_0)
    rolling_mean_7    : the mean of the last 7 observed days
ML candidates, chosen for a small (hundreds of rows), autoregressive, tabular regression problem -- NOT because they sound impressive:
    ridge             : regularised linear autoregression (scaler fit on the training split only, inside the pipeline)
    random_forest     : shallow forest (captures non-linear lag interactions, cannot extrapolate beyond the training range)
    hist_gradient_boosting : small boosted trees (same limitation; more prone to over-fitting at this size)
All have fixed hyper-parameters and a fixed random_state (no search on the test period). Model selection uses VALIDATION error only.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from pipeline.ml.dataset import FEATURE_COLUMNS

BASELINES: dict[str, Callable[[pd.DataFrame], np.ndarray]] = {
    "persistence": lambda X: X["lag_0"].to_numpy(dtype=float),
    "rolling_mean_7": lambda X: X["rolling_mean_7"].to_numpy(dtype=float),
}


def candidate_models() -> dict:
    """Fresh, unfitted candidate estimators with fixed settings."""
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return {"ridge": make_pipeline(StandardScaler(), Ridge(alpha=10.0)),
            "random_forest": RandomForestRegressor(n_estimators=200, max_depth=6, min_samples_leaf=5, random_state=0, n_jobs=1),
            "hist_gradient_boosting": HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=10, random_state=0)}


def xy(frame: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    return frame[FEATURE_COLUMNS], frame["target"].to_numpy(dtype=float)


def fit_predict(name: str, train: pd.DataFrame, other: pd.DataFrame):
    """Fit the named candidate on `train` only and predict `other`. Returns (fitted estimator, predictions)."""
    est = candidate_models()[name]
    Xtr, ytr = xy(train)
    est.fit(Xtr, ytr)
    return est, est.predict(other[FEATURE_COLUMNS])
