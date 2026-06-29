"""
Streamlit 프론트엔드.
TIF·XML 모두 파일 업로드 방식. XML 미업로드 시 sample_images/{stem}.xml 자동 매칭.
"""
import io
import time

import numpy as np
import pandas as pd
import requests
import streamlit as st

from viz import draw_boxes, metrics_card, load_scene_for_vis

# ── 페이지 설정 ────────────────────────────────────────────────────
st.set_page_config(page_title="DOM SAR 차량 탐지", layout="wide")

st.title("DOM SAR 차량 탐지 데모")
st.caption("YOLO11n (SAHI) + ConvNeXt-Tiny (14대분류)")

# ══════════════════════════════════════════════════════════════════
# 사이드바
# ══════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("설정")
    BACKEND = st.text_input("백엔드 URL", value="http://localhost:8000")

    # 모델 상태
    try:
        health = requests.get(f"{BACKEND}/health", timeout=3).json()
        if health.get("models_loaded"):
            st.success("모델 로드됨")
        else:
            st.error(f"모델 미로드: {health.get('error', '')}")
    except Exception as e:
        st.warning(f"백엔드 연결 실패: {e}")

    st.divider()
    st.header("입력")

    # ── TIF 업로드 ────────────────────────────────────────────────
    tif_file = st.file_uploader("TIF 파일 업로드", type=["tif", "tiff"])

    # sample_images/ 의 XML 목록 (참고용)
    try:
        ann_resp = requests.get(f"{BACKEND}/annotations", timeout=3).json()
        xmls = ann_resp.get("xmls", [])
    except Exception:
        xmls = []

    if xmls:
        st.caption(f"자동 매칭 가능한 XML ({len(xmls)}개) — TIF와 같은 이름이면 GT 채점됨")
    else:
        st.caption("sample_images/ 에 XML 없음 — GT 채점 생략될 수 있음")

    # XML 수동 업로드 (선택)
    with st.expander("XML 수동 업로드 (자동 매칭 덮어쓰기)", expanded=False):
        uploaded_xml = st.file_uploader("GT XML", type=["xml"])

    # 수동 회전 폴백
    with st.expander("수동 회전 (방위각/GT 없을 때 폴백)", expanded=False):
        manual_rot = st.select_slider(
            "회전 각도", options=[0, 90, 180, 270], value=0,
            format_func=lambda v: f"{v}°",
        )
        rotate_k_manual = manual_rot // 90

    run_btn = st.button("실행", type="primary", use_container_width=True)
    cmp_btn = st.button("SAHI vs 수동 비교 실행", use_container_width=True)


# ══════════════════════════════════════════════════════════════════
# 추론 실행
# ══════════════════════════════════════════════════════════════════
if run_btn:
    if tif_file is None:
        st.warning("TIF 파일을 업로드하세요.")
        st.stop()

    tif_bytes = tif_file.getvalue()

    with st.spinner("추론 중... (CPU 전용, 수십 초 소요될 수 있습니다)"):
        t0 = time.time()
        try:
            files = {"tif": (tif_file.name, tif_bytes, "image/tiff")}
            if uploaded_xml is not None:
                files["xml"] = (uploaded_xml.name, uploaded_xml.getvalue(), "application/xml")

            resp = requests.post(
                f"{BACKEND}/infer",
                data={"rotate_k": rotate_k_manual},
                files=files,
                timeout=600,
            )
            elapsed_client = round(time.time() - t0, 1)

            if resp.status_code != 200:
                st.error(f"서버 오류 {resp.status_code}: {resp.text}")
                st.stop()

            result = resp.json()

        except requests.exceptions.Timeout:
            st.error("타임아웃 — 처리 시간이 너무 깁니다.")
            st.stop()
        except Exception as e:
            st.error(f"요청 실패: {e}")
            st.stop()

    # ── 결과 헤더 ──────────────────────────────────────────────────
    xml_note = "XML 매칭됨" if result.get("xml_matched") else "XML 없음"
    st.success(
        f"완료  {result.get('elapsed_sec', elapsed_client)}s  |  "
        f"탐지 {len(result['detections'])}개  |  "
        f"회전 {result['rotate_deg']}° ({'자동' if result.get('auto_rotation') else '수동'})  |  "
        + (f"방위각 {result['azimuth']}°  |  " if result.get('azimuth') is not None else "")
        + xml_note
    )

    # ── 장면 이미지 로드 (시각화용, 업로드 바이트에서) ──────────────
    scene_rgb = load_scene_for_vis(io.BytesIO(tif_bytes))
    if scene_rgb is None:
        W, H = result["image_size"]
        scene_rgb = np.zeros((H, W, 3), dtype=np.uint8)

    detections = result["detections"]
    missed     = result.get("missed", [])
    metrics    = result.get("metrics")

    if metrics:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("탐지 결과")
            st.image(draw_boxes(scene_rgb, detections, use_status=False), use_container_width=True)
        with col2:
            st.subheader("GT 대조  초록=정답 / 빨강=오답 / 노랑=오탐 / 파랑=미탐지")
            st.image(draw_boxes(scene_rgb, detections + missed, use_status=True), use_container_width=True)
        st.subheader("평가 지표")
        metrics_card(metrics)
    else:
        st.subheader("탐지 결과")
        st.image(draw_boxes(scene_rgb, detections, use_status=False), use_container_width=True)
        st.caption("XML이 없어 GT 채점을 건너뜁니다.")

    # ── 검출 표 ────────────────────────────────────────────────────
    rows = detections + missed
    if rows:
        st.subheader(f"검출 목록 (탐지 {len(detections)} / 미탐지 {len(missed)})")
        df = pd.DataFrame([
            {
                "label":    d["label"],
                "det_conf": round(d["det_conf"], 3) if d.get("det_conf") is not None else None,
                "cls_conf": round(d["cls_conf"], 3) if d.get("cls_conf") is not None else None,
                "status":   d.get("status", "-"),
                "x1": int(d["bbox"][0]), "y1": int(d["bbox"][1]),
                "x2": int(d["bbox"][2]), "y2": int(d["bbox"][3]),
            }
            for d in rows
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("탐지된 차량이 없습니다.")


# ══════════════════════════════════════════════════════════════════
# SAHI vs 수동타일링+배치 비교
# ══════════════════════════════════════════════════════════════════
if cmp_btn:
    if tif_file is None:
        st.warning("TIF 파일을 업로드하세요.")
        st.stop()

    tif_bytes = tif_file.getvalue()

    with st.spinner("두 방식 비교 중... (SAHI가 느려 1분 이상 걸릴 수 있습니다)"):
        try:
            files = {"tif": (tif_file.name, tif_bytes, "image/tiff")}
            if uploaded_xml is not None:
                files["xml"] = (uploaded_xml.name, uploaded_xml.getvalue(), "application/xml")
            resp = requests.post(
                f"{BACKEND}/compare",
                data={"rotate_k": rotate_k_manual},
                files=files,
                timeout=1200,
            )
            if resp.status_code != 200:
                st.error(f"서버 오류 {resp.status_code}: {resp.text}")
                st.stop()
            result = resp.json()
        except requests.exceptions.Timeout:
            st.error("타임아웃 — 처리 시간이 너무 깁니다.")
            st.stop()
        except Exception as e:
            st.error(f"요청 실패: {e}")
            st.stop()

    sahi   = result["sahi"]
    manual = result["manual"]

    # ── 수치 비교 표 ───────────────────────────────────────────────
    def _row(name, r):
        m = r.get("metrics") or {}
        return {
            "방식":     name,
            "탐지수":   r["n_det"],
            "FP(오탐)": r["n_fp"],
            "recall":   m.get("recall"),
            "cls/det":  m.get("cls_on_det"),
            "E2E":      m.get("E2E"),
            "시간(s)":  r["elapsed_sec"],
        }
    st.subheader("수치 비교")
    st.dataframe(
        pd.DataFrame([_row("SAHI", sahi), _row("수동+배치", manual)]),
        use_container_width=True, hide_index=True,
    )
    spd = sahi["elapsed_sec"] / manual["elapsed_sec"] if manual["elapsed_sec"] else 0
    st.caption(f"속도: 수동+배치가 SAHI 대비 약 {spd:.1f}배 · 회전 {manual['rotate_deg']}°")

    # ── 장면 로드 ──────────────────────────────────────────────────
    scene_rgb = load_scene_for_vis(io.BytesIO(tif_bytes))
    if scene_rgb is None:
        W, H = result["image_size"]
        scene_rgb = np.zeros((H, W, 3), dtype=np.uint8)

    # ── 좌우 나란히 (GT 대조: 초록=정답/빨강=오답/노랑=오탐/파랑=미탐) ──
    c1, c2 = st.columns(2)
    for col, (name, r) in zip((c1, c2), [("SAHI", sahi), ("수동+배치", manual)]):
        with col:
            st.subheader(name)
            boxes = r["detections"] + r.get("missed", [])
            st.image(draw_boxes(scene_rgb, boxes, use_status=True), use_container_width=True)
            st.caption(f"탐지 {r['n_det']} / 오탐 {r['n_fp']} / {r['elapsed_sec']}s")
