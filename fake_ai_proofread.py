import argparse
import json
from docx_editor import Document

REQUIRED_ISSUE_FIELDS = {
    "issue_id", "paragraph_index", "position_label",
    "original_text", "suggested_text", "action_type",
    "category_code", "category_label", "grade", "grade_label",
    "reason", "global_consistency", "add_to_book_rules",
    "needs_human_review", "needs_source_check",
}


def make_issue(issue_id, paragraph_index, action_type, original_text, suggested_text,
               category_code, category_label, grade, grade_label, reason,
               position_label="段落內文字", comment_text="",
               global_consistency=False, add_to_book_rules=False,
               needs_human_review=False, needs_source_check=False,
               confidence=0.9):
    return {
        "issue_id": issue_id,
        "paragraph_index": paragraph_index,
        "position_label": position_label,
        "original_text": original_text,
        "suggested_text": suggested_text,
        "action_type": action_type,
        "action": action_type,
        "comment_text": comment_text,
        "category_code": category_code,
        "category_label": category_label,
        "category": category_label,
        "grade": grade,
        "grade_label": grade_label,
        "severity": grade,
        "reason": reason,
        "global_consistency": global_consistency,
        "add_to_book_rules": add_to_book_rules,
        "needs_human_review": needs_human_review,
        "needs_source_check": needs_source_check,
        "confidence": confidence,
    }

def extract_paragraphs(input_file):
    paragraphs_data = []

    with Document.open(input_file) as doc:
        paragraphs = doc.list_paragraphs()

        for index, record in enumerate(paragraphs, start=1):
            if "|" in record:
                _ref, text = record.split("|", 1)
            else:
                text = record

            text = text.strip()

            if text:
                paragraphs_data.append({
                    "paragraph_index": index,
                    "text": text
                })

    return paragraphs_data


def fake_proofread(paragraphs_data):
    """
    這是假 AI。
    目的只是模擬未來 OpenAI 會產生的 JSON 格式。
    """
    issues = []

    for paragraph in paragraphs_data:
        idx = paragraph["paragraph_index"]
        text = paragraph["text"]

        if "," in text:
            edits.append({
                "paragraph_index": idx,
                "action": "replace",
                "original_text": ",",
                "suggested_text": "，",
                "comment_text": "",
                "category": "標點",
                "severity": "low",
                "reason": "中文正文應使用全形逗號。",
                "confidence": 0.95
            })

        if "在內容方面是非常" in text:
            issues.append(make_issue(
                issue_id=f"P{idx}-delete-redundant-phrase",
                paragraph_index=idx,
                position_label="冗詞片段",
                action_type="delete",
                original_text="在內容方面是非常",
                suggested_text="",
                category_code="conciseness",
                category_label="語句精簡",
                grade="medium",
                grade_label="中",
                reason="冗詞，可刪減。",
                confidence=0.9,
            ))

        if "他說這很好" in text:
            issues.append(make_issue(
                issue_id=f"P{idx}-replace-quote-colon",
                paragraph_index=idx,
                position_label="引述語前",
                action_type="replace",
                original_text="他說",
                suggested_text="他說：",
                category_code="punctuation",
                category_label="標點",
                grade="low",
                grade_label="低",
                reason="補上冒號，使引述語氣更清楚。",
                confidence=0.95,
            ))
        if "成本為100元" in text:
            edits.append({
                "paragraph_index": idx,
                "action": "add",
                "anchor_text": "100元",
                "position": "before",
                "added_text": "港幣",
                "original_text": "100元",
                "suggested_text": "港幣100元",
                "comment_text": "",
                "category": "單位",
                "severity": "low",
                "reason": "補上幣別，使金額表述更清楚。",
                "confidence": 0.95
            })    
        if "人物之間的關係" in text:
            issues.append(make_issue(
                issue_id=f"P{idx}-comment-long-sentence",
                paragraph_index=idx,
                position_label="人物關係描述",
                action_type="comment",
                original_text="人物之間的關係",
                suggested_text="",
                comment_text="此句較長，建議人工確認是否需要拆句。",
                category_code="sentence",
                category_label="語句",
                grade="medium",
                grade_label="中",
                reason="直接改寫可能改變作者語氣，建議先用批註提醒。",
                needs_human_review=True,
                confidence=0.8,
            ))


    return issues

def validate_edits(edits, paragraphs_data):
    allowed_actions = {"replace", "delete", "comment"}
    paragraph_map = {
        paragraph["paragraph_index"]: paragraph["text"]
        for paragraph in paragraphs_data
    }
 
            
    valid_edits = []
    validation_errors = []

    for edit_number, edit in enumerate(edits, start=1):
        paragraph_index = edit.get("paragraph_index")
        action = edit.get("action_type") or edit.get("action")
        original_text = edit.get("original_text", "")
   
        missing_fields = [
                field for field in sorted(REQUIRED_ISSUE_FIELDS)
                if field not in edit
            ]
        if missing_fields:
                error = "缺少必要欄位：" + "、".join(missing_fields)
        elif action not in allowed_actions:
                error = f"action_type 只允許 replace、delete、comment；目前是 {action!r}。"
        
        error = None

        if action not in allowed_actions:
            error = f"action 只允許 replace、delete、comment；目前是 {action!r}。"
        elif paragraph_index not in paragraph_map:
            error = f"paragraph_index {paragraph_index!r} 不存在於原文段落。"
        else:
            paragraph_text = paragraph_map[paragraph_index]

            if action in {"replace", "delete"}:
                if not original_text:
                    error = "replace/delete 必須提供 original_text。"
                elif original_text not in paragraph_text:
                    error = "original_text 不在指定段落中。"
            elif action == "comment" and original_text and original_text not in paragraph_text:
                error = "comment 的 original_text 不在指定段落中。"

        if error:
            validation_errors.append({
                "edit_number": edit_number,
                "paragraph_index": paragraph_index,
                "action": action,
                "original_text": original_text,
                "error": error,
            })
        else:
            valid_edit = dict(edit)
            valid_edit["action_type"] = action
            valid_edit["action"] = action
            valid_edits.append(valid_edit)

    return valid_edits, validation_errors

def main():
    parser = argparse.ArgumentParser(description="Fake AI proofreader that outputs JSON edits.")
    parser.add_argument("--input", required=True, help="原始 Word 檔，例如 multi_original.docx")
    parser.add_argument("--output", required=True, help="輸出的 JSON 檔，例如 fake_ai_edits.json")

    args = parser.parse_args()

    paragraphs_data = extract_paragraphs(args.input)
    edits = fake_proofread(paragraphs_data)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(edits, f, ensure_ascii=False, indent=2)

    print(f"已讀取段落數：{len(paragraphs_data)}")
    print(f"已產生校對建議：{len(edits)} 條")
    print(f"已建立：{args.output}")


if __name__ == "__main__":
    main()