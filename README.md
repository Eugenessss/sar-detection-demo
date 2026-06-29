# DOM SAR 차량 탐지 데모

YOLO11n(SAHI) + ConvNeXt-Tiny(14대분류) 로컬 데모.  
백엔드 FastAPI + 프론트엔드 Streamlit, CPU 전용.

---

## 프로젝트 구조

```
demo/
├── backend/
│   ├── config.py          # 경로·하이퍼파라미터 (ANNOTATION_DIR 포함)
│   ├── models.py          # 전역 모델 객체, load_models, get_models_status
│   ├── image.py           # load_dom_rgb
│   ├── detect.py          # detect_on (SAHI 슬라이스 탐지)
│   ├── classify.py        # classify_boxes_batch, classify_box
│   ├── rotation.py        # rot_k, inv_box, parse_azi 등 회전 유틸
│   ├── gt.py              # load_gt, infer_gt_xml, iou
│   ├── pipeline.py        # eval_at_k, correct_rotation, run_full_inference
│   ├── main.py            # FastAPI app + lifespan + include_router
│   ├── routers/
│   │   ├── health.py      # GET /health
│   │   ├── annotations.py # GET /annotations
│   │   └── infer.py       # POST /infer
│   └── checkpoints/       # 가중치 파일 (직접 투입 필요)
├── frontend/
│   ├── app.py             # 레이아웃·입력·결과 표시
│   └── viz.py             # draw_boxes, metrics_card, load_scene_for_vis
└── sample_images/         # GT XML 어노테이션
```

---

## 파일 배치 (직접 투입 필요)

| 경로 | 설명 |
|------|------|
| `backend/checkpoints/yolo_detector_yolo11n.pt` | YOLO11n 탐지기 가중치 |
| `backend/checkpoints/convnext_soc14_final.pth` | ConvNeXt-Tiny 분류기 가중치 |
| `backend/results/convnext_soc14.json` | 클래스 정보 JSON |
| `sample_images/*.xml` | GT 어노테이션 (TIF와 동일한 stem 이름으로 저장) |

> **TIF 파일은 여기 두지 않습니다.** 프론트엔드 사이드바에서 로컬 파일 경로를 직접 붙여넣어 사용합니다.

### convnext_soc14.json 형식

```json
{
  "classes": ["2S1","BMP2","BRDM_2","BTR70","BTR_60","Bus","Car","Construction","D7","T62","T72","Truck","ZIL131","ZSU_23_4"],
  "type2group": {
    "T-72":  "T72",
    "BMP-2": "BMP2"
  }
}
```

---

## 환경 설정 및 실행 (Windows, CPU, Miniconda)

```powershell
# 1) conda 환경 생성 & 패키지 설치 (최초 1회)
conda create -n sar-demo python=3.10 -y
conda activate sar-demo
cd demo
pip install -r requirements.txt
```

### 서버 시작 (터미널 2개, 둘 다 `conda activate sar-demo`)

```powershell
# 터미널 1 — 백엔드
conda activate sar-demo
cd demo
uvicorn backend.main:app --port 8000

# 터미널 2 — 프론트엔드
conda activate sar-demo
cd demo
streamlit run frontend/app.py
```

브라우저에서 `http://localhost:8501` 접속.

---

## 파이프라인 사양

| 항목 | 값 |
|------|----|
| 탐지 타일 | 256×256, overlap 0.25 |
| 탐지 conf | 0.3 |
| 박스 최대 크기 | 100px (건물 등 제외) |
| 분류 크롭 | 중심 고정 128×128 (타이트 크롭 아님) |
| Transform | Resize(128,128) → Grayscale(3ch) → ToTensor (Normalize 없음) |
| 회전 보정 | 폴더명 방위각 파싱 → 최근접 90° 스냅 (GT 있으면 E2E 최대 k 자동 선택) |
| GT 매칭 IoU | ≥ 0.3 |

---

## 사용 흐름

1. 사이드바 **TIF 파일 경로** 입력란에 로컬 경로를 붙여넣습니다.  
   예) `C:\data\120azi_ID5.tif`
2. TIF stem과 같은 이름의 XML이 `sample_images/`에 있으면 자동으로 GT 채점이 활성화됩니다.  
   예) `sample_images\120azi_ID5.xml`
3. XML이 없으면 탐지·분류 결과만 표시됩니다.
4. 수동 XML 업로드로 자동 매칭을 덮어쓸 수 있습니다.

---

## 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/health` | 모델 로드 상태 |
| GET | `/annotations` | `sample_images/` 에 보관된 XML 목록 |
| POST | `/infer` | `filepath`(로컬 TIF 절대경로) + 선택 xml → 탐지·분류·채점 결과 |

`/docs` 에서 Swagger UI로 엔드포인트를 직접 테스트할 수 있습니다.
