#!/usr/bin/env python3
# cam_recorder.py
# Run on Camera RPi (cam1, cam2)
#
# Captures num images at interval_ms intervals starting from a specified time.
# CSV: sample | scheduled_time | actual_time | filename
#
# * scheduled_time : T + n x interval_ms  (reference for CSI matching)
# * actual_time    : actual capture time
# * total experiment duration = num x interval_ms (ms)
# * full sensor FOV scaled down to output resolution (no crop)

import argparse
import os
import csv
import shutil
import datetime
import threading
import queue
import time

from picamera2 import Picamera2
from PIL import Image

# ==========================================
# Argument parsing
# ==========================================
parser = argparse.ArgumentParser()
parser.add_argument("--start",    type=str,   required=True)
parser.add_argument("--num",      type=int,   default=100,  help="number of samples")
parser.add_argument("--interval", type=int,   default=100,  help="interval (ms)")
parser.add_argument("--width",    type=int,   default=640)
parser.add_argument("--height",   type=int,   default=480)
parser.add_argument("--quality",  type=int,   default=80,   help="JPEG quality (0-100)")
parser.add_argument("--exposure", type=float, default=20.0, help="exposure time (ms)")
parser.add_argument("--gain",     type=float, default=2.0,  help="analogue gain")
args = parser.parse_args()

FPS               = 1000.0 / args.interval
FRAME_DURATION_US = int(args.interval * 1000)  # ms -> us

# ==========================================
# Output directory initialization
# ==========================================
HOSTNAME = os.uname().nodename
SAVE_DIR = f"cam_data_{HOSTNAME}"
CSV_PATH = os.path.join(SAVE_DIR, "log.csv")

if os.path.exists(SAVE_DIR):
    shutil.rmtree(SAVE_DIR)
os.makedirs(SAVE_DIR)
print(f"🗑️  {SAVE_DIR} initialized")

# ==========================================
# Camera initialization
# ==========================================
picam2 = Picamera2()

# Select maximum sensor resolution
sensor_modes = picam2.sensor_modes
full_mode = max(sensor_modes, key=lambda m: m["size"][0] * m["size"][1])
sensor_w, sensor_h = full_mode["size"]
print(f"📷 Sensor mode: {sensor_w}x{sensor_h} -> output: {args.width}x{args.height} (full FOV scaled)")

config = picam2.create_video_configuration(
    main={"size": (args.width, args.height), "format": "RGB888"},
    sensor={"output_size": full_mode["size"], "bit_depth": full_mode["bit_depth"]},
)
picam2.configure(config)
picam2.set_controls({
    "AeEnable":            False,
    "ExposureTime":        int(args.exposure * 1000),
    "AnalogueGain":        args.gain,
    "AwbEnable":           False,        # Disable AWB: maintain consistent color across frames
    "ColourGains":         (1.63, 1.56), # AWB measured values (indoor fluorescent lighting)
                                         # Re-measure if lighting environment changes
    "NoiseReductionMode":  1,            # Fixed noise reduction (0=off, 1=fast, 2=high)
    "Sharpness":           1.0,          # Fixed sharpness
    "FrameDurationLimits": (FRAME_DURATION_US, FRAME_DURATION_US),
})
picam2.start()
# ScalerCrop must be applied after start()
# Setting it before start() is ignored and causes cropping.
# (0, 0, sensor_w, sensor_h) = full FOV -> scaled down to output resolution
picam2.set_controls({"ScalerCrop": (0, 0, sensor_w, sensor_h)})
time.sleep(1.0)  # Sensor stabilization (includes ScalerCrop propagation delay)
print(f"📷 Camera ready: {args.width}x{args.height} @{FPS:.1f}fps ({args.interval}ms/frame)")
print(f"📷 Total duration: {args.num * args.interval / 1000:.1f}s ({args.num} samples x {args.interval}ms)")

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
# Image capture
# ==========================================
def run_image_mode(start_dt):
    # JPEG saving in a separate thread to avoid blocking the capture loop
    save_queue = queue.Queue()

    def save_worker():
        while True:
            item = save_queue.get()
            if item is None:
                break
            arr, filepath = item
            # BGR->RGB conversion (picamera2 make_array() returns BGR)
            # Camera is physically mounted upside-down, so rotate 180 degrees
            Image.fromarray(arr[:, :, ::-1]).rotate(180).save(filepath, "JPEG", quality=args.quality)
            save_queue.task_done()

    save_thread = threading.Thread(target=save_worker, daemon=True)
    save_thread.start()

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sample", "scheduled_time", "actual_time", "filename"])
        f.flush()

        print(f"\n🚀 Image capture started: {args.num} samples @ {args.interval}ms interval ({FPS:.1f}fps)")

        for i in range(args.num):
            sample = i + 1

            # Scheduled time: T + n x interval_ms
            scheduled_dt  = start_dt + datetime.timedelta(milliseconds=i * args.interval)
            scheduled_str = fmt_dt(scheduled_dt)

            # Precise wait until scheduled time
            wait_sec = (scheduled_dt - datetime.datetime.now()).total_seconds()
            if wait_sec > 0:
                time.sleep(wait_sec)

            actual_str = fmt_dt(datetime.datetime.now())
            request = picam2.capture_request()
            arr = request.make_array("main")
            request.release()

            filename = f"img_{sample:04d}.jpg"
            filepath = os.path.join(SAVE_DIR, filename)
            save_queue.put((arr, filepath))

            writer.writerow([sample, scheduled_str, actual_str, filename])
            f.flush()

            print(f"[{sample:4d}/{args.num}] ✅ {filename}  sched={scheduled_str}  actual={actual_str}")

    save_queue.put(None)
    save_queue.join()
    print(f"===== Image capture complete: {args.num} samples =====")

# ==========================================
# Entry point
# ==========================================
try:
    start_dt = parse_start_time(args.start)
    wait_until(start_dt)
    run_image_mode(start_dt)

finally:
    picam2.stop()
    print("Camera resources released.")
