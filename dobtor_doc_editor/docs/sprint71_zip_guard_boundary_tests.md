# Sprint 71：doc_zip_guard.py 邊界 audit + 補測缺口

**性質**：code change（test coverage 補完）
**日期**：2026-05-16
**前置**：Sprint 70 揭示「audit 既有 controller」應用模式，Sprint 71 走 zip_guard

---

## 0. 一句話定位

Sprint 70 揭示 audit pattern；Sprint 71 走 `models/doc_zip_guard.py`（Sprint 20 W9-10 落地的 zip bomb 防護）。**設計乾淨無紀律 #11 適用點**（無 filesystem 互動、無 extractall、無 zip slip），但 audit 既有 test_zip_guard.py 6 個 test 發現 3 個缺口、本 sprint 補。

---

## 1. Audit Findings

### 1.1 設計層面（無問題）

- 用 `zipfile.ZipFile(io.BytesIO(raw_bytes))` 純 in-memory、不寫 disk、無 tempfile
- 無 `extractall()` 呼叫 → zip slip 不適用
- 3 道閘門：input size (50MB) / total uncompressed (200MB) / entry count (1000) — 合理
- 單檔壓縮比 check：`ratio > 100x AND file_size > 1MB` — 防單檔 bomb
- `UserError` 是 Odoo 標準 graceful exception

### 1.2 既有 test 6 個（W9-10 落地）

| Test | Cover |
|---|---|
| `test_small_valid_zip_passes` | 正常 zip pass |
| `test_oversized_input_rejected` | 50MB+ 擋 |
| `test_too_many_entries_rejected` | 1001 entries 擋 |
| `test_total_uncompressed_overflow_rejected` | 200MB+ 擋 |
| `test_malformed_zip_rejected` | 非 zip 擋 |
| `test_safe_open_returns_zipfile` | integration |

### 1.3 Sprint 71 揭示的缺口

| # | 缺口 | 風險 |
|---|---|---|
| 1 | 單檔壓縮比 bomb（doc_zip_guard.py line 115-121）無覆蓋 | 單檔 bomb 路徑可能 silent regress |
| 2 | <1MB 高壓縮率小檔誤判（line 117 file_size > 1MB threshold）無覆蓋 | 正常 docx 小 XML 高壓縮可能誤擋 |
| 3 | 預設常數一致性（50MB/200MB/1000）無 sanity check | docstring drift 風險 |

---

## 2. Method

加 3 個 test 到既有 `TestZipGuard` class：

| 新增 test | 對應缺口 |
|---|---|
| `test_single_file_high_ratio_bomb_detected` | 缺口 1 — 2MB 全 X 寫入 ZIP_DEFLATED 高壓縮、驗證觸發 ratio bomb 偵測 |
| `test_small_high_ratio_file_not_flagged` | 缺口 2 — 500KB 全 X 高壓縮、驗證不誤判（< 1MB threshold） |
| `test_default_constants_match_docstring_claims` | 缺口 3 — assert 三個預設常數 = docstring 宣告值 |

同步加 `'zip_guard'` tag 到 `TestZipGuard` class（讓 `--test-tags=zip_guard` 能 target）。

---

## 3. Result（三層 SOP）

### 3.1 第一次跑（tag 缺失）

```
WARNING odoo18_dev odoo.tests.result: 0 failed, 0 error(s) of 0 tests
```

Class tag 是 `'post_install', '-at_install', 'dobtor_doc_editor'`、無 `zip_guard` tag → `--test-tags=zip_guard` 抓不到。

### 3.2 加 tag 後重跑

```
INFO odoo18_dev odoo.tests.result: 0 failed, 0 error(s) of 9 tests
```

**9 個 tests 全綠**（6 既有 + 3 Sprint 71 補測缺口）：
- `test_single_file_high_ratio_bomb_detected` ✓（2MB 全 X 觸發 ratio bomb 偵測）
- `test_small_high_ratio_file_not_flagged` ✓（500KB 小檔不誤判）
- `test_default_constants_match_docstring_claims` ✓（常數一致）

### 3.3 三層 SOP 對齊

| 層 | 結果 |
|---|---|
| L1 Vitest | 不跑（純 Python test 變動） |
| L2 VR | 0.073191 不變 |
| L3 Python flake8 + AST | ✓ |
| L4 Odoo HttpCase / TransactionCase | **9 passed** ✓ |

---

## 4. 紀律與啟示

### 4.1 紀律 #11 不適用 — 設計層面的「無 filesystem 互動」是好設計

`doc_zip_guard.py` 全程用 `io.BytesIO` in-memory、沒有 `tempfile` / `extractall` / `os.path` 互動。**紀律 #11 對它不適用 — 因為設計上 sidestep 了 filesystem**。

→ 揭示：**有些 controller / model 之所以「lint clean」是因為設計上避開了 filesystem**。紀律 #11 應用優先級 = filesystem-heavy controller > in-memory model。

### 4.2 既有 test 缺口分布

Sprint 20 W9-10 寫的 test 涵蓋 **3 道閘門的「擋下」路徑**、但漏了：
- 單檔 bomb 的「擋下」路徑（line 115-121 的特殊邏輯）
- 邊界 threshold（< 1MB 不誤判）
- 常數一致性 sanity check

→ **W9-10 era 的 test 補完是「最小可行 coverage」、不是「邊界完整 coverage」**。Sprint 71 是 catch-up to W9-10 era 的紀律 #10 應用（catch-up 應補到當前紀律標準）。

### 4.3 Test tag 是 contract — 缺 tag 等於 silent skip

Sprint 71 first run `0 of 0 tests` 揭示：**沒 tag 的 test 不會被選跑、與沒寫 test 結果相同**。

→ 新紀律候選（第 12 條）：每個 test class 必須 explicit tag 對應到 `--test-tags` query、否則 CI 跑不到等同 dead test。

---

## 5. 後續 sprint 候選

- Sprint 72：CI 加 `--test-tags font_serve,zip_guard` job
- Sprint 73：docs/glossary.md
- 紀律 #12 對其他 test class 套用 — grep 所有 `@tagged` 看是否有 untagged-by-purpose

---

## 6. 一句話結論

**Sprint 71 補完 zip_guard 既有 test 的 3 個邊界缺口**：9 個 tests 全綠、揭示「無 filesystem 互動是好設計」+ 新紀律 #12 候選「test class 必須 explicit tag」。Sprint 50-71 累積 21 sprints。
