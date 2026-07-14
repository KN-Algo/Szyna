"""
SAMODZIELNY PROGRAM DO PYCHARMA

Instalacja bibliotek w terminalu PyCharma:
    pip install numpy pandas scikit-learn joblib matplotlib

Opcjonalnie dla dodatkowego modelu:
    pip install lightgbm

Plik CSV należy umieścić obok tego pliku .py albo w podfolderze "data".
Program:
- buduje cechy wyłącznie z przeszłych danych,
- testuje modele chronologicznie,
- przewiduje opad za 15, 30, 45 i 60 minut,
- klasyfikuje opad jako deszcz, opad mieszany lub śnieg,
- szacuje ilość opadu oraz orientacyjną grubość świeżego śniegu,
- zapisuje model, raporty CSV, JSON i wykres.
"""

from __future__ import annotations

import json
import math
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor
from pandas.errors import PerformanceWarning
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    precision_score,
    recall_score,
)

try:
    from lightgbm import LGBMClassifier, LGBMRegressor

    LIGHTGBM_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback for a minimal environment
    LIGHTGBM_AVAILABLE = False


REQUIRED_COLUMNS = (
    "data_czas",
    "temperatura_powietrza_C",
    "punkt_rosy_C",
    "opad_mm",
    "wiatr_m_s",
    "naslonecznienie_sekundy",
)
HORIZONS_MIN = (15, 30, 45, 60)
HORIZON_STEPS = {15: 1, 30: 2, 45: 3, 60: 4}
PRECIP_THRESHOLD_MM = 1e-9
RANDOM_STATE = 42
warnings.simplefilter("ignore", PerformanceWarning)


@dataclass
class HorizonForecast:
    horizon_min: int
    will_precipitate: bool
    probability: float
    precipitation_type: str
    precipitation_amount_mm_15min: float
    predicted_air_temperature_C: float
    predicted_dew_point_C: float
    predicted_wet_bulb_C: float
    snow_water_equivalent_mm: float
    estimated_fresh_snow_depth_cm: float


@dataclass
class BenchmarkMetrics:
    dataset: str
    horizon_min: int
    model: str
    threshold: float
    test_samples: int
    event_rate: float
    accuracy: float
    balanced_accuracy: float
    precision: float
    recall: float
    f1: float
    persistence_accuracy: float
    persistence_balanced_accuracy: float
    persistence_f1: float
    amount_mae_mm_on_true_events: Optional[float]
    heuristic_phase_accuracy_on_true_events: Optional[float]
    confusion_tn_fp_fn_tp: List[int]


def calculate_relative_humidity(temp_c: np.ndarray | pd.Series, dew_point_c: np.ndarray | pd.Series) -> np.ndarray:
    """Relative humidity [%] from air and dew-point temperature."""
    temp = np.asarray(temp_c, dtype=float)
    dew = np.asarray(dew_point_c, dtype=float)
    a = 17.625
    b = 243.04
    rh = 100.0 * np.exp((a * dew) / (b + dew) - (a * temp) / (b + temp))
    return np.clip(rh, 0.0, 100.0)


def calculate_wet_bulb_stull(temp_c: np.ndarray | pd.Series, rh_pct: np.ndarray | pd.Series) -> np.ndarray:
    """Stull approximation of wet-bulb temperature [°C]."""
    temp = np.asarray(temp_c, dtype=float)
    rh = np.clip(np.asarray(rh_pct, dtype=float), 1.0, 100.0)
    return (
        temp * np.arctan(0.151977 * np.sqrt(rh + 8.313659))
        + np.arctan(temp + rh)
        - np.arctan(rh - 1.676331)
        + 0.00391838 * np.power(rh, 1.5) * np.arctan(0.023101 * rh)
        - 4.686035
    )


def classify_precipitation_phase(wet_bulb_c: float) -> str:
    """Heuristic phase partition because the CSV files contain no measured phase label."""
    if wet_bulb_c <= 0.0:
        return "snow"
    if wet_bulb_c <= 1.0:
        return "mixed"
    return "rain"


def snow_fraction_from_wet_bulb(wet_bulb_c: float) -> float:
    if wet_bulb_c <= 0.0:
        return 1.0
    if wet_bulb_c >= 1.0:
        return 0.0
    return float(1.0 - wet_bulb_c)


def snow_to_liquid_ratio(wet_bulb_c: float) -> float:
    """Approximate fresh-snow depth / liquid-water depth ratio."""
    points_t = np.array([-20.0, -12.0, -8.0, -3.0, 0.0, 1.0])
    points_ratio = np.array([18.0, 17.0, 15.0, 12.0, 8.0, 5.0])
    return float(np.interp(wet_bulb_c, points_t, points_ratio))


def validate_input_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Brak wymaganych kolumn: {missing}")

    data = df.loc[:, REQUIRED_COLUMNS].copy()
    data["data_czas"] = pd.to_datetime(data["data_czas"], errors="coerce")
    for column in REQUIRED_COLUMNS[1:]:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    if data.isna().any().any():
        counts = data.isna().sum()
        bad = counts[counts > 0].to_dict()
        raise ValueError(f"Dane zawierają braki lub błędne wartości: {bad}")

    data = data.sort_values("data_czas").drop_duplicates("data_czas", keep="last").reset_index(drop=True)
    if len(data) < 200:
        raise ValueError("Za mało rekordów. Wymagane jest co najmniej 200 próbek 15-minutowych.")

    cadence = data["data_czas"].diff().dropna().median()
    if cadence != pd.Timedelta(minutes=15):
        warnings.warn(
            f"Mediana kroku czasowego wynosi {cadence}, a model został przygotowany dla 15 minut.",
            RuntimeWarning,
        )
    if (data["opad_mm"] < 0).any():
        raise ValueError("Kolumna opad_mm zawiera wartości ujemne.")
    return data


def _consecutive_run_lengths(values: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    wet_run = np.zeros(len(values), dtype=np.int32)
    dry_run = np.zeros(len(values), dtype=np.int32)
    wet_count = 0
    dry_count = 0
    for i, value in enumerate(values):
        if value:
            wet_count += 1
            dry_count = 0
        else:
            dry_count += 1
            wet_count = 0
        wet_run[i] = wet_count
        dry_run[i] = dry_count
    return wet_run, dry_run


def build_feature_table(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Create strictly causal features: row t uses only observations up to t."""
    df = validate_input_dataframe(raw_df)
    timestamp = df["data_czas"]

    df["RH_pct"] = calculate_relative_humidity(
        df["temperatura_powietrza_C"], df["punkt_rosy_C"]
    )
    df["wet_bulb_C"] = calculate_wet_bulb_stull(df["temperatura_powietrza_C"], df["RH_pct"])
    df["dewpoint_depression_C"] = df["temperatura_powietrza_C"] - df["punkt_rosy_C"]
    df["is_precip_now"] = (df["opad_mm"] > PRECIP_THRESHOLD_MM).astype(np.int8)

    wet_run, dry_run = _consecutive_run_lengths(df["is_precip_now"].to_numpy())
    df["wet_run_steps"] = wet_run
    df["dry_run_steps"] = dry_run

    hour = timestamp.dt.hour + timestamp.dt.minute / 60.0
    day_of_year = timestamp.dt.dayofyear + hour / 24.0
    df["hour_sin"] = np.sin(2.0 * np.pi * hour / 24.0)
    df["hour_cos"] = np.cos(2.0 * np.pi * hour / 24.0)
    df["year_sin"] = np.sin(2.0 * np.pi * day_of_year / 365.25)
    df["year_cos"] = np.cos(2.0 * np.pi * day_of_year / 365.25)

    base_columns = (
        "temperatura_powietrza_C",
        "punkt_rosy_C",
        "opad_mm",
        "wiatr_m_s",
        "naslonecznienie_sekundy",
        "RH_pct",
        "wet_bulb_C",
        "dewpoint_depression_C",
    )

    for lag in (1, 2, 3, 4, 6, 8, 12):
        for column in base_columns:
            df[f"{column}_lag_{lag}"] = df[column].shift(lag)

    for window in (2, 4, 8, 12):
        for column in (
            "temperatura_powietrza_C",
            "punkt_rosy_C",
            "wiatr_m_s",
            "RH_pct",
            "wet_bulb_C",
            "dewpoint_depression_C",
        ):
            rolling = df[column].rolling(window=window, min_periods=window)
            df[f"{column}_mean_{window}"] = rolling.mean()
            df[f"{column}_std_{window}"] = rolling.std()
        df[f"opad_sum_{window}"] = df["opad_mm"].rolling(window, min_periods=window).sum()
        df[f"opad_max_{window}"] = df["opad_mm"].rolling(window, min_periods=window).max()
        df[f"wet_fraction_{window}"] = df["is_precip_now"].rolling(window, min_periods=window).mean()
        df[f"sun_sum_{window}"] = df["naslonecznienie_sekundy"].rolling(window, min_periods=window).sum()

    for lag in (1, 2, 4):
        for column in (
            "temperatura_powietrza_C",
            "punkt_rosy_C",
            "wiatr_m_s",
            "RH_pct",
            "wet_bulb_C",
            "opad_mm",
        ):
            df[f"{column}_delta_{lag}"] = df[column] - df[column].shift(lag)

    return df


def _classifier_candidates() -> Dict[str, Any]:
    candidates: Dict[str, Any] = {
        "extra_trees": ExtraTreesClassifier(
            n_estimators=120,
            max_features=0.65,
            min_samples_leaf=2,
            class_weight="balanced",
            n_jobs=-1,
            random_state=RANDOM_STATE,
        )
    }
    if LIGHTGBM_AVAILABLE:
        candidates["lightgbm"] = LGBMClassifier(
            n_estimators=110,
            learning_rate=0.05,
            num_leaves=15,
            min_child_samples=15,
            max_bin=63,
            class_weight="balanced",
            subsample=0.9,
            colsample_bytree=0.78,
            reg_lambda=0.7,
            verbosity=-1,
            n_jobs=4,
            force_col_wise=True,
            random_state=RANDOM_STATE,
        )
    return candidates


def _new_classifier(model_name: str, final_fit: bool = False) -> Any:
    if model_name == "lightgbm" and LIGHTGBM_AVAILABLE:
        return LGBMClassifier(
            n_estimators=160 if final_fit else 120,
            learning_rate=0.05,
            num_leaves=15,
            min_child_samples=15,
            max_bin=63,
            class_weight="balanced",
            subsample=0.9,
            colsample_bytree=0.78,
            reg_lambda=0.7,
            verbosity=-1,
            n_jobs=4,
            force_col_wise=True,
            random_state=RANDOM_STATE,
        )
    return ExtraTreesClassifier(
        n_estimators=200 if final_fit else 140,
        max_features=0.65,
        min_samples_leaf=2,
        class_weight="balanced",
        n_jobs=-1,
        random_state=RANDOM_STATE,
    )


def _new_regressor() -> Any:
    return ExtraTreesRegressor(
        n_estimators=120,
        max_features=0.75,
        min_samples_leaf=2,
        n_jobs=-1,
        random_state=RANDOM_STATE,
    )


def _select_probability_threshold(y_true: pd.Series, probabilities: np.ndarray) -> Tuple[float, Dict[str, float]]:
    best: Optional[Tuple[float, float, Dict[str, float]]] = None
    for threshold in np.arange(0.05, 0.951, 0.025):
        prediction = (probabilities >= threshold).astype(np.int8)
        metrics = {
            "accuracy": accuracy_score(y_true, prediction),
            "balanced_accuracy": balanced_accuracy_score(y_true, prediction),
            "precision": precision_score(y_true, prediction, zero_division=0),
            "recall": recall_score(y_true, prediction, zero_division=0),
            "f1": f1_score(y_true, prediction, zero_division=0),
        }
        score = 0.50 * metrics["f1"] + 0.35 * metrics["balanced_accuracy"] + 0.15 * metrics["accuracy"]
        if metrics["accuracy"] < 0.80:
            score -= 2.0 * (0.80 - metrics["accuracy"])
        candidate = (score, float(threshold), metrics)
        if best is None or candidate[0] > best[0]:
            best = candidate
    assert best is not None
    return best[1], best[2]


def _safe_positive_amount_model(X: pd.DataFrame, y_amount: pd.Series) -> Dict[str, Any]:
    positive = y_amount > PRECIP_THRESHOLD_MM
    positive_values = y_amount.loc[positive]
    if len(positive_values) < 20:
        median_value = float(positive_values.median()) if len(positive_values) else 0.0
        return {"kind": "constant", "value": median_value, "max_value": max(median_value, 0.0)}

    model = _new_regressor()
    model.fit(X.loc[positive], np.log1p(positive_values))
    max_value = float(max(positive_values.quantile(0.995), positive_values.max()))
    return {"kind": "model", "model": model, "max_value": max_value}


def _predict_amount(model_info: Dict[str, Any], X: pd.DataFrame) -> np.ndarray:
    if model_info["kind"] == "constant":
        values = np.full(len(X), float(model_info["value"]), dtype=float)
    else:
        values = np.expm1(model_info["model"].predict(X))
    return np.clip(values, 0.0, float(model_info["max_value"]))


def _chronological_boundaries(n_samples: int) -> Tuple[int, int]:
    train_end = max(1, int(n_samples * 0.60))
    validation_end = max(train_end + 1, int(n_samples * 0.80))
    validation_end = min(validation_end, n_samples - 1)
    return train_end, validation_end


def _extrapolate_thermodynamics(X: pd.DataFrame, horizon_min: int) -> Tuple[np.ndarray, np.ndarray]:
    """Damped linear extrapolation from the last hour; no future information is used."""
    steps = horizon_min / 15.0
    temp_now = X["temperatura_powietrza_C"].to_numpy(dtype=float)
    dew_now = X["punkt_rosy_C"].to_numpy(dtype=float)
    temp_hour_delta = temp_now - X["temperatura_powietrza_C_lag_4"].to_numpy(dtype=float)
    dew_hour_delta = dew_now - X["punkt_rosy_C_lag_4"].to_numpy(dtype=float)
    damping = 0.70
    predicted_temp = temp_now + damping * steps * temp_hour_delta / 4.0
    predicted_dew = dew_now + damping * steps * dew_hour_delta / 4.0
    predicted_temp = np.clip(predicted_temp, temp_now - 5.0, temp_now + 5.0)
    predicted_dew = np.clip(predicted_dew, dew_now - 5.0, dew_now + 5.0)
    predicted_dew = np.minimum(predicted_dew, predicted_temp + 0.5)
    return predicted_temp, predicted_dew


class PrecipitationNowcaster:
    """Four direct 15-minute nowcasting models: +15, +30, +45 and +60 min."""

    def __init__(self, dataset_name: str):
        self.dataset_name = dataset_name
        self.feature_columns: List[str] = []
        self.classifiers: Dict[int, Any] = {}
        self.thresholds: Dict[int, float] = {}
        self.model_names: Dict[int, str] = {}
        self.amount_models: Dict[int, Dict[str, Any]] = {}
        self.training_metadata: Dict[str, Any] = {}

    @staticmethod
    def _feature_columns(feature_table: pd.DataFrame) -> List[str]:
        excluded = {"data_czas"}
        return [column for column in feature_table.columns if column not in excluded]

    def _prepare_supervised(self, features: pd.DataFrame, horizon_min: int) -> Tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series, pd.Series]:
        step = HORIZON_STEPS[horizon_min]
        supervised = features.copy()
        supervised["target_occurrence"] = (
            supervised["opad_mm"].shift(-step) > PRECIP_THRESHOLD_MM
        ).astype(float)
        supervised["target_amount"] = supervised["opad_mm"].shift(-step)
        supervised["target_temperature"] = supervised["temperatura_powietrza_C"].shift(-step)
        supervised["target_dew_point"] = supervised["punkt_rosy_C"].shift(-step)
        supervised = supervised.iloc[:-step].dropna().reset_index(drop=True)

        feature_columns = [
            column
            for column in features.columns
            if column != "data_czas"
        ]
        X = supervised[feature_columns]
        return (
            X,
            supervised["target_occurrence"].astype(np.int8),
            supervised["target_amount"].astype(float),
            supervised["target_temperature"].astype(float),
            supervised["target_dew_point"].astype(float),
        )

    def benchmark_and_fit(self, raw_df: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
        output_dir.mkdir(parents=True, exist_ok=True)
        metrics_rows: List[BenchmarkMetrics] = []
        prediction_rows: List[Dict[str, Any]] = []
        final_feature_columns: Optional[List[str]] = None
        feature_table = build_feature_table(raw_df)

        for horizon_min in HORIZONS_MIN:
            X, y, y_amount, y_temperature, y_dew = self._prepare_supervised(feature_table, horizon_min)
            if y.nunique() < 2:
                raise ValueError(
                    f"Dla horyzontu {horizon_min} min występuje tylko jedna klasa opadu; modelu nie da się nauczyć."
                )

            train_end, validation_end = _chronological_boundaries(len(X))
            X_train = X.iloc[:train_end]
            y_train = y.iloc[:train_end]
            X_validation = X.iloc[train_end:validation_end]
            y_validation = y.iloc[train_end:validation_end]
            X_test = X.iloc[validation_end:]
            y_test = y.iloc[validation_end:]

            best_name: Optional[str] = None
            best_threshold: Optional[float] = None
            best_score = -np.inf

            for model_name, model in _classifier_candidates().items():
                model.fit(X_train, y_train)
                validation_probability = model.predict_proba(X_validation)[:, 1]
                threshold, validation_metrics = _select_probability_threshold(
                    y_validation, validation_probability
                )
                validation_score = (
                    0.50 * validation_metrics["f1"]
                    + 0.35 * validation_metrics["balanced_accuracy"]
                    + 0.15 * validation_metrics["accuracy"]
                )
                if validation_score > best_score:
                    best_score = validation_score
                    best_name = model_name
                    best_threshold = threshold

            assert best_name is not None and best_threshold is not None

            benchmark_classifier = _new_classifier(best_name, final_fit=True)
            benchmark_classifier.fit(X.iloc[:validation_end], y.iloc[:validation_end])
            test_probability = benchmark_classifier.predict_proba(X_test)[:, 1]
            test_prediction = (test_probability >= best_threshold).astype(np.int8)

            persistence_prediction = (
                X_test["opad_mm"].to_numpy() > PRECIP_THRESHOLD_MM
            ).astype(np.int8)

            benchmark_amount_model = _safe_positive_amount_model(
                X.iloc[:validation_end], y_amount.iloc[:validation_end]
            )
            test_amount_prediction = _predict_amount(benchmark_amount_model, X_test)
            true_event_mask = y_test.to_numpy().astype(bool)
            amount_mae: Optional[float] = None
            if true_event_mask.any():
                amount_mae = float(
                    mean_absolute_error(
                        y_amount.iloc[validation_end:].to_numpy()[true_event_mask],
                        test_amount_prediction[true_event_mask],
                    )
                )

            predicted_temp, predicted_dew = _extrapolate_thermodynamics(X_test, horizon_min)
            predicted_rh = calculate_relative_humidity(predicted_temp, predicted_dew)
            predicted_tw = calculate_wet_bulb_stull(predicted_temp, predicted_rh)

            actual_temp = y_temperature.iloc[validation_end:].to_numpy()
            actual_dew = y_dew.iloc[validation_end:].to_numpy()
            actual_rh = calculate_relative_humidity(actual_temp, actual_dew)
            actual_tw = calculate_wet_bulb_stull(actual_temp, actual_rh)

            phase_accuracy: Optional[float] = None
            if true_event_mask.any():
                predicted_phase = np.array(
                    [classify_precipitation_phase(value) for value in predicted_tw]
                )
                actual_phase = np.array(
                    [classify_precipitation_phase(value) for value in actual_tw]
                )
                phase_accuracy = float(
                    np.mean(predicted_phase[true_event_mask] == actual_phase[true_event_mask])
                )

            tn, fp, fn, tp = confusion_matrix(y_test, test_prediction, labels=[0, 1]).ravel()
            metrics_rows.append(
                BenchmarkMetrics(
                    dataset=self.dataset_name,
                    horizon_min=horizon_min,
                    model=best_name,
                    threshold=float(best_threshold),
                    test_samples=len(y_test),
                    event_rate=float(y_test.mean()),
                    accuracy=float(accuracy_score(y_test, test_prediction)),
                    balanced_accuracy=float(
                        balanced_accuracy_score(y_test, test_prediction)
                    ),
                    precision=float(
                        precision_score(y_test, test_prediction, zero_division=0)
                    ),
                    recall=float(recall_score(y_test, test_prediction, zero_division=0)),
                    f1=float(f1_score(y_test, test_prediction, zero_division=0)),
                    persistence_accuracy=float(
                        accuracy_score(y_test, persistence_prediction)
                    ),
                    persistence_balanced_accuracy=float(
                        balanced_accuracy_score(y_test, persistence_prediction)
                    ),
                    persistence_f1=float(
                        f1_score(y_test, persistence_prediction, zero_division=0)
                    ),
                    amount_mae_mm_on_true_events=amount_mae,
                    heuristic_phase_accuracy_on_true_events=phase_accuracy,
                    confusion_tn_fp_fn_tp=[int(tn), int(fp), int(fn), int(tp)],
                )
            )

            test_indices = X_test.index
            for local_i, source_index in enumerate(test_indices):
                prediction_rows.append(
                    {
                        "dataset": self.dataset_name,
                        "horizon_min": horizon_min,
                        "source_row": int(source_index),
                        "actual_precipitation": int(y_test.iloc[local_i]),
                        "predicted_precipitation": int(test_prediction[local_i]),
                        "probability": float(test_probability[local_i]),
                        "actual_amount_mm": float(y_amount.iloc[source_index]),
                        "predicted_amount_mm": float(test_amount_prediction[local_i]),
                        "actual_phase_heuristic": classify_precipitation_phase(
                            float(actual_tw[local_i])
                        )
                        if y_test.iloc[local_i]
                        else "none",
                        "predicted_phase_heuristic": classify_precipitation_phase(
                            float(predicted_tw[local_i])
                        )
                        if test_prediction[local_i]
                        else "none",
                    }
                )

            # Final deployment fit on all available labelled rows.
            final_classifier = _new_classifier(best_name, final_fit=True)
            final_classifier.fit(X, y)
            final_amount_model = _safe_positive_amount_model(X, y_amount)
            self.classifiers[horizon_min] = final_classifier
            self.thresholds[horizon_min] = float(best_threshold)
            self.model_names[horizon_min] = best_name
            self.amount_models[horizon_min] = final_amount_model
            final_feature_columns = list(X.columns)

        assert final_feature_columns is not None
        self.feature_columns = final_feature_columns
        validated = validate_input_dataframe(raw_df)
        self.training_metadata = {
            "dataset_name": self.dataset_name,
            "rows": len(validated),
            "start": validated["data_czas"].min().isoformat(),
            "end": validated["data_czas"].max().isoformat(),
            "horizons_min": list(HORIZONS_MIN),
            "phase_label_is_heuristic": True,
            "lightgbm_available": LIGHTGBM_AVAILABLE,
        }

        metrics_df = pd.DataFrame([asdict(row) for row in metrics_rows])
        predictions_df = pd.DataFrame(prediction_rows)
        metrics_df.to_csv(output_dir / "benchmark_metrics.csv", index=False)
        predictions_df.to_csv(output_dir / "benchmark_predictions.csv", index=False)
        with (output_dir / "training_metadata.json").open("w", encoding="utf-8") as handle:
            json.dump(self.training_metadata, handle, ensure_ascii=False, indent=2)
        self.save(output_dir / "nowcaster.joblib")
        return metrics_df

    def predict_horizons(self, history_df: pd.DataFrame) -> List[HorizonForecast]:
        if not self.classifiers or not self.feature_columns:
            raise RuntimeError("Model nie został wytrenowany lub wczytany.")

        feature_table = build_feature_table(history_df).dropna().reset_index(drop=True)
        if feature_table.empty:
            raise ValueError("Za krótka historia. Podaj co najmniej 3 godziny danych 15-minutowych.")
        last_row = feature_table.iloc[[-1]][self.feature_columns]

        forecasts: List[HorizonForecast] = []
        for horizon_min in HORIZONS_MIN:
            probability = float(self.classifiers[horizon_min].predict_proba(last_row)[0, 1])
            will_precipitate = probability >= self.thresholds[horizon_min]
            predicted_amount = float(_predict_amount(self.amount_models[horizon_min], last_row)[0])
            if not will_precipitate:
                predicted_amount = 0.0

            predicted_temp_arr, predicted_dew_arr = _extrapolate_thermodynamics(last_row, horizon_min)
            predicted_temp = float(predicted_temp_arr[0])
            predicted_dew = float(predicted_dew_arr[0])
            predicted_rh = float(calculate_relative_humidity([predicted_temp], [predicted_dew])[0])
            predicted_tw = float(calculate_wet_bulb_stull([predicted_temp], [predicted_rh])[0])

            phase = classify_precipitation_phase(predicted_tw) if will_precipitate else "none"
            snow_fraction = snow_fraction_from_wet_bulb(predicted_tw) if will_precipitate else 0.0
            snow_water_equivalent = predicted_amount * snow_fraction
            snow_depth_cm = (
                snow_water_equivalent * snow_to_liquid_ratio(predicted_tw) / 10.0
            )

            forecasts.append(
                HorizonForecast(
                    horizon_min=horizon_min,
                    will_precipitate=bool(will_precipitate),
                    probability=round(probability, 6),
                    precipitation_type=phase,
                    precipitation_amount_mm_15min=round(predicted_amount, 4),
                    predicted_air_temperature_C=round(predicted_temp, 3),
                    predicted_dew_point_C=round(predicted_dew, 3),
                    predicted_wet_bulb_C=round(predicted_tw, 3),
                    snow_water_equivalent_mm=round(snow_water_equivalent, 4),
                    estimated_fresh_snow_depth_cm=round(snow_depth_cm, 4),
                )
            )
        return forecasts

    def forecast_flag_time_amount(
        self, history_df: pd.DataFrame
    ) -> Tuple[bool, Optional[int], Dict[str, Any]]:
        """
        Required three-element API:
        1) flag whether precipitation is forecast,
        2) earliest lead time in minutes,
        3) details including phase and rain/snow amount.
        """
        forecasts = self.predict_horizons(history_df)
        earliest = next((forecast for forecast in forecasts if forecast.will_precipitate), None)
        if earliest is None:
            return False, None, {
                "type": "none",
                "precipitation_amount_mm_15min": 0.0,
                "snow_water_equivalent_mm": 0.0,
                "estimated_fresh_snow_depth_cm": 0.0,
                "horizons": [asdict(item) for item in forecasts],
            }
        details = asdict(earliest)
        details["type"] = details.pop("precipitation_type")
        details["horizons"] = [asdict(item) for item in forecasts]
        return True, earliest.horizon_min, details

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path, compress=3)

    @staticmethod
    def load(path: Path | str) -> "PrecipitationNowcaster":
        model = joblib.load(path)
        if not isinstance(model, PrecipitationNowcaster):
            raise TypeError("Plik nie zawiera modelu PrecipitationNowcaster.")
        return model


def run_dataset_program(
    csv_path: Path | str,
    output_dir: Path | str,
    dataset_name: str,
    force_train: bool = False,
) -> Tuple[pd.DataFrame, Tuple[bool, Optional[int], Dict[str, Any]]]:
    csv_path = Path(csv_path)
    output_dir = Path(output_dir)
    if not csv_path.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku CSV: {csv_path}")

    raw_df = pd.read_csv(csv_path)
    model_path = output_dir / "nowcaster.joblib"
    metrics_path = output_dir / "benchmark_metrics.csv"

    if force_train or not model_path.exists() or not metrics_path.exists():
        nowcaster = PrecipitationNowcaster(dataset_name=dataset_name)
        metrics = nowcaster.benchmark_and_fit(raw_df, output_dir)
    else:
        nowcaster = PrecipitationNowcaster.load(model_path)
        metrics = pd.read_csv(metrics_path)

    result = nowcaster.forecast_flag_time_amount(raw_df)
    with (output_dir / "latest_forecast.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {"will_precipitate": result[0], "lead_time_min": result[1], "details": result[2]},
            handle,
            ensure_ascii=False,
            indent=2,
        )
    return metrics, result


# =====================================================================
# 4. KONFIGURACJA TEGO KONKRETNEGO PLIKU
# =====================================================================
CSV_FILENAME = 'suwalki_pogoda_15_min_model_2010.csv'
DATASET_NAME = 'suwalki_2010'
OUTPUT_FOLDER_NAME = 'wyniki_prognozy_suwalki_2010'
PROGRAM_TITLE = 'Prognoza deszczu i śniegu — Suwałki 2010'


# =====================================================================
# 5. FUNKCJE URUCHOMIENIOWE — PLIK JEST CAŁKOWICIE SAMODZIELNY
# =====================================================================
def find_csv_file(custom_path=None):
    """
    Szuka pliku CSV:
    1. pod ścieżką podaną przez --csv,
    2. obok tego pliku .py,
    3. w podfolderze data obok pliku .py,
    4. w aktualnym katalogu roboczym PyCharma.
    """
    if custom_path:
        path = Path(custom_path).expanduser().resolve()
        if path.exists():
            return path
        raise FileNotFoundError(f"Nie znaleziono wskazanego pliku CSV: {path}")

    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / CSV_FILENAME,
        script_dir / "data" / CSV_FILENAME,
        Path.cwd() / CSV_FILENAME,
        Path.cwd() / "data" / CSV_FILENAME,
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    searched = "\n".join(f" - {path}" for path in candidates)
    raise FileNotFoundError(
        f"Nie znaleziono pliku {CSV_FILENAME}.\n"
        f"Umieść go obok programu albo w folderze data.\n"
        f"Sprawdzone lokalizacje:\n{searched}"
    )


def print_forecast_result(result):
    """Czytelne wypisanie wymaganych trzech wartości."""
    flag, lead_time_min, details = result

    print("\n" + "=" * 76)
    print("WYNIK FUNKCJI: (flaga, czas, szczegóły)")
    print("=" * 76)
    print(f"1. Czy będzie padać: {flag}")
    print(f"2. Najwcześniejszy czas opadu: {lead_time_min} minut")
    print(f"3. Szczegóły: {details.get('type', 'none')}")

    if flag:
        print(f"   Prawdopodobieństwo: {details.get('probability', 0.0) * 100:.2f}%")
        print(
            "   Prognozowana ilość opadu: "
            f"{details.get('precipitation_amount_mm_15min', 0.0):.4f} mm / 15 min"
        )
        print(
            "   Ekwiwalent wodny śniegu: "
            f"{details.get('snow_water_equivalent_mm', 0.0):.4f} mm"
        )
        print(
            "   Szacowana grubość świeżego śniegu: "
            f"{details.get('estimated_fresh_snow_depth_cm', 0.0):.4f} cm"
        )
    else:
        print("   W horyzoncie 60 minut model nie przewiduje opadu.")

    print("\nPrognozy dla wszystkich horyzontów:")
    print(
        f"{'Horyzont':>10} | {'Opad':>6} | {'Prawdop.':>10} | "
        f"{'Typ':>8} | {'Ilość mm':>10} | {'Śnieg cm':>10}"
    )
    print("-" * 76)
    for item in details.get("horizons", []):
        print(
            f"{item['horizon_min']:>8} m | "
            f"{str(item['will_precipitate']):>6} | "
            f"{item['probability'] * 100:>9.2f}% | "
            f"{item['precipitation_type']:>8} | "
            f"{item['precipitation_amount_mm_15min']:>10.4f} | "
            f"{item['estimated_fresh_snow_depth_cm']:>10.4f}"
        )
    print("=" * 76)


def create_result_chart(metrics, result, output_dir):
    """
    Wykres podobny ideowo do głównego programu:
    - panel 1: jakość modeli,
    - panel 2: prawdopodobieństwo opadu,
    - panel 3: prognozowana ilość opadu i śniegu.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Brak matplotlib — pomijam wykres. Instalacja: pip install matplotlib")
        return

    horizons = [int(item["horizon_min"]) for item in result[2]["horizons"]]
    probabilities = [float(item["probability"]) * 100.0 for item in result[2]["horizons"]]
    amounts = [
        float(item["precipitation_amount_mm_15min"])
        for item in result[2]["horizons"]
    ]
    snow_depth = [
        float(item["estimated_fresh_snow_depth_cm"])
        for item in result[2]["horizons"]
    ]

    metric_by_horizon = metrics.sort_values("horizon_min")
    accuracy = metric_by_horizon["accuracy"].to_numpy(dtype=float) * 100.0
    balanced_accuracy = (
        metric_by_horizon["balanced_accuracy"].to_numpy(dtype=float) * 100.0
    )
    f1 = metric_by_horizon["f1"].to_numpy(dtype=float) * 100.0

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(13, 10))
    fig.suptitle(PROGRAM_TITLE, fontsize=15, fontweight="bold")

    ax1.plot(horizons, accuracy, marker="o", label="Accuracy")
    ax1.plot(horizons, balanced_accuracy, marker="o", label="Balanced accuracy")
    ax1.plot(horizons, f1, marker="o", label="F1")
    ax1.axhline(80.0, linestyle="--", label="Cel 80%")
    ax1.set_ylabel("Wynik [%]")
    ax1.set_xticks(horizons)
    ax1.set_ylim(0.0, 105.0)
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend()

    ax2.plot(horizons, probabilities, marker="o", linewidth=2)
    ax2.axhline(50.0, linestyle="--")
    ax2.set_ylabel("Prawdopodobieństwo [%]")
    ax2.set_xticks(horizons)
    ax2.set_ylim(0.0, 105.0)
    ax2.grid(True, linestyle=":", alpha=0.6)

    width = 5
    ax3.bar([value - width / 2 for value in horizons], amounts, width=width,
            label="Opad [mm / 15 min]")
    ax3.bar([value + width / 2 for value in horizons], snow_depth, width=width,
            label="Świeży śnieg [cm]")
    ax3.set_xlabel("Horyzont prognozy [min]")
    ax3.set_ylabel("Prognozowana ilość")
    ax3.set_xticks(horizons)
    ax3.grid(True, axis="y", linestyle=":", alpha=0.6)
    ax3.legend()

    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    output_dir.mkdir(parents=True, exist_ok=True)
    chart_path = output_dir / "wykres_prognozy_i_jakosci.png"
    fig.savefig(chart_path, dpi=160)
    print(f"\nZapisano wykres: {chart_path}")
    plt.show()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Samodzielny program przewidujący opad deszczu/śniegu "
            "za 15, 30, 45 i 60 minut."
        )
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="Opcjonalna pełna ścieżka do pliku CSV.",
    )
    parser.add_argument(
        "--train",
        action="store_true",
        help="Wymuś ponowny trening modeli zamiast użycia zapisanego modelu.",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Nie otwieraj wykresu po zakończeniu.",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    csv_path = find_csv_file(args.csv)
    output_dir = script_dir / OUTPUT_FOLDER_NAME

    print("=" * 76)
    print(PROGRAM_TITLE)
    print("=" * 76)
    print(f"Plik danych: {csv_path}")
    print(f"Folder wyników: {output_dir}")
    print(f"LightGBM dostępny: {LIGHTGBM_AVAILABLE}")
    if not LIGHTGBM_AVAILABLE:
        print("Używany będzie model Extra Trees.")
        print("Opcjonalnie można doinstalować LightGBM: pip install lightgbm")

    metrics, result = run_dataset_program(
        csv_path=csv_path,
        output_dir=output_dir,
        dataset_name=DATASET_NAME,
        force_train=args.train,
    )

    print("\nMETRYKI NA NIEWIDZIANYM, KOŃCOWYM FRAGMENCIE DANYCH:")
    columns = [
        "horizon_min",
        "model",
        "threshold",
        "accuracy",
        "balanced_accuracy",
        "precision",
        "recall",
        "f1",
        "amount_mae_mm_on_true_events",
    ]
    display_metrics = metrics.loc[:, columns].copy()
    for column in (
        "accuracy",
        "balanced_accuracy",
        "precision",
        "recall",
        "f1",
    ):
        display_metrics[column] = (display_metrics[column] * 100.0).round(2)
    print(display_metrics.to_string(index=False))

    print_forecast_result(result)

    print("\nWymagana funkcja zwróciła dokładnie:")
    print(result)

    if not args.no_plot:
        create_result_chart(metrics, result, output_dir)


if __name__ == "__main__":
    main()
