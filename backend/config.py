"""
Paths and hyperparameters.
Edit this file when swapping weights or tuning detection params.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# --- weight paths ---
DET_WEIGHT = BASE_DIR / "checkpoints" / "yolo_detector_yolo11n.pt"
CLS_WEIGHT = BASE_DIR / "checkpoints" / "convnext_soc14_final.pth"
CLS_JSON   = BASE_DIR / "results"     / "convnext_soc14.json"

# --- detection hyperparameters ---
DET_CONF        = 0.5
DET_TILE_SIZE   = 256
DET_OVERLAP     = 0.25
DET_BOX_MAX_PX  = 100   # drop boxes larger than this (buildings, etc.)

# --- classification ---
CLS_WIN_SIZE    = 128   # center-fixed crop window size

# --- GT scoring ---
IOU_THRESH      = 0.3

# --- annotation (XML) folder: auto-match {stem}.xml when XML not uploaded ---
ANNOTATION_DIR = BASE_DIR.parent / "sample_images"
