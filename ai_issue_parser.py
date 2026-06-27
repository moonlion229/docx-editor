import json


REQUIRED_ISSUE_FIELDS = {
    "issue_id",
    "paragraph_index",
    "position_label",
    "original_text",
    "suggested_text",
    "action_type",
    "category_code",
    "category_label",
    "grade",
    "grade_label",
    "reason",
    "global_consistency",
    "add_to_book_rules",
    "needs_human_review",
    "needs_source_check",
    "original_sentence",
    "suggested_sentence",
}


MOCK_AI_RESPONSE_TEXT = json.dumps(
    [
        {
            "issue_id": "mock-replace-quote-colon",
            "paragraph_index": 1,
            "position_label": "引述語前",
            "original_text": "他說",
            "suggested_text": "他說：",
            "action_type": "replace",
            "category_code": "punctuation",
            "category_label": "標點",
            "grade": "low",
            "grade_label": "低",
            "reason": "補上冒號，使引述語氣更清楚。",
            "global_consistency": False,
            "add_to_book_rules": False,
            "needs_human_review": False,
            "needs_source_check": False,
            "comment_text": "",
        },
        {
            "issue_id": "mock-invalid-original-text",
            "paragraph_index": 1,
            "position_label": "錯誤示範",
            "original_text": "這段文字不存在",
            "suggested_text": "測試",
            "action_type": "replace",
            "category_code": "test",
            "category_label": "測試",
            "grade": "low",
            "grade_label": "低",
            "reason": "測試 validation 是否能擋下不存在的原文。",
            "global_consistency": False,
            "add_to_book_rules": False,
            "needs_human_review": False,
            "needs_source_check": False,
            "comment_text": "",
        },
        {
                "issue_id": "mock-comment-pawnshop-description",
                "paragraph_index": 2,
                "position_label": "當鋪物品描述",
                "original_text": "典當的東西",
                "suggested_text": "",
                "action_type": "comment",
                "category_code": "sentence",
                "category_label": "語句",
                "grade": "medium",
                "grade_label": "中",
                "reason": "此處描述較概括，可考慮補充更明確的物品分類或視覺細節。",
                "global_consistency": False,
                "add_to_book_rules": False,
                "needs_human_review": True,
                "needs_source_check": False,
                "comment_text": "建議人工確認此處描述是否需要更具體。",
        },
        {
            "issue_id": "mock-delete-redundant-phrase",
            "paragraph_index": 6,
            "position_label": "冗詞片段",
            "original_text": "在內容方面是非常",
            "suggested_text": "",
            "action_type": "delete",
            "category_code": "conciseness",
            "category_label": "語句精簡",
            "grade": "medium",
            "grade_label": "中",
            "reason": "冗詞，可刪減。",
            "global_consistency": False,
            "add_to_book_rules": False,
            "needs_human_review": False,
            "needs_source_check": False,
            "comment_text": "",
        },
        {
            "issue_id": "mock-invalid-missing-reason",
            "paragraph_index": 1,
            "position_label": "錯誤示範",
            "original_text": "不存在的文字",
            "suggested_text": "測試",
            "action_type": "replace",
            "category_code": "test",
            "category_label": "測試",
            "grade": "low",
            "grade_label": "低",
            "global_consistency": False,
            "add_to_book_rules": False,
            "needs_human_review": False,
            "needs_source_check": False,
            "comment_text": "",
        },
    ],
    ensure_ascii=False,
)


def parse_ai_issues_response(response_text, paragraphs_data):
    try:
        issues = json.loads(response_text)
    except json.JSONDecodeError as exc:
        return [], [{"error": f"JSON 格式不合法：{exc.msg}"}]

    if not isinstance(issues, list):
        return [], [{"error": "AI 回傳 JSON 必須是 list。"}]

    paragraph_map = {
        paragraph["paragraph_index"]: paragraph["text"]
        for paragraph in paragraphs_data
    }

    valid_issues = []
    validation_errors = []
    allowed_actions = {"replace", "delete", "comment"}

    for issue_number, issue in enumerate(issues, start=1):
        if not isinstance(issue, dict):
            validation_errors.append({
                "issue_number": issue_number,
                "error": "list 裡每一項都必須是 dict/object。",
            })
            continue

        issue_id = issue.get("issue_id", f"issue_{issue_number}")
        action_type = issue.get("action_type")
        paragraph_index = issue.get("paragraph_index")
        original_text = issue.get("original_text", "")

        missing_fields = [
            field for field in sorted(REQUIRED_ISSUE_FIELDS)
            if field not in issue
        ]

        error = None

        if missing_fields:
            error = "缺少必要欄位：" + "、".join(missing_fields)
        elif action_type not in allowed_actions:
            error = f"action_type 只允許 replace、delete、comment；目前是 {action_type!r}。"
        elif paragraph_index not in paragraph_map:
            error = f"paragraph_index {paragraph_index!r} 不存在於原文段落。"
        else:
            paragraph_text = paragraph_map[paragraph_index]

            if action_type in {"replace", "delete"}:
                if not original_text:
                    error = "replace/delete 必須提供 original_text。"
                elif original_text not in paragraph_text:
                    error = "original_text 不在指定段落中。"
            elif action_type == "comment" and original_text and original_text not in paragraph_text:
                error = "comment 的 original_text 不在指定段落中。"

        if error:
            validation_errors.append({
                "issue_number": issue_number,
                "issue_id": issue_id,
                "paragraph_index": paragraph_index,
                "action_type": action_type,
                "original_text": original_text,
                "paragraph_text": paragraph_map.get(paragraph_index, ""),
                "error": error,
            })
            continue

        valid_issue = dict(issue)
        valid_issue["action"] = action_type
        valid_issue["category"] = valid_issue.get("category_label", "")
        valid_issue["severity"] = valid_issue.get("grade", "")
        valid_issue.setdefault("comment_text", "")
        valid_issue.setdefault("original_sentence", "")
        valid_issue.setdefault("suggested_sentence", "")
        valid_issue.setdefault("rule_id", "")
        valid_issues.append(valid_issue)
 

    return valid_issues, validation_errors