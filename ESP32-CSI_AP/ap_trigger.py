#!/usr/bin/env python3
# ap_trigger.py
# Run on AP RPi
# Outputs num GPIO trigger pulses at interval_ms intervals starting from a specified time.
#
# GPIO wiring:
#   RPi BCM17 (pin 11) -> ESP32 AP GPIO14
#   RPi GND   (pin 6)  -> ESP32 AP GND
#
# CSV log: sample | scheduled_time | actual_time

import argparse
import os
import csv
import shutil
import datetime
import time
import RPi.GPIO as GPIO

# ==========================================
# Argument parsing
# ==========================================
parser = argparse.ArgumentParser()
parser.add_argument("--start",    type=str, required=True, help="start time HH:MM:SS")
parser.add_argument("--num",      type=int, default=100,   help="number of samples")
parser.add_argument("--interval", type=int, default=100,   help="interval (ms)")
args = parser.parse_args()

TRIGGER_PIN      = 17   # BCM17 -> ESP32 GPIO14
TRIGGER_PULSE_MS = 1    # trigger pulse duration (ms)

# ==========================================
# Output directory initialization
# ==========================================
SAVE_DIR = "trigger_data"
CSV_PATH = os.path.join(SAVE_DIR, "trigger_log.csv")

if os.path.exists(SAVE_DIR):
    shutil.rmtree(SAVE_DIR)
os.makedirs(SAVE_DIR)
print(f"🗑️  {SAVE_DIR} initialized")

# ==========================================
# GPIO initialization
# ==========================================
GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIGGER_PIN, GPIO.OUT, initial=GPIO.LOW)
print(f"GPIO BCM{TRIGGER_PIN} initialized")

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

def fmt_dt(dt):
    return dt.strftime("%H-%M-%S.%f")[:-3]

# ==========================================
# Trigger execution
# ==========================================
def run_trigger(start_dt):
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sample", "scheduled_time", "actual_time"])
        f.flush()

        print(f"\n🚀 Trigger started: {args.num} pulses @ {args.interval}ms interval")

        for i in range(args.num):
            sample = i + 1

            # Scheduled time: T + n x interval_ms
            scheduled_dt  = start_dt + datetime.timedelta(milliseconds=i * args.interval)
            scheduled_str = fmt_dt(scheduled_dt)

            # Precise wait until scheduled time
            wait_sec = (scheduled_dt - datetime.datetime.now()).total_seconds()
            if wait_sec > 0:
                time.sleep(wait_sec)

            # Record actual trigger time
            actual_str = fmt_dt(datetime.datetime.now())

            # Output GPIO pulse
            GPIO.output(TRIGGER_PIN, GPIO.HIGH)
            time.sleep(TRIGGER_PULSE_MS / 1000.0)
            GPIO.output(TRIGGER_PIN, GPIO.LOW)

            writer.writerow([sample, scheduled_str, actual_str])
            f.flush()

            print(f"[{sample:4d}/{args.num}] ✅ sched={scheduled_str}  actual={actual_str}")

    print(f"===== Trigger complete: {args.num} samples =====")
    print(f"📄 Log: {CSV_PATH}")

# ==========================================
# Entry point
# ==========================================
try:
    start_dt = parse_start_time(args.start)
    wait_until(start_dt)
    run_trigger(start_dt)

finally:
    GPIO.cleanup()
    print("GPIO resources released.")
