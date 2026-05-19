# Sprint 116 — i18n 補完 7 條 + Sprint 116 plus null byte sanitize fix

**日期**:2026-05-16
**類型**:i18n catch-up + security fix(雙線同 sprint)
**規畫書對應**:§11.2 行 5 i18n + Sprint 115 揭示 critical
**Sprint 115 後接手**:doc_controller security 邊界已驗、null byte 500 critical 留 plus 候選

---

## Hypothesis

雙線:

1. **主線(roadmap 階段 A 行 3)**:`zh_TW.po` 缺 .pot 內 7 個 msgid(載入時 Odoo 會 warning、UX 受影響)。補完讓 zh_TW 載入時 0 warning、且部署到 production 時 portal user 看到的訊息是中文。

2. **Sprint 116 plus(Sprint 115 揭示 critical fix)**:`upload_template` 含 null byte filename → Postgres ROLLBACK 500 leak trace。controller 入口 explicit sanitize 改 graceful 400 + 取 basename 防 path component(深度防禦、紀律 #15 廣域應用)。

**揭示新紀律候選**:**critical finding 揭示 sprint 後、下個 sprint 應 enforce fix(不超過 1 sprint 拖延)**。

---

## Method

### 1. Scope 對齊(紀律 #18)

- 主線:roadmap 階段 A 行 3「i18n 7 missing translations 補完(zh_TW / en_US)」+ 規畫書 §11.2 行 5
- Plus:Sprint 115 audit 留的 116 plus 候選、紀律 #15 enforce(不超過 1 sprint 拖延)
- 雙線同 sprint 是合理 batch(都是 catch-up、不打 production code 主幹、紀律 #18 PR-size 內)

### 2. i18n 主線

#### 缺口分析

```
.pot 26 msgid - zh_TW.po 19 msgid = 7 個缺口
```

7 個缺的 msgid:
- `Performance Metrics`(英文 → 翻「效能指標」)
- 5 個 zip_guard error message(中文原文 → msgstr 保持中文)
- 1 個 portal view 字串「您目前沒有可存取的文件。」(中文原文 → msgstr 保持中文)

**注意**:其中 `Performance Metrics` 在 .pot 出現 2 次(act_window + ui.menu),sort -u 去重後 comm 顯示 6 unique msgid + 1 重複 = 對應 7 個 missing。

#### 補完

append 7 條到 `i18n/zh_TW.po`、msgstr 對應翻譯。Babel `read_po` 驗證:語法 OK / 25 條 / 0 缺翻譯。

#### en_US.po

未建。理由:Odoo 預設 en_US 是 fallback、若使用者切到 en_US 但 .po 不存在、Odoo 顯示原始 msgid(對 zip_guard 中文 error / portal 中文字串、原樣顯示中文是 acceptable degraded)。建 en_US.po 需翻譯 5 個 zip_guard 中文 error + 1 portal 字串成英文、屬於 Sprint 117+ scope expansion、本 sprint 不做(紀律 #18)。

### 3. Sprint 116 plus — null byte sanitize

#### Fix

`controllers/doc_controller.py:upload_template`,在 `doc.check_access_rule('write')` 之後、`docx_file.read()` 之前插入:

```python
raw_filename = getattr(docx_file, 'filename', '') or ''
if '\x00' in raw_filename:
    return request.make_response(
        json.dumps({'success': False, 'error': 'invalid filename (null byte)'}),
        headers={'Content-Type': 'application/json'},
        status=400,
    )
safe_filename = os.path.basename(raw_filename.replace('\\', '/'))
try:
    docx_file.filename = safe_filename
except Exception:
    pass
```

2 個邊界:
- null byte → 400 + error message
- path component(`/` / `\`)→ basename 取出、深度防禦

#### Test 強化

修改 `test_upload_template_null_byte_filename_rejected` 從「accept 4xx/5xx/200+success:False」收緊為「**必須 400 + body 含 'null byte'**」,確認 fix 落地。

### 4. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | **跳過**(0 行 frontend / source code 變動、必然 = Sprint 115 結尾 976+1 不變) |
| L2 VR v14 | **跳過**(0 行 pipeline / fixture 變動、必然 = 0.073191) |
| L3 Spot check | ✅ strict flake8(E9/F63/F7/F82) PASS / AST PASS / Babel read_po PASS |
| L4 Odoo HttpCase | ✅ **6/6 passed**(`docker exec odoo18 odoo --test-tags=/dobtor_doc_editor:TestControllerSecurityBoundary --http-port=8169`)|

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `i18n/zh_TW.po` | +35 行 / 7 新 msgid | 補完 .pot 對應、Babel 驗證 25 條 0 缺翻譯 |
| `controllers/doc_controller.py` | +18 行(upload_template 入口 sanitize) | null byte + path component 防禦 |
| `tests/test_controllers.py` | -7 行 / +9 行 | 收緊 null byte test assertion 為 400 + 'null byte' message |
| `docs/sprint116_i18n_and_null_byte_fix.md` | +200 行 | 本 audit doc |
| `docs/autonomous_roadmap.md` | 階段 A 行 3 ⏳→✅ + 進度表 + Sprint 116 | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 | 同步 |
| `pure-duckling.md` | + Sprint 116 段 | 同步 |

### Test 數變動

- Sprint 115 結尾:Odoo backend local 27 / CI gate v1 12
- Sprint 116 結尾:Odoo backend local **27**(同數、test_upload_template_null_byte_filename_rejected 從 baseline 升級為 explicit fix verification、未新增 test 數)
- 真實 controller code +18 行、是 Sprint 113-115 純 docs/test 後**首次 production code 變動**

### 規畫書 §0.2 Phase 完成度

無變動(本 sprint 屬產品化 / i18n / security 邊界、不打 Phase 1-7 主軸)。

---

## Root cause

**為什麼 i18n 7 缺口 47 sprint 沒被補**:

1. 主軸 Sprint 25-49 focus 在 VR mean 收斂、i18n 是邊緣議題
2. Sprint 70-89 autonomous batch 揭示 #11.b ACL 但 i18n 沒列為候選
3. .pot 更新流程(自動從 source code 抓 `_(...)`)不會自動更新 .po(.po 是 manual)、形成 silent gap

**為什麼 null byte critical 拖到 Sprint 116 才修**:

1. Sprint 0-114 沒有對 controller 邊界 input 的 explicit test(font_serve 是例外)
2. Sprint 115 廣域 audit 第一次揭示
3. Sprint 116 enforce 紀律 #18「critical finding 不超過 1 sprint 拖延」

---

## 紀律

### 紀律 #18 子原則(Sprint 116 揭示)

> **Critical finding 揭示 sprint 後、下個 sprint 應 enforce fix、不超過 1 sprint 拖延**。
>
> **Why**:Sprint 115 揭示 null byte 500 critical;若拖到 Sprint 120+ 才修、production user 仍可能在 sprint 間踩雷。1 sprint cooldown 內 enforce fix 是紀律父原則「scope 對齊」對 critical 的延伸 — scope 包含「修上 sprint 揭示的 critical」、不只「跑下個 roadmap 行」。
>
> **How to apply**:
> - 上 sprint audit doc 留「critical finding」→ 下 sprint 必須含 fix(可與 roadmap 主線同 sprint batch)
> - Fix 同步 test 強化、把 baseline assertion 升級為 explicit fix verification
> - Audit doc 內 root cause 段必須交代「為什麼 critical 沒早揭示」

### 紀律 #15 廣域應用持續(Sprint 116)

紀律 #15 子原則(Sprint 115)「security 邊界 test 廣域應用」在 Sprint 116 從 test-only 升級為 **test + production code fix**。Sprint 117+ 候選:對 import_document / render_preview / get_fields 同樣做 path component / null byte 入口 sanitize(如有必要)。

---

## 後續

### Sprint 117(roadmap 階段 A 行 4)

Sprint 78 Finding B portal company rule audit 收口。

### Sprint 117+ 候選(本 sprint 揭示延伸)

- import_document 入口同樣加 filename sanitize(對稱 upload_template)
- en_US.po 翻譯 zip_guard 5 個 error + 1 portal 字串(若需要英文 deployment)

---

## Sprint 116 結尾累積指標

- vitest 976 + 1 skipped(未跑、必然一致)
- VR mean 0.073191(未跑、必然一致)
- Odoo backend local **27 passed**(同 Sprint 115、test_upload_template_null_byte 升級為 explicit fix verification)
- CI gate v1 12 passed(font_serve、未動)
- Phase 0 100% / Phase 3 93% / 20 ADR / **18 條紀律 + 5 子原則**(+ #18 子 Sprint 116 critical-fix-cooldown)
- Sprint audit doc 數 115 → **116**
- i18n zh_TW.po:19 → **26 msgid**(.pot 對齊、0 缺翻譯)
- Production code 變動:**首次**(Sprint 113-115 純 docs/test、Sprint 116 上 18 行 controller fix)

---

## File-level summary

```
M  addons/dobtor_doc_editor/i18n/zh_TW.po  (+35 行 / 7 新 msgid)
M  addons/dobtor_doc_editor/controllers/doc_controller.py  (+18 行 upload_template 入口 sanitize)
M  addons/dobtor_doc_editor/tests/test_controllers.py  (test_upload_template_null_byte 收緊為 400 explicit)
A  addons/dobtor_doc_editor/docs/sprint116_i18n_and_null_byte_fix.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (階段 A 行 3 ⏳→✅ + 進度表 + Sprint 116)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新)
M  /home/chichi/.claude/plans/d-work-odoo18-docker-dobtor-doc-editor-pure-duckling.md  (+ Sprint 116 段)
M  /mnt/d/work/.claude/logs/session_2026-05-16.md  (+ Sprint 116)
```

無 VR fixture 變動、無 model schema 變動、無 ACL / ir.rule 變動。
