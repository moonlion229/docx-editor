import json
import tempfile
from pathlib import Path

import streamlit as st
import pandas as pd
from fake_ai_proofread import extract_paragraphs, fake_proofread, validate_edits
from proofread_apply import apply_edits_to_docx
from ai_issue_parser import MOCK_AI_RESPONSE_TEXT, parse_ai_issues_response

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
proofread_source = st.radio(
    "校對來源",
    ["使用 fake_proofread()", "使用 mock AI JSON parser"],
)
with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir_path = Path(tmpdir)

    input_path = tmpdir_path / "input.docx"
    edits_path = tmpdir_path / "fake_ai_edits.json"
    output_path = tmpdir_path / "proofread_result.docx"

    input_path.write_bytes(uploaded_file.getvalue())

    paragraphs_data = extract_paragraphs(str(input_path))

    st.subheader("讀取到的段落")
    st.write(f"共讀取到 {len(paragraphs_data)} 個段落。")
    st.dataframe(paragraphs_data, use_container_width=True)

    if proofread_source == "使用 mock AI JSON parser":
        valid_edits, validation_errors = parse_ai_issues_response(
            MOCK_AI_RESPONSE_TEXT,
            paragraphs_data,
        )
        total_issue_count = len(valid_edits) + len(validation_errors)
    else:
        edits = fake_proofread(paragraphs_data)
        valid_edits, validation_errors = validate_edits(edits, paragraphs_data)
        total_issue_count = len(edits)

    st.subheader("校對建議表")

    display_rows = []

    for index, edit in enumerate(valid_edits, start=1):
        action_type = edit.get("action_type") or edit.get("action", "")
        issue_id = edit.get("issue_id") or f"edit_{index}"
        apply_key = f"apply_issue_{issue_id}"

        if apply_key not in st.session_state:
            st.session_state[apply_key] = True

        display_rows.append({
            "issue_id": issue_id,
            "是否套用": st.session_state[apply_key],
            "位置": edit.get("position_label", ""),
            "段落": edit.get("paragraph_index", ""),
            "動作": action_type,
            "類別代碼": edit.get("category_code", ""),
            "類別": edit.get("category_label", ""),
            "分級": edit.get("grade_label", ""),
            "原文片段": edit.get("original_text", ""),
            "建議文字": edit.get("suggested_text", ""),
            "批註內容": edit.get("comment_text", ""),
            "原因": edit.get("reason", ""),
            "全書一致性": edit.get("global_consistency", ""),
            "加入用字規則": edit.get("add_to_book_rules", ""),
            "需人工覆核": edit.get("needs_human_review", ""),
            "需查證來源": edit.get("needs_source_check", ""),
        })

    checked_edits = []

    if display_rows:
        display_df = pd.DataFrame(display_rows)

        edited_df = st.data_editor(
            display_df,
            use_container_width=True,
            hide_index=True,
            disabled=[
                "issue_id",
                "位置",
                "段落",
                "動作",
                "類別代碼",
                "類別",
                "分級",
                "原文片段",
                "建議文字",
                "批註內容",
                "原因",
                "全書一致性",
                "加入用字規則",
                "需人工覆核",
                "需查證來源",
            ],
            column_config={
                "是否套用": st.column_config.CheckboxColumn(
                    "是否套用",
                    default=True,
                )
            },
        )

        for index, edit in enumerate(valid_edits, start=1):
            issue_id = edit.get("issue_id") or f"edit_{index}"
            apply_key = f"apply_issue_{issue_id}"
            st.session_state[apply_key] = bool(edited_df.iloc[index - 1]["是否套用"])

        st.subheader("逐條審核")

        for index, edit in enumerate(valid_edits, start=1):
            issue_id = edit.get("issue_id") or f"edit_{index}"
            action_type = edit.get("action_type") or edit.get("action", "")
            apply_key = f"apply_issue_{issue_id}"

            st.markdown("---")
            st.checkbox("是否套用", key=apply_key)

            st.write(
                f"位置：{edit.get('position_label', '')}｜"
                f"段落：{edit.get('paragraph_index', '')}｜"
                f"動作：{action_type}"
            )
            st.write(f"原文片段：{edit.get('original_text', '')}")
            st.write(f"建議改為：{edit.get('suggested_text', '')}")

            if action_type == "comment":
                st.write(f"批註內容：{edit.get('comment_text', '')}")

            st.write(f"原因：{edit.get('reason', '')}")
            st.write(f"建議程度 / 分級：{edit.get('grade_label', '')}")
            
        checked_edits = [
            edit
            for index, edit in enumerate(valid_edits, start=1)
            if st.session_state[f"apply_issue_{edit.get('issue_id') or f'edit_{index}'}"]
        ]

        st.write(
            f"總建議數：{total_issue_count}｜"
            f"通過驗證數：{len(valid_edits)}｜"
            f"已勾選套用數：{len(checked_edits)}｜"
            f"驗證錯誤數：{len(validation_errors)}"
        )

        csv_data = edited_df.to_csv(index=False).encode("utf-8-sig")

        st.download_button(
            label="下載校對建議 CSV",
            data=csv_data,
            file_name="proofread_suggestions.csv",
            mime="text/csv",
        )
    else:
        st.info("沒有通過驗證的校對建議。")
        st.write(
            f"總建議數：{len(edits)}｜"
            f"通過驗證數：{len(valid_edits)}｜"
            f"已勾選套用數：0｜"
            f"驗證錯誤數：{len(validation_errors)}"
        )
        
    st.subheader("驗證錯誤")

    if validation_errors:
        st.warning(f"有 {len(validation_errors)} 條建議未通過驗證，這些建議不會套用到 Word。")
        st.dataframe(pd.DataFrame(validation_errors), use_container_width=True)
    else:
        st.success("所有校對建議都通過驗證。")

    if st.button("產生已勾選建議的追蹤修訂 Word"):
        with open(edits_path, "w", encoding="utf-8") as f:
            json.dump(checked_edits, f, ensure_ascii=False, indent=2)

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