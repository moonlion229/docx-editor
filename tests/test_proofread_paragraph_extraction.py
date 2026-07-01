import json

from ai_issue_parser import parse_ai_issues_response
from fake_ai_proofread import FULL_PARAGRAPH_MAX_CHARS, extract_paragraphs
from proofread_apply import COMMENT_ANCHOR_MAX_CHARS, get_paragraph_ref_and_text, resolve_comment_anchor


class FakeDocument:
    def __init__(self, records):
        self.records = records
        self.max_chars_seen = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def list_paragraphs(self, max_chars=80):
        self.max_chars_seen = max_chars
        if max_chars == 80:
            return ["P1#abcd| 結果就是，我們在馬路上經..."]
        return self.records


class FakeDocumentFactory:
    def __init__(self, fake_doc):
        self.fake_doc = fake_doc

    def open(self, _input_file):
        return self.fake_doc


def test_extract_paragraphs_uses_full_text_not_preview(monkeypatch):
    full_text = "結果就是，我們在馬路上經常看到各種奇怪事情，而這句在 Word 中並沒有省略號。"
    fake_doc = FakeDocument([f"P1#abcd| {full_text}"])

    import fake_ai_proofread

    monkeypatch.setattr(fake_ai_proofread, "Document", FakeDocumentFactory(fake_doc))

    paragraphs = extract_paragraphs("input.docx")

    assert fake_doc.max_chars_seen == FULL_PARAGRAPH_MAX_CHARS
    assert paragraphs == [{"paragraph_index": 1, "text": full_text}]
    assert paragraphs[0]["text"].endswith("。")
    assert not paragraphs[0]["text"].endswith("...")


def test_apply_lookup_uses_full_text_not_preview():
    full_text = "結果就是，我們在馬路上經常看到各種奇怪事情，而這句在 Word 中並沒有省略號。"
    fake_doc = FakeDocument([f"P1#abcd| {full_text}"])

    ref, paragraph_text = get_paragraph_ref_and_text(fake_doc, 1)

    assert fake_doc.max_chars_seen == FULL_PARAGRAPH_MAX_CHARS
    assert ref == "P1#abcd"
    assert paragraph_text == full_text
    assert not paragraph_text.endswith("...")


def test_resolve_comment_anchor_uses_sentence_when_available():
    paragraph_text = "第一句。這一句需要人工判斷。第三句。"
    edit = {
        "original_text": "",
        "original_sentence": "這一句需要人工判斷。",
    }

    assert resolve_comment_anchor(edit, paragraph_text) == "這一句需要人工判斷。"


def test_resolve_comment_anchor_falls_back_to_paragraph_start():
    paragraph_text = "這是一段沒有精準錨點但仍要加入批註的文字。"
    edit = {
        "original_text": "",
        "original_sentence": "",
    }

    assert resolve_comment_anchor(edit, paragraph_text) == paragraph_text[:COMMENT_ANCHOR_MAX_CHARS]


def test_parser_rejects_artificial_preview_ellipsis():
    paragraphs = [{"paragraph_index": 1, "text": "結果就是，我們在馬路上經常看到各種奇怪事情。"}]
    issue = {
        "issue_id": "fake-ellipsis",
        "paragraph_index": 1,
        "position_label": "段落尾部",
        "original_text": "結果就是",
        "suggested_text": "結果就是",
        "action_type": "replace",
        "category_code": "C",
        "category_label": "標點",
        "grade": "A",
        "grade_label": "可直接改",
        "reason": "測試不應接受截斷預覽造成的假省略號。",
        "global_consistency": False,
        "add_to_book_rules": False,
        "needs_human_review": False,
        "needs_source_check": False,
        "original_sentence": "結果就是，我們在馬路上經...",
        "suggested_sentence": "結果就是，我們在馬路上經……",
    }

    valid, errors = parse_ai_issues_response(json.dumps([issue], ensure_ascii=False), paragraphs)

    assert valid == []
    assert len(errors) == 1
    assert "疑似截斷預覽" in errors[0]["error"]
