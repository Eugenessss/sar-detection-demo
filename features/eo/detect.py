"""
[EO 도메인 - 탐지]
EO 이미지 한 장에서 표적 후보를 찾아 '박스 + 클래스 이름 + 신뢰도' 목록으로 돌려준다.
원래 주피터 노트북에서 화면 출력(matplotlib)까지 한 번에 하던 코드를, 서버에서
요청마다 재사용할 수 있는 순수 함수로 정리한 것이다. (시각화는 프론트엔드가 담당)
"""
from typing import Any, Dict, List, Union

import numpy as np

from features.eo import config
from features.eo import models as _m


def detect_on(image: Union[str, np.ndarray]) -> List[Dict[str, Any]]:
    """이미지(파일 경로 또는 배열)에서 표적을 탐지해 목록으로 돌려준다."""
    model = _m.get_detector_model()
    class_names = _m.get_class_names()

    # 학습 규격(imgsz=640)과 확신도 기준(conf=0.25)을 맞춰 CPU로 추론한다.
    results = model.predict(
        source=image,
        imgsz=config.DET_IMGSZ,
        conf=config.DET_CONF,
        device="cpu",
        verbose=False,
    )

    detections: List[Dict[str, Any]] = []
    for result in results:
        if result.boxes is None:
            continue
        for box in result.boxes:
            class_id = int(box.cls[0])
            detections.append(
                {
                    "bbox": [float(v) for v in box.xyxy[0].tolist()],   # [x1, y1, x2, y2]
                    "label": class_names.get(class_id, str(class_id)),
                    "conf": float(box.conf[0]),
                }
            )
    return detections
