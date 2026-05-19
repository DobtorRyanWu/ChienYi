# Sprint 50-72 橫向回顧（hook auto-loop + manual sprint）

> Sprint 74 落地。23 個 sprint（Sprint 50 → Sprint 72）的 cross-sprint 分析、收益曲線、紀律生成軌跡。

## 1. 高層數字

| 指標 | Sprint 50 起點 | Sprint 72 結束 | Delta |
|---|---|---|---|
| **VR mean** | 0.0749（baseline）| **0.073191**（新 default）| **-0.001708 / -2.3%** |
| **VR failed pages** | 0 | **0** | 持平（無 regression）|
| **vitest** | 866 passed | **976 passed + 1 skipped** | **+110 tests** |
| **Odoo backend tests** | 0（無 backend test infra）| **21 passed**（font_serve 12 + zip_guard 9）| **+21** |
| **Page count baseline（Sprint 16）** | 全綠 | 全綠 | 持平 |
| **Fingerprint baseline（Sprint 12）** | 全綠 | 全綠 | 持平 |
| **Sprint audit docs** | 49 | **72**（+23）| **+47%** |
| **紀律條數** | 0 條 explicit | **13 條 explicit** | 從 0 到 13 |

## 2. Sprint 分類分布

| 類型 | 個數 | 比例 | 代表 sprint |
|---|---|---|---|
| Code change（改善）| 8 | 35% | 51 / 52 / 54 / 56 / 58 / 62 / 69 / 70 |
| Code change（neutral）| 3 | 13% | 57 / 59 / 64b |
| 純診斷 | 7 | 30% | 50 / 60 / 63 / 64 / 70 audit / 71 audit |
| Mechanical commit | 1 | 4% | 65 |
| Catch-up sprint | 4 | 17% | 66 / 67 / 68 / 71 |

**純診斷 + neutral + mechanical + catch-up ≈ 64%**。看起來「無 code 變動」但是讓「有 code 變動」的 sprint 真正 land — 這是工程紀律分布的健康訊號。

## 3. 紀律生成軌跡（13 條）

```
Sprint 50 ─┐ 量測為先（路線 A 轉折）
        │
Sprint 57 ─┼─ 紀律 #1: 改 renderer 強制跑全 VR
        │   紀律 #2: spy 驗 API、VR 驗 pixels
        │
Sprint 60 ─┼─ 紀律 #3: 高風險改造前 probe
        │
Sprint 61 ─┼─ 紀律 #4: 負面結果 sprint 揭示 assumption（揭示 LO anchor）
        │
Sprint 62 ─┼─ 紀律 #5: vitest 通過 ≠ IIFE bundle work（揭示 nodeModuleStub 47-sprint blocker）
        │
Sprint 63 ─┼─ 紀律 #6: promote default 前 per-fixture delta
        │
Sprint 64 ─┼─ baseline drift probe
        │
Sprint 65 ─┼─ 紀律 #7: mechanical commit 是多 sprint 紀律的內化
        │
Sprint 64b ┼─ 紀律 #8: 架構發現的 sprint 也要記、誠實定位 vs 假設一致
        │
Sprint 66 ─┼─ catch-up（補 Sprint 64b Python tests）
Sprint 67 ─┼─ 紀律 #9: §附錄 A `[ ]` 項是 autonomous 優先選擇（CONTRIBUTING.md）
Sprint 68 ─┼─ 紀律 #10: catch-up 不停最低限度、應對齊當前紀律標準
Sprint 69 ─┼─ 紀律 #11: filesystem 必須 cross-check production 環境（揭示 FONT_PATH_MAP dead code）
Sprint 70 ─┼─ 紀律 #11 第一應用（doc_controller PDF fallback）
Sprint 71 ─┼─ 紀律 #12: test class 必須 explicit tag
Sprint 72 ─┘ 紀律 #13（候選）: backend test 必須有定期跑機制
```

## 4. 收益曲線

### 4.1 VR mean 收斂（Sprint 50-65）

```
Sprint 50  ████████████████████████████████  0.0749 (baseline)
Sprint 51  ████████████████████████████████  0.0749（AST cache 落地、VR 不變）
Sprint 52  ████████████████████████████████  0.0749（IDB cache、VR 不變）
Sprint 53  ████████████████████████████████  0.0749（virtualize、VR 不變）
Sprint 54  ████████████████████████████████  0.0749（image cache、VR 不變）
Sprint 55  ████████████████████████████████  0.0749（full-warm bench）
Sprint 56  ████████████████████████████████  0.0749（ImageBitmap）
Sprint 57  ████████████████████████████████  0.0749（aggressive 翻車 + revert）
Sprint 58  ████████████████████████████████  0.0749（LayoutCache）
Sprint 59  ████████████████████████████████  0.0749（path coalescing）
Sprint 60  ████████████████████████████████  0.0749（probe）
Sprint 61  █████████████████████████████████ 0.0762（BrowserTextMetrics negative）
Sprint 62  ███████████████████████████████   0.0732（FontMetricsAdapter + IIFE 修復）★ -1.7%
Sprint 63  ███████████████████████████████   0.0732（per-fixture delta probe）
Sprint 64  ███████████████████████████████   0.0732（drift probe）
Sprint 65  ███████████████████████████████   0.0732 → new default
Sprint 66-72                                  0.0732 不變
```

**關鍵 inflection**：Sprint 62 命中 -1.7%。**前 12 個 sprint 的 cache/perf 工作沒打進 VR**、Sprint 60-62 三步揭示鏈才命中。

### 4.2 Tests 累積

```
vitest:
Sprint 50  866 passed
Sprint 51  877 passed (+11 AstCache)
Sprint 52  886 passed (+9 IdbAstCache)
Sprint 54  896 passed (+10 ImageDecodeCache)
Sprint 56  908 passed (+12 ImageBitmapIdbCache)
Sprint 57  921 passed (+13 memoize)
Sprint 58  940 passed (+19 LayoutCache)
Sprint 59  953 passed (+13 PathCoalescing)
Sprint 61  967 passed (+14 BrowserTextMetrics)
Sprint 64b 976 passed (+9 FontLoader)
Sprint 65-72 976 不變

Odoo backend (新類別):
Sprint 66  6 tests (TestFontServeLogic 2 + TestFontServeHttp 4)
Sprint 68  +5 tests (TestFontServeSecurity)
Sprint 69  schema 改 → 12 tests（含原 skipped 解禁）
Sprint 71  +3 tests (zip_guard 補測)
Sprint 72  21 tests total（一鍵跑）
```

## 5. 重大事件時間軸

| Sprint | 事件 | 影響 |
|---|---|---|
| 50 | Phase 7 效能基線量測 — 轉路線 A（商業化先行）| 揭示 parse 60.7% 主要瓶頸 |
| 57 | **aggressive fast path 翻車** | 揭示 紀律 #1 + #2 |
| 60 | **OffscreenCanvas probe** | 揭示 紀律 #3 |
| 61 | **BrowserTextMetrics negative** | 揭示 goldens = LO anchor、紀律 #4 |
| 62 | **IIFE bundle 47-sprint blocker 揭示+修復** | 紀律 #5 + 命中 VR -1.7% |
| 65 | **promote `--font-metrics` default** | 1 行 mechanical commit、紀律 #7 |
| 64b | **production 走 canvas-editor 不是自家 pipeline** | 紀律 #8、誠實定位 |
| 67 | **CONTRIBUTING.md 補完** | Phase 0 從 95% → 100%、紀律 #9 |
| 69 | **`FONT_PATH_MAP` dead code 揭示+修復** | 紀律 #11、紀律 #5 三 sprint 收口 |
| 70 | **`fill_template` PDF 500 揭示+修** | 紀律 #11 第一應用 |
| 72 | **`run_backend_tests.sh` 一鍵 21 tests** | 紀律 #12 + #13 候選 |

## 6. 對未來 sprint 的啟示

### 6.1 純診斷 30% 比例是健康訊號

如果都是 code change sprint、會錯過揭示 assumption 的機會。Sprint 60-64 連 5 個 probe / negative / drift sprint 才讓 Sprint 65 的 1 行 commit 站得住腳。

### 6.2 catch-up 17% 比例也健康

Sprint 66-68 連 3 個 catch-up、Sprint 71 又一個 — 看起來「沒新功能」但每次 catch-up 都揭示更深的 assumption gap、最終 Sprint 69 收口找到實質可修。

### 6.3 「揭示」比「修」更有價值

Sprint 61 是 negative result，但揭示「goldens = LO anchor」這個 47 個 sprint 沒人意識到的事實 — 比修對某個 fixture 更值錢。**未來 sprint 應該主動追求「揭示」、不只是「修」**。

### 6.4 紀律生成節奏 ≈ 1 條 / 2 sprint

Sprint 50-72 = 23 sprint、13 條紀律 = 平均 1.77 sprint / 條。**這個節奏是經驗品質的指標**：太快可能是浮淺、太慢可能是工程懈怠。

## 7. Sprint 73+ 候選清單（基於 retro）

- 🟢 **Sprint 75**：docs/architecture_decision.md 補完（ADR 系列）
- 🟢 **Sprint 76+**：紀律 #11 廣域應用（檢視 `models/doc_document.py` / `wizards/*.py` 是否有 filesystem path drift）
- 🟢 **Sprint 77+**：紀律 #13 真正落地（CI 加 Odoo runtime job、不只 lint）
- 🔴 **Sprint 80+**：User 決策方向（migrate doc_editor.js / 重生 goldens / OffscreenCanvas worker / 50+ 頁 fixture）

## 8. 一句話結論

**Sprint 50-72（23 sprints）從 0.0749 → 0.0732 VR mean、+110 vitest + 21 backend tests、累積 13 條紀律、Phase 0 從 95% → 100%**。純診斷 + neutral + mechanical + catch-up = 64% 比例反映工程紀律分布健康。Sprint 60-62 三步揭示鏈是最大收益 inflection。
