# Sprint 76：models/ + wizards/ filesystem audit（紀律 #11 廣域應用）

**性質**：純診斷 sprint
**日期**：2026-05-16

## 0. 一句話

Sprint 70 audit controllers/、Sprint 71 audit doc_zip_guard.py、Sprint 76 audit `models/doc_document.py` + `wizards/`。**全部 audit clean、無新 dead code blocker**。

## 1. Findings

### 1.1 `models/doc_document.py:638` `_generate_docx_via_libreoffice` ✓ GOOD

```python
if not shutil.which('soffice'):
    return self._generate_docx_via_python(record)  # graceful fallback
```

- ✓ `shutil.which` check 在最前
- ✓ Fallback 到 `_generate_docx_via_python`（python-docx-based）
- ✓ `tempfile.TemporaryDirectory()` 自動清理
- ✓ `subprocess.run(capture_output=True, timeout=60)` 沒 `check=True`、手動 check returncode 後 raise `UserError`
- ✓ Output file 找不到 → 嘗試其他副檔名 → 最終 raise `UserError` 結構化

→ 設計上紀律 #11 已被內化。Production container 內無 soffice → 走 fallback、user 看不到差異。

### 1.2 `models/doc_document.py` 其他 filesystem 互動 ✓ SAFE

- `zipfile.ZipFile(io.BytesIO(...))` × 3（line 148, 211, 212）— in-memory、無 filesystem
- 無 `extractall` / 無 `os.path.exists` 對 user input

### 1.3 `wizards/` ✓ NO FILESYSTEM INTERACTIONS

`doc_bulk_import_wizard.py` + `doc_field_picker.py` 共 200 行、grep `os.path|open\(|tempfile|shutil|subprocess|extractall` **無結果**。設計上 sidestep 了 filesystem。

## 2. 紀律啟示

### 2.1 紀律 #11 應用優先級排序

| 優先級 | 範圍 | Sprint 70-76 audit 結果 |
|---|---|---|
| 高 | controllers（HTTP 入口、user-facing）| Sprint 70 揭示 1 個 broken（已修）|
| 中 | models filesystem-heavy | Sprint 76 audit 全 graceful、無問題 |
| 低 | models in-memory | Sprint 71 zip_guard sidestep 了 filesystem |
| 0 | wizards | Sprint 76 grep clean、無 filesystem |

→ **dobtor_doc_editor 整體紀律 #11 暴露面 ≈ 5 處、4 處已內化 graceful fallback、1 處 Sprint 70 補完**。Sprint 76 揭示「紀律 #11 廣域應用」收口。

### 2.2 純診斷 sprint 的價值

Sprint 76 **0 code 變動、0 新 audit doc finding**、看起來無產出。但實際上：

- 確認 Sprint 70-71 收口（紀律 #11 暴露面已掃完）
- 證明 `wizards/` 設計上 sidestep filesystem（紀律 #11 例外）
- 避免未來 sprint 重複 audit 相同範圍

→ 「沒發現問題的 audit」也是 audit。紀律 #3 應用：probe 不是只為了找問題、也為了 confirm scope 已盡。

## 3. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | 不跑 |
| L2 VR | 0.073191 不變 |
| L3 Python lint | 0 變動、AST OK |
| L4 grep audit | controllers / models / wizards 全部 clean |

## 4. 後續 sprint 候選

- Sprint 77：i18n strings audit（`_("...")` 是否一致 + `i18n/` 目錄完整性）
- Sprint 78：`security/ir.model.access.csv` ACL audit（紀律 #11 應用到 ACL 層）
- Sprint 79：Makefile 加 `make test-backend` target 整合 Sprint 72 script

## 5. 一句話結論

**Sprint 76 確認紀律 #11 暴露面已掃完**（5 處 filesystem 互動：1 修、4 graceful）、純診斷 sprint 0 finding 等同「scope 已盡」確認、避免未來重複 audit。
