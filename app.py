import csv
import os
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, url_for
from monitor import DEVICES_FILE, REPORTS_DIR, run_health_check

app = Flask(__name__)


@app.route("/")
def dashboard():
    notify = request.args.get("notify", "1") == "1"
    data = run_health_check(notify_telegram=notify)
    return render_template("index.html", data=data)


@app.route("/api/scan")
def api_scan():
    notify = request.args.get("notify", "0") == "1"
    data = run_health_check(notify_telegram=notify)
    return jsonify(data)


@app.route("/add-device", methods=["POST"])
def add_device():
    name = request.form.get("device_name", "").strip()
    ip = request.form.get("ip_address", "").strip()
    port = request.form.get("port", "").strip()
    category = request.form.get("category", "General").strip()

    if name and ip:
        with open(DEVICES_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([name, ip, port, category])

    return redirect(url_for("dashboard", notify=0))


@app.route("/download/<filename>")
def download_report(filename):
    return send_from_directory(REPORTS_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, port=5000)