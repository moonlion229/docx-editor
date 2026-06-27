# proofreadK MVP End-to-End Test Plan

本文件用於手動測試 proofreadK MVP，範圍涵蓋從上傳 `.docx` 到輸出 Word、CSV、Excel 的完整流程。

## 測試前準備

1. 確認可啟動 Streamlit app。
2. 準備測試檔案：
   - `tests/test_data/simple.docx`
   - 一份自訂中文 `.docx`，用於測試 Gemini proofread。
3. 如需測試 Gemini：
   - 設定 `GEMINI_API_KEY`
   - 確認已安裝 `google-genai`
4. 如需測試 Excel：
   - 確認已安裝 `openpyxl`

## 1. Fake Proofread 模式

測試目的：確認本地 fake 規則能產生 replace、delete、comment，並套用到 Word。

操作步驟：
1. 啟動 Streamlit。
2. 上傳 `tests/test_data/simple.docx`。
3. 選擇 Fake proofread。
4. 檢查「校對建議表」與「逐條審核」。
5. 保持所有 valid issues 勾選。
6. 點擊產生追蹤修訂 Word。
7. 用 Microsoft Word 開啟結果檔。

預期結果：
- 頁面顯示 replace、delete、comment。
- validation errors 不包含這三條合法建議。
- Word 內可看到 replace / delete 追蹤修訂與 comment 批註。

失敗時檢查：
- `fake_ai_proofread.py`：`fake_proofread()`、`validate_edits()`
- `streamlit_app.py`：模式分支、`checked_edits`
- `proofread_apply.py`：`apply_edits_to_docx()`

## 2. Mock AI JSON 模式

測試目的：確認 mock JSON 可經 parser / validation 轉成 app 可用 issue list。

操作步驟：
1. 上傳與 `MOCK_AI_RESPONSE_TEXT` 對應的測試 `.docx`。
2. 選擇 Mock AI JSON。
3. 檢查校對建議表、逐條審核與 validation errors。

預期結果：
- 合法 mock issues 顯示在表格與逐條審核。
- 故意錯誤 issue 顯示在 validation errors。
- 錯誤 issue 不會套用到 Word。

失敗時檢查：
- `ai_issue_parser.py`：`MOCK_AI_RESPONSE_TEXT`、`parse_ai_issues_response()`
- 上傳 `.docx` 是否與 mock JSON 的 `paragraph_index` / `original_text` 對應。

## 3. Gemini Proofread 模式

測試目的：確認 Gemini 回傳內容可進入 parser / validation，且錯誤不會令 app 崩潰。

操作步驟：
1. 不設定 `GEMINI_API_KEY`，選擇 Gemini proofread。
2. 確認 app 顯示清楚錯誤。
3. 設定 `GEMINI_API_KEY` 後重啟 Streamlit。
4. 上傳一份小型 `.docx`。
5. 選擇 Gemini proofread。

預期結果：
- 沒有 `GEMINI_API_KEY` 時，app 顯示錯誤但不崩潰。
- 有 `GEMINI_API_KEY` 時，Gemini 只處理前 5 個非空段落。
- Gemini 回傳內容先進 parser / validation。
- 合法 issue 顯示在表格與逐條卡片。
- 不合法 issue 顯示在 validation errors。

失敗時檢查：
- `gemini_proofread.py`：prompt、API key、回傳文字清理
- `ai_issue_parser.py`：JSON parsing、schema validation
- `streamlit_app.py`：Gemini 模式分支

## 4. Validation Errors

測試目的：確認 validation errors 能阻止不合法 issue 套用到 Word。

操作步驟：
1. 使用 Mock AI JSON 或 Gemini 產生至少一條不合法 issue。
2. 查看 validation errors 表格。
3. 點擊產生 Word。

預期結果：
- validation errors 清楚顯示錯誤原因。
- 不合法 issue 不會出現在可勾選 valid issues 中。
- 不合法 issue 不會套用到 Word。

失敗時檢查：
- `ai_issue_parser.py`：`REQUIRED_ISSUE_FIELDS`、`parse_ai_issues_response()`
- `fake_ai_proofread.py`：`validate_edits()`

## 5. Checkbox 是否套用

測試目的：確認勾選狀態能控制哪些 issue 寫入 JSON 並套用到 Word。

操作步驟：
1. 使用 Fake proofread。
2. 取消勾選所有 issues，產生 Word。
3. 只勾選 replace，產生 Word。
4. 只勾選 delete，產生 Word。
5. 只勾選 comment，產生 Word。
6. 全部勾選，產生 Word。

預期結果：
- 不勾選任何項目時，Word 不應有修改痕跡。
- 只勾選 replace，只出現 replace 追蹤修訂。
- 只勾選 delete，只出現 delete 追蹤修訂。
- 只勾選 comment，只出現批註。
- 全部勾選時三種結果都出現。

失敗時檢查：
- `streamlit_app.py`：`apply_key`、`st.session_state`、`checked_edits`
- `json.dump(checked_edits, ...)`

## 6. CSV 下載

測試目的：確認 CSV 下載保留完整 issue 欄位。

操作步驟：
1. 產生 valid issues。
2. 點擊「下載校對建議 CSV」。
3. 用 Excel 或文字編輯器開啟 CSV。

預期結果：
CSV 欄位包含：
- `issue_id`
- `是否套用`
- `位置`
- `段落`
- `動作`
- `類別代碼`
- `類別`
- `分級`
- `原文片段`
- `建議文字`
- `批註內容`
- `原因`
- `全書一致性`
- `加入用字規則`
- `需人工覆核`
- `需查證來源`

失敗時檢查：
- `streamlit_app.py`：`display_rows`、`edited_df`、CSV download button

## 7. Excel 下載

測試目的：確認 `.xlsx` 問題清單可下載並具備基本格式。

操作步驟：
1. 產生 valid issues。
2. 點擊「下載校對建議 Excel」。
3. 用 Microsoft Excel 開啟 `proofread_issues.xlsx`。

預期結果：
- `.xlsx` 可開啟。
- 有工作表「校對建議」。
- 欄位與 CSV 一致。
- 表頭加粗。
- 首列凍結。
- 有自動篩選。
- 原文片段、建議文字、批註內容、原因欄位會換行。

失敗時檢查：
- `excel_export.py`：`build_issues_excel()`
- `streamlit_app.py`：Excel download button
- 是否已安裝 `openpyxl`

## 8. Word 追蹤修訂輸出

測試目的：確認 replace / delete 可輸出 Word 追蹤修訂。

操作步驟：
1. 使用 Fake proofread。
2. 勾選 replace / delete issue。
3. 產生並下載 Word。
4. 用 Microsoft Word 開啟。

預期結果：
- replace 顯示為追蹤修訂替換。
- delete 顯示為追蹤修訂刪除。
- 原文可被定位。

失敗時檢查：
- `proofread_apply.py`：`apply_edits_to_docx()`、`get_paragraph_ref_and_text()`
- `docx_editor/document.py`：只檢查，不修改。

## 9. Word 批註輸出

測試目的：確認 comment action 可輸出 Word 批註。

操作步驟：
1. 使用 Fake proofread 或 Mock AI JSON。
2. 只勾選 comment issue。
3. 產生並下載 Word。
4. 用 Microsoft Word 開啟。

預期結果：
- 指定文字旁出現批註。
- 批註內容等於 issue 的 `comment_text` 或 `reason`。

失敗時檢查：
- `proofread_apply.py`：comment branch、`doc.add_comment(original_text, final_comment)`
- issue 的 `original_text` 是否存在於指定段落。

## 明顯缺口與最小修正建議

1. Gemini 可能回傳 markdown code fence 或說明文字。  
   最小建議：在 `gemini_proofread.py` 對回傳文字做 JSON 清理，只抽出第一個 `[` 到最後一個 `]`。

2. Mock AI JSON 與上傳文件不一致時會大量 validation errors。  
   最小建議：文件中明確說明 mock 模式要使用對應測試 `.docx`。

3. Excel 下載依賴 `openpyxl`。  
   最小建議：在 `pyproject.toml` 或安裝說明中列明 `openpyxl`。

4. Checkbox 同時存在表格與逐條卡片時，需維持單一狀態來源。  
   最小建議：繼續以 `st.session_state[apply_key]` 作為唯一套用狀態。

## 完成判定

完成 MVP E2E 測試時，應至少確認：

- Fake / Mock / Gemini 三種模式都不崩潰。
- validation errors 能阻止不合法 issue。
- checkbox 能控制 Word 輸出。
- CSV 和 Excel 均可下載。
- Word 追蹤修訂和批註可在 Microsoft Word 中檢視。