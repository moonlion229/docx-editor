import json
import os
import urllib.error
import urllib.request


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-4.1-mini"


def build_proofread_prompt(paragraphs_data, max_paragraphs=5):
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

每個 issue 必須包含：
issue_id, paragraph_index, position_label, original_text, suggested_text,
action_type, category_code, category_label, grade, grade_label, reason,
global_consistency, add_to_book_rules, needs_human_review, needs_source_check,
comment_text

段落：
{chr(10).join(paragraph_lines)}
""".strip()


def request_openai_proofread_response(paragraphs_data, model=DEFAULT_MODEL):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, "找不到 OPENAI_API_KEY。請先設定環境變數。"

    payload = {
        "model": model,
        "input": build_proofread_prompt(paragraphs_data),
        "temperature": 0,
    }

    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return None, f"OpenAI API HTTP 錯誤：{exc.code} {body}"
    except urllib.error.URLError as exc:
        return None, f"OpenAI API 連線錯誤：{exc.reason}"
    except json.JSONDecodeError as exc:
        return None, f"OpenAI API 回應不是合法 JSON：{exc.msg}"

    output_text = data.get("output_text")
    if output_text:
        return output_text, None

    return None, "OpenAI API 沒有回傳 output_text。"