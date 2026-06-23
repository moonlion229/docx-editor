import json
import tempfile
from pathlib import Path

import streamlit as st
import pandas as pd
from fake_ai_proofread import extract_paragraphs, fake_proofread
from proofread_apply import apply_edits_to_docx


st.set_page_config(
    page_title="AI 校對 Word 測試版",
    page_icon="📝",
    layout="wide",
)



st.title("AI 校對 Word 測試版")
st.caption("目前版本使用假 AI 規則測試流程：Word → JSON 校對建議 → 追蹤修訂 Word。")

st.warning(
    "目前只是測試版：不會連接真正 OpenAI，也不要上傳真實公司書稿或敏感文件。"
)

uploaded_file = st.file_uploader(
    "請上傳 .docx Word 檔",
    type=["docx"],
)

if uploaded_file is None:
    st.info("請先上傳一個 .docx 檔案。")
    st.stop()

st.success(f"已上傳：{uploaded_file.name}")

if st.button("開始假 AI 校對並產生追蹤修訂 Word"):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        input_path = tmpdir_path / "input.docx"
        edits_path = tmpdir_path / "fake_ai_edits.json"
        output_path = tmpdir_path / "proofread_result.docx"

        # 儲存上傳檔案到暫存位置
        input_path.write_bytes(uploaded_file.getvalue())

        # 第一步：讀取段落
        paragraphs_data = extract_paragraphs(str(input_path))

        st.subheader("讀取到的段落")
        st.write(f"共讀取到 {len(paragraphs_data)} 個段落。")
        st.dataframe(paragraphs_data, use_container_width=True)

        # 第二步：假 AI 產生 JSON 校對建議
        edits = fake_proofread(paragraphs_data)

        with open(edits_path, "w", encoding="utf-8") as f:
            json.dump(edits, f, ensure_ascii=False, indent=2)

        st.subheader("校對建議表")
        st.write(f"共產生 {len(edits)} 條建議。")

        if edits:
            display_rows = []
            for edit in edits:
                display_rows.append({
                    "段落": edit.get("paragraph_index", ""),
                    "動作": edit.get("action", ""),
                    "類別": edit.get("category", ""),
                    "嚴重程度": edit.get("severity", ""),
                    "原文片段": edit.get("original_text", ""),
                    "建議文字": edit.get("suggested_text", ""),
                    "批註內容": edit.get("comment_text", ""),
                    "原因": edit.get("reason", ""),
                    "信心": edit.get("confidence", ""),
                })

            display_df = pd.DataFrame(display_rows)

            st.dataframe(display_df, use_container_width=True)

            csv_data = display_df.to_csv(index=False).encode("utf-8-sig")

            st.download_button(
                label="下載校對建議 CSV",
                data=csv_data,
                file_name="proofread_suggestions.csv",
                mime="text/csv",
            )
        else:
            st.info("沒有找到校對建議。")

        # 第三步：把 JSON 套用回 Word
        apply_edits_to_docx(
            input_file=str(input_path),
            edits_file=str(edits_path),
            output_file=str(output_path),
        )

        result_bytes = output_path.read_bytes()

        st.success("已產生追蹤修訂版 Word。")

        st.download_button(
            label="下載追蹤修訂版 Word",
            data=result_bytes,
            file_name="proofread_result.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )