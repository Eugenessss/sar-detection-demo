"""
Paths and hyperparameters.
Edit this file when swapping weights or tuning detection params.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = Path(os.getenv("SAR_ARTIFACT_DIR", str(BASE_DIR)))

# --- weight paths ---
DET_WEIGHT = ARTIFACT_DIR / "checkpoints" / "yolo_detector_yolo11n.pt"
CLS_WEIGHT = ARTIFACT_DIR / "checkpoints" / "convnext_soc14_final.pth"
CLS_JSON   = ARTIFACT_DIR / "results"     / "convnext_soc14.json"

# --- detection hyperparameters ---
DET_CONF        = 0.5
DET_TILE_SIZE   = 256
DET_OVERLAP     = 0.25
DET_BOX_MAX_PX  = 100   # drop boxes larger than this (buildings, etc.)

# --- classification ---
CLS_WIN_SIZE    = 128   # center-fixed crop window size
