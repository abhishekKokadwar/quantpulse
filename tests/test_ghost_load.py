"""
Unit Test Suite for Hostel Ghost Load & Unoccupied Room Waste Detector
Verifies robust Median/MAD baselines, hysteresis state machines,
AC vs resistive load disaggregation, alert cooldown, and benchmark evaluation metrics.
"""

import os
import sys
import unittest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analysis.ghost_load_detector import (
    is_academic_hours,
    WingWasteStateMachine,
    HostelGhostLoadDetector,
    MAD_SCALE_FACTOR,
)
from consumer.webhook_dispatcher import (
    dispatch_ghost_load_alert,
    LAST_GHOST_ALERT_DISPATCH,
)


class TestHostelGhostLoadDetector(unittest.TestCase):

    def test_01_academic_hours_filter(self):
        """Verifies lecture hours filtering (Mon-Fri 09:00 to 17:00)."""
        # Monday 11:30 AM -> True
        dt_weekday_day = datetime(2026, 9, 14, 11, 30)
        self.assertTrue(is_academic_hours(dt_weekday_day))

        # Monday 08:30 AM (before classes) -> False
        dt_weekday_early = datetime(2026, 9, 14, 8, 30)
        self.assertFalse(is_academic_hours(dt_weekday_early))

        # Monday 18:00 PM (after classes) -> False
        dt_weekday_night = datetime(2026, 9, 14, 18, 0)
        self.assertFalse(is_academic_hours(dt_weekday_night))

        # Saturday 12:00 PM (weekend) -> False
        dt_weekend = datetime(2026, 9, 19, 12, 0)
        self.assertFalse(is_academic_hours(dt_weekend))

    def test_02_robust_median_mad_baseline(self):
        """Verifies that Median and MAD resist contamination from extreme waste outliers."""
        clean_data = [9.0, 10.0, 9.5, 10.5, 10.0, 11.0, 9.8, 10.2]
        # Inject recurrent waste outliers
        contaminated_data = clean_data + [32.0, 35.0]

        mean_val = np.mean(contaminated_data)
        std_val = np.std(contaminated_data)
        med_val = np.median(contaminated_data)
        mad_val = np.median(np.abs(contaminated_data - med_val))

        # Mean is pulled up to ~14.7 kW by outliers
        self.assertGreater(mean_val, 13.0)
        # Median remains resiliently close to 10.0 kW
        self.assertAlmostEqual(med_val, 10.1, delta=0.5)
        # Robust scale factor matches consistency
        robust_std = MAD_SCALE_FACTOR * mad_val
        self.assertLess(robust_std, std_val)

    def test_03_state_machine_hysteresis(self):
        """Verifies hysteresis state machine: open at Z > 2.5 for >=45m, close at Z < 1.5."""
        sm = WingWasteStateMachine(wing_id="BH1", meter_id="M001")
        base_time = datetime(2026, 9, 14, 10, 0)  # Monday 10:00

        # Step 1: 15 mins elevated (Z=3.0) -> elevated_minutes = 15, event_open = False
        res1 = sm.update(base_time, p_kw=25.0, pf=0.78, baseline_med=10.0, baseline_mad=2.0, step_minutes=15.0)
        self.assertIsNone(res1)
        self.assertEqual(sm.elevated_minutes, 15.0)
        self.assertFalse(sm.event_open)

        # Step 2: 30 mins elevated -> elevated_minutes = 30, event_open = False
        res2 = sm.update(base_time + timedelta(minutes=15), p_kw=24.5, pf=0.78, baseline_med=10.0, baseline_mad=2.0, step_minutes=15.0)
        self.assertIsNone(res2)
        self.assertEqual(sm.elevated_minutes, 30.0)
        self.assertFalse(sm.event_open)

        # Step 3: 45 mins elevated -> elevated_minutes = 45, event_open = True! Alert triggered!
        res3 = sm.update(base_time + timedelta(minutes=30), p_kw=25.2, pf=0.78, baseline_med=10.0, baseline_mad=2.0, step_minutes=15.0)
        self.assertIsNotNone(res3)
        self.assertTrue(sm.event_open)
        self.assertEqual(res3["alert_type"], "GHOST_LOAD_OPENED")

        # Step 4: Normalizes back below Z < 1.5 (e.g. 11.0 kW) -> event closes!
        sm.update(base_time + timedelta(minutes=45), p_kw=11.0, pf=0.95, baseline_med=10.0, baseline_mad=2.0, step_minutes=15.0)
        self.assertFalse(sm.event_open)
        self.assertEqual(len(sm.closed_events), 1)

    def test_04_ac_compressor_disaggregation(self):
        """Verifies NILM disaggregation tags low PF and periodic loads as 'Likely Unattended AC'."""
        sm = WingWasteStateMachine(wing_id="BH1", meter_id="M001")
        base_time = datetime(2026, 9, 14, 10, 0)

        # Feed 3 steps of inductive AC compressor load (PF 0.78, power 25 kW)
        for i in range(3):
            sm.update(base_time + timedelta(minutes=i * 15), p_kw=25.0 + (i % 2) * 2.0, pf=0.78, baseline_med=10.0, baseline_mad=1.5, step_minutes=15.0)

        self.assertTrue(sm.event_open)
        self.assertEqual(sm.cause, "Likely Unattended AC")
        self.assertGreaterEqual(sm.estimated_units, 2)

    def test_05_resistive_lighting_disaggregation(self):
        """Verifies NILM disaggregation tags high PF loads as 'Likely Resistive / Lighting / Heater'."""
        sm = WingWasteStateMachine(wing_id="BH2", meter_id="M004")
        base_time = datetime(2026, 9, 14, 11, 0)

        # Feed 3 steps of flat resistive lighting load (PF 0.99, power 20 kW)
        for i in range(3):
            sm.update(base_time + timedelta(minutes=i * 15), p_kw=20.0, pf=0.99, baseline_med=10.0, baseline_mad=1.5, step_minutes=15.0)

        self.assertTrue(sm.event_open)
        self.assertEqual(sm.cause, "Likely Resistive / Lighting / Heater")

    def test_06_alert_cooldown(self):
        """Verifies that incident dispatcher respects the 60-minute cooldown policy per wing."""
        wing = "BH_TEST_WING"
        LAST_GHOST_ALERT_DISPATCH.clear()

        # First alert -> SENT or SIMULATED_SUCCESS
        resp1 = dispatch_ghost_load_alert(
            wing_id=wing,
            current_kw=28.0,
            baseline_med_kw=10.0,
            excess_kw=18.0,
            duration_minutes=60.0,
            cause="Likely Unattended AC",
            estimated_units=3,
            wasted_kwh=18.0,
            cost_inr=153.0,
            co2_kg=14.7,
            cooldown_minutes=60.0,
        )
        self.assertIn(resp1["status"], ["SENT", "SIMULATED_SUCCESS"])

        # Immediate second alert for same wing -> SUPPRESSED_COOLDOWN
        resp2 = dispatch_ghost_load_alert(
            wing_id=wing,
            current_kw=29.0,
            baseline_med_kw=10.0,
            excess_kw=19.0,
            duration_minutes=65.0,
            cause="Likely Unattended AC",
            estimated_units=3,
            wasted_kwh=19.0,
            cost_inr=161.5,
            co2_kg=15.5,
            cooldown_minutes=60.0,
        )
        self.assertEqual(resp2["status"], "SUPPRESSED_COOLDOWN")

    def test_07_ground_truth_evaluation_metrics(self):
        """Verifies precision, recall, and detection delay calculation against ground truth."""
        detector = HostelGhostLoadDetector()
        start = datetime(2026, 9, 14, 10, 30)
        end = datetime(2026, 9, 14, 15, 30)

        gt_events = [
            {
                "event_id": "GT_1",
                "building_id": "BH1",
                "meter_id": "M001",
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "duration_minutes": 300,
                "expected_trigger": True,
            },
            {
                "event_id": "GT_2",
                "building_id": "BH4",
                "meter_id": "M010",
                "start_time": (start + timedelta(days=1)).isoformat(),
                "end_time": (start + timedelta(days=1, minutes=20)).isoformat(),
                "duration_minutes": 20,
                "expected_trigger": False,  # Transient spike, should not trigger
            },
        ]

        # Injected match in detected events log
        detector.detected_events_log.append({
            "event_id": "GHOST_M001_1",
            "wing_id": "BH1",
            "meter_id": "M001",
            "timestamp": (start + timedelta(minutes=45)).isoformat(),
        })

        metrics = detector.evaluate_against_ground_truth(gt_events)
        self.assertEqual(metrics["true_positives"], 1)
        self.assertEqual(metrics["false_positives"], 0)
        self.assertEqual(metrics["false_negatives"], 0)
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["recall"], 1.0)
        self.assertEqual(metrics["mean_detection_delay_minutes"], 45.0)


if __name__ == "__main__":
    unittest.main()
