import argparse
import json
from docx_editor import Document


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
    edits = []

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
            edits.append({
                "paragraph_index": idx,
                "action": "delete",
                "original_text": "在內容方面是非常",
                "suggested_text": "",
                "comment_text": "",
                "category": "語句精簡",
                "severity": "medium",
                "reason": "冗詞，可刪減。",
                "confidence": 0.9
            })

        if "他說這很好" in text:
            edits.append({
                "paragraph_index": idx,
                "action": "add",
                "anchor_text": "他說",
                "position": "after",
                "added_text": "：",
                "original_text": "他說",
                "suggested_text": "他說：",
                "comment_text": "",
                "category": "標點",
                "severity": "low",
                "reason": "補上冒號，使引述語氣更清楚。",
                "confidence": 0.95
            })
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
            edits.append({
                "paragraph_index": idx,
                "action": "comment",
                "original_text": "人物之間的關係",
                "suggested_text": "",
                "comment_text": "此句較長，建議人工確認是否需要拆句。",
                "category": "語句",
                "severity": "medium",
                "reason": "直接改寫可能改變作者語氣，建議先用批註提醒。",
                "confidence": 0.8
            })

    return edits


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