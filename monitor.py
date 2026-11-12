import csv
import os
import platform
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

DEVICES_FILE = "devices.csv"
REPORTS_DIR = "reports"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def send_telegram_alert(offline_devices: list[dict]) -> bool:
    """
    Menghantar notifikasi amaran ke Telegram jika terdapat peranti OFFLINE atau port CLOSED.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not offline_devices:
        return False

    timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    lines = [
        "🚨 *AMARAN KESIHATAN RANGKAIAN* 🚨",
        f"🕒 Masa Imbasan: `{timestamp}`\n",
    ]

    for dev in offline_devices:
        lines.append(
            f"🔴 *{dev['device_name']}* (`{dev['ip_address']}`)\n"
            f"   • Status: `{dev['status']}`\n"
            f"   • Port {dev['port']}: `{dev['port_status']}`\n"
        )

    message = "\n".join(lines)
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def ping_host(host: str) -> tuple[bool, str]:
    is_windows = platform.system().lower() == "windows"
    param_count = "-n" if is_windows else "-c"
    param_timeout = "-w" if is_windows else "-W"
    timeout_val = "1000" if is_windows else "1"

    command = ["ping", param_count, "1", param_timeout, timeout_val, host]

    start_time = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3,
        )
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        if result.returncode == 0:
            return True, f"{elapsed_ms} ms"
        return False, "Timeout"
    except Exception:
        return False, "Error"


def check_tcp_port(host: str, port: int, timeout: float = 2.0) -> str:
    if not port:
        return "N/A"
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "OPEN"
    except (socket.timeout, ConnectionRefusedError, OSError):
        return "CLOSED"


def inspect_device(device: dict) -> dict:
    name = device["device_name"].strip()
    ip = device["ip_address"].strip()
    category = device["category"].strip()
    port_str = device["port"].strip()
    port = int(port_str) if port_str.isdigit() else 0

    is_up, latency = ping_host(ip)
    port_status = check_tcp_port(ip, port) if is_up else "UNREACHABLE"
    overall_status = "ONLINE" if is_up else "OFFLINE"

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "device_name": name,
        "ip_address": ip,
        "category": category,
        "status": overall_status,
        "latency": latency,
        "port": port if port else "None",
        "port_status": port_status,
    }


def load_devices(filepath: str = DEVICES_FILE) -> list[dict]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Fail konfigurasi '{filepath}' tidak dijumpai.")

    with open(filepath, mode="r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_report(results: list[dict]) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = f"health_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = os.path.join(REPORTS_DIR, filename)

    fieldnames = [
        "timestamp",
        "device_name",
        "ip_address",
        "category",
        "status",
        "latency",
        "port",
        "port_status",
    ]

    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    return filepath


def run_health_check(notify_telegram: bool = True) -> dict:
    """
    Menjalankan imbasan penuh dan memulangkan data berstruktur untuk Web UI & CLI.
    """
    devices = load_devices(DEVICES_FILE)

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(inspect_device, devices))

    report_path = save_report(results)

    online_count = sum(1 for r in results if r["status"] == "ONLINE")
    offline_count = len(results) - online_count

    # Kumpul peranti bermasalah (Offline atau Port Tertutup)
    issues = [
        r for r in results if r["status"] == "OFFLINE" or r["port_status"] == "CLOSED"
    ]

    alert_sent = False
    if notify_telegram and issues:
        alert_sent = send_telegram_alert(issues)

    return {
        "scanned_at": datetime.now().strftime("%d %b %Y, %H:%M:%S"),
        "total": len(results),
        "online": online_count,
        "offline": offline_count,
        "alert_sent": alert_sent,
        "report_file": os.path.basename(report_path),
        "results": results,
    }


if __name__ == "__main__":
    summary = run_health_check(notify_telegram=True)
    print(f"Imbasan selesai ({summary['scanned_at']}).")
    print(
        f"Total: {summary['total']} | Online: {summary['online']} | Offline: {summary['offline']}"
    )
    print(f"Amaran Telegram Dihantar: {summary['alert_sent']}")