import streamlit as st

from views.inference import render_inference_page
from views.placeholders import (
    render_blank_1_page,
    render_blank_2_page,
    render_blank_3_page,
)


st.set_page_config(page_title="DOM SAR", layout="wide")

pages = [
    st.Page(render_inference_page, title="Inference", url_path="inference", default=True),
    st.Page(render_blank_1_page, title="Blank 1", url_path="blank-1"),
    st.Page(render_blank_2_page, title="Blank 2", url_path="blank-2"),
    st.Page(render_blank_3_page, title="Blank 3", url_path="blank-3"),
]

current_page = st.navigation(pages, position="top")
current_page.run()
