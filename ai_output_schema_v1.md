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

### paragraph_index

數字。代表第幾段，從 1 開始。

### action

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

- comment：必填
- replace / delete：可留空

### category

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

AI 對此建議的信心，0 到 1 之間。

## 範例

[
  {
    "paragraph_index": 1,
    "action": "replace",
    "original_text": ",",
    "suggested_text": "，",
    "comment_text": "",
    "category": "標點",
    "severity": "low",
    "reason": "中文正文應使用全形逗號。",
    "confidence": 0.95
  },
  {
    "paragraph_index": 2,
    "action": "delete",
    "original_text": "在內容方面是非常",
    "suggested_text": "",
    "comment_text": "",
    "category": "語句精簡",
    "severity": "medium",
    "reason": "冗詞，可刪減，不影響原意。",
    "confidence": 0.9
  },
  {
    "paragraph_index": 3,
    "action": "comment",
    "original_text": "人物之間的關係",
    "suggested_text": "",
    "comment_text": "此句較長，建議人工確認是否需要拆句。",
    "category": "語句",
    "severity": "medium",
    "reason": "直接改寫可能改變作者語氣，建議先用批註提醒。",
    "confidence": 0.8
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