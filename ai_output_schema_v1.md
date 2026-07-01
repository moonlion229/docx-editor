# AI 校對 JSON Action 輸出規格 v1

本文件是 proofreadK 目前的 AI 輸出來源規格。AI 在「批次校對」階段必須輸出結構化 JSON issue list，讓系統可逐條審核、套用 Word 追蹤修訂，或轉成批註與 Excel 清單。

## 核心原則

1. 只輸出 JSON array，不要輸出 Markdown、說明文字或完整改寫稿。
2. 每一個 item 代表一條可審核的校對建議。
3. 優先做局部、精準、可定位的修改，不要整段覆蓋式改寫。
4. `replace` 和 `delete` 只可用於 `original_text` 逐字存在於指定段落的情況。
5. 不確定、需作者判斷、需查證、涉及語氣或專業口徑時，使用 `comment`。
6. 每段最多輸出 5 條建議，避免過度校對。
7. 批次校對預設使用省 token 模式：AI 只輸出校對員判斷必需資訊，完整原句與修改後句子優先由程式根據段落本地生成。

## JSON 結構

AI 必須輸出一個 JSON array：

```json
[
  {
    "issue_id": "P13-mixed-space-001",
    "paragraph_index": 13,
    "position_label": "第九章，段首「一位馬拉松跑者……」",
    "original_text": "6週內",
    "suggested_text": "6 週內",
    "action_type": "replace",
    "category_code": "D",
    "category_label": "數字／格式",
    "grade": "A",
    "grade_label": "可直接改",
    "reason": "中文與阿拉伯數字交界需留半形空格。",
    "global_consistency": true,
    "add_to_book_rules": true,
    "needs_human_review": false,
    "needs_source_check": false,
    "comment_text": "",
    "original_sentence": "6週內配速從每公里5分鐘提升到4分40秒",
    "suggested_sentence": "6 週內配速從每公里 5 分鐘提升到 4 分 40 秒",
    "rule_id": "MIXED_SPACE",
    "rule_description": "中英／中數混排時，中文與半形英文、阿拉伯數字、單位之間應依本書口徑留半形空格。",
    "norm_basis": "文學／實用書校對 SOP：數字與混排格式",
    "confidence_label": "高",
    "requires_human_check": false
  }
]
```

## 必填欄位

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `issue_id` | string | 每條建議的唯一 ID。建議包含段落、類型與序號。 |
| `paragraph_index` | integer | 對應 Word 段落序號，由系統提供，通常由 1 開始。 |
| `position_label` | string | 給校對員回查的位置，例如章節、小節、段首字或關鍵詞。不可虛構頁碼行號。 |
| `original_text` | string | 原文中要定位的精準文字。`replace/delete` 必須逐字存在於段落中。 |
| `suggested_text` | string | 建議文字。`delete` 可為空字串；`comment` 可留空或填處理方向。 |
| `action_type` | string | 只允許 `replace`、`delete`、`comment`。 |
| `category_code` | string | 問題大類代碼，例如 `A`、`B`、`C`。 |
| `category_label` | string | 問題大類名稱。 |
| `grade` | string | 只允許 `A`、`B`、`C`、`D`。 |
| `grade_label` | string | 只允許「可直接改」、「建議改」、「只標示」、「需人工判斷」。 |
| `reason` | string | 具體原因，不可只寫「較通順」或「比較好」。 |
| `global_consistency` | boolean | 是否涉及全書統一。 |
| `add_to_book_rules` | boolean | 是否建議加入本書附則、詞表或格式表。 |
| `needs_human_review` | boolean | 是否需要作者、責編或校對員人工判斷。 |
| `needs_source_check` | boolean | 是否需要查證來源、數據、醫療／安全或事實內容。 |

## 建議欄位

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `comment_text` | string | Word 批註文字。`comment` 類建議尤其應填寫。 |
| `original_sentence` | string | 原句或含原文的最小可讀上下文。不要用 `...` 人工省略。 |
| `suggested_sentence` | string | 修改後句子；`comment` 可填清楚的處理建議。 |
| `rule_id` | string | 規則 ID，例如 `PUNC_FULLWIDTH`、`MIXED_SPACE`、`TERM_CONSISTENCY`。 |
| `rule_description` | string | 規則或判斷依據。 |
| `norm_basis` | string | 依據來源，例如「已確認本書附則」、「文學類校對 SOP」。 |
| `confidence_label` | string | 「高」、「中」、「低」。 |
| `requires_human_check` | boolean | 舊欄位相容用；通常與 `needs_human_review` 一致。 |

## 省 token 輸出模式

批次校對時，AI 應優先輸出精簡 issue。以下欄位足夠讓 proofreadK 驗證、顯示修改方式，並輸出 Word 追蹤修訂：

```json
{
  "issue_id": "P13-term-001",
  "paragraph_index": 13,
  "position_label": "段落 13",
  "original_text": "自由神經系統",
  "suggested_text": "自主神經系統",
  "action_type": "replace",
  "category_code": "B",
  "category_label": "術語／全書統一",
  "grade": "A",
  "grade_label": "可直接改",
  "reason": "醫學術語應為「自主神經系統」。",
  "global_consistency": true,
  "add_to_book_rules": true,
  "needs_human_review": false,
  "needs_source_check": true
}
```

省 token 模式下：

- 不要輸出完整段落。
- 不要重複輸出 `original_sentence` 和 `suggested_sentence`，除非原句邊界很難由程式判斷。
- 不要輸出冗長 `rule_description` 或 `norm_basis`，除非原因不足以讓校對員判斷。
- `reason` 必須保留校對員判斷所需的具體資訊，可寫 1-2 句；不要只寫規範名稱，也不要重複冗長規範描述。
- `comment` 類 issue 必須用 `comment_text` 寫清楚處理方式。

## action_type 使用規則

### replace

用於精準替換文字。

適用情況：

- 明確錯字或字形錯誤。
- 明確標點錯誤。
- 中英／中數混排空格。
- 已確認的全書統一口徑。

限制：

- `original_text` 必須逐字存在於該段落。
- 不可替換整段。
- 若替代詞未確認，改用 `comment`。

### delete

用於刪除明確多餘文字。

適用情況：

- 重複字詞。
- 明確殘留標記。
- 已確認不應出現的多餘符號。

限制：

- `original_text` 必須逐字存在於該段落。
- 若刪除會影響語氣、意思或節奏，改用 `comment`。

### comment

用於只標示，不直接改文。

適用情況：

- 專名、術語、器材名、地域詞需統一。
- 涉及作者聲線、人物口吻、章題風格、比喻、詩行節奏。
- 涉及醫療、安全、訓練效果、來源或事實查證。
- 相片標記、圖說、附件、設計稿、排版稿待確認。
- `original_text` 無法安全定位。

## 分級規則

| grade | grade_label | 動作政策 | 例子 |
| --- | --- | --- | --- |
| `A` | 可直接改 | 可用 `replace/delete`。 | `6週` 改為 `6 週`；半形 `?` 改全形 `？`。 |
| `B` | 建議改 | 可用精準 `replace`，但不確定時用 `comment`。 | `八字型` 建議改 `八字形`；同一英文術語大小寫不一致。 |
| `C` | 只標示 | 使用 `comment`，不直接改文。 | 效果語句、作者比喻、章題風格。 |
| `D` | 需人工判斷 | 必須使用 `comment`。 | `骨盆／盆骨`、`拉力帶／橡筋帶`、`alignment` 譯法。 |

## 問題類別建議

| category_code | category_label | 說明 |
| --- | --- | --- |
| `A` | 錯字／字形 | 明確錯字、繁簡混入、同音誤字。 |
| `B` | 術語／全書統一 | 專名、術語、器材名、動作名稱、地域詞。 |
| `C` | 標點／符號 | 全半形、問號、冒號、句號後空格、引號。 |
| `D` | 數字／格式 | 中英混排、中數混排、單位、組數、配速、時間。 |
| `E` | 分區文本／製作標記 | 相片標記、圖說、章題、小標、附件、設計稿提示。 |
| `F` | 來源／安全風險 | 醫療、安全、訓練效果、數據、來源待查。 |
| `G` | 灰區／作者聲線 | 比喻、口吻、敘事節奏、地域語感、章題風格。 |

## 文學／實用書特殊規則

1. Word 流稿無穩定版面時，不可虛構頁碼或行號。
2. 相片位置如 `attachment: ch10-02` 應列入分區文本或相片位置檢查，不當正文錯字處理。
3. 已知錯字但替代詞未定時，使用 `comment`。例如 `盤骨` 已知有問題，但 `骨盆／盆骨` 未定，須人工判斷。
4. 本書術語候選應以 `global_consistency=true` 標示，並用 `add_to_book_rules=true` 推入本書附則或詞表。
5. 醫療、安全、訓練效果和來源內容只標示風險，不由 AI 查證或改寫，除非使用者明確提供來源與口徑。
6. 作者風格、幽默比喻、章題語氣、人物口吻不作硬改。

## 可直接改例子

```json
{
  "issue_id": "P1-punc-question-001",
  "paragraph_index": 1,
  "position_label": "第十一章章題",
  "original_text": "已經很努力，為什麼仍跑得不夠快?",
  "suggested_text": "已經很努力，為什麼仍跑得不夠快？",
  "action_type": "replace",
  "category_code": "C",
  "category_label": "標點／符號",
  "grade": "A",
  "grade_label": "可直接改",
  "reason": "中文章題應使用全形問號。",
  "global_consistency": true,
  "add_to_book_rules": true,
  "needs_human_review": false,
  "needs_source_check": false
}
```

## 只標示例子

```json
{
  "issue_id": "P34-term-pelvis-001",
  "paragraph_index": 34,
  "position_label": "第十二章，器材設置",
  "original_text": "固定於跑者盆骨",
  "suggested_text": "",
  "action_type": "comment",
  "category_code": "B",
  "category_label": "術語／全書統一",
  "grade": "D",
  "grade_label": "需人工判斷",
  "reason": "本書仍需確認「骨盆／盆骨」主用詞；不可由 AI 直接定稿。",
  "global_consistency": true,
  "add_to_book_rules": true,
  "needs_human_review": true,
  "needs_source_check": false,
  "comment_text": "請作者或責編確認本書主用詞為「骨盆」還是「盆骨」。"
}
```
