import csv
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timedelta

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from database.db import (
        init_db,
        seed_dimensions,
        insert_readings_and_alerts,
        get_db_stats,
    )
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False

# Structured categorization of campus infrastructure
GROUND_TRUTH_PATH = os.path.join(PROJECT_ROOT, "data", "simulator", "ground_truth_waste_events.json")


def get_ground_truth_events():
    """Reads recorded ground-truth unoccupied waste events from JSON audit log."""
    if os.path.exists(GROUND_TRUTH_PATH):
        try:
            with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_ground_truth_event(event_dict):
    """Appends a ground-truth waste event to the audit store."""
    os.makedirs(os.path.dirname(GROUND_TRUTH_PATH), exist_ok=True)
    events = get_ground_truth_events()
    # Avoid duplicate event_id
    if not any(e.get("event_id") == event_dict.get("event_id") for e in events):
        events.append(event_dict)
        with open(GROUND_TRUTH_PATH, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2, default=str)


def clear_ground_truth_events():
    """Clears the ground-truth waste events audit file."""
    if os.path.exists(GROUND_TRUTH_PATH):
        try:
            os.remove(GROUND_TRUTH_PATH)
        except Exception:
            pass


CAMPUS_INFRASTRUCTURE = {
    "Hostels": {
        "BH1": 3,
        "BH2": 3,
        "BH3": 3,
        "BH4": 3,
        "GH": 3,
        "IVH": 3,
        "Satpura": 3,
    },
    "Departments": {
        "Management": 1,
        "IT": 1,
        "CS": 1,
        "EEE": 1,
        "Engineering Science": 1,
        "GEN-LAB": 1,
    },
    "Lecture Theatres": {
        "LT1": 2,
        "LT2": 2,
    },
    "Facilities": {
        "Convention Center": 2,
        "SC": 2,
        "Academic Block": 2,
        "Library": 2,
        "Cafeteria": 1,
        "Powerhouse": 1,
        "OAT": 1,
    },
}

CSV_HEADERS = [
    "event_id",
    "timestamp",
    "meter_id",
    "building_id",
    "building_type",
    "power_kw",
    "voltage_v",
    "current_a",
    "power_factor",
]


def create_meters():
    """Generates a list of meter configurations mapped to campus buildings and categories."""
    meters = []
    meter_number = 1

    for category, buildings in CAMPUS_INFRASTRUCTURE.items():
        for building, number_of_meters in buildings.items():
            for _ in range(number_of_meters):
                meter = {
                    "meter_id": f"M{meter_number:03d}",
                    "building_id": building,
                    "building_type": category,
                }
                meters.append(meter)
                meter_number += 1

    return meters


def calculate_building_power(building, category, dt):
    """
    Realistic schedule-driven power simulation based on:
    - Time of day (hours 0-24)
    - Weekdays vs Weekends (Mon-Fri vs Sat-Sun)
    - Specific rules:
        * Classes 9 AM - 6 PM on weekdays for Depts and Lecture Theatres
        * Library closed on Sundays (minimal idle power)
        * Hostels peak early morning & late evenings/nights
        * Cafeteria peaks during breakfast, lunch, and dinner
    """
    hour = dt.hour + dt.minute / 60.0
    day_of_week = dt.weekday()  # 0: Monday ... 5: Saturday, 6: Sunday
    is_weekend = day_of_week in [5, 6]
    is_sunday = day_of_week == 6

    # 1. Departments (Management, IT, CS, EEE, Eng Science, GEN-LAB)
    if category == "Departments":
        if not is_weekend and (8.5 <= hour <= 18.5):
            bell_curve = math.sin((hour - 8.5) / 10.0 * math.pi)
            base_power = 22 + 18 * bell_curve + random.uniform(-2, 3)
        elif not is_weekend and (18.5 < hour <= 21.5):
            base_power = random.uniform(8, 15)
        elif is_weekend and (10 <= hour <= 16):
            base_power = random.uniform(5, 11)
        else:
            base_power = random.uniform(3.5, 7.5)

    # 2. Lecture Theatres (LT1, LT2)
    elif category == "Lecture Theatres":
        if not is_weekend and (8.5 <= hour <= 18.0):
            bell_curve = math.sin((hour - 8.5) / 9.5 * math.pi)
            base_power = 18 + 14 * bell_curve + random.uniform(-2, 3)
        elif not is_weekend and (18.0 < hour <= 21.0):
            base_power = random.uniform(6, 12)
        else:
            base_power = random.uniform(1.5, 4.0)

    # 3. Hostels (BH1-BH4, GH, IVH, Satpura)
    elif category == "Hostels":
        if not is_weekend:
            if 6.0 <= hour <= 9.0:
                base_power = random.uniform(20, 32)
            elif 9.0 < hour < 17.5:
                base_power = random.uniform(7, 13)
            elif 17.5 <= hour <= 24.0:
                base_power = random.uniform(22, 36)
            else:
                base_power = random.uniform(9, 16)
        else:
            if 9.0 <= hour <= 24.0:
                base_power = random.uniform(18, 32)
            else:
                base_power = random.uniform(10, 17)

    # 4. Facilities (Library, Cafeteria, Powerhouse, SC, OAT, Academic Block, Convention Center)
    elif category == "Facilities":
        if building == "Library":
            if is_sunday:
                base_power = random.uniform(1.5, 3.5)
            elif not is_sunday and (8.0 <= hour <= 22.0):
                bell_curve = math.sin((hour - 8.0) / 14.0 * math.pi)
                base_power = 20 + 16 * bell_curve + random.uniform(-2, 2.5)
            else:
                base_power = random.uniform(3.0, 5.5)

        elif building == "Convention Center":
            if (is_weekend and 10 <= hour <= 20) or (16 <= hour <= 21):
                base_power = random.uniform(22, 38)
            else:
                base_power = random.uniform(3.0, 7.0)

        elif building == "Cafeteria":
            if (7.0 <= hour <= 9.5) or (12.0 <= hour <= 14.5) or (19.0 <= hour <= 22.0):
                base_power = random.uniform(22, 36)
            elif 15.0 <= hour <= 18.0:
                base_power = random.uniform(10, 16)
            else:
                base_power = random.uniform(4.0, 7.5)

        elif building == "Powerhouse":
            base_power = random.uniform(38, 55)

        elif building in ["SC", "OAT"]:
            if 16.0 <= hour <= 22.5:
                base_power = random.uniform(14, 28)
            else:
                base_power = random.uniform(2.5, 6.0)

        elif building == "Academic Block":
            if not is_weekend and (8.5 <= hour <= 18.0):
                base_power = random.uniform(22, 38)
            else:
                base_power = random.uniform(4.0, 9.0)

        else:
            base_power = random.uniform(6.0, 15.0)

    else:
        base_power = random.uniform(5.0, 15.0)

    return max(1.0, base_power)


def generate_reading(meter, event_id, dt=None, inject_waste=False, waste_config=None):
    """
    Generates a single simulated meter reading.
    Supports unoccupied hostel waste injection (AC compressor or resistive lighting)
    during weekday lecture hours (10:00 to 16:00).
    """
    if dt is None:
        dt = datetime.now()

    building = meter["building_id"]
    category = meter["building_type"]

    power_kw = calculate_building_power(building, category, dt)
    hour_float = dt.hour + dt.minute / 60.0
    day_of_week = dt.weekday()
    is_weekday_academic = (day_of_week < 5) and (10.0 <= hour_float <= 16.0)

    # Voltage simulation: nominal 230V
    base_voltage = 233.0 - (power_kw / 50.0) * 4.0
    voltage_v = base_voltage + random.gauss(0, 2.5)

    # 1.5% chance of realistic grid anomaly injection (sag or surge)
    rand_anom = random.random()
    if rand_anom < 0.01:
        voltage_v = random.uniform(205.0, 217.0)
    elif rand_anom < 0.02:
        voltage_v = random.uniform(242.0, 249.0)

    # Power Factor calculation
    if category in ["Facilities", "Departments"]:
        base_pf = random.uniform(0.86, 0.95)
    else:
        base_pf = random.uniform(0.90, 0.98)

    if random.random() < 0.01:
        base_pf = random.uniform(0.78, 0.84)

    # ---------------------------------------------------------
    # Unoccupied Hostel Waste Injection Logic
    # ---------------------------------------------------------
    injected_meta = None
    if inject_waste and category == "Hostels" and is_weekday_academic:
        # Default waste config if not specified
        if waste_config is None:
            waste_config = {
                "BH1": {"type": "AC_COMPRESSOR", "excess_kw": 14.0, "target_pf": 0.78, "on_mins": 18, "off_mins": 10},
                "BH3": {"type": "AC_COMPRESSOR", "excess_kw": 16.5, "target_pf": 0.77, "on_mins": 18, "off_mins": 10},
                "BH2": {"type": "RESISTIVE_LIGHTING", "excess_kw": 9.0, "target_pf": 0.99},
            }

        cfg = waste_config.get(building)
        if cfg:
            w_type = cfg.get("type", "AC_COMPRESSOR")
            excess_kw = cfg.get("excess_kw", 14.0)
            target_pf = cfg.get("target_pf", 0.78)

            if w_type == "AC_COMPRESSOR":
                on_m = cfg.get("on_mins", 18)
                off_m = cfg.get("off_mins", 10)
                period = max(1, on_m + off_m)
                cycle_minute = int((dt.hour * 60 + dt.minute) % period)
                if cycle_minute < on_m:
                    # Compressor ON: heavy inductive load with low power factor
                    power_kw += excess_kw + random.uniform(-0.4, 0.4)
                    base_pf = random.uniform(target_pf - 0.02, target_pf + 0.02)
                    injected_meta = {
                        "waste_type": "AC_COMPRESSOR",
                        "duty_state": "ON",
                        "excess_kw": excess_kw,
                        "pf": base_pf,
                    }
                else:
                    # Compressor OFF (resting between cycles)
                    injected_meta = {
                        "waste_type": "AC_COMPRESSOR",
                        "duty_state": "OFF",
                        "excess_kw": 0.0,
                        "pf": base_pf,
                    }
            elif w_type == "RESISTIVE_LIGHTING":
                # Flat resistive load: steady high PF
                power_kw += excess_kw + random.uniform(-0.3, 0.3)
                base_pf = min(1.0, random.uniform(target_pf - 0.01, 1.0))
                injected_meta = {
                    "waste_type": "RESISTIVE_LIGHTING",
                    "duty_state": "ON",
                    "excess_kw": excess_kw,
                    "pf": base_pf,
                }

    current_a = (power_kw * 1000.0) / max(voltage_v, 1.0)

    reading = {
        "event_id": f"E{event_id:06d}",
        "timestamp": dt.isoformat(timespec="seconds"),
        "meter_id": meter["meter_id"],
        "building_id": meter["building_id"],
        "building_type": meter["building_type"],
        "power_kw": round(power_kw, 2),
        "voltage_v": round(voltage_v, 2),
        "current_a": round(current_a, 2),
        "power_factor": round(base_pf, 3),
    }
    if injected_meta:
        reading["waste_injection"] = injected_meta

    return reading


def save_readings_to_csv(readings, filepath="data/raw/energy_data.csv", overwrite=False):
    """Appends or writes readings to CSV file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    mode = "w" if overwrite else "a"
    file_exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0 and not overwrite

    with open(filepath, mode=mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(readings)


def generate_historical_batch(
    days=7,
    interval_minutes=30,
    output_path="data/raw/energy_data.csv",
    save_to_db=True,
    overwrite_csv=True,
):
    """
    Generates realistic multi-day historical time-series data:
    - Sinks to normalized PostgreSQL tables (`energy_readings` and `alerts`)
    - Sinks to raw CSV for backward compatibility
    """
    meters = create_meters()
    readings = []
    event_id = 1

    total_intervals = int((days * 24 * 60) / interval_minutes)
    now = datetime.now()
    start_time = now - timedelta(days=days)

    print(f"[SIMULATOR] Generating {days}-day dataset ({interval_minutes}m interval across {len(meters)} meters)...")

    for i in range(total_intervals):
        current_dt = start_time + timedelta(minutes=i * interval_minutes)
        for meter in meters:
            reading = generate_reading(meter, event_id=event_id, dt=current_dt)
            readings.append(reading)
            event_id += 1

    # Save to CSV
    save_readings_to_csv(readings, output_path, overwrite=overwrite_csv)
    print(f"[CSV] Saved {len(readings)} records -> {output_path}")

    # Save to PostgreSQL
    if save_to_db and DB_AVAILABLE:
        try:
            print("[POSTGRES] Seeding dimension tables (buildings, meters)...")
            seed_dimensions(CAMPUS_INFRASTRUCTURE)

            print("[POSTGRES] Ingesting historical batch into energy_readings & alerts...")
            chunk_size = 4000
            total_readings = 0
            total_alerts = 0
            for k in range(0, len(readings), chunk_size):
                chunk = readings[k : k + chunk_size]
                n_readings, n_alerts = insert_readings_and_alerts(chunk)
                total_readings += n_readings
                total_alerts += n_alerts

            print(f"[POSTGRES] Ingested {total_readings} rows into `energy_readings` and {total_alerts} alerts into `alerts` table!")
            stats = get_db_stats()
            print(f"[POSTGRES STATS] Current DB State: {stats}")
        except Exception as e:
            print(f"[POSTGRES ERROR] Failed inserting to DB: {e}")

    return readings


def run_live_simulation(interval_sec=3, save_to_db=True, output_path="data/raw/energy_data.csv"):
    """Continuously generates live readings and streams them into PostgreSQL & CSV."""
    meters = create_meters()
    print(f"[START] Live Simulator active ({len(meters)} meters, interval: {interval_sec}s)")
    if save_to_db and DB_AVAILABLE:
        seed_dimensions(CAMPUS_INFRASTRUCTURE)
        print("[SINK] Streaming to normalized Neon PostgreSQL schema and CSV.")
    print("Press Ctrl+C to stop.\n")

    event_id = int(time.time())
    iteration = 0
    try:
        while True:
            batch = []
            now = datetime.now()
            for meter in meters:
                batch.append(generate_reading(meter, event_id=event_id, dt=now))
                event_id += 1

            # Save to CSV
            save_readings_to_csv(batch, output_path, overwrite=False)

            # Insert into PostgreSQL
            if save_to_db and DB_AVAILABLE:
                try:
                    insert_readings_and_alerts(batch)
                except Exception as e:
                    print(f"[DB ERROR] {e}")

            iteration += 1
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Ingested {len(batch)} readings to DB & CSV (Batch #{iteration})")
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        print("\n[STOP] Simulation stopped by user.")


def generate_hostel_waste_scenario(
    days=5,
    interval_minutes=15,
    output_path=None,
    record_ground_truth=True,
    clear_existing_ground_truth=True,
):
    """
    Generates a multi-day time-series with synthetic ground-truth injected
    unoccupied hostel waste events (AC compressor cycling and resistive lighting)
    during academic hours (10:00 to 16:00).
    Logs ground-truth episodes to data/simulator/ground_truth_waste_events.json.
    """
    if clear_existing_ground_truth:
        clear_ground_truth_events()

    meters = create_meters()
    readings = []
    event_id = 1

    # Start on a Monday 00:00 to ensure clear weekday/weekend cycles
    now = datetime.now()
    days_since_monday = now.weekday()
    monday_start = (now - timedelta(days=days_since_monday + 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    total_intervals = int((days * 24 * 60) / interval_minutes)

    # Pre-defined ground truth waste injection schedule
    # Format: day_offset (0=Mon, 1=Tue...), start_hour, end_hour, building, meter_id, type, excess_kw, target_pf, expected_trigger
    gt_schedule = [
        # Episode 1: BH1 Wing A (M001) - AC Compressor waste on Monday 10:30 - 15:30 (5 hours, >=45m -> True Positive)
        {
            "event_id": "GT_BH1_MON_AC",
            "day_offset": 0,
            "start_time": (monday_start + timedelta(days=0, hours=10, minutes=30)),
            "end_time": (monday_start + timedelta(days=0, hours=15, minutes=30)),
            "building_id": "BH1",
            "meter_id": "M001",
            "waste_type": "AC_COMPRESSOR",
            "excess_kw": 14.5,
            "target_pf": 0.78,
            "on_mins": 18,
            "off_mins": 10,
            "expected_trigger": True,
        },
        # Episode 2: BH2 Wing A (M004) - Resistive Lighting waste on Tuesday 11:00 - 14:30 (3.5 hours, >=45m -> True Positive)
        {
            "event_id": "GT_BH2_TUE_LIGHTS",
            "day_offset": 1,
            "start_time": (monday_start + timedelta(days=1, hours=11, minutes=0)),
            "end_time": (monday_start + timedelta(days=1, hours=14, minutes=30)),
            "building_id": "BH2",
            "meter_id": "M004",
            "waste_type": "RESISTIVE_LIGHTING",
            "excess_kw": 9.5,
            "target_pf": 0.99,
            "expected_trigger": True,
        },
        # Episode 3: BH3 Wing A (M007) - AC Compressor waste on Thursday 10:15 - 15:45 (5.5 hours, >=45m -> True Positive)
        {
            "event_id": "GT_BH3_THU_AC",
            "day_offset": 3,
            "start_time": (monday_start + timedelta(days=3, hours=10, minutes=15)),
            "end_time": (monday_start + timedelta(days=3, hours=15, minutes=45)),
            "building_id": "BH3",
            "meter_id": "M007",
            "waste_type": "AC_COMPRESSOR",
            "excess_kw": 15.5,
            "target_pf": 0.77,
            "on_mins": 18,
            "off_mins": 10,
            "expected_trigger": True,
        },
        # Episode 4: BH4 Wing A (M010) - Short transient spike on Wednesday 12:00 - 12:20 (20 minutes, <45m -> Must NOT trigger!)
        {
            "event_id": "GT_BH4_WED_TRANSIENT",
            "day_offset": 2,
            "start_time": (monday_start + timedelta(days=2, hours=12, minutes=0)),
            "end_time": (monday_start + timedelta(days=2, hours=12, minutes=20)),
            "building_id": "BH4",
            "meter_id": "M010",
            "waste_type": "RESISTIVE_LIGHTING",
            "excess_kw": 11.0,
            "target_pf": 0.96,
            "expected_trigger": False,
        },
    ]

    # Save ground truth audit records
    if record_ground_truth:
        for ep in gt_schedule:
            save_ground_truth_event({
                "event_id": ep["event_id"],
                "building_id": ep["building_id"],
                "meter_id": ep["meter_id"],
                "waste_type": ep["waste_type"],
                "start_time": ep["start_time"].isoformat(),
                "end_time": ep["end_time"].isoformat(),
                "duration_minutes": int((ep["end_time"] - ep["start_time"]).total_seconds() / 60),
                "excess_kw": ep["excess_kw"],
                "target_pf": ep["target_pf"],
                "expected_trigger": ep["expected_trigger"],
            })

    # Generate readings
    for i in range(total_intervals):
        dt = monday_start + timedelta(minutes=i * interval_minutes)

        # Check if any ground truth event is active at this instant for a specific meter
        active_meter_wastes = {}
        for ep in gt_schedule:
            if ep["start_time"] <= dt <= ep["end_time"]:
                active_meter_wastes[ep["meter_id"]] = {
                    "type": ep["waste_type"],
                    "excess_kw": ep["excess_kw"],
                    "target_pf": ep["target_pf"],
                    "on_mins": ep.get("on_mins", 18),
                    "off_mins": ep.get("off_mins", 10),
                }

        for meter in meters:
            m_id = meter["meter_id"]
            b_id = meter["building_id"]
            if m_id in active_meter_wastes:
                reading = generate_reading(
                    meter,
                    event_id=event_id,
                    dt=dt,
                    inject_waste=True,
                    waste_config={b_id: active_meter_wastes[m_id]},
                )
            else:
                reading = generate_reading(meter, event_id=event_id, dt=dt, inject_waste=False)
            readings.append(reading)
            event_id += 1

    if output_path:
        save_readings_to_csv(readings, output_path, overwrite=True)

    return readings


if __name__ == "__main__":
    output_csv = os.path.join("data", "raw", "energy_data.csv")
    generate_historical_batch(days=7, interval_minutes=30, output_path=output_csv, save_to_db=True)