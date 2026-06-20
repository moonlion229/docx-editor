import argparse
import json
from docx_editor import Document


def get_paragraph_ref_and_text(doc, paragraph_index):
    """
    paragraph_index 使用 1, 2, 3... 這種人類容易理解的段落編號。
    程式內部會轉成 0, 1, 2...
    """
    paragraphs = doc.list_paragraphs()
    zero_based_index = paragraph_index - 1

    if zero_based_index < 0 or zero_based_index >= len(paragraphs):
        return None, None

    paragraph_record = paragraphs[zero_based_index]

    if "|" in paragraph_record:
        ref, text = paragraph_record.split("|", 1)
    else:
        ref = paragraph_record
        text = paragraph_record

    return ref, text


def apply_edits_to_docx(input_file, edits_file, output_file):
    with open(edits_file, "r", encoding="utf-8") as f:
        edits = json.load(f)

    applied_count = 0
    skipped_count = 0

    with Document.open(input_file) as doc:
        for i, edit in enumerate(edits, start=1):
            paragraph_index = edit.get("paragraph_index")
            action = edit.get("action")
            original_text = edit.get("original_text", "")
            suggested_text = edit.get("suggested_text", "")
            comment_text = edit.get("comment_text", "")
            reason = edit.get("reason", "")

            ref, paragraph_text = get_paragraph_ref_and_text(doc, paragraph_index)

            if ref is None:
                print(f"跳過第 {i} 條：找不到第 {paragraph_index} 段")
                skipped_count += 1
                continue

            if original_text not in paragraph_text:
                print(f"跳過第 {i} 條：第 {paragraph_index} 段找不到「{original_text}」")
                print(f"目前段落內容：{paragraph_text}")
                skipped_count += 1
                continue

            if action == "replace":
                doc.replace(original_text, suggested_text, paragraph=ref)
                print(f"已套用第 {i} 條：第 {paragraph_index} 段，把「{original_text}」改成「{suggested_text}」")
                applied_count += 1

            elif action == "delete":
                doc.replace(original_text, "", paragraph=ref)
                print(f"已套用第 {i} 條：第 {paragraph_index} 段，刪除「{original_text}」")
                applied_count += 1

            elif action == "comment":
                final_comment = comment_text or reason
                if not final_comment:
                    final_comment = "請人工確認此處。"

                doc.add_comment(original_text, final_comment)
                print(f"已套用第 {i} 條：第 {paragraph_index} 段，在「{original_text}」加入批註")
                applied_count += 1

            else:
                print(f"跳過第 {i} 條：暫不支援 action = {action}")
                skipped_count += 1

        doc.save(output_file)

    print("處理完成")
    print(f"成功套用：{applied_count} 條")
    print(f"跳過：{skipped_count} 條")
    print(f"已建立：{output_file}")


def main():
    parser = argparse.ArgumentParser(description="Apply proofreading JSON edits to a DOCX file with tracked changes and comments.")
    parser.add_argument("--input", required=True, help="原始 Word 檔，例如 multi_original.docx")
    parser.add_argument("--edits", required=True, help="校對建議 JSON，例如 edits_with_comment.json")
    parser.add_argument("--output", required=True, help="輸出的追蹤修訂 Word，例如 revised.docx")

    args = parser.parse_args()

    apply_edits_to_docx(
        input_file=args.input,
        edits_file=args.edits,
        output_file=args.output
    )


if __name__ == "__main__":
    main()
