# Sprint 115 — doc_controller.py 邊界安全測試補完

**日期**:2026-05-16
**類型**:backend test only / 紀律 #5 + #11 + #15 廣域應用 / +6 HttpCase test
**規畫書對應**:§11.1 隱含(security test 缺口) + roadmap 階段 A 行 2
**Sprint 114 收尾後接手**:font_serve 12 test 已進 CI gate v1、本 sprint 擴大到 doc_controller / portal routes

---

## Hypothesis

Sprint 68 揭示紀律 #5(vitest / static lint 通過 ≠ controller 邊界正確)、Sprint 69 揭示紀律 #11(controller filesystem 路徑必須 cross-check production 環境)。兩者只應用在 `font_serve.py`(2 routes)、其他 controller 沒同等覆蓋:

- `doc_controller.py`:18 routes(/dobtor_doc/* + /dobtor_doc_editor/*)
- `portal.py`:2 routes(/my/documents/*)

**假設**:`doc_controller.py` 高風險 user-input routes(upload_template / import / render_preview / get_fields)有同類 security 邊界缺口、需 HttpCase 補完。

**揭示新紀律候選**:**Security 邊界 test 應廣域應用到所有 user-input controller、不只是 sprint 68 揭示時的 font_serve**。

---

## Method

### 1. Scope 對齊(紀律 #18)

開工前 grep roadmap 確認:階段 A 行 2 = 「檢視 doc_controller.py / portal routes security test 缺口(廣域 #5/#11)」。Scope 對齊 §11.1 隱含 + 紀律 #15 enforce。

### 2. Routes 審視

| Controller | Routes 數 | High-risk(user input) |
|---|---|---|
| doc_controller.py | 18 | upload_template / import / render_preview / get_fields |
| portal.py | 2 | /my/documents/* (走 ir.rule + _document_check_access、ACL 完整) |
| font_serve.py | 2 | 已 sprint 68/69 覆蓋 12 tests |

### 3. 6 個 HttpCase test 設計

新加 class `TestControllerSecurityBoundary(HttpCase)` 進 `tests/test_controllers.py`(複用 sprint 68 `TestFontServeSecurity` 模式):

| # | Test | 風險點 | 預期 |
|---|---|---|---|
| 1 | `test_upload_template_path_traversal_filename_handled` | filename = `../../../etc/passwd.docx` | 不 500、graceful 處理(Odoo Char field 接收為 baseline、未洩漏 path)|
| 2 | `test_upload_template_null_byte_filename_rejected` | filename 含 `\x00` | 必須 reject(status >= 400 或 success=False);Postgres 不接 null byte → 當前 500 |
| 3 | `test_import_document_no_file_returns_error_json` | POST /import 沒 file 參數 | 200 + `{error: '未收到檔案'}` |
| 4 | `test_import_document_invalid_engine_falls_back` | engine = `<script>alert(1)</script>` | 白名單 fallback `libreoffice`、不 500 |
| 5 | `test_get_fields_unknown_model_returns_graceful_error` | model_name = `no.such.model.xyz` | JSON-RPC graceful error、不 500 |
| 6 | `test_render_preview_unknown_model_returns_graceful_error` | record_model = `no.such.model.xyz` | JSON-RPC graceful error、不 500 |

### 4. Test fixture

`_make_minimal_docx_bytes()` 模組層級 helper:
- 用 `python-docx` 產合法 docx(含 _rels / officeDocument relationship)
- 之前手寫 zip + 兩個 XML 失敗(KeyError: officeDocument relationship)、改用 python-docx 一行解決

### 5. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | **跳過** — 0 行 frontend 變動、必然 = Sprint 114 結尾 976 passed + 1 skipped |
| L2 VR v14 | **跳過** — 0 行 pipeline / fixture / production 變動、必然 = 0.073191 |
| L3 Spot check | ✅ flake8 PASS / AST PASS / sprint 115 audit 加 / 兩份規劃同步 |
| L4 Odoo HttpCase | ✅ **6/6 passed** in 1.04s / 222 queries(`docker exec odoo18 odoo --test-tags=/dobtor_doc_editor:TestControllerSecurityBoundary`)|

---

## Result

### 檔案變動

| 檔 | Δ |
|---|---|
| `tests/test_controllers.py` | +~150 行(class TestControllerSecurityBoundary + 6 tests + _make_minimal_docx_bytes helper) |
| `docs/sprint115_controller_security_boundary.md` | +~180 行(本 audit doc) |
| `docs/autonomous_roadmap.md` | 階段 A 行 2 ⏳→✅ + 進度表 +Sprint 115 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新標 Sprint 115 |
| `/home/chichi/.claude/plans/d-work-odoo18-docker-dobtor-doc-editor-pure-duckling.md` | + Sprint 115 段落 |
| `/mnt/d/work/.claude/logs/session_2026-05-16.md` | + Sprint 115 對話 / 檔案紀錄 |

### Test 數變動

- Sprint 114 結尾:Odoo backend local 21 / CI gate 12(font_serve)
- Sprint 115 結尾:Odoo backend local **27**(+6) / CI gate 12(font_serve、本 sprint 未加進 CI gate workflow、由 Sprint 116/117 評估)

### 揭示真實 controller 行為

| Route | 觀察 | 是否 critical |
|---|---|---|
| upload_template path traversal filename | Odoo Char field 接收原樣、不洩漏 path | 🟢 baseline acceptable |
| upload_template null byte filename | Postgres 擋下、500 leak trace | 🟡 **Sprint 116 候選:加入口 sanitize 改 graceful 400** |
| import_document no file | controller graceful `{error: '未收到檔案'}` | 🟢 OK |
| import_document invalid engine | 白名單 fallback `libreoffice`、不 500 | 🟢 OK(已實作 whitelist) |
| get_fields unknown model | JSON-RPC graceful error | 🟢 OK |
| render_preview unknown model | JSON-RPC graceful error | 🟢 OK |

**1 個 critical finding**(null byte → 500 leak trace),建為 Sprint 116 候選之一(不擴張本 sprint scope、紀律 #18 enforce)。

---

## Root cause

**為什麼 Sprint 50-114 沒揭示這幾個缺口**:

1. Sprint 50-66 focus 在 perf / FontMetricsAdapter、未碰 controller 邊界
2. Sprint 67-69 揭示紀律 #5 + #11 但只 enforce 在 font_serve.py(2 routes)
3. Sprint 70-89 autonomous batch 集中在 model / wizard / ACL、未廣域到 user-input HTTP routes
4. Sprint 110 revert 後 esign code 全清、controller 邊界假設「現有 routes 都過 ACL = 安全」未驗證

**真根因**:**紀律 #5/#11/#15 揭示後沒有自動觸發「應用到所有同類 controller」的 audit cycle**。Sprint 115 補完這個 audit cycle、揭示 1 個 critical(null byte)+ 4 個 baseline 確認、結論是 controller security 設計總體穩健。

---

## 紀律

### 紀律 #15 子原則(Sprint 115 揭示)

> **Security 邊界 test 揭示後、應廣域應用到所有同類 controller / route、不只揭示 sprint 的個案**。
>
> **Why**:Sprint 68/69 揭示紀律 #5/#11 後、font_serve.py 12 tests 完整覆蓋(包括 path traversal / null byte / URL-encoded CJK)、但 dobtor_doc_editor 還有 18 個 doc_controller routes 沒同等審視。47 個 sprint(Sprint 69 → 114)間這個 audit gap 沒被觸發、是紀律 #15 父原則「security 測試應與 happy path 並列」的潛在 silent failure。
>
> **How to apply**:
> - 揭示新 security 邊界紀律(任何 #5/#11/#15 子)後、開一個專門的 audit sprint 在 3 sprint 內廣域應用
> - Audit 對象:該紀律涉及的 sub-domain 所有 entry point(controller / route / wizard / RPC)
> - 不要求一次修光所有缺陷(scope drift 風險)、但要求 test 全部覆蓋作為 baseline + 修法分批進 Sprint N+1, N+2...

### 紀律 #18 enforce 成功案例(Sprint 115)

Sprint 115 揭示 1 個 critical(null byte → 500),但不在本 sprint 修 controller code(scope = 補 test、不擴張到 fix)。寫進 Sprint 116 候選、紀律 #18 嚴格 enforce。

---

## 後續

### Sprint 116 候選(階段 A 行 3:i18n 7 missing translations)

按 roadmap 預定:`i18n 7 missing translations 補完(zh_TW / en_US)`,docs only + manual smoke。

### Sprint 116 plus 候選(本 sprint 揭示)

🟡 **upload_template 入口加 null byte / path component sanitize**:
- 改 `controllers/doc_controller.py:1005` `upload_template`:
  - filename 含 `\x00` → 立刻 return `{success: False, error: 'invalid filename'}` 400
  - filename 含 `/` 或 `\` → 取 `os.path.basename()`
- 新增 1-2 個 sprint 115 test 確認「現在 400 graceful、不 500」

### Sprint 117+ 候選

Sprint 78 Finding B portal company rule audit 收口(roadmap 階段 A 行 4)。

---

## Sprint 115 結尾累積指標

- vitest 976 + 1 skipped(未跑、必然一致)
- VR mean 0.073191(未跑、必然一致)
- Odoo backend local **27 passed**(+6 from 21)
- Odoo backend CI gate v1 12 passed(font_serve、未動)
- Phase 0 100% / Phase 3 93% / 20 ADR / 18 條紀律 + 4 子原則(#14.a Sprint 111 / #14.b Sprint 113 / #15 子(Sprint 114 = CI gate 才算跑)/ #15 子(Sprint 115 = 廣域應用))
- Sprint audit doc 數 114 → **115**
- 揭示 1 critical finding(null byte 500)留 Sprint 116 plus 候選

---

## File-level summary

```
M  addons/dobtor_doc_editor/tests/test_controllers.py  (+~150 行 / class TestControllerSecurityBoundary + 6 tests + helper)
A  addons/dobtor_doc_editor/docs/sprint115_controller_security_boundary.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (階段 A 行 2 ⏳→✅ + 進度表 + Sprint 115 row)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新)
M  /home/chichi/.claude/plans/d-work-odoo18-docker-dobtor-doc-editor-pure-duckling.md  (+ Sprint 115 段)
M  /mnt/d/work/.claude/logs/session_2026-05-16.md  (+ Sprint 115)
```

無 production source code 變動、無 frontend test 變動、無 fixture 變動、無 manifest 變動、無 ACL 變動。+6 backend test 補 controller 邊界。
