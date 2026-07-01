import difflib
import html
import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from ai_issue_parser import MOCK_AI_RESPONSE_TEXT, parse_ai_issues_response
from excel_export import build_issues_excel
from fake_ai_proofread import extract_paragraphs, fake_proofread, validate_edits
from gemini_proofread import (
    request_gemini_proofread_response,
    request_gemini_startup_response,
    select_paragraphs,
)
from proofread_apply import apply_edits_to_docx

SENTENCE_BOUNDARIES = "。！？；;\n"

GRADE_HELP = {
    "A": "A 可直接改：明確錯誤，通常可直接接受修訂。",
    "B": "B 建議改：大致明確，但仍建議快速檢查。",
    "C": "C 只標示：不直接改文，只提醒校對員留意。",
    "D": "D 需人工判斷：涉及語意、事實或風格，必須人工決定。",
    "low": "低：影響較小，可快速檢查後決定。",
    "medium": "中：建議仔細確認，可能影響理解或一致性。",
    "high": "高：優先處理，可能明顯影響文本品質。",
}

ISSUE_TYPE_LABELS = {
    "norm_description": "規範描述",
    "homophone_error": "同音錯誤",
    "missing_word": "遺漏字詞",
    "redundant_word": "冗餘字詞",
    "shape_similar_error": "形近錯誤",
    "word_order_error": "語序錯誤",
    "place_name": "地名",
    "date_format": "日期不合規",
    "punctuation": "標點",
    "typo": "錯別字",
    "consistency": "一致性",
    "style": "風格",
    "fact_check": "需人工查證",
    "comment_only": "提示 / 批註",
}

FILTER_OPTIONS = [
    "全部",
    "已接受",
    "已忽略",
    "未處理",
    "A 級",
    "B 級",
    "C 級",
    "D 級",
    "規範描述",
    "同音錯誤",
    "遺漏字詞",
    "冗餘字詞",
    "形近錯誤",
    "語序錯誤",
    "地名",
    "日期不合規",
    "標點",
    "錯別字",
    "一致性",
    "需人工查證",
]


def build_paragraph_map(paragraphs_data):
    return {paragraph["paragraph_index"]: paragraph["text"] for paragraph in paragraphs_data}


def extract_original_sentence(paragraph_text, original_text, fallback_chars=40):
    if not paragraph_text:
        return original_text or ""

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


def build_suggested_sentence(action_type, original_sentence, original_text, suggested_text, comment_text=""):
    if action_type == "replace":
        return original_sentence.replace(original_text, suggested_text, 1)
    if action_type == "delete":
        return original_sentence.replace(original_text, "", 1)
    if action_type == "comment":
        return comment_text or "不直接修改，加入批註"
    return suggested_text or ""


def get_grade_key(edit):
    for field in ("grade", "level", "severity", "priority", "suggestion_level"):
        value = edit.get(field)
        if value:
            return str(value)
    return ""


def get_grade_help(edit):
    grade = get_grade_key(edit)
    return GRADE_HELP.get(grade, edit.get("grade_label") or grade or "未分級")


def get_issue_type_label(edit):
    issue_type = edit.get("issue_type", "")
    return (
        edit.get("issue_type_label")
        or ISSUE_TYPE_LABELS.get(issue_type)
        or edit.get("category_label")
        or edit.get("category")
        or edit.get("category_code")
        or "未分類"
    )


def render_diff_html(original_sentence, suggested_sentence):
    matcher = difflib.SequenceMatcher(None, original_sentence or "", suggested_sentence or "")
    original_parts = []
    suggested_parts = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        original_text = html.escape((original_sentence or "")[i1:i2])
        suggested_text = html.escape((suggested_sentence or "")[j1:j2])

        if tag == "equal":
            original_parts.append(original_text)
            suggested_parts.append(suggested_text)
        elif tag == "delete":
            original_parts.append(
                f'<span style="color:#b42318;text-decoration:line-through;font-weight:700;">{original_text}</span>'
            )
        elif tag == "insert":
            suggested_parts.append(
                f'<span style="color:#067647;font-weight:700;background:#dcfae6;">{suggested_text}</span>'
            )
        elif tag == "replace":
            original_parts.append(
                f'<span style="color:#b42318;text-decoration:line-through;font-weight:700;">{original_text}</span>'
            )
            suggested_parts.append(
                f'<span style="color:#067647;font-weight:700;background:#dcfae6;">{suggested_text}</span>'
            )

    return "".join(original_parts), "".join(suggested_parts)


def render_review_sentence_html(action_type, original_html, suggested_html):
    if action_type == "replace":
        return f"→ {suggested_html}"
    if action_type == "delete":
        return f"→ {suggested_html or '（刪除此片段）'}"
    return ""


def render_grouped_paragraph_html(paragraph_text, edits):
    matches = []
    search_from = 0
    for order, edit in enumerate(edits):
        action_type = edit.get("action_type") or edit.get("action", "")
        original_text = edit.get("original_text", "")
        if action_type not in {"replace", "delete"} or not original_text:
            continue

        start = paragraph_text.find(original_text, search_from)
        if start == -1:
            start = paragraph_text.find(original_text)
        if start == -1:
            continue

        end = start + len(original_text)
        matches.append({
            "start": start,
            "end": end,
            "order": order,
            "action_type": action_type,
            "original_text": original_text,
            "suggested_text": edit.get("suggested_text", ""),
        })
        search_from = end

    matches.sort(key=lambda item: (item["start"], item["end"]))
    html_parts = []
    cursor = 0
    for match in matches:
        if match["start"] < cursor:
            continue
        html_parts.append(html.escape(paragraph_text[cursor:match["start"]]))
        original_html = html.escape(match["original_text"])
        html_parts.append(
            f'<span style="color:#b42318;text-decoration:line-through;font-weight:700;">{original_html}</span>'
        )
        if match["action_type"] == "replace":
            suggested_html = html.escape(match["suggested_text"])
            html_parts.append(
                f'<span style="color:#067647;background:#dcfae6;border-bottom:2px solid #12b76a;font-weight:700;">'
                f'{suggested_html}</span>'
            )
        cursor = match["end"]

    html_parts.append(html.escape(paragraph_text[cursor:]))
    return "".join(html_parts)


def is_edit_located_in_paragraph(paragraph_text, edit):
    action_type = edit.get("action_type") or edit.get("action", "")
    original_text = edit.get("original_text", "")
    if action_type not in {"replace", "delete"}:
        return True
    return bool(original_text and original_text in (paragraph_text or ""))


def build_checkbox_label(edit):
    action_type = edit.get("action_type") or edit.get("action", "")
    issue_label = get_issue_type_label(edit)
    grade_label = edit.get("grade_label") or get_grade_key(edit) or "未分級"
    original_text = edit.get("original_text", "")
    suggested_text = edit.get("suggested_text", "")

    if action_type == "replace":
        detail = f"「{original_text}」→「{suggested_text}」"
    elif action_type == "delete":
        detail = f"刪去「{original_text}」"
    else:
        detail = edit.get("comment_text") or edit.get("suggested_sentence") or "加入批註"

    return f"套用：{detail} | {issue_label} | {grade_label}"


def group_filtered_items_by_paragraph(filtered_items):
    grouped = []
    current_paragraph = object()
    current_items = []
    for index, edit in sorted(filtered_items, key=lambda item: (item[1].get("paragraph_index", 0), item[0])):
        paragraph_index = edit.get("paragraph_index")
        if paragraph_index != current_paragraph:
            if current_items:
                grouped.append((current_paragraph, current_items))
            current_paragraph = paragraph_index
            current_items = []
        current_items.append((index, edit))
    if current_items:
        grouped.append((current_paragraph, current_items))
    return grouped


def issue_state_key(issue_id, index):
    return f"apply_issue_{issue_id or f'edit_{index}'}"


def issue_status_key(issue_id, index):
    return f"issue_status_{issue_id or f'edit_{index}'}"


def get_issue_status(issue_id, index):
    return st.session_state.get(issue_status_key(issue_id, index), "pending")


def set_issue_status(issue_id, index, status):
    st.session_state[issue_status_key(issue_id, index)] = status
    st.session_state[issue_state_key(issue_id, index)] = status == "accepted"


def status_label(status):
    labels = {
        "pending": "待處理",
        "accepted": "已接受",
        "ignored": "已忽略",
    }
    return labels.get(status, "待處理")


def filter_matches(edit, filter_value, status):
    if filter_value == "全部":
        return True
    if filter_value == "已接受":
        return status == "accepted"
    if filter_value == "已忽略":
        return status == "ignored"
    if filter_value == "未處理":
        return status == "pending"

    grade = get_grade_key(edit)
    if filter_value == "A 級":
        return grade == "A"
    if filter_value == "B 級":
        return grade == "B"
    if filter_value == "C 級":
        return grade == "C"
    if filter_value == "D 級":
        return grade == "D"

    label = get_issue_type_label(edit)
    if filter_value == "需人工查證":
        return bool(edit.get("requires_human_check") or edit.get("needs_source_check"))
    return label == filter_value


def build_display_rows(valid_edits):
    rows = []
    for index, edit in enumerate(valid_edits, start=1):
        issue_id = edit.get("issue_id") or f"edit_{index}"
        status = get_issue_status(issue_id, index)
        rows.append({
            "issue_id": issue_id,
            "rule_id": edit.get("rule_id", ""),
            "issue_type": edit.get("issue_type", ""),
            "issue_type_label": get_issue_type_label(edit),
            "rule_description": edit.get("rule_description", ""),
            "norm_basis": edit.get("norm_basis", ""),
            "confidence_label": edit.get("confidence_label", ""),
            "requires_human_check": edit.get("requires_human_check", edit.get("needs_human_review", "")),
            "審核狀態": status_label(status),
            "是否套用": status == "accepted",
            "位置": edit.get("position_label", ""),
            "段落": edit.get("paragraph_index", ""),
            "動作": edit.get("action_type") or edit.get("action", ""),
            "類別代碼": edit.get("category_code", ""),
            "類別": edit.get("category_label", ""),
            "分級": edit.get("grade_label") or get_grade_key(edit),
            "原文片段": edit.get("original_text", ""),
            "建議文字": edit.get("suggested_text", ""),
            "原文句子": edit.get("original_sentence", ""),
            "建議句子": edit.get("suggested_sentence", ""),
            "批註內容": edit.get("comment_text", ""),
            "原因": edit.get("reason", ""),
            "全書一致性": edit.get("global_consistency", ""),
            "加入用字規則": edit.get("add_to_book_rules", ""),
            "需人工覆核": edit.get("needs_human_review", ""),
            "需查證來源": edit.get("needs_source_check", ""),
        })
    return rows


def count_words(paragraphs_data):
    return sum(len(paragraph["text"]) for paragraph in paragraphs_data)


def format_paragraph_preview(paragraphs_data):
    lines = []
    for paragraph in paragraphs_data:
        text = (paragraph.get("text") or "").strip()
        if not text:
            continue
        lines.append(f'[{paragraph.get("paragraph_index")}] {text}')
    return "\n\n".join(lines)


def clamp_paragraph_range(start_index, end_index, paragraph_count):
    start_index = max(1, min(start_index, paragraph_count))
    end_index = max(start_index, min(end_index, paragraph_count))
    return start_index, end_index


def render_ai_diagnostics(response_text, validation_errors):
    with st.expander("AI 原始回應 / 驗證診斷", expanded=False):
        if response_text:
            st.download_button(
                label="下載 AI 原始回應",
                data=response_text.encode("utf-8"),
                file_name="gemini_raw_response.txt",
                mime="text/plain",
            )
            st.text_area("AI 原始回應", response_text, height=260)
        else:
            st.info("本次沒有可顯示的 AI 原始回應。")

        if validation_errors:
            errors_df = pd.DataFrame(validation_errors)
            st.download_button(
                label="下載驗證錯誤 CSV",
                data=errors_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="proofread_validation_errors.csv",
                mime="text/csv",
            )


def build_book_context_text(
    book_title,
    genre,
    origin_type,
    layout_direction,
    topic_sensitivity,
    style_rules,
    gray_rules,
    direct_rules,
    proper_nouns,
    terminology,
    number_policy,
    punctuation_policy,
    format_policy,
    fact_check_policy,
    extra_notes,
):
    lines = [
        "已確認的本書校對上下文：",
        f"- 書名：{book_title or '未提供'}",
        f"- 文類：{genre}",
        f"- 原創／翻譯：{origin_type}",
        f"- 排版方向：{layout_direction}",
        f"- 題材敏感度：{topic_sensitivity}",
    ]

    selected_rules = style_rules + gray_rules + direct_rules
    if selected_rules:
        lines.append("- 已確認處理原則：")
        lines.extend(f"  - {rule}" for rule in selected_rules)

    if proper_nouns:
        lines.append(f"- 專名／人物／地名口徑：{proper_nouns}")
    if terminology:
        lines.append(f"- 術語／特殊用字口徑：{terminology}")
    if number_policy:
        lines.append(f"- 數字口徑：{number_policy}")
    if punctuation_policy:
        lines.append(f"- 標點口徑：{punctuation_policy}")
    if format_policy:
        lines.append(f"- 格式口徑：{format_policy}")
    if fact_check_policy:
        lines.append(f"- 查證口徑：{fact_check_policy}")
    if extra_notes:
        lines.append(f"- 其他補充：{extra_notes}")

    lines.append("- 批次校對時必須沿用以上口徑；不確定時以 comment 標示，不可硬改。")
    return "\n".join(lines)


st.set_page_config(
    page_title="proofreadK v0.6",
    page_icon="PK",
    layout="wide",
)

st.title("proofreadK v0.6")
st.caption("Professional Review Workspace：上傳 Word，逐條審核 AI 校對建議，再輸出追蹤修訂檔。")
st.warning("MVP 測試版：請先用測試文件驗證流程，再處理正式稿件。")

uploaded_file = st.file_uploader("上傳 .docx Word 檔", type=["docx"])

if uploaded_file is None:
    st.info("請先上傳一個 .docx 檔案。")
    st.stop()

st.success(f"已上傳：{uploaded_file.name}")

with st.expander("開發者選項 / 測試模式", expanded=False):
    proofread_stage = st.radio(
        "校對階段",
        ["啟動流程 / 抽樣分析", "確認本書附則", "批次校對"],
        help="啟動流程產生分析；確認本書附則用來整理你的回答；批次校對才會產生可審核的 action。",
    )
    proofread_source = st.radio(
        "校對來源",
        ["Gemini proofread", "使用 fake_proofread", "使用 Mock AI JSON"],
        help="Fake / Mock 只供測試 UI、validation 和 Word 輸出；一般流程使用 Gemini。",
    )
    paragraph_start_input = st.number_input(
        "起始段落",
        min_value=1,
        value=1,
        step=1,
        help="Word 流稿先用段落編號控制抽樣或批次範圍，不虛構頁碼或行號。",
    )
    paragraph_end_input = st.number_input(
        "結束段落",
        min_value=1,
        value=10,
        step=1,
    )
    batch_note = st.text_area(
        "本批說明 / 已知資料",
        value="",
        placeholder="例如：啟動抽樣：目錄、序、開頭章節；或第一批：第 1–30 段。",
    )

with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir_path = Path(tmpdir)
    input_path = tmpdir_path / "input.docx"
    edits_path = tmpdir_path / "fake_ai_edits.json"
    output_path = tmpdir_path / "proofread_result.docx"

    input_path.write_bytes(uploaded_file.getvalue())
    paragraphs_data = extract_paragraphs(str(input_path))
    paragraph_map = build_paragraph_map(paragraphs_data)
    paragraph_count = len(paragraphs_data)
    if paragraph_count == 0:
        st.error("這份 .docx 沒有讀取到可校對段落。請換一份有正文內容的 Word 檔。")
        st.stop()
    paragraph_start, paragraph_end = clamp_paragraph_range(
        int(paragraph_start_input),
        int(paragraph_end_input),
        paragraph_count,
    )
    selected_paragraphs = select_paragraphs(
        paragraphs_data,
        start_index=paragraph_start,
        end_index=paragraph_end,
    )

    with st.expander("📄 文件預覽", expanded=True):
        show_full_document = st.checkbox("顯示完整文件", value=False)
        preview_paragraphs = paragraphs_data if show_full_document else selected_paragraphs
        st.text(format_paragraph_preview(preview_paragraphs))

    st.caption(
        f"本次選取段落：第 {paragraph_start}–{paragraph_end} 段，"
        f"共 {len(selected_paragraphs)} 段。"
    )

    if "startup_report" not in st.session_state:
        st.session_state["startup_report"] = ""

    with st.expander("本書校對上下文 / 已確認附則", expanded=proofread_stage != "批次校對"):
        st.write("完成啟動分析後，請在這裏把本書口徑整理成可執行設定。批次校對會把這些設定一併送給 Gemini。")
        base_cols = st.columns(3)
        book_title = base_cols[0].text_input("書名", key="ctx_book_title")
        genre = base_cols[1].selectbox(
            "文類",
            ["未確認", "原創小說", "原創散文", "新詩", "家族／歷史敘事", "其他文學類"],
            key="ctx_genre",
        )
        origin_type = base_cols[2].selectbox(
            "原創／翻譯",
            ["未確認", "原創", "翻譯", "改寫／整理稿"],
            key="ctx_origin_type",
        )

        meta_cols = st.columns(3)
        layout_direction = meta_cols[0].selectbox(
            "排版方向",
            ["未確認", "橫排", "直排", "混合／需人工確認"],
            key="ctx_layout_direction",
        )
        topic_sensitivity = meta_cols[1].selectbox(
            "題材敏感度",
            ["未確認", "一般題材", "嚴肅／歷史／家族題材", "涉及史料或外部查證"],
            key="ctx_topic_sensitivity",
        )
        fact_check_policy = meta_cols[2].selectbox(
            "查證口徑",
            ["資料不足時只標示，不硬改", "年代／地名／專名一律需人工查證", "只處理書稿內部一致性，不作外部查證"],
            key="ctx_fact_check_policy",
        )

        style_rules = st.multiselect(
            "作者語氣／文學風格",
            [
                "保留作者語氣，不作風格潤飾",
                "人物口吻、地域語境、口語詞先標示，不硬改",
                "詩行、節奏、特殊斷句先標示，不硬改",
                "避免整句重寫，只做局部精準修改",
            ],
            default=["保留作者語氣，不作風格潤飾", "避免整句重寫，只做局部精準修改"],
            key="ctx_style_rules",
        )
        gray_rules = st.multiselect(
            "灰區處理",
            [
                "涉及史料原貌、引用、題簽、影印原件，只標示不硬改",
                "設計字、特殊版式、圖說、附錄層級，需人工判斷",
                "語感差異不列為硬錯",
                "資料不足時標示「需補資料」或「需人工判斷」",
            ],
            default=["語感差異不列為硬錯", "資料不足時標示「需補資料」或「需人工判斷」"],
            key="ctx_gray_rules",
        )
        direct_rules = st.multiselect(
            "可直接處理項目",
            [
                "明確錯別字可直接改",
                "明確標點錯誤可直接改",
                "同一詞在本批內前後不一致時先標示一致性問題",
                "疑似舊稿殘留、占位文字、章題不一致需標示",
            ],
            default=["明確錯別字可直接改", "明確標點錯誤可直接改"],
            key="ctx_direct_rules",
        )

        proper_nouns = st.text_input(
            "專名／人物／地名口徑",
            key="ctx_proper_nouns",
            placeholder="例：央生當鋪保留；人物名 A/B 不可互改；地名需人工查證。",
        )
        terminology = st.text_input(
            "術語／特殊用字口徑",
            key="ctx_terminology",
            placeholder="例：「寫住」若屬角色口語先標示不硬改；某些粵語詞保留。",
        )
        policy_cols = st.columns(3)
        number_policy = policy_cols[0].text_input(
            "數字口徑",
            key="ctx_number_policy",
            placeholder="例：年代用阿拉伯數字；概數保留中文數字。",
        )
        punctuation_policy = policy_cols[1].text_input(
            "標點口徑",
            key="ctx_punctuation_policy",
            placeholder="例：引號、破折號、省略號按 SOP；特殊節奏先標示。",
        )
        format_policy = policy_cols[2].text_input(
            "格式口徑",
            key="ctx_format_policy",
            placeholder="例：章題、附錄、圖說層級需人工確認。",
        )
        extra_notes = st.text_area(
            "其他補充／回答啟動分析中的問題",
            key="ctx_extra_notes",
            height=100,
            placeholder="把啟動分析中 Gemini 問你的問題逐條回答在這裏。",
        )

        book_context = build_book_context_text(
            book_title,
            genre,
            origin_type,
            layout_direction,
            topic_sensitivity,
            style_rules,
            gray_rules,
            direct_rules,
            proper_nouns,
            terminology,
            number_policy,
            punctuation_policy,
            format_policy,
            fact_check_policy,
            extra_notes,
        )
        st.text_area("將帶入批次校對的本書上下文預覽", value=book_context, height=220, disabled=True)
        if st.session_state["startup_report"]:
            st.text_area(
                "最近一次啟動分析報告（只作參考，不會自動當成已確認口徑）",
                value=st.session_state["startup_report"],
                height=220,
                disabled=True,
            )

    if proofread_stage == "啟動流程 / 抽樣分析":
        st.subheader("啟動流程 / 抽樣分析")
        st.info("此階段只產生校對設定、抽樣觀察與待確認問題，不會建立 Word 追蹤修訂。")

        if proofread_source != "Gemini proofread":
            st.warning("啟動分析需要使用 Gemini proofread；Fake / Mock 只適合測試批次校對 action。")
            st.stop()

        if st.button("產生 / 更新啟動分析報告", type="primary"):
            response_text, gemini_error = request_gemini_startup_response(
                selected_paragraphs,
                batch_note=batch_note,
            )
            if gemini_error:
                st.error(gemini_error)
            else:
                st.session_state["startup_report"] = response_text
                st.success("啟動分析已完成。請依下列步驟把報告轉成本書校對設定。")
                st.markdown(
                    """
**下一步**
1. 閱讀報告中的「待我確認的問題」與「灰區／需人工判斷」。
2. 回到上方「本書校對上下文 / 已確認附則」，勾選或填寫本書口徑。
3. 特別補充專名、術語、數字、標點、人物口吻、查證原則。
4. 切換到「確認本書附則」檢查上下文預覽。
5. 再切換到「批次校對」，按「產生 / 更新批次校對建議」。
"""
                )
                st.markdown(response_text)
        elif st.session_state["startup_report"]:
            st.success("已載入最近一次啟動分析報告。請把確認後的口徑填到上方表單，再進入「確認本書附則」。")
            st.markdown(
                """
**下一步**
1. 檢查報告中的待確認問題。
2. 在上方表單勾選／填寫本書附則。
3. 切換到「確認本書附則」檢查。
4. 確認後再進入「批次校對」。
"""
            )
            st.markdown(st.session_state["startup_report"])
        else:
            st.info("按「產生 / 更新啟動分析報告」開始。取得報告後，請把你確認的口徑填入上方「本書校對上下文 / 已確認附則」。")
        st.stop()

    if proofread_stage == "確認本書附則":
        st.subheader("確認本書附則")
        st.info("請檢查上方「將帶入批次校對的本書上下文預覽」。這段文字會作為下一步正式批次校對的依據。")
        st.markdown(
            """
**確認檢查**
1. 文類、原創／翻譯、排版方向是否正確。
2. 人物口吻、地域語境、詩行節奏等是否已設定為「只標示／不硬改」。
3. 專名、術語、數字、標點、格式口徑是否已補充。
4. 啟動分析中 Gemini 問你的問題，是否已回答在「其他補充」。
5. 若都已確認，切到「批次校對」。
"""
        )
        if st.session_state["startup_report"]:
            st.markdown(st.session_state["startup_report"])
        else:
            st.warning("目前尚未產生啟動分析報告。你仍可先手動填寫本書附則，再進入批次校對。")
        st.stop()

    batch_signature = json.dumps(
        {
            "file": uploaded_file.name,
            "source": proofread_source,
            "start": paragraph_start,
            "end": paragraph_end,
            "batch_note": batch_note,
            "book_context": book_context,
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    run_batch = st.button("產生 / 更新批次校對建議", type="primary")
    cached_batch = st.session_state.get("batch_result")

    if run_batch:
        response_text = ""

        if proofread_source == "使用 Mock AI JSON":
            response_text = MOCK_AI_RESPONSE_TEXT
            valid_edits, validation_errors = parse_ai_issues_response(MOCK_AI_RESPONSE_TEXT, selected_paragraphs)
            total_issue_count = len(valid_edits) + len(validation_errors)
        elif proofread_source == "Gemini proofread":
            response_text, gemini_error = request_gemini_proofread_response(
                selected_paragraphs,
                book_context=book_context,
            )
            if gemini_error:
                response_text = ""
                valid_edits = []
                validation_errors = [{"error": gemini_error}]
            else:
                valid_edits, validation_errors = parse_ai_issues_response(response_text, selected_paragraphs)
            total_issue_count = len(valid_edits) + len(validation_errors)
        else:
            edits = fake_proofread(selected_paragraphs)
            response_text = json.dumps(edits, ensure_ascii=False, indent=2)
            valid_edits, validation_errors = validate_edits(edits, selected_paragraphs)
            total_issue_count = len(edits)

        st.session_state["batch_result"] = {
            "signature": batch_signature,
            "response_text": response_text,
            "valid_edits": valid_edits,
            "validation_errors": validation_errors,
            "total_issue_count": total_issue_count,
        }
    elif cached_batch and cached_batch.get("signature") == batch_signature:
        response_text = cached_batch["response_text"]
        valid_edits = cached_batch["valid_edits"]
        validation_errors = cached_batch["validation_errors"]
        total_issue_count = cached_batch["total_issue_count"]
    else:
        st.info("請先按「產生 / 更新批次校對建議」。之後勾選或取消勾選建議時，不會重新呼叫 Gemini。")
        st.stop()

    for index, edit in enumerate(valid_edits, start=1):
        action_type = edit.get("action_type") or edit.get("action", "")
        paragraph_text = paragraph_map.get(edit.get("paragraph_index"), "")
        original_sentence = edit.get("original_sentence") or extract_original_sentence(
            paragraph_text,
            edit.get("original_text", ""),
        )
        suggested_sentence = edit.get("suggested_sentence") or build_suggested_sentence(
            action_type,
            original_sentence,
            edit.get("original_text", ""),
            edit.get("suggested_text", ""),
            edit.get("comment_text", ""),
        )
        edit["original_sentence"] = original_sentence or edit.get("original_text", "")
        edit["suggested_sentence"] = suggested_sentence or edit.get("suggested_text") or edit.get("comment_text", "")
        edit.setdefault("issue_type_label", get_issue_type_label(edit))
        edit.setdefault("rule_description", "")
        edit.setdefault("norm_basis", "")
        edit.setdefault("confidence_label", "")
        edit.setdefault("requires_human_check", edit.get("needs_human_review", False))

        issue_id = edit.get("issue_id") or f"edit_{index}"
        apply_key = issue_state_key(issue_id, index)
        status_key = issue_status_key(issue_id, index)
        if apply_key not in st.session_state:
            st.session_state[apply_key] = st.session_state.get(status_key, "accepted") == "accepted"
        st.session_state[status_key] = "accepted" if st.session_state[apply_key] else "ignored"

    accepted_count = sum(
        1
        for index, edit in enumerate(valid_edits, start=1)
        if get_issue_status(edit.get("issue_id"), index) == "accepted"
    )
    ignored_count = sum(
        1
        for index, edit in enumerate(valid_edits, start=1)
        if get_issue_status(edit.get("issue_id"), index) == "ignored"
    )
    pending_count = len(valid_edits) - accepted_count - ignored_count

    st.subheader("校對建議審核清單")
    st.write(
        f"文件：{uploaded_file.name} | "
        f"段落數：{len(paragraphs_data)} | "
        f"本批範圍：第 {paragraph_start}–{paragraph_end} 段 | "
        f"字數：約 {count_words(paragraphs_data)} | "
        f"校對建議數：{len(valid_edits)}"
    )

    if valid_edits:
        filter_value = st.selectbox("篩選建議", FILTER_OPTIONS)
        filtered_items = [
            (index, edit)
            for index, edit in enumerate(valid_edits, start=1)
            if filter_matches(edit, filter_value, get_issue_status(edit.get("issue_id"), index))
        ]

        grade_a_count = sum(1 for edit in valid_edits if get_grade_key(edit) == "A")
        grade_b_count = sum(1 for edit in valid_edits if get_grade_key(edit) == "B")
        grade_c_count = sum(1 for edit in valid_edits if get_grade_key(edit) == "C")
        grade_d_count = sum(1 for edit in valid_edits if get_grade_key(edit) == "D")

        metric_cols = st.columns(4)
        metric_cols[0].metric("全部", len(valid_edits))
        metric_cols[1].metric("已接受", accepted_count)
        metric_cols[2].metric("已忽略", ignored_count)
        metric_cols[3].metric("未處理", pending_count)
        st.caption(f"A 級：{grade_a_count} | B 級：{grade_b_count} | C 級：{grade_c_count} | D 級：{grade_d_count}")

        batch_cols = st.columns(4)
        if batch_cols[0].button("接受所有 A 級建議"):
            for index, edit in enumerate(valid_edits, start=1):
                if get_grade_key(edit) == "A":
                    set_issue_status(edit.get("issue_id"), index, "accepted")
            st.rerun()
        if batch_cols[1].button("全選目前篩選結果"):
            for index, edit in filtered_items:
                set_issue_status(edit.get("issue_id"), index, "accepted")
            st.rerun()
        if batch_cols[2].button("清除全部選取"):
            for index, edit in enumerate(valid_edits, start=1):
                set_issue_status(edit.get("issue_id"), index, "pending")
            st.rerun()
        if batch_cols[3].button("忽略目前篩選結果"):
            for index, edit in filtered_items:
                set_issue_status(edit.get("issue_id"), index, "ignored")
            st.rerun()

        if not filtered_items:
            st.info("目前篩選沒有校對建議。")

        st.markdown("### 校對建議")
        for group_number, (paragraph_index, group_items) in enumerate(group_filtered_items_by_paragraph(filtered_items), start=1):
            st.markdown("---")
            paragraph_text = paragraph_map.get(paragraph_index, "")
            st.markdown(f"**修改 {group_number}（段落 {paragraph_index}）**")

            st.markdown(
                f"""
<div style="border:1px solid #d0d5dd;border-radius:6px;padding:14px 16px;line-height:1.9;">
{render_grouped_paragraph_html(paragraph_text, [edit for _, edit in group_items])}
</div>
""",
                unsafe_allow_html=True,
            )

            reason_lines = []
            for index, edit in group_items:
                issue_id = edit.get("issue_id") or f"edit_{index}"
                action_type = edit.get("action_type") or edit.get("action", "")
                apply_key = issue_state_key(issue_id, index)
                status_key = issue_status_key(issue_id, index)
                apply_checked = st.checkbox(build_checkbox_label(edit), key=apply_key)
                status = "accepted" if apply_checked else "ignored"
                st.session_state[status_key] = status

                if action_type == "comment":
                    suggestion = edit.get("comment_text") or edit.get("suggested_sentence") or "加入批註，交由人工判斷。"
                    reason_lines.append(f"💡 {suggestion}")

                reason = edit.get("reason") or "未提供。"
                original_text = edit.get("original_text", "")
                suggested_text = edit.get("suggested_text", "")
                located = is_edit_located_in_paragraph(paragraph_text, edit)
                location_warning = "" if located else "（未能在段落中定位原文片段，請人工確認）"
                if action_type == "replace":
                    reason_lines.append(f"💡 修改「{original_text}」為「{suggested_text}」{location_warning}：{reason}")
                elif action_type == "delete":
                    reason_lines.append(f"💡 刪去「{original_text}」{location_warning}：{reason}")
                else:
                    reason_lines.append(f"💡 修改原因：{reason}")

            for line in reason_lines:
                st.caption(line)

        checked_edits = [
            edit
            for index, edit in enumerate(valid_edits, start=1)
            if get_issue_status(edit.get("issue_id"), index) == "accepted"
        ]

        display_rows = build_display_rows(valid_edits)
        display_df = pd.DataFrame(display_rows)

        st.markdown("---")
        st.write(
            f"總建議數：{total_issue_count} | "
            f"通過驗證數：{len(valid_edits)} | "
            f"已接受套用數：{len(checked_edits)} | "
            f"驗證錯誤數：{len(validation_errors)}"
        )

        if checked_edits:
            st.info(f"將套用 {len(checked_edits)} 項已接受建議。未處理與已忽略的建議不會寫入 Word。")
        else:
            st.warning("目前沒有已勾選套用的建議。請先勾選至少一項建議，才可產生追蹤修訂 Word。")

        if st.button("產生追蹤修訂 Word", type="primary", disabled=not checked_edits):
            with open(edits_path, "w", encoding="utf-8") as f:
                json.dump(checked_edits, f, ensure_ascii=False, indent=2)

            apply_edits_to_docx(
                input_file=str(input_path),
                edits_file=str(edits_path),
                output_file=str(output_path),
            )
            result_bytes = output_path.read_bytes()
            st.success("已產生追蹤修訂 Word。")
            st.download_button(
                label="下載追蹤修訂 Word",
                data=result_bytes,
                file_name="proofread_result.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        with st.expander("匯出問題清單", expanded=False):
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

        with st.expander("進階資料 / 完整校對建議表", expanded=False):
            st.dataframe(display_df, use_container_width=True)
    else:
        st.warning("沒有可安全套用到 Word 的校對建議，因此本輪不會顯示追蹤修訂 Word 下載按鈕。")
        st.info("常見原因：Gemini 回傳的 original_text 不在指定段落中、漏填必要欄位、或 paragraph_index 不在本批範圍。可縮小段落範圍後重試，或查看下方驗證錯誤。")
        st.write(
            f"總建議數：{total_issue_count} | "
            f"通過驗證數：0 | "
            f"已接受套用數：0 | "
            f"驗證錯誤數：{len(validation_errors)}"
        )
        render_ai_diagnostics(response_text, validation_errors)

    st.subheader("驗證錯誤")
    if validation_errors:
        st.warning(f"有 {len(validation_errors)} 條建議未通過驗證，這些建議不會套用到 Word。")
        st.dataframe(pd.DataFrame(validation_errors), use_container_width=True)
        if valid_edits:
            render_ai_diagnostics(response_text, validation_errors)
    else:
        st.success("所有校對建議都通過驗證。")
