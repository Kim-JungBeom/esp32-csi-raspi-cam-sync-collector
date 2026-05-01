# ESP32-CSI Raspberry Pi Camera Sync Collector

Synchronized CSI/RSSI and RGB camera data collection system using ESP32 and Raspberry Pi.  
Designed for vision-based wireless sensing research.

---

## System Overview

This system synchronizes CSI/RSSI collection (ESP32-S3) and RGB image capture (Raspberry Pi Camera Module V2) across the STA, AP, and distributed cameras using Network Time Protocol (NTP)-based time synchronization.

```
[macOS / PC]  ←  Commander.ipynb
     │  SSH (simultaneous)
     ├── [cam1 RPi] ── cam_recorder.py ── Picamera2 ──> images/
     ├── [cam2 RPi] ── cam_recorder.py ── Picamera2 ──> images/
     ├── [ap-rpi]   ── ap_trigger.py ── GPIO ──> [ESP32 AP]
     │                                                  │ UDP
     └── [sta-rpi]  ── csi_save.py <── Serial ── [ESP32 STA]
                              │
                              └──> CSI Data/
```

---

## Hardware Requirements

| Device | Role |
|---|---|
| Raspberry Pi × 2 (cam1, cam2) | RGB image capture |
| Raspberry Pi (ap-rpi) | GPIO trigger → ESP32 AP |
| Raspberry Pi (sta-rpi) | Serial read from ESP32 STA |
| ESP32 × 1 (AP mode) | Receives GPIO trigger → sends UDP packet |
| ESP32 × 1 (STA mode) | Receives UDP → captures CSI → serial output |

**GPIO Wiring:**
- RPi BCM17 (pin 11) → ESP32 AP GPIO14
- RPi GND (pin 6) → ESP32 AP GND

---

## Repository Structure

```
.
├── Commander.ipynb          # Experiment controller (run on PC/macOS)
├── Raspcam/
│   └── cam_recorder.py      # Camera capture script (run on cam1, cam2)
├── ESP32-CSI_AP/
│   ├── main/ap_main.c       # ESP32 AP firmware
│   └── ap_trigger.py        # GPIO trigger script (run on ap-rpi)
└── ESP32-CSI_Sta/
    ├── main/
    │   ├── csi_station_main.c   # ESP32 STA firmware
    │   └── csi_router_logger.c  # CSI queue & serial output
    └── csi_save.py              # CSI serial reader & CSV saver (run on sta-rpi)
```

---
### ESP32
- ESP-IDF v4.4.x
- Tested on **ESP32-S3** (other ESP32 variants should work)
- Build and flash `ESP32-CSI_AP` to AP ESP32
- Build and flash `ESP32-CSI_Sta` to STA ESP32

---

## Configuration

All experiment parameters are configured at the top of `Commander.ipynb`:

```python
DELAY_SECONDS  = 30       # Delay before experiment starts
NUM_SAMPLES    = 10000    # Number of image samples
INTERVAL_MS    = 50       # Image capture interval (ms) → 20Hz

CSI_MULTIPLIER = 2        # CSI collected N× denser than images
                          # CSI interval = INTERVAL_MS / CSI_MULTIPLIER
                          # CSI samples  = NUM_SAMPLES × CSI_MULTIPLIER

CAM_WIDTH    = 640
CAM_HEIGHT   = 480
CAM_QUALITY  = 80         # JPEG quality (0-100)
CAM_EXPOSURE = 10         # Exposure time (ms)
CAM_GAIN     = 2.0        # Analogue gain
```

SSH credentials:
```python
SSH_USER = "your_username"
SSH_PASS = ""             # or use SSH key
DEVICES = {
    "cam1"   : "cam1.local",
    "cam2"   : "cam2.local",
    "ap-rpi" : "ap-rpi.local",
    "sta-rpi": "sta-rpi.local",
}
```

---

## Usage

1. Flash ESP32 AP and STA firmware
2. Ensure all Raspberry Pis are on the same network and reachable via mDNS
3. Open `Commander.ipynb` and set parameters
4. Run the notebook — it will SSH into all 4 devices simultaneously and start the experiment at the same scheduled time

---

## Output Data

| Device | Output | Format |
|---|---|---|
| cam1, cam2 | `~/Raspcam/cam_data_{hostname}/` | JPEG + timestamp CSV |
| sta-rpi | `~/ESP32-CSI_Sta/CSI Data/` | CSV (sample, RSSI, CSI raw) |
| ap-rpi | `~/ESP32-CSI_AP/trigger_data/` | CSV (sample, scheduled_time, actual_time) |

---
## Citation

If you used this system and it is relevant to your research, 
please consider citing:
```bibtex
@misc{kim2026distributedmultiviewvisiononlyrssi,
      title={Distributed Multi-View Vision-Only RSSI Estimation}, 
      author={Jung-Beom Kim and Woongsup Lee},
      year={2026},
      eprint={2604.26738},
      archivePrefix={arXiv},
      primaryClass={cs.IT},
      url={[https://arxiv.org/abs/2604.26738](https://arxiv.org/abs/2604.26738)}, 
}
```
## Contact

For any questions or inquiries, please contact:
**Jung-Beom Kim** ([kjung99@yonsei.ac.kr](mailto:kjung99@yonsei.ac.kr))

## Acknowledgements

This project is based on [ESP32-CSI-Tool](https://github.com/StevenMHernandez/ESP32-CSI-Tool) by Steven M. Hernandez, licensed under the MIT License.
Modifications by Kim-JungBeom.

- GitHub: https://github.com/StevenMHernandez/ESP32-CSI-Tool
- Website: https://stevenmhernandez.github.io/ESP32-CSI-Tool/
