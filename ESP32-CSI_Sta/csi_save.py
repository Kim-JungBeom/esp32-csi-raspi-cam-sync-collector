#!/usr/bin/env python3
# csi_save.py
# Run on STA RPi
# Parses ESP32 STA serial output and saves CSI data to CSV.
#
# CSV format:
#   sample, datetime(HH-MM-SS.mmm), rssi, csi_data

import argparse
import os
import csv
import shutil
import datetime
import time
import re
import serial
import serial.tools.list_ports

# ==========================================
# Argument parsing
# ==========================================
parser = argparse.ArgumentParser()
parser.add_argument("--start",    type=str, required=True, help="start time HH:MM:SS")
parser.add_argument("--num",      type=int, default=100,   help="number of samples")
parser.add_argument("--interval", type=int, default=100,   help="interval (ms)")
parser.add_argument("--port",     type=str, default=None,  help="serial port (auto-detect if not specified)")
parser.add_argument("--baud",     type=int, default=115200, help="baud rate")
args = parser.parse_args()

# ==========================================
# Output directory initialization
# ==========================================
SAVE_DIR = "CSI Data"
CSV_PATH = os.path.join(SAVE_DIR, "csi.csv")

if os.path.exists(SAVE_DIR):
    shutil.rmtree(SAVE_DIR)
os.makedirs(SAVE_DIR)
print(f"🗑️  CSI Data directory initialized")
print(f"📁 CSI save path: {os.path.abspath(CSV_PATH)}")

# ==========================================
# Serial port auto-detection
# ==========================================
def find_port():
    if args.port:
        return args.port
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        if "ttyACM" in p.device or "ttyUSB" in p.device:
            print(f"📡 Serial port auto-detected: {p.device}")
            return p.device
    raise RuntimeError("ESP32 serial port not found. Specify with --port.")

# ==========================================
# Utilities
# ==========================================
def parse_start_time(hms_str):
    now = datetime.datetime.now()
    return now.replace(
        hour=int(hms_str[0:2]),
        minute=int(hms_str[3:5]),
        second=int(hms_str[6:8]),
        microsecond=0,
    )

def wait_until(target_dt):
    delta = (target_dt - datetime.datetime.now()).total_seconds()
    print(f"⏳ Waiting... ({delta:.3f}s until {target_dt.strftime('%H:%M:%S')})")
    if delta > 0:
        time.sleep(delta)

# Strip ANSI escape codes and ESP-IDF log prefixes
ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
esp_log_pattern = re.compile(r'[IWE] \(\d+\) [^:]+:.*')

# ==========================================
# CSI collection
# ==========================================
def run_collector(start_dt, ser):
    # Serial is already open (opened before wait_until)
    # Flush buffer just before start_dt to discard data accumulated during wait
    ser.reset_input_buffer()
    print(f"📡 CSI buffer flushed, starting collection")

    saved_count = 0

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sample", "datetime", "rssi", "csi_data"])
        f.flush()

        print(f"📡 Waiting for CSI data...")

        while saved_count < args.num:
            try:
                raw = ser.readline()
                if not raw:
                    continue

                line = raw.decode("utf-8", errors="ignore")
                clean = ansi_escape.sub("", line).strip()

                # Discard any data before CSI_DATA even if mixed into the same line
                idx = clean.find("CSI_DATA,")
                if idx == -1:
                    continue
                clean = clean[idx:]  # Force alignment to start from "CSI_DATA,"

                if "wifi" in clean.lower():
                    continue

                # Split into at most 4 fields
                parts = clean.split(",", 3)
                if len(parts) < 4:
                    continue

                # Ignore ESP32 sample number (parts[1]); use only RSSI and CSI data
                _, _, rssi_str, csi_data_raw = parts

                try:
                    rssi = int(rssi_str)
                except ValueError:
                    continue

                # Clean data
                csi_data = esp_log_pattern.sub("", csi_data_raw)
                csi_data = re.sub(r'\s+', ' ', csi_data).strip()

                if not csi_data:
                    continue

                # Assign sample number directly (ignore ESP32 numbering)
                saved_count += 1
                actual_sample = saved_count

                now    = datetime.datetime.now()
                dt_str = now.strftime("%H-%M-%S.%f")[:-3]

                writer.writerow([actual_sample, dt_str, rssi, csi_data])
                f.flush()
                os.fsync(f.fileno())

                print(f"[{saved_count:4d}/{args.num}] ✅ sample={actual_sample}  rssi={rssi}  {dt_str}")

            except Exception as e:
                print(f"⚠️ Error (ignored): {e}")

    ser.close()
    print(f"\n===== CSI collection complete: {saved_count} samples =====")
    print(f"📄 Saved to: {CSV_PATH}")

# ==========================================
# Entry point
# ==========================================
try:
    start_dt = parse_start_time(args.start)

    # Open serial before wait_until so collection can start immediately at start_dt
    port = find_port()
    print(f"📡 Serial connected: {port} @ {args.baud}baud")
    ser = serial.Serial(port, args.baud, timeout=1)
    ser.reset_input_buffer()

    wait_until(start_dt)
    run_collector(start_dt, ser)

except KeyboardInterrupt:
    print("\n🛑 Interrupted.")
