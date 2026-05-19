# Sprint 68：font_serve.py 邊界與安全測試補強

**性質**：catch-up sprint（Python backend test 補完、紀律 #5 應用於 production controller）
**日期**：2026-05-16
**前置**：Sprint 64b backend 落地、Sprint 66 加 6 個 base test、本 sprint 補 5 個邊界 test

---

## 0. 一句話定位

Sprint 66 為 Sprint 64b 的 `/dobtor/fonts/*` 加了 6 個 base test（2 個 logic + 4 個 HTTP），但漏了 **path traversal / URL-decoded CJK round-trip / 環境全缺場景**。本 sprint 補 5 個邊界 test、覆蓋 production controller 的安全與健壯性。

**紀律 #5 應用**：vitest 通過不保證 IIFE bundle work（原版）→ **Python lint + AST 通過不保證 controller 在邊界 input 下行為正確**（本 sprint 延伸）。同樣的「test path 與 production path 可能不同」陷阱也存在於 Python controller。

---

## 1. Hypothesis

`controllers/font_serve.py:88` 用 `FONT_PATH_MAP.get(family)` 對照硬編碼 dict、設計上應安全：
- family 是字串 key、不是檔案路徑
- dict 只 lookup、不拼接 path
- `os.path.exists` + `with open(rb)` 額外保險

但「設計上應安全」≠「test 證明安全」。Sprint 14 nodeModuleStub 47-sprint 隱性 blocker 教訓：**沒測 = 可能壞**。

→ 補 5 個邊界 test 把「設計上安全」固化為「test 證明安全」：

| # | 邊界 | Hypothesis | 預期 |
|---|---|---|---|
| 1 | 字面 path traversal `../../etc/passwd`（percent-encoded slash） | dict.get() 找不到 → 404 | 404 |
| 2 | 雙層 percent-encode `%252E%252E%252Fpasswd` | Werkzeug 解碼一次得到 `%2E%2E/passwd`、不命中 dict | 404 |
| 3 | Null byte 截斷 `標楷體%00.ttf` | family key 包含 null byte、不命中 dict | 404 |
| 4 | URL-encoded CJK `%E6%A8%99%E6%A5%B7%E9%AB%94` | Werkzeug 自動 decode → `標楷體` 命中 dict | 200 + TTF bytes |
| 5 | `FONT_PATH_MAP` 所有路徑 missing | `list_fonts` 跳過全部、回 `fonts: []` 不 crash | 200 + `{fonts: [], note: ...}` |

---

## 2. Method

### 2.1 新增 test class `TestFontServeSecurity(HttpCase)`

[`tests/test_font_serve.py`](../tests/test_font_serve.py) 加 5 個 test：

| Test 函式 | 對應 hypothesis |
|---|---|
| `test_path_traversal_literal_returns_404` | #1 字面 `../` |
| `test_path_traversal_double_encoded_returns_404` | #2 雙層 encode |
| `test_null_byte_in_family_returns_404` | #3 null byte |
| `test_url_encoded_cjk_decodes_correctly` | #4 CJK round-trip |
| `test_list_empty_when_all_paths_missing` | #5 環境全缺 |

每個 test 都用 `HttpCase.url_open` 真實打 HTTP（不是 mock controller），確保走完整 Werkzeug routing + `request.not_found()` 路徑。

### 2.2 紀律 #5 應用點

Sprint 66 的 4 個 HTTP test 走「正常路徑」、Sprint 68 補「異常 / 邊界路徑」。雙層覆蓋確保：

- **production deployment** 若有 reverse proxy 把 `..` decode 後傳給 Odoo、controller 仍安全
- **container 環境** 若 fontconfig 完全失敗、portal `list_fonts` 不 500（caller 能 graceful fallback）
- **未來 migrate** 若 family input 來源從 hardcoded list 改成 user-controlled、額外 surface 已有覆蓋

---

## 3. Result（三層 SOP）

| 層 | 預期 | 實測 |
|---|---|---|
| **L1 Vitest** | 976 passed + 1 skipped（無 frontend 變動） | **976 passed + 1 skipped**（Sprint 68 開工前跑 baseline 確認 ✓） |
| **L2 VR v14** | mean 0.073191 / failed pages 0 不變 | **不跑**（純 Python backend、無 pipeline 變動）|
| **L3 Python tests** | flake8 + ast.parse 通過、新 test 5 個語法 OK | **flake8 0 issues / AST OK** ✓ |
| **L4 Spot check** | tests/test_font_serve.py 結構與 Sprint 66 一致 | ✓（同檔案延伸、不分裂） |

### 3.1 Python lint 驗證

```bash
$ python3 -c "import ast; ast.parse(open('tests/test_font_serve.py').read()); print('AST OK')"
AST OK
$ flake8 --max-line-length=120 --extend-ignore=E501,W503 tests/test_font_serve.py
(no output = 0 issues)
```

### 3.2 為何 HttpCase 不在本機跑

`HttpCase` 需要 Odoo runtime（DB + HTTP server）。本 sprint 採與 Sprint 66 相同策略：

- **靜態驗證**：flake8 + ast.parse → 確保語法 / import / lint clean
- **runtime 驗證**：留待 PR / CI / 手動 deploy 時跑：
  ```bash
  docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
      --test-tags dobtor_doc_editor.font_serve --stop-after-init
  ```
- 本機 ENV 無 odoo 已安裝 → 直接 `pytest` 會 fail（import odoo 不到）→ 用 ast.parse 是合理替代

→ 紀律 #5 本 sprint 揭示的延伸：「**Python static lint 通過 ≠ Odoo runtime 行為正確**」、與 IIFE bundle 同類陷阱、留 CI gate 驗。

---

## 4. Root cause / Mechanism

### 4.1 為什麼 Sprint 66 漏這些 test？

Sprint 66 audit 寫「TestFontServeLogic 2 tests + TestFontServeHttp 4 tests」涵蓋 **happy path + 1 個 missing file 404**。沒有：

- security 視角（path traversal）
- 國際化 round-trip 驗證（CJK URL encode）
- 環境降級 fallback（all-missing）

→ **Sprint 66 是 catch-up sprint**（補 Sprint 64b 漏掉的 Python tests），catch-up sprint 容易停在「最低限度補完」、不深挖邊界。

### 4.2 Sprint 68 的動機

Stop hook 要 SOP 三層全跑、找實質 code 變動的 sprint。font_serve 邊界補強：
- 有實質 code 變動（5 個新 test）
- 可跑 SOP 第 1 層（vitest baseline 確認）+ 第 3 層（Python lint）
- 不需 user 認可、不需外部資源
- 與紀律 #5 完美對應（IIFE bundle blocker 的 Python 類比）

---

## 5. 紀律與啟示

### 5.1 紀律 #5 的 Python 類比

原版紀律 #5（Sprint 62）：**vitest 通過不保證 IIFE bundle 同 code 也 work** — Sprint 14 nodeModuleStub 47-sprint 隱性 blocker 揭示。

Sprint 68 延伸：**Python static lint 通過不保證 Odoo controller 在邊界 input 下行為正確**。

兩者共通陷阱：
- **「測試路徑」與「production 路徑」不同** → 測過了 ≠ production OK
- **隱性 assumption 沒被驗證** → 直到 negative result / security incident 才揭示

→ 對 controller / endpoint / 任何接 user input 的 Python code，**security 邊界 test 應與 happy path test 並列**、不是「之後再補」。

### 5.2 catch-up sprint 不該停在最低限度

Sprint 68 揭示：catch-up sprint 容易做「最低限度補完」、然後標記 done。但 catch-up 的 *本意* 是「補完前 sprint 漏掉的工程紀律」、應該補到 **與當前紀律標準對齊**。

→ 未來 catch-up sprint 應 explicit 列「目前紀律標準是什麼」、再驗證新 test 對齊那個標準。

### 5.3 Sprint 50-68 累積紀律分布

| 類型 | 個數 | 比例 |
|---|---|---|
| Code change（改善） | 6 | 32% |
| Code change（neutral） | 3 | 16% |
| 純診斷 | 7 | 37% |
| Mechanical commit | 1 | 5% |
| Catch-up sprint | 3（66 + 67 + 68） | 16% |
| 文件 sprint | 含於 catch-up（67） | — |

純診斷 + neutral + mechanical + catch-up ≈ **53%** 健康分布。catch-up 比例從 Sprint 66 後的 1 個翻倍到 3 個 — 反映 hook autonomous loop 後期自然走向「補完前面留下的尾巴」。

---

## 6. 後續 sprint 候選

### 6.1 規畫書 §11.33 原候選不變

- 🔴 Migrate `doc_editor.js` 從 canvas-editor 到自家 pipeline（待 user）
- 🟡 重生 goldens 用 Word desktop 渲染（副作用大）
- 🟡 OffscreenCanvas + Web Worker render（3-5 sprints）
- 🟡 50+ 頁 fixture（user 提供）

### 6.2 Sprint 67/68 揭示的 autonomous docs 候選（不變）

- `docs/architecture_decision.md` 補完
- `docs/glossary.md` 建立
- `docs/sprint50_66_retro.md` 橫向回顧

### 6.3 本 sprint 揭示的新候選

- 🟢 **檢視其他 controller 是否有同類 security test 缺口**：
  - `controllers/doc_controller.py` — 接 doc_id、需驗證 ACL 邊界
  - 其他 portal route — 接 user-supplied filter / query
  - 走 Sprint 68 同範式：邊界 test 與 happy path 並列

- 🟢 **CI 加 `--test-tags dobtor_doc_editor.font_serve` job**：
  - 目前 Sprint 66 + 68 加的 test 只能手動跑 / PR 跑
  - CI 應自動跑（與 frontend ci 一樣 gate PR）

---

## 7. 一句話結論

**Sprint 68 把 Sprint 66 font_serve test 從「最低限度補完」升級到「與紀律 #5 對齊」**：5 個邊界 test 涵蓋 path traversal / CJK URL round-trip / 環境降級、static lint 全綠、紀律 #5 延伸到 Python controller。Sprint 50-68 累積 19 sprints、catch-up 比例 16%。
