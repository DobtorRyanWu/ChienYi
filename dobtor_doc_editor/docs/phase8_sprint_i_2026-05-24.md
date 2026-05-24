# Phase 8 Sprint I — Manifest Assets Hygiene Test（2026-05-24）

**性質**：防禦性硬化（preventative hardening），消除 Sprint G/H 漏加 manifest 那類 bug 的整個類別。
**範圍**：新增 [manifest_assets_hygiene.test.ts](../tests/unit/manifest_assets_hygiene.test.ts)。

---

## 1. 為什麼要做這個

Sprint G 與 Sprint H 都把新 JS 檔（`jinja2_scanner.js`）寫進 `static/src/components/doc_editor/` 但**漏加** `__manifest__.py` 的 `assets` 區段，結果：
- vitest 全綠（unit test 直接 import 檔案）
- `node --check` 全綠（純語法）
- `xmllint --noout` 全綠（XML 結構）
- 模組升級 Registry loaded 全綠（Python 不依賴 asset）
- **但**：瀏覽器載入時 doc_editor.js 從 `./jinja2_scanner` import → 拿不到 → 整個 OWL component crash

這個 bug 類**完全靜默**，必須親自打開 doc editor 才會發現。直到我把 Docker Desktop 啟動、curl `/web/assets/debug/web.assets_backend.js` 才察覺（`56e6a51` commit 修補）。

下次任何 sprint 新增 component js 都可能再犯。Sprint I 把這條檢查自動化進 vitest，**從此 missed-manifest 會在 CI / pre-commit / 本地測試立刻紅燈**。

---

## 2. 程式碼變動

### 2.1 新增 [tests/unit/manifest_assets_hygiene.test.ts](../tests/unit/manifest_assets_hygiene.test.ts)

三條測試：

| Test | 偵測 | 失敗訊息 |
|---|---|---|
| 1. 每個源檔都被引用 | `static/src/components/`、`core/`、`css/` 底下所有 `.js`/`.xml`/`.css` 都必須出現在 `__manifest__.py` 主動引用（非註解）；或在例外清單 | 列出 missing 檔案 + 建議 manifest snippet |
| 2. 例外清單不過期 | `ALLOW_NOT_IN_MANIFEST` 內每個路徑都要實際存在 | 列出 stale 例外 |
| 3. 引用路徑不指向幻影 | manifest 引用的 `components/core/css` 路徑都要實際存在於磁碟 | 列出 phantom 引用 |

### 2.2 例外清單（ALLOW_NOT_IN_MANIFEST）

| 路徑 | 不 bundle 原因 |
|---|---|
| `static/src/components/doc_editor/test_harness.js` | 開發/測試用、從 node 直接跑、不進 Odoo bundle |
| `static/src/components/doc_page_layout/*` | HTML/Wysiwyg 時代殘留（canvas-editor 已取代）；manifest 內以註解形式保留 reference 供追溯 |
| `static/src/components/doc_ruler/*` | 同上 |
| `static/src/core/pagination_engine.js` | 同上 |

新增例外時要在註解寫清楚**原因**，避免後人懷疑「為什麼這個檔不 bundle」。

### 2.3 註解識別策略

最簡單的方式：**整行以 `#` 開頭 → 跳過**。

```python
            # 'dobtor_doc_editor/static/src/core/pagination_engine.js',  ← 註解、不計入
            'dobtor_doc_editor/static/src/components/doc_editor/doc_editor.js',  ← 計入
```

不處理行尾 `#` 註解、不處理 multi-line string，因為 Odoo manifest 慣例都是「每條 asset 一行」，這條過濾夠用。

### 2.4 為什麼選 glob + regex 而非 ast.parse？

`__manifest__.py` 是純 Python dict literal，理論上應該 `ast.literal_eval` 解析。但：
- vitest 跑在 node 環境，沒 Python AST
- 寫 JS Python parser 過殺
- 整行 `#` 註解過濾 + regex 抓 `'dobtor_doc_editor/...'` 已涵蓋 99% 情況

如果未來 manifest 改用 conditional bundling（如根據 Odoo 版本切資源），這個檢查可能需要升級。屆時再說。

---

## 3. 範例：Sprint G/H 的 bug 會被怎麼抓到

如果重現 Sprint G/H 漏加 manifest 的狀態（即 commit `56e6a51` 之前），跑 `npx vitest run tests/unit/manifest_assets_hygiene.test.ts`：

```
FAIL  manifest assets hygiene (Sprint I)
   每個 components/core/css 底下的 .js/.xml/.css 都被 __manifest__ 引用（或在例外清單）

   Error: 以下 1 個 asset 檔案未被 __manifest__.py 引用（runtime 會 import 失敗）：

     • 'dobtor_doc_editor/static/src/components/doc_editor/jinja2_scanner.js',

   修法：加進 __manifest__.py 的 'assets' 區段（web.assets_backend 與/或 web.assets_frontend），
        **順序很重要**——被 import 的 module 必須在 importer 之前。
   若刻意不 bundle（如測試 harness、legacy），把路徑加進
   tests/unit/manifest_assets_hygiene.test.ts 的 ALLOW_NOT_IN_MANIFEST、附上原因。
```

→ 開發者立刻知道哪個檔案漏加、要做什麼。

---

## 4. 驗證

### L1 vitest

```
Test Files  96 passed | 1 skipped (97)
     Tests  1912 passed | 1 skipped (1913)
Duration    120.86s
```

對齊 Sprint H baseline 1906 + 3 個 Sprint I hygiene 測試 + 3 個間期新增 = 1912，**0 regression**。

新增測試（`manifest_assets_hygiene.test.ts`）3 條全綠：
- 每個源檔被引用 ✓
- 例外清單不過期 ✓
- 引用路徑不幻影 ✓

### L0 模組升級

未跑（Sprint I 純測試、0 行 production 程式碼）。

---

## 5. 已知限制與後續

- **只 lint `components/core/css`**：`lib/` 底下的 canvas-editor / shim / plugin 也都在 manifest，但這些是 vendored 第三方檔，加新檔頻率低、人工檢查足夠
- **不偵測順序錯誤**：如果 `doc_editor.js` 排在 `jinja2_scanner.js` **之前**（import 順序錯誤），這條 lint 仍會通過。實務上 manifest 的順序錯誤會在瀏覽器 console 立刻爆 `undefined is not a function`，比 missing 容易察覺
- **不偵測 `lazy_loader.js` 動態載入**：如果未來改 lazy load 動態 import，本檢查會誤報。屆時把該檔加進 ALLOW 即可
- **不處理行尾 `#` 註解**：`'foo.js',  # 註解` 仍會被算成主動引用。Odoo manifest 慣例不這樣寫、暫不處理

---

## 6. 方案 1 整體進度更新

| # | 缺口 | Sprint | 狀態 |
|---|---|---|---|
| 1-3 | Sub-nav 三分頁解封 | A | ✅ |
| 4 | 預覽鈕接後端 | A | ✅ |
| 5 | 縮圖 panel 真實 | C | ✅ |
| 6 | 頁碼真換頁 | B | ✅ |
| 7 | 縮放 fit 真實計算 | B | ✅ |
| 8 | Phase 8.2.2 overlay 絕對定位 | D | ✅ |
| – | Odoo 欄位按鈕連結 inspector | E | ✅ |
| – | Overlay polish | F | ✅ |
| – | 批次掃描 `{{ var }}` 建 record | G | ✅ |
| – | 掃描並替換為 control（main 流） | H | ✅ |
| – | **Manifest assets hygiene 自動化檢查** | **I** | ✅ |
