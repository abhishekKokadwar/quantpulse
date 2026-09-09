"""
GridPulse Orchestration Task: Automated ML Model Retraining
Periodically re-trains the 24-hour recursive load forecaster using chronological
splits and validates regression KPIs (MAE, RMSE, MAPE) before model promotion.
"""

import os
import sys
import time
from typing import Dict, Any

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def retrain_forecaster_model(
    max_acceptable_mae: float = 120.0,
    max_acceptable_rmse: float = 160.0,
    max_acceptable_mape: float = 25.0,
) -> Dict[str, Any]:
    """
    Executes automated model retraining, evaluates candidate performance,
    and conditionally promotes the model artifact if regression KPIs meet quality contracts.

    Returns:
        Dict containing model name, metrics, promotion status, and duration.
    """
    start_time = time.time()
    from analysis.forecaster import LoadForecaster, DEFAULT_MODEL_PATH

    forecaster = LoadForecaster(model_path=DEFAULT_MODEL_PATH)
    try:
        evaluation = forecaster.train_and_evaluate(train_ratio=0.8)
        metrics = evaluation.get("metrics", {})
        mae = metrics.get("MAE", 999.0)
        rmse = metrics.get("RMSE", 999.0)
        mape = metrics.get("MAPE", 999.0)

        # Quality contract assertions
        kpi_checks = {
            "mae_ok": mae <= max_acceptable_mae,
            "rmse_ok": rmse <= max_acceptable_rmse,
            "mape_ok": mape <= max_acceptable_mape,
        }
        passed_quality_gates = all(kpi_checks.values())
        status = "SUCCESS" if passed_quality_gates else "KPI_DEGRADATION"

        duration_s = round(time.time() - start_time, 3)

        return {
            "task": "model_retrain_task",
            "status": status,
            "promoted": passed_quality_gates,
            "model_name": evaluation.get("model_name", "Unknown"),
            "metrics": metrics,
            "quality_gates": kpi_checks,
            "thresholds": {
                "max_mae": max_acceptable_mae,
                "max_rmse": max_acceptable_rmse,
                "max_mape": max_acceptable_mape,
            },
            "duration_seconds": duration_s,
            "message": (
                f"Model retraining completed with status {status} in {duration_s}s. "
                f"Model: {evaluation.get('model_name')}, MAE: {mae} kW, RMSE: {rmse} kW, MAPE: {mape}%."
            ),
        }

    except Exception as e:
        duration_s = round(time.time() - start_time, 3)
        return {
            "task": "model_retrain_task",
            "status": "FAILED",
            "promoted": False,
            "error": str(e),
            "duration_seconds": duration_s,
            "message": f"Model retraining failed: {str(e)}",
        }


if __name__ == "__main__":
    res = retrain_forecaster_model()
    print("[RETRAIN TASK OUTPUT]")
    for k, v in res.items():
        print(f"  {k}: {v}")
