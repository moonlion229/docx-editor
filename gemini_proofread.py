import os

from google import genai

import json
from pathlib import Path

DEFAULT_MODEL = "gemini-2.5-flash"


def select_paragraphs(paragraphs_data, start_index=None, end_index=None, max_paragraphs=None):
    selected = paragraphs_data
    if start_index is not None:
        selected = [
            paragraph for paragraph in selected
            if paragraph["paragraph_index"] >= start_index
        ]
    if end_index is not None:
        selected = [
            paragraph for paragraph in selected
            if paragraph["paragraph_index"] <= end_index
        ]
    if max_paragraphs is not None:
        selected = selected[:max_paragraphs]
    return selected


def build_paragraph_lines(paragraphs_data):
    return [
        f'{p["paragraph_index"]}: {p["text"]}'
        for p in paragraphs_data
    ]


def build_gemini_startup_prompt(paragraphs_data, batch_note=""):
    paragraph_lines = build_paragraph_lines(paragraphs_data)
    sop_rules = load_literary_sop_rules()
    sop_rules_text = json.dumps(sop_rules, ensure_ascii=False, indent=2)
    return f"""
你是資深中文校對編輯與出版流程管理顧問。請根據《文學類校對 SOP V2.3》的精神，先做本書長文校對的啟動設定與抽樣分析，不要直接逐段全文校對，也不要輸出 Word 修改 action。

請一律使用繁體中文、香港常見書面語與標點。若資料不足，直接標示「書稿未提供」、「需補資料」、「需人工判斷」或「需人工查證」。

工作邊界：
- 只根據本次提供的段落與下方 SOP rules pack 判斷。
- 不要加入外部資料、常識補充、作者意圖或市場判斷。
- 不要大規模潤飾、改寫、重寫或補寫。
- 不要生成本書 Excel 模板；只可評估第一次正式校對後是否需要。
- 涉及人物口吻、敘事聲音、標點節奏、特殊版式、史料原貌或外部查證者，列為灰區或需人工判斷。

請按以下格式輸出：
1. 簡單版摘要
2. 本次處理範圍
3. 已讀取或仍缺漏的資料
4. 本書啟動設定
5. 抽樣分析結果
6. 可直接沿用的 SOP 規則
7. 需建立的本書附則
8. 舊 Excel 參考模板的可用與不可用部分
9. 灰區／需人工判斷
10. 待我確認的問題
11. 1–3 個例子
12. 前提、限制與不確定性
13. 自我評分，10 分制，並說明扣分原因

本批說明：
{batch_note or "未提供"}

SOP rules pack：
{sop_rules_text}

抽樣段落：
{chr(10).join(paragraph_lines)}
""".strip()


def build_gemini_proofread_prompt(paragraphs_data, max_paragraphs=None, book_context=""):
    selected = select_paragraphs(paragraphs_data, max_paragraphs=max_paragraphs)
    paragraph_lines = [
        f'{p["paragraph_index"]}: {p["text"]}'
        for p in selected
    ]
    sop_rules = load_literary_sop_rules()
    sop_rules_text = json.dumps(sop_rules, ensure_ascii=False, separators=(",", ":"))
    return f"""
你是出版校對助理。請只根據以下段落與已確認的本書校對上下文產生校對問題 issue list。

限制：
- 只輸出 JSON array，不要輸出 Markdown，不要輸出解釋文字。
- 以節省輸出 token 為目標；每條建議只保留校對員判斷必需資訊。
- action_type 只允許 replace、delete、comment。
- replace/delete 的 original_text 必須是指定 paragraph_index 中真實存在的連續文字。
- comment 的 original_text 可以為空；若不為空，也必須存在於指定段落。
- 不要整段改寫，優先局部、精準、可定位。
- 如沒有明確問題，輸出空陣列 []。
- paragraph_index 只能使用下方「段落」中列出的編號，不可自行編造。
- replace/delete 的 original_text 必須逐字複製原段落中的連續片段，不可改字、不可省略、不可用意譯。
- 如果你不能確定 original_text 是否逐字存在，請改用 action_type="comment"，並把 original_text 設為空字串。
- 輸出前請自行檢查每一項是否能通過程式驗證；不能通過的項目不要輸出。
- 文學語氣、敘事聲音、人物口吻、節奏、外部查證與灰區問題，預設使用 comment，不要硬改。
- 絕對不可用「...」表示段落或句子未完；除非原文真的逐字出現三個英文句點，否則不要在 original_text、suggested_text、original_sentence、suggested_sentence 中輸出「...」。
- 如果段落在本批資料中看似未完，請視為 Word 流稿自然分段或本批範圍切分，不可判斷為省略號錯誤。

每個 issue 必須包含：
issue_id, paragraph_index, position_label, original_text, suggested_text,
action_type, category_code, category_label, grade, grade_label, reason,
global_consistency, add_to_book_rules, needs_human_review, needs_source_check

只有 comment 類 issue 才必須加入 comment_text。
如可行，可加入 issue_type，但不要為了補欄位輸出空泛內容。

請不要輸出以下長欄位，除非校對員沒有它就無法判斷：
original_sentence, suggested_sentence, rule_description, norm_basis, confidence_label

- A 級明確錯誤可用 replace/delete。
- C/D 級問題不要硬改，使用 action_type="comment"。
- 不確定時使用 comment，needs_human_review=true。
- 地名、日期、專名若需要外部資料核實，needs_source_check 必須是 true；不要假裝已查證外部資料。
- category_code 必須使用 taxonomy：A/B/C/D/E/F/G。
- grade 必須使用 A/B/C/D；grade_label 使用「可直接改」、「建議改」、「只標示」、「需人工判斷」其中之一。
- issue_type 請優先使用：norm_description, homophone_error, missing_word, redundant_word,
  shape_similar_error, word_order_error, place_name, date_format, punctuation,
  typo, consistency, style, fact_check, comment_only。
- position_label 保持簡短，例如「段落 13」或「第九章術語」。
- reason 必須保留校對員判斷所需的具體資訊，可寫 1-2 句；不要只寫規範名稱，也不要重複冗長規範描述。
- replace/delete 的 suggested_text 只填替換文字或空字串，不要填完整句。
- comment_text 只寫處理方式，不超過 40 個中文字。
- 不確定時不要硬改，使用 action_type="comment"。

SOP rules pack：
{sop_rules_text}

已確認的本書校對上下文：
{book_context or "未提供。請只依 SOP rules pack 與本批段落校對。"}

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
    
def request_gemini_proofread_response(paragraphs_data, model=DEFAULT_MODEL, max_paragraphs=None, book_context=""):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "找不到 GEMINI_API_KEY。請先設定環境變數。"

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=build_gemini_proofread_prompt(
                paragraphs_data,
                max_paragraphs=max_paragraphs,
                book_context=book_context,
            ),
        )
    except Exception as exc:
        return None, f"Gemini API 錯誤：{exc}"

    response_text = getattr(response, "text", None)
    if not response_text:
        return None, "Gemini API 沒有回傳文字內容。"

    return clean_json_response_text(response_text), None


def request_gemini_startup_response(paragraphs_data, batch_note="", model=DEFAULT_MODEL):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "找不到 GEMINI_API_KEY。請先設定環境變數。"

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=build_gemini_startup_prompt(paragraphs_data, batch_note=batch_note),
        )
    except Exception as exc:
        return None, f"Gemini API 錯誤：{exc}"

    response_text = getattr(response, "text", None)
    if not response_text:
        return None, "Gemini API 沒有回傳文字內容。"

    return response_text.strip(), None
