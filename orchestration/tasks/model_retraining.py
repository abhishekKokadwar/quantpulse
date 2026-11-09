"""
GridPulse Orchestration Task: Automated ML Model Retraining
Periodically re-trains the multi-horizon alpha forecaster using chronological
splits and validates regression KPIs before model promotion.
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
    min_acceptable_hit_rate: float = 0.51,
    min_acceptable_ic: float = 0.02,
) -> Dict[str, Any]:
    """
    Executes automated model retraining, evaluates candidate performance,
    and conditionally promotes the model artifact if regression KPIs meet quality contracts.

    Returns:
        Dict containing model name, metrics, promotion status, and duration.
    """
    start_time = time.time()
    from analysis.alpha_forecaster import train_alpha_forecaster_pipeline, DEFAULT_MODEL_DIR

    try:
        model, metrics = train_alpha_forecaster_pipeline(symbol="BTC/USDT", horizon=1)
        
        hit_rate = metrics.get("hit_rate", 0.0)
        rank_ic = metrics.get("rank_ic", 0.0)
        # Populate uppercase keys for legacy test compatibility
        metrics["MAE"] = metrics.get("mae", 0.0)
        metrics["RMSE"] = metrics.get("rmse", 0.0)
        metrics["R2"] = metrics.get("r2", 0.0)

        # Quality contract assertions
        kpi_checks = {
            "hit_rate_ok": hit_rate >= min_acceptable_hit_rate,
            "rank_ic_ok": rank_ic >= min_acceptable_ic,
        }
        passed_quality_gates = all(kpi_checks.values())
        status = "SUCCESS" if passed_quality_gates else "KPI_DEGRADATION"

        duration_s = round(time.time() - start_time, 3)

        return {
            "task": "model_retrain_task",
            "status": status,
            "promoted": passed_quality_gates,
            "model_name": "alpha_BTC-USDT_1m",
            "metrics": metrics,
            "quality_gates": kpi_checks,
            "thresholds": {
                "min_hit_rate": min_acceptable_hit_rate,
                "min_ic": min_acceptable_ic,
            },
            "duration_seconds": duration_s,
            "message": (
                f"Model retraining completed with status {status} in {duration_s}s. "
                f"Model: alpha_BTC-USDT_1m, Hit Rate: {hit_rate}, Rank IC: {rank_ic}."
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
