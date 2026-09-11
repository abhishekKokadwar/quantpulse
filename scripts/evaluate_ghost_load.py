#!/usr/bin/env python
"""
Evaluation Runner for Hostel Ghost Load & Unoccupied Room Waste Detector
Evaluates precision, recall, false alarm rate, and detection latency against
synthetic ground-truth waste episodes logged by the simulator.
"""

import os
import sys
import argparse
import pandas as pd
from datetime import datetime

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from simulator.simulator import (
    generate_hostel_waste_scenario,
    get_ground_truth_events,
    clear_ground_truth_events,
)
from analysis.ghost_load_detector import (
    HostelGhostLoadDetector,
    DEFAULT_TARIFF_INR_PER_KWH,
)
from consumer.webhook_dispatcher import dispatch_ghost_load_alert


def run_evaluation(days: int = 5, generate_new: bool = True, send_sample_alert: bool = False):
    print("=" * 70)
    print("⚡ GRIDPULSE: HOSTEL GHOST LOAD & UNOCCUPIED ROOM WASTE BENCHMARK")
    print("=" * 70)

    # 1. Generate or load ground truth scenario
    if generate_new or not get_ground_truth_events():
        print(f"[SIMULATOR] Generating {days}-day multi-hostel scenario with ground-truth waste injection...")
        readings = generate_hostel_waste_scenario(
            days=days,
            interval_minutes=15,
            record_ground_truth=True,
            clear_existing_ground_truth=True,
        )
        df_readings = pd.DataFrame(readings)
    else:
        print("[SIMULATOR] Loading existing ground truth events...")
        readings = generate_hostel_waste_scenario(
            days=days,
            interval_minutes=15,
            record_ground_truth=False,
            clear_existing_ground_truth=False,
        )
        df_readings = pd.DataFrame(readings)

    gt_events = get_ground_truth_events()
    print(f"[GROUND TRUTH] Injected Episodes: {len(gt_events)}")
    for i, gt in enumerate(gt_events, 1):
        trig = "Trigger >= 45m" if gt.get("expected_trigger", True) else "Ignore < 45m"
        print(f"  {i}. [{gt['event_id']}] {gt['building_id']} - {gt['waste_type']} ({gt['duration_minutes']}m, +{gt['excess_kw']} kW, PF {gt['target_pf']}) -> {trig}")

    # 2. Train robust Median & MAD baselines
    print("\n[DETECTOR] Fitting robust Median & MAD baselines across (day_of_week, 15m_slot)...")
    detector = HostelGhostLoadDetector(tariff_inr=DEFAULT_TARIFF_INR_PER_KWH)
    # Exclude injected ground truth windows to ensure pure baseline
    detector.fit(df_readings, exclude_flagged_waste=True)

    # 3. Process time-series through state machine
    print("[DETECTOR] Processing time-series telemetry through hysteresis state machines...")
    df_enriched, detected_alerts = detector.process_dataframe(df_readings, step_minutes=15.0)

    # 4. Evaluate against ground truth
    print("\n[BENCHMARK] Computing evaluation metrics against ground truth...")
    metrics = detector.evaluate_against_ground_truth(gt_events)

    print("\n" + "=" * 70)
    print("📊 BENCHMARK EVALUATION RESULTS")
    print("=" * 70)
    print(f"  Total Ground Truth Episodes  : {metrics['ground_truth_total']}")
    print(f"  Expected Triggers (>= 45 min): {metrics['expected_triggers']}")
    print(f"  Transient Spikes (< 45 min)  : {metrics['unwanted_transients']}")
    print(f"  True Positives (Detected)    : {metrics['true_positives']} / {metrics['expected_triggers']}")
    print(f"  False Positives (Alarms)     : {metrics['false_positives']}")
    print(f"  False Negatives (Missed)     : {metrics['false_negatives']}")
    print("  -------------------------------------------------------------------")
    print(f"  ⭐ PRECISION                 : {metrics['precision'] * 100:.1f}%")
    print(f"  ⭐ RECALL (Detection Rate)   : {metrics['recall'] * 100:.1f}%")
    print(f"  ⭐ F1-SCORE                  : {metrics['f1_score'] * 100:.1f}%")
    print(f"  ⭐ MEAN DETECTION LATENCY    : {metrics['mean_detection_delay_minutes']} minutes (Threshold: 45 min)")
    print("=" * 70)

    # 5. Detected event details
    summary = detector.get_summary()
    print(f"\n[SUMMARY METRICS]")
    print(f"  Total Wasted Energy Today    : {summary['total_wasted_kwh_today']} kWh")
    print(f"  Total Financial Loss Today   : ₹{summary['total_cost_inr']:,.2f}")
    print(f"  Total CO2 Emissions          : {summary['total_co2_kg']} kg CO2")
    print(f"  Active Unattended AC Count   : {summary['total_ghost_acs']} units")

    # 6. Optional sample alert dispatch
    if send_sample_alert and metrics["all_detected_events"]:
        sample_ev = metrics["all_detected_events"][0]
        print(f"\n[DISPATCH] Dispatching sample incident webhook for {sample_ev.get('wing_id')}...")
        resp = dispatch_ghost_load_alert(
            wing_id=sample_ev.get("wing_id", "BH1"),
            current_kw=sample_ev.get("current_kw", 28.5),
            baseline_med_kw=sample_ev.get("baseline_med_kw", 10.0),
            excess_kw=sample_ev.get("excess_kw", 18.5),
            duration_minutes=sample_ev.get("duration_minutes", 60.0),
            cause=sample_ev.get("cause", "Likely Unattended AC"),
            estimated_units=sample_ev.get("estimated_units", 3),
            wasted_kwh=sample_ev.get("wasted_kwh", 18.5),
            cost_inr=sample_ev.get("cost_inr", 157.25),
            co2_kg=sample_ev.get("co2_kg", 15.17),
        )
        print(f"  Status: {resp.get('status')} | Message: {resp.get('message', 'Incident card created')}")

    print("\n✅ Evaluation successfully completed.\n")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Hostel Ghost Load Detector")
    parser.add_argument("--days", type=int, default=5, help="Number of days to simulate (default: 5)")
    parser.add_argument("--no-new", action="store_true", help="Do not generate a new scenario; use existing")
    parser.add_argument("--send-alert", action="store_true", help="Send sample webhook alert")
    args = parser.parse_args()

    run_evaluation(
        days=args.days,
        generate_new=not args.no_new,
        send_sample_alert=args.send_alert,
    )
