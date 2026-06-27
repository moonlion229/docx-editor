# AI 校對輸出格式 v1

本文件定義 AI 校對工具必須輸出的 JSON 格式。

## 基本原則

AI 不應只輸出「修改後整段文字」。
AI 應盡量輸出「最小可修改片段」，以便 Word 追蹤修訂只標示實際修改的位置。

優先順序：

1. 能用 replace，就不要用 rewrite。
2. 能用 delete，就不要整句重寫。
3. 不確定是否應直接修改時，使用 comment。
4. rewrite 只用於明確需要整句或整段改寫的情況。

## JSON 必須是一個陣列

每一個 item 代表一條校對建議。

## 欄位說明
每一個 item 代表一條「校對問題 issue」。

### issue_id

字串。每條校對問題的唯一 ID。

範例：

```json
"P1-replace-quote-colon"

### paragraph_index

數字。代表第幾段，從 1 開始。

### position label
字串。給使用者看的位置描述。
範例：
引述語前
冗詞片段
人物關係描述

### original_text
Word 原文中要定位的文字片段。
要求：
replace / delete 必須填寫
comment 可為空，但若有填寫，必須真的存在於該段落
不應使用整段，除非沒有其他選擇

### action
暫時保留的相容欄位。
值應與 action_type 相同，供目前 proofread_apply.py 套用 Word 使用。

### action_type

字串。支援以下值：

- replace：替換文字
- delete：刪除文字
- comment：加入批註

### original_text

Word 原文中要定位的文字片段。

要求：

- 必須是原文中真實存在的連續文字
- 應盡量短
- 不應使用整段，除非沒有其他選擇

### suggested_text

建議替換成的文字。

- replace：必填
- delete：留空字串
- comment：可留空

### comment_text

Word 批註內容。

- comment：必填或建議填寫
- replace / delete：可留空

### category_code
字串。機器用的問題類別代碼。
範例：
punctuation
conciseness
sentence
terminology
consistency
source_check

### category_label
字串。給使用者看的問題類別名稱。
範例：
標點
語句精簡
語句
專有名詞
前後一致性
需查證

###grade
字串。機器用的嚴重程度。
建議值：
low
medium
high

###grade_label
字串。給使用者看的嚴重程度。
範例：
低
中
高

### reason
字串。說明為甚麼提出這條校對問題。

### global_consistency
布林值。是否涉及全書一致性問題。
範例：
false

### add_to_book_rules
布林值。是否建議加入書稿規則或用字表。
範例：
false

### needs_human_review
布林值。是否需要人工覆核。
範例：
true

### needs_source_check
布林值。是否需要查證資料來源或事實。
範例：
false

問題類別，例如：

- 標點
- 錯字
- 用詞
- 語句精簡
- 格式
- 專有名詞
- 需人工確認

### severity

嚴重程度：

- low
- medium
- high

### reason

給使用者看的修改原因。

### confidence

數字。AI 或規則對此建議的信心，0 到 1 之間。


然後把 `## 範例` 改成這種格式：

```md
## 範例

```json
[
  {
    "issue_id": "P1-replace-quote-colon",
    "paragraph_index": 1,
    "position_label": "引述語前",
    "original_text": "他說",
    "suggested_text": "他說：",
    "action_type": "replace",
    "action": "replace",
    "comment_text": "",
    "category_code": "punctuation",
    "category_label": "標點",
    "grade": "low",
    "grade_label": "低",
    "reason": "補上冒號，使引述語氣更清楚。",
    "global_consistency": false,
    "add_to_book_rules": false,
    "needs_human_review": false,
    "needs_source_check": false,
    "confidence": 0.95
  }
]


## AI 輸出限制

AI 必須遵守：

1. 只輸出 JSON，不要輸出解釋文字。
2. 不要輸出 Markdown。
3. 不要把整段文字當成 original_text，除非 action 是 comment 或日後明確支援 rewrite。
4. 如果無法確定應否修改，使用 comment。
5. 如果找不到明確原文片段，不要輸出 replace/delete。
6. 不要改變作者原意。
7. 不要把風格性文字改成公文腔。
8. 每段最多輸出 5 條建議，避免過度校對。