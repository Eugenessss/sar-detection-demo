from typing import Any, Dict

from backend.sar.services import model_registry


def get_app_health() -> Dict[str, Any]:
    models_loaded, error = model_registry.get_status()
    return {
        "status": "ok",
        "models_loaded": models_loaded,
        "error": error,
    }
