import json
import tempfile
from pathlib import Path
import html
import streamlit as st
import pandas as pd
from gemini_proofread import request_gemini_proofread_response
from fake_ai_proofread import extract_paragraphs, fake_proofread, validate_edits
from proofread_apply import apply_edits_to_docx
from ai_issue_parser import MOCK_AI_RESPONSE_TEXT, parse_ai_issues_response
from excel_export import build_issues_excel
SENTENCE_BOUNDARIES = "。！？；;\n"

GRADE_HELP = {
    "A": "A 可直接套用：明確錯誤，通常可直接接受修訂。",
    "B": "B 建議套用：大致明確，但仍建議快速檢查。",
    "C": "C 只作提示：不直接改文，只提醒校對員留意。",
    "D": "D 需人工判斷：涉及語意、事實或風格，必須人工決定。",
}


def get_grade_help(edit):
    grade = edit.get("grade", "")
    return GRADE_HELP.get(grade, edit.get("grade_label", ""))


def highlight_text(text, target, color="#c0392b", strike=False):
    safe_text = html.escape(text or "")
    safe_target = html.escape(target or "")

    if not safe_target or safe_target not in safe_text:
        return safe_text

    style = f"color:{color}; font-weight:700;"
    if strike:
        style += " text-decoration:line-through;"

    return safe_text.replace(
        safe_target,
        f'<span style="{style}">{safe_target}</span>',
        1,
    )


def render_original_sentence(action_type, original_sentence, original_text):
    return highlight_text(
        original_sentence,
        original_text,
        color="#c0392b",
        strike=(action_type == "delete"),
    )


def render_suggested_sentence(action_type, suggested_sentence, suggested_text):
    if action_type == "replace":
        return highlight_text(suggested_sentence, suggested_text, color="#1e8449")
    return html.escape(suggested_sentence or "")

def build_paragraph_map(paragraphs_data):
    return {
        paragraph["paragraph_index"]: paragraph["text"]
        for paragraph in paragraphs_data
    }


def extract_original_sentence(paragraph_text, original_text, fallback_chars=40):
    if not paragraph_text:
        return original_text

    if not original_text or original_text not in paragraph_text:
        return paragraph_text[: fallback_chars * 2].strip()

    start = paragraph_text.find(original_text)
    end = start + len(original_text)

    sentence_start = 0
    for index in range(start - 1, -1, -1):
        if paragraph_text[index] in SENTENCE_BOUNDARIES:
            sentence_start = index + 1
            break

    sentence_end = len(paragraph_text)
    for index in range(end, len(paragraph_text)):
        if paragraph_text[index] in SENTENCE_BOUNDARIES:
            sentence_end = index + 1
            break

    sentence = paragraph_text[sentence_start:sentence_end].strip()
    if sentence:
        return sentence

    fallback_start = max(start - fallback_chars, 0)
    fallback_end = min(end + fallback_chars, len(paragraph_text))
    return paragraph_text[fallback_start:fallback_end].strip()


def build_suggested_sentence(action_type, original_sentence, original_text, suggested_text):
    if action_type == "replace":
        return original_sentence.replace(original_text, suggested_text, 1)
    if action_type == "delete":
        return original_sentence.replace(original_text, "", 1)
    if action_type == "comment":
        return "不直接修改，加入批註"
    return suggested_text

st.set_page_config(
    page_title="AI 校對 Word 測試版",
    page_icon="📝",
    layout="wide",
)



st.title("AI 校對 Word 測試版")
st.caption("目前版本使用假 AI 規則測試流程：Word → JSON 校對建議 → 追蹤修訂 Word。")

st.warning(
    "目前只是測試版：不會連接真正Gemini，也不要上傳真實公司書稿或敏感文件。"
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
    ["使用 fake_proofread", "使用 Mock AI JSON", "Gemini proofread"],
)
with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir_path = Path(tmpdir)

    input_path = tmpdir_path / "input.docx"
    edits_path = tmpdir_path / "fake_ai_edits.json"
    output_path = tmpdir_path / "proofread_result.docx"

    input_path.write_bytes(uploaded_file.getvalue())

    paragraphs_data = extract_paragraphs(str(input_path))
    paragraph_map = build_paragraph_map(paragraphs_data)
    st.subheader("讀取到的段落")
    st.write(f"共讀取到 {len(paragraphs_data)} 個段落。")
    st.dataframe(paragraphs_data, use_container_width=True)

    if proofread_source == "Mock AI JSON":
        valid_edits, validation_errors = parse_ai_issues_response(
            MOCK_AI_RESPONSE_TEXT,
            paragraphs_data,
        )
        total_issue_count = len(valid_edits) + len(validation_errors)

    elif proofread_source == "Gemini proofread":
        response_text, gemini_error = request_gemini_proofread_response(paragraphs_data)

        if gemini_error:
            valid_edits = []
            validation_errors = [{"error": gemini_error}]
        else:
            valid_edits, validation_errors = parse_ai_issues_response(
                response_text,
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
        paragraph_text = paragraph_map.get(edit.get("paragraph_index"), "")
        original_sentence = extract_original_sentence(
            paragraph_text,
            edit.get("original_text", ""),
        )
        suggested_sentence = build_suggested_sentence(
            action_type,
            original_sentence,
            edit.get("original_text", ""),
            edit.get("suggested_text", ""),
        )

        edit["original_sentence"] = original_sentence
        edit["suggested_sentence"] = suggested_sentence
        issue_id = edit.get("issue_id") or f"edit_{index}"
        apply_key = f"apply_issue_{issue_id}"

        if apply_key not in st.session_state:
            st.session_state[apply_key] = True

        display_rows.append({
            "issue_id": issue_id,
            "rule_id": edit.get("rule_id", ""),
            "是否套用": st.session_state[apply_key],
            "位置": edit.get("position_label", ""),
            "段落": edit.get("paragraph_index", ""),
            "動作": action_type,
            "類別代碼": edit.get("category_code", ""),
            "類別": edit.get("category_label", ""),
            "分級": edit.get("grade_label", ""),
            "原文片段": edit.get("original_text", ""),
            "建議文字": edit.get("suggested_text", ""),
            "原文句子": original_sentence,
            "建議句子": suggested_sentence,
            "批註內容": edit.get("comment_text", ""),
            "原因": edit.get("reason", ""),
            "全書一致性": edit.get("global_consistency", ""),
            "加入用字規則": edit.get("add_to_book_rules", ""),
            "需人工覆核": edit.get("needs_human_review", ""),
            "需查證來源": edit.get("needs_source_check", ""),
        })

    checked_edits = []

    if display_rows:
        st.subheader("逐條審核")

        for index, edit in enumerate(valid_edits, start=1):
            issue_id = edit.get("issue_id") or f"edit_{index}"
            action_type = edit.get("action_type") or edit.get("action", "")
            apply_key = f"apply_issue_{issue_id}"

            st.markdown("---")
            st.checkbox("是否套用", key=apply_key)

            st.write(f"位置：{edit.get('position_label', '')}")
            st.write(f"問題類型：{edit.get('category_label', '')}")
            st.write(f"建議程度：{get_grade_help(edit)}")

            st.markdown("原文句子：", help="紅色部分是系統定位到的問題位置。")
            st.markdown(
                render_original_sentence(
                    action_type,
                    edit.get("original_sentence", ""),
                    edit.get("original_text", ""),
                ),
                unsafe_allow_html=True,
            )

            if action_type == "comment":
                st.write("建議處理：不直接修改，加入批註")
                st.write(f"批註內容：{edit.get('comment_text', '')}")
            elif action_type == "delete":
                st.write(f"建議處理：刪除「{edit.get('original_text', '')}」")
                st.write(f"刪除後句子：{edit.get('suggested_sentence', '')}")
            else:
                st.write("建議改為：")
                st.markdown(
                    render_suggested_sentence(
                        action_type,
                        edit.get("suggested_sentence", ""),
                        edit.get("suggested_text", ""),
                    ),
                    unsafe_allow_html=True,
                )

            st.write(f"原因：{edit.get('reason', '')}")

        checked_edits = [
            edit
            for index, edit in enumerate(valid_edits, start=1)
            if st.session_state[f"apply_issue_{edit.get('issue_id') or f'edit_{index}'}"]
        ]

        for index, row in enumerate(display_rows, start=1):
            issue_id = row.get("issue_id") or f"edit_{index}"
            row["是否套用"] = st.session_state.get(f"apply_issue_{issue_id}", True)

        display_df = pd.DataFrame(display_rows)

        st.write(
            f"總建議數：{total_issue_count}｜"
            f"通過驗證數：{len(valid_edits)}｜"
            f"已勾選套用數：{len(checked_edits)}｜"
            f"驗證錯誤數：{len(validation_errors)}"
        )

        with st.expander("進階資料 / 完整校對建議表"):
            st.dataframe(display_df, use_container_width=True)

        csv_data = display_df.to_csv(index=False).encode("utf-8-sig")

        st.download_button(
            label="下載校對建議 CSV",
            data=csv_data,
            file_name="proofread_suggestions.csv",
            mime="text/csv",
        )

        excel_data = build_issues_excel(display_df.to_dict(orient="records"))

        st.download_button(
            label="下載校對建議 Excel",
            data=excel_data,
            file_name="proofread_issues.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    else:
        st.info("沒有通過驗證的校對建議。")
        st.write(
            f"總建議數：{total_issue_count}｜"
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