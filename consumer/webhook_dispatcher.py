"""
GridPulse Automated Webhook Alert & Incident Dispatcher (Phase 6)
Dispatches structured incident cards to external webhooks (Slack, Discord, MS Teams, HTTP endpoints)
or mock event sinks for peak-shaving notifications and critical SCADA anomalies.
"""

import os
import sys
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import requests
from dotenv import load_dotenv

# Add project root to sys.path and remove script_dir to prevent package shadowing
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir in sys.path:
    sys.path.remove(script_dir)
PROJECT_ROOT = os.path.abspath(os.path.join(script_dir, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

def get_default_webhook_url() -> str:
    """Returns the current ALERT_WEBHOOK_URL from environment or st.secrets."""
    url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    if not url:
        try:
            import streamlit as st
            if hasattr(st, "secrets"):
                if "ALERT_WEBHOOK_URL" in st.secrets:
                    url = str(st.secrets["ALERT_WEBHOOK_URL"]).strip()
                elif "alert_webhook_url" in st.secrets:
                    url = str(st.secrets["alert_webhook_url"]).strip()
        except Exception:
            pass
    return url


def get_telegram_config() -> Dict[str, str]:
    """Returns the Telegram Bot Token and Chat ID from environment or st.secrets."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        try:
            import streamlit as st
            if hasattr(st, "secrets"):
                token = token or str(st.secrets.get("TELEGRAM_BOT_TOKEN", "")).strip()
                chat_id = chat_id or str(st.secrets.get("TELEGRAM_CHAT_ID", "")).strip()
        except Exception:
            pass
    return {"bot_token": token, "chat_id": chat_id}


DEFAULT_WEBHOOK_URL = get_default_webhook_url()
DISPATCH_HISTORY_FILE = os.path.join(PROJECT_ROOT, "tmp", "webhook_dispatch_history.json")


def format_telegram_message(
    title: str,
    summary: str,
    fields: List[Dict[str, str]],
    portal_url: str = "http://localhost:3000",
) -> str:
    """Formats incident information into clean Telegram HTML markup."""
    clean_summary = summary.replace("*", "")
    lines = [
        f"⚡ <b>GRIDPULSE SCADA ALERT</b>",
        f"<b>{title}</b>",
        "",
        clean_summary,
        "",
    ]
    for f in fields:
        clean_val = str(f.get("value", "")).replace("*", "")
        lines.append(f"• <b>{f['name']}:</b> {clean_val}")
    lines.append("")
    lines.append(f'🔗 <a href="{portal_url}">Open GridPulse Operations Console</a>')
    return "\n".join(lines)


def _deliver_alert(
    url: Optional[str],
    slack_payload: Dict[str, Any],
    telegram_text: str,
) -> Tuple[str, int]:
    """
    Intelligently routes alerts to Telegram Bot API or Slack/Discord webhook.
    Priority order:
    1. Direct Telegram Bot Token & Chat ID
    2. Explicit Telegram webhook/API URL
    3. Slack / Teams / Discord webhook URL
    4. Mock / Simulation fallback
    """
    tg_config = get_telegram_config()
    bot_token = tg_config["bot_token"]
    chat_id = tg_config["chat_id"]

    # 1. Deliver via Telegram Bot API if configured
    if bot_token and chat_id:
        tg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        try:
            resp = requests.post(
                tg_url,
                json={
                    "chat_id": chat_id,
                    "text": telegram_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                },
                timeout=5,
            )
            return ("SENT_TELEGRAM", resp.status_code)
        except Exception as e:
            return (f"FAILED_TELEGRAM: {e}", 500)

    # 2. If URL itself is a Telegram Bot endpoint
    if url and "api.telegram.org" in url:
        try:
            resp = requests.post(
                url,
                json={"text": telegram_text, "parse_mode": "HTML"},
                timeout=5,
            )
            return ("SENT_TELEGRAM", resp.status_code)
        except Exception as e:
            return (f"FAILED_TELEGRAM: {e}", 500)

    # 3. Deliver via Standard Slack / Discord / MS Teams webhook
    if url and url.startswith("http"):
        try:
            resp = requests.post(url, json=slack_payload, timeout=5)
            return ("SENT", resp.status_code)
        except Exception as e:
            return (f"FAILED: {e}", 500)

    # 4. Simulation fallback
    return ("SIMULATED_SUCCESS", 200)


def _record_dispatch_history(entry: Dict[str, Any]):
    """Records dispatched alert to local history file for dashboard audit trail."""
    os.makedirs(os.path.dirname(DISPATCH_HISTORY_FILE), exist_ok=True)
    history = []
    if os.path.exists(DISPATCH_HISTORY_FILE):
        try:
            with open(DISPATCH_HISTORY_FILE, "r") as f:
                history = json.load(f)
        except Exception:
            history = []

    history.insert(0, entry)
    history = history[:50]  # Keep latest 50

    with open(DISPATCH_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, default=str)


def get_dispatch_history() -> List[Dict[str, Any]]:
    """Returns list of recent webhook dispatch events."""
    if os.path.exists(DISPATCH_HISTORY_FILE):
        try:
            with open(DISPATCH_HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def format_slack_card(
    title: str,
    color: str,
    fields: List[Dict[str, str]],
    summary: str,
    username: str = "GridPulse AI Dispatcher",
    icon_emoji: str = ":zap:",
) -> Dict[str, Any]:
    """Formats an incident payload into Slack Block Kit / Attachment compatible JSON."""
    return {
        "username": username,
        "icon_emoji": icon_emoji,
        "attachments": [
            {
                "fallback": f"GridPulse Alert: {title}",
                "color": color,
                "title": f"⚡ GridPulse Incident Dispatch: {title}",
                "text": f"{summary}\n🔗 <http://localhost:8501|Open GridPulse Operations Portal>",
                "fields": [{"title": f["name"], "value": f["value"], "short": f.get("short", True)} for f in fields],
                "footer": "GridPulse Automated Demand Response & SCADA Engine",
                "ts": int(time.time()),
            }
        ],
    }


def dispatch_peak_shaving_alert(dispatch_plan: Dict[str, Any], webhook_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Constructs and dispatches automated peak-shaving alert payload.
    """
    url = webhook_url or get_default_webhook_url()
    max_kw = dispatch_plan.get("peak_forecast_kw", 0.0)
    thresh_kw = dispatch_plan.get("threshold_kw", 850.0)
    overload = dispatch_plan.get("max_overload_kw", 0.0)
    savings = dispatch_plan.get("est_monthly_savings", 0.0)
    actions = dispatch_plan.get("actions", [])

    action_summary_lines = []
    for a in actions:
        if a["status"] == "ARMED":
            action_summary_lines.append(f"• *Tier {a['tier']} ({a['category']}):* {a['name']} -> {a['active_shed_kw']} kW active shed")

    action_text = "\n".join(action_summary_lines) if action_summary_lines else "No automated action required."

    fields = [
        {"name": "Forecast Peak", "value": f"{max_kw:,.1f} kW", "short": True},
        {"name": "Contract Threshold", "value": f"{thresh_kw:,.1f} kW", "short": True},
        {"name": "Projected Overload", "value": f"+{overload:.1f} kW", "short": True},
        {"name": "Potential Penalty Savings", "value": f"INR {savings:,.0f}", "short": True},
        {"name": "Active Dispatch Directives", "value": action_text, "short": False},
    ]

    payload = format_slack_card(
        title=f"IMPENDING PEAK DEMAND BREACH (+{overload:.1f} kW)",
        color="#f59e0b" if overload < 100 else "#ef4444",
        fields=fields,
        summary=f"Automated Demand Response system has triggered peak-shaving countermeasures to prevent contract demand penalties.",
        username="GridPulse AI Dispatcher",
        icon_emoji=":battery:",
    )

    telegram_text = format_telegram_message(
        title=f"IMPENDING PEAK DEMAND BREACH (+{overload:.1f} kW)",
        summary="Automated Demand Response system has triggered peak-shaving countermeasures to prevent contract demand penalties.",
        fields=fields,
    )

    result_status, status_code = _deliver_alert(url, payload, telegram_text)

    record = {
        "timestamp": datetime.now().isoformat(),
        "event_type": "PEAK_SHAVING_DISPATCH",
        "title": f"Peak Demand Breach (+{overload:.1f} kW)",
        "target_url": url if url else ("TELEGRAM_BOT" if get_telegram_config()["bot_token"] else "MOCK_CONSOLE"),
        "status": result_status,
        "status_code": status_code,
        "payload": payload,
        "telegram_text": telegram_text,
    }
    _record_dispatch_history(record)
    return record


def dispatch_scada_fault_alert(
    meter_id: str,
    building_id: str,
    alert_type: str,
    severity: str,
    metric_value: float,
    threshold_value: float,
    webhook_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Constructs and dispatches immediate SCADA electrical fault alert (e.g. Voltage Sag).
    """
    url = webhook_url or get_default_webhook_url()
    color_map = {"CRITICAL": "#ef4444", "WARNING": "#f59e0b", "INFO": "#3b82f6"}

    fields = [
        {"name": "Meter Identifier", "value": meter_id, "short": True},
        {"name": "Building Location", "value": building_id, "short": True},
        {"name": "Observed Metric", "value": f"{metric_value:.2f}", "short": True},
        {"name": "Breached Limit", "value": f"{threshold_value:.2f}", "short": True},
    ]

    payload = format_slack_card(
        title=f"SCADA Electrical Fault: {alert_type} [{severity}]",
        color=color_map.get(severity, "#ef4444"),
        fields=fields,
        summary=f"Sub-meter {meter_id} in {building_id} observed a {alert_type} breach ({metric_value:.2f} vs limit {threshold_value:.2f}).",
        username="GridPulse SCADA Watchdog",
        icon_emoji=":rotating_light:",
    )

    telegram_text = format_telegram_message(
        title=f"SCADA Electrical Fault: {alert_type} [{severity}]",
        summary=f"Sub-meter {meter_id} in {building_id} observed a {alert_type} breach ({metric_value:.2f} vs limit {threshold_value:.2f}).",
        fields=fields,
    )

    result_status, status_code = _deliver_alert(url, payload, telegram_text)

    record = {
        "timestamp": datetime.now().isoformat(),
        "event_type": f"SCADA_{alert_type}",
        "title": f"{alert_type} at {meter_id} ({building_id})",
        "target_url": url if url else ("TELEGRAM_BOT" if get_telegram_config()["bot_token"] else "MOCK_CONSOLE"),
        "status": result_status,
        "status_code": status_code,
        "payload": payload,
        "telegram_text": telegram_text,
    }
    _record_dispatch_history(record)
    return record


# In-memory cooldown cache mapping wing_id -> last_dispatched_unix_timestamp
LAST_GHOST_ALERT_DISPATCH: Dict[str, float] = {}


def dispatch_ghost_load_alert(
    wing_id: str,
    current_kw: float,
    baseline_med_kw: float,
    excess_kw: float,
    duration_minutes: float,
    cause: str,
    estimated_units: int,
    wasted_kwh: float,
    cost_inr: float,
    co2_kg: float,
    meter_id: Optional[str] = None,
    webhook_url: Optional[str] = None,
    cooldown_minutes: float = 60.0,
) -> Dict[str, Any]:
    """
    Dispatches a structured incident card for an unoccupied hostel room ghost-load anomaly.
    Enforces a strict per-wing cooldown (default 60 minutes) to prevent notification fatigue.
    """
    now_ts = time.time()
    last_sent = LAST_GHOST_ALERT_DISPATCH.get(wing_id, 0.0)
    cooldown_seconds = cooldown_minutes * 60.0

    if (now_ts - last_sent) < cooldown_seconds:
        remaining_m = round((cooldown_seconds - (now_ts - last_sent)) / 60.0, 1)
        return {
            "status": "SUPPRESSED_COOLDOWN",
            "message": f"Alert for {wing_id} suppressed by cooldown policy ({remaining_m}m remaining).",
            "wing_id": wing_id,
            "timestamp": datetime.now().isoformat(),
        }

    url = webhook_url or get_default_webhook_url()
    color = "#f97316" if "AC" in cause else "#eab308"

    fields = [
        {"name": "Hostel Facility", "value": f"*{wing_id}* ({meter_id or 'Main Meter'})", "short": True},
        {"name": "Appliance Diagnosis", "value": f"*{cause}* (~{estimated_units} units)", "short": True},
        {"name": "Current Demand", "value": f"{current_kw:.1f} kW", "short": True},
        {"name": "Normal Baseline", "value": f"{baseline_med_kw:.1f} kW", "short": True},
        {"name": "Excess Phantom Load", "value": f"*+{excess_kw:.1f} kW*", "short": True},
        {"name": "Unoccupied Duration", "value": f"{duration_minutes:.0f} mins", "short": True},
        {"name": "Accumulated Waste", "value": f"{wasted_kwh:.1f} kWh", "short": True},
        {"name": "Financial / Carbon Impact", "value": f"₹{cost_inr:,.0f} | {co2_kg:.1f} kg CO₂", "short": True},
    ]

    payload = format_slack_card(
        title=f"Unoccupied Hostel Ghost Load: {wing_id}",
        color=color,
        fields=fields,
        summary=(
            f"⚠️ *Unattended Energy Waste Alert*: {wing_id} is exhibiting +{excess_kw:.1f} kW above expected "
            f"academic baseline for {duration_minutes:.0f} continuous minutes during scheduled lecture hours. "
            f"Probable cause: *{cause}*."
        ),
        username="GridPulse Hostel Watchdog",
        icon_emoji=":bed:",
    )

    telegram_text = format_telegram_message(
        title=f"🚨 GHOST LOAD ALERT: {wing_id}",
        summary=(
            f"Unattended Energy Waste Alert: {wing_id} is exhibiting +{excess_kw:.1f} kW above expected "
            f"academic baseline for {duration_minutes:.0f} continuous minutes during scheduled lecture hours. "
            f"Probable cause: {cause}."
        ),
        fields=fields,
    )

    result_status, status_code = _deliver_alert(url, payload, telegram_text)
    LAST_GHOST_ALERT_DISPATCH[wing_id] = now_ts

    record = {
        "timestamp": datetime.now().isoformat(),
        "event_type": "GHOST_LOAD_ALERT",
        "title": f"Ghost Load at {wing_id} ({cause})",
        "target_url": url if url else ("TELEGRAM_BOT" if get_telegram_config()["bot_token"] else "MOCK_CONSOLE"),
        "status": result_status,
        "status_code": status_code,
        "payload": payload,
        "telegram_text": telegram_text,
    }
    _record_dispatch_history(record)
    return record


if __name__ == "__main__":
    print("[WEBHOOK DISPATCHER TEST]")
    test_plan = {
        "peak_forecast_kw": 885.5,
        "threshold_kw": 800.0,
        "max_overload_kw": 85.5,
        "est_monthly_savings": 29925.0,
        "actions": [
            {"tier": 1, "category": "Soft Shedding", "name": "Non-Critical Facilities & EV Setback", "active_shed_kw": 45.0, "status": "ARMED"},
            {"tier": 2, "category": "Chiller Cycling", "name": "Lecture Theatre & Academic HVAC Cycling", "active_shed_kw": 40.5, "status": "ARMED"},
        ],
    }
    res = dispatch_peak_shaving_alert(test_plan)
    print("Peak alert dispatch result:", res["status"])

    fault_res = dispatch_scada_fault_alert(
        meter_id="M001",
        building_id="BH1",
        alert_type="VOLTAGE_SAG",
        severity="CRITICAL",
        metric_value=211.4,
        threshold_value=220.0,
    )
    print("Fault alert dispatch result:", fault_res["status"])
    print(f"Total entries in dispatch audit log: {len(get_dispatch_history())}")
