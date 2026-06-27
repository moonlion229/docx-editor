import os

from google import genai


DEFAULT_MODEL = "gemini-2.5-flash"

def build_gemini_proofread_prompt(paragraphs_data, max_paragraphs=5):
    selected = paragraphs_data[:max_paragraphs]
    paragraph_lines = [
        f'{p["paragraph_index"]}: {p["text"]}'
        for p in selected
    ]

    return f"""
你是出版校對助理。請只根據以下段落產生校對問題 issue list。

限制：
- 只輸出 JSON array，不要輸出 Markdown，不要輸出解釋文字。
- action_type 只允許 replace、delete、comment。
- replace/delete 的 original_text 必須是指定 paragraph_index 中真實存在的連續文字。
- comment 的 original_text 可以為空；若不為空，也必須存在於指定段落。
- 不要整段改寫，優先局部、精準、可定位。
- 如沒有明確問題，輸出空陣列 []。

每個 issue 必須包含：
issue_id, paragraph_index, position_label, original_text, suggested_text,
action_type, category_code, category_label, grade, grade_label, reason,
global_consistency, add_to_book_rules, needs_human_review, needs_source_check,
comment_text

段落：
{chr(10).join(paragraph_lines)}
""".strip()

def clean_json_response_text(response_text):
    text = response_text.strip()

    if text.startswith("```json"):
        text = text.removeprefix("```json").strip()

    if text.startswith("```"):
        text = text.removeprefix("```").strip()

    if text.endswith("```"):
        text = text.removesuffix("```").strip()

    start = text.find("[")
    end = text.rfind("]")

    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1].strip()

    return text

def request_gemini_proofread_response(paragraphs_data, model=DEFAULT_MODEL):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "找不到 GEMINI_API_KEY。請先設定環境變數。"

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=build_gemini_proofread_prompt(paragraphs_data),
        )
    except Exception as exc:
        return None, f"Gemini API 錯誤：{exc}"

    response_text = getattr(response, "text", None)
    if not response_text:
        return None, "Gemini API 沒有回傳文字內容。"

    return clean_json_response_text(response_text), None

