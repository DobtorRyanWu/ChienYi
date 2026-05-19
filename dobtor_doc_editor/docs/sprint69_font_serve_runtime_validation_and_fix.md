# Sprint 69：font_serve HttpCase runtime 驗證 + dead code 修正

**性質**：code change（改善）— 驗證 + 揭示 + 修正 + 重驗 完整鏈條
**日期**：2026-05-16
**前置**：Sprint 64b 落地、Sprint 66 加 Python tests、Sprint 68 補邊界 tests；本 sprint 跑 runtime 驗證、揭示架構缺陷、修正

---

## 0. 一句話定位

Sprint 66 + 68 的 Python tests 之前只跑了 `flake8 + ast.parse` static 驗證（紀律 #5 揭示的「static 通過 ≠ runtime OK」陷阱）。Sprint 69 在 odoo18 container 真跑 `docker exec odoo18 odoo --test-tags=font_serve` HttpCase 驗證：

- **第一次跑**：11 個 tests passed + **2 個 skipped**（CJK / serve test 因「DroidSansFallback 不存在」）
- **揭示**：odoo18 container 內 **`/usr/share/fonts/truetype/droid/` 和 `/usr/share/fonts/truetype/liberation/` 都不存在**！container 只有 `fonts-noto-cjk` + `fonts-dejavu-core`。Sprint 64b 寫的 `FONT_PATH_MAP` 在 production container 是 **dead code**（永遠 404）。
- **修正**：改 schema 從 `dict[str, str]` → `dict[str, tuple[str, ...]]` candidate fallback chain（WSL host 用 droid、container 用 Noto CJK）+ 加 `resolve_font_path()` resolver
- **重驗**：12 個 tests 全綠、**0 skipped**（之前 skipped 的 CJK serve test 現在實際跑了並通過）

---

## 1. Hypothesis

### 1.1 開工時 hypothesis

Sprint 66 + 68 寫的 11 個 test（2 logic + 4 HTTP + 5 security）只跑過 `flake8 + ast.parse`。Hypothesis：HttpCase runtime 驗證會「11 tests pass」確認 Sprint 66 + 68 工作完整、Sprint 64b infrastructure 在 production 可用。

### 1.2 揭示後修正 hypothesis

odoo18 container 內預期字型路徑都不存在 → Sprint 64b/66/68 寫的「production endpoint」實際在當前 container 永遠 404。修法 = candidate fallback chain（WSL host 與 container 各自指向實際存在的字型）。

**預期**：修法後 endpoint 在 container 內真的能 serve Noto CJK bytes、12 tests 全綠（含之前 skipped 的）。

---

## 2. Method

### 2.1 Step 1 — 跑 HttpCase runtime

```bash
docker exec odoo18 odoo -c /etc/odoo/odoo.conf -d odoo18_dev \
    --test-enable --test-tags=font_serve --stop-after-init \
    -u dobtor_doc_editor --http-port=8169
```

注意：
- `--http-port=8169` 避開 already-running Odoo server 的 `8069`
- `--test-tags=font_serve`（不是 `dobtor_doc_editor.font_serve`，Odoo 18 tag 格式是單 tag）
- `-u dobtor_doc_editor`（不 reinstall、只 upgrade）

### 2.2 Step 2 — 揭示 container 字型現況

```bash
$ docker exec odoo18 ls /usr/share/fonts/truetype/droid/ /usr/share/fonts/truetype/liberation/
ls: cannot access '/usr/share/fonts/truetype/droid/': No such file or directory
ls: cannot access '/usr/share/fonts/truetype/liberation/': No such file or directory

$ docker exec odoo18 find /usr/share/fonts -iname '*noto*'
/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc
/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc
/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc

$ docker exec odoo18 dpkg -l | grep -iE 'droid|liberation|noto-cjk'
ii  fonts-noto-cjk    1:20230817+repack1-3    all    "No Tofu" font families with large Unicode coverage (CJK regular and bold)
# droid / liberation 都沒安裝
```

→ container 是 minimal Ubuntu base + `fonts-noto-cjk` + `fonts-dejavu-core`，沒有 `fonts-droid-fallback` / `fonts-liberation`。

### 2.3 Step 3 — 修 `controllers/font_serve.py`

#### 3.1 加 candidate chain constants

```python
CJK_CANDIDATES = (
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",  # WSL host (VR pipeline)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",     # odoo18 container
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",    # fallback CJK
)
SERIF_CANDIDATES = (
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",  # WSL host
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",                  # odoo18 container
)
SANS_CANDIDATES = (
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
```

#### 3.2 改 `FONT_PATH_MAP` schema 從 `str` 到 `tuple[str, ...]`

#### 3.3 加 helper

```python
def resolve_font_path(family):
    """回傳 family 對應第一個存在的字型路徑、無對應或全 missing 時回 None。"""
    candidates = FONT_PATH_MAP.get(family)
    if not candidates:
        return None
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _content_type_for(path):
    """TTC 是 OpenType Collection、用 font/collection。"""
    if path.endswith(".ttc"):
        return "font/collection"
    if path.endswith(".otf"):
        return "font/otf"
    return "font/ttf"
```

#### 3.4 改 `serve_font` 與 `list_fonts` 用 resolver

### 2.4 Step 4 — 更新 11 個 tests 兼容新 schema

- `test_font_path_map_structure`：驗證 schema 為 tuple、所有 candidate 路徑為 `.ttf/.ttc/.otf`
- `test_cjk_families_share_same_candidate_chain`（**取代** `test_cjk_families_all_map_to_droidsans`）：驗證所有 CJK family 共用同一 candidate chain、chain 中至少有 Droid 或 NotoCJK
- `test_resolve_font_path_handles_unknown_family`（**新增**）：驗證 `resolve_font_path()` 對未知 / 空 family 回 None
- HTTP / Security tests 改用 `resolve_font_path(family)` 判斷 skip 條件、Content-Type assertion 接受 `font/ttf | font/collection | font/otf` 三種

### 2.5 Step 5 — 重跑 + 重驗

---

## 3. Result（三層 SOP）

### 3.1 開工前 baseline

| Sprint 68 結尾 | 結果 |
|---|---|
| vitest | 976 passed + 1 skipped ✓ |
| Python flake8 + ast.parse | 全綠 ✓ |
| HttpCase runtime | **未跑過**（只 static 驗證）|

### 3.2 Sprint 69 第一次跑（揭示 dead code）

```
2026-05-16 03:43:18,179 odoo.tests.result: 0 failed, 0 error(s) of 11 tests
```

11 個 tests passed、但 **2 個 skipped**：
- `TestFontServeHttp.test_serve_known_family_returns_ttf : 系統字型都不存在（minimal container？）— skip HTTP serve test`
- `TestFontServeSecurity.test_url_encoded_cjk_decodes_correctly : DroidSansFallback 不存在（minimal container？）`

→ Sprint 64b/66/68 的 endpoint 在當前 container 是 dead code、user 看不到 font bytes。

### 3.3 Sprint 69 修正後重跑

```
2026-05-16 03:48:08,178 odoo.tests.result: 0 failed, 0 error(s) of 12 tests
```

**12 個 tests 全綠、0 skipped**：
- `TestFontServeLogic`：3 tests（含新 `test_resolve_font_path_handles_unknown_family`）
- `TestFontServeHttp`：4 tests（含原 skip 的 `test_serve_known_family_returns_font_bytes` 改名+實跑）
- `TestFontServeSecurity`：5 tests（含原 skip 的 `test_url_encoded_cjk_decodes_correctly` 實跑）

→ Sprint 64b endpoint **現在真的能 serve Noto CJK font bytes**（CJK chain resolve 到 `NotoSansCJK-Regular.ttc`）。

### 3.4 三層 SOP 對齊

| 層 | 結果 |
|---|---|
| L1 Vitest | **976 passed + 1 skipped**（與 Sprint 68 一致、Sprint 69 對 frontend 0 影響 ✓）|
| L2 VR v14 | **0.073191 不變**（無 pipeline 變動）|
| L3 Python flake8 + ast.parse | **全綠** ✓ |
| L4 Odoo HttpCase runtime | **12 passed + 0 skipped**（紀律 #5 揭示後補完）✓ |

---

## 4. Root cause / Mechanism

### 4.1 為什麼 Sprint 64b 寫死 droid/liberation 路徑？

Sprint 64b audit 寫：「用 WSL Linux 已安裝的 LO 系統 fallback fonts（DroidSansFallback + LiberationSerif）」。當時 *WSL host* 環境有 droid/liberation（LibreOffice 安裝時順帶裝的），author 直接把同樣路徑寫進 controller、假設 odoo18 container 也有同樣字型。

→ **隱性 assumption**：「VR pipeline 跑得起來 = production controller 也能用同樣 paths」。Sprint 69 揭示這個假設錯了 — VR pipeline 跑在 WSL host（`node scripts/visual_regression_v14.mjs`），controller 跑在 odoo18 container。**兩者 OS 環境不同**。

### 4.2 為什麼 Sprint 66 + 68 沒抓到？

- Sprint 66 / 68 都只跑 `flake8 + ast.parse` static lint
- HttpCase runtime 從 Sprint 64b 落地以來 **3 個 sprint（64b / 66 / 68）都沒跑過**
- 紀律 #5 揭示「static 通過 ≠ runtime OK」、但實際 Odoo 環境的 runtime gate 一直 deferred

→ **本 sprint 揭示**：紀律 #5 的延伸應用 — 「Python static lint 通過 ≠ Odoo controller 在 production container 環境下 work」。

### 4.3 為什麼跑 test 才揭示而不是直接看 controller 路徑？

container 內 `/usr/share/fonts/truetype/droid/` 不存在這個事實**任何時刻 `docker exec ls` 都能查**。但 Sprint 64b/66/68 是 WSL host 視角寫 controller、沒有 cross-check container 環境。

→ **新教訓（紀律 #11 候選）**：寫 production controller 觸碰 filesystem 路徑時、必須 cross-check production 環境（container）實際路徑、不是 dev 環境路徑。

---

## 5. 紀律與啟示

### 5.1 紀律 #5 完整循環

| 階段 | Sprint | 紀律狀態 |
|---|---|---|
| 揭示 | 62 | vitest 通過 ≠ IIFE bundle work（nodeModuleStub 47-sprint blocker）|
| 延伸 | 68 | Python static lint 通過 ≠ Odoo controller 邊界 input 正確 |
| **完成** | **69** | **HttpCase runtime 確認 + 揭示「path assumption 跨環境不一致」陷阱** |

紀律 #5 從 Sprint 62 揭示到 Sprint 69 完整循環、3 個 sprint 累積成熟：
1. Sprint 62 抓到「測試環境 ≠ production 環境」一般原則
2. Sprint 68 延伸到「Python static 驗證 ≠ runtime 驗證」
3. Sprint 69 抓到「dev 環境 ≠ production container 環境」具體實例

→ Sprint 69 之後、任何 controller 的 file-system 互動必須**有 HttpCase runtime test 跑在 production-like 環境**驗證。

### 5.2 紀律 #10 應用

Sprint 68 揭示紀律 #10：「catch-up sprint 不該停在最低限度補完、應補到當前紀律標準」。Sprint 69 是這條紀律的應用實例：

- Sprint 66 是 catch-up（補 Sprint 64b 漏掉的 Python tests）→ 停在「跑得了 static lint」
- Sprint 68 是 catch-up to catch-up（補 Sprint 66 漏掉的 security tests）→ 仍停在 static lint
- Sprint 69 是 catch-up to catch-up to catch-up（**補 HttpCase runtime 驗證**）→ 揭示 dead code 並修

→ catch-up 鏈條每多一層都揭示更深的假設陷阱。**Sprint 69 把鏈條收口** — runtime 驗證後沒有更深的 catch-up 必要（除非新功能加入）。

### 5.3 紀律 #11 候選（本 sprint 揭示）

> **Controller 觸碰 filesystem 路徑時、必須 cross-check production 環境（container）實際路徑、不是 dev 環境路徑**。`docker exec ls` 是寫死路徑前的 30 秒投資、能省下 3 個 sprint 的 dead code blocker。

→ 通用化：所有「假設 X 路徑存在」「假設 Y 套件已裝」「假設 Z 環境變數有值」的 production code、寫死前必須 explicit 列 hypothesis、在 production-like 環境驗證至少一次。

### 5.4 Sprint 50-69 累積紀律分布（20 sprints）

| 類型 | 個數 | 比例 |
|---|---|---|
| Code change（改善） | 7（+Sprint 69）| 35% |
| Code change（neutral） | 3 | 15% |
| 純診斷 | 7 | 35% |
| Mechanical commit | 1 | 5% |
| Catch-up sprint | 3（66 + 67 + 68） | 15% |

Sprint 69 不算 catch-up — 它揭示了真實架構缺陷並修正、是 **「揭示 + 修 + 重驗」的 code change improvement sprint**。純診斷 + neutral + mechanical + catch-up ≈ **70%** 但只有 30% code change improvement（含 Sprint 69）。

Catch-up 鏈條從 Sprint 66 開始（66 → 67 → 68）終於在 Sprint 69 收口 — 找到實質可修的問題並修。

---

## 6. 後續 sprint 候選

### 6.1 原 §11.33 / §11.34 / §11.35 候選不變

- 🔴 Migrate `doc_editor.js` 從 canvas-editor 到自家 pipeline（待 user）
- 🟡 重生 goldens 用 Word desktop 渲染（副作用大）
- 🟡 OffscreenCanvas + Web Worker render（3-5 sprints）
- 🟡 50+ 頁 fixture（user 提供）

### 6.2 Sprint 69 揭示的新候選

- 🟢 **檢視其他 controller 觸碰 filesystem 的地方**（紀律 #11 應用域）：
  - `controllers/doc_controller.py` — 有寫死路徑嗎？
  - `models/doc_zip_guard.py` — temp dir 路徑跨環境一致？
  - 其他 `os.path.exists` / `open()` 呼叫處
- 🟢 **CI 加 `--test-tags font_serve` job**：當前 HttpCase 只有手動 + 本 sprint 跑過、應 gate PR
- 🟢 **container 字型套件審計**：odoo18 Dockerfile 是否要加裝 `fonts-droid-fallback` / `fonts-liberation` 對齊 WSL host？這是「擴 container 字型」vs「擴 candidate fallback」的選擇 — Sprint 69 走後者（更輕量）

### 6.3 autonomous docs sprint 候選（Sprint 67 揭示）

- `docs/architecture_decision.md` 補完
- `docs/glossary.md` 建立
- `docs/sprint50_66_retro.md` 橫向回顧

---

## 7. 對規畫書的同步動作

| 段落 | 改動 |
|---|---|
| 標頭「最後更新」 | 改 Sprint 69 |
| §0.4 Sprint 表 | 加 Sprint 69 row、Sprint 70+ 候選刷新 |
| §11.36 | 新增 Sprint 69 完整 entry |
| pure-duckling.md | 加 Sprint 69 完整 entry + Sprint 70+ 候選表 |

---

## 8. 一句話結論

**Sprint 69 把 Sprint 64b 的 dead-code endpoint 救回來、並完整 trigger 紀律 #5 三 sprint 循環收口**。修法 = candidate fallback chain（WSL host + odoo18 container 跨環境兼容）、12 個 HttpCase tests 全綠 / 0 skipped、揭示紀律 #11 候選（controller filesystem path 必須 cross-check production 環境）。Sprint 50-69 累積 20 sprints、catch-up 鏈條（66 → 67 → 68 → 69）終於找到實質可修的問題並修。
