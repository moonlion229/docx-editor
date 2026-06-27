import os

from google import genai

import json
from pathlib import Path

DEFAULT_MODEL = "gemini-2.5-flash-lite"

def build_gemini_proofread_prompt(paragraphs_data, max_paragraphs=5):
    selected = paragraphs_data[:max_paragraphs]
    paragraph_lines = [
        f'{p["paragraph_index"]}: {p["text"]}'
        for p in selected
    ]
    sop_rules = load_literary_sop_rules()
    sop_rules_text = json.dumps(sop_rules, ensure_ascii=False, indent=2)
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
comment_text,original_sentence, suggested_sentence
如可行，請加入 rule_id。

- A 級明確錯誤可用 replace/delete。
- C/D 級問題不要硬改，使用 action_type="comment"。
- 不確定時使用 comment，needs_human_review=true。
- category_code 必須使用 taxonomy：A/B/C/D/E/F/G。
- original_sentence 必須是包含 original_text 的完整原句，且忠於原文。
- suggested_sentence 必須是修改後完整句；若 action_type="comment"，填寫清楚處理建議。
- 不確定時不要硬改，使用 action_type="comment"。

SOP rules pack：
{sop_rules_text}
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

def load_literary_sop_rules():
    rules_path = Path(__file__).with_name("sop_rules_literary_v1.json")
    with open(rules_path, "r", encoding="utf-8") as f:
        return json.load(f)
    
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

