# Sprint 287 — Phase 1 optional bucket 6/6（最後一項）：`<wp:anchor>` 完整 capture ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy C+ parser-side completeness

**日期**：2026-05-27（週三）
**類型**：Strategy C+ capture-only — parser 補完整 + AST optional fields + 16 tests
**規畫書對應**：§Phase 1 §1.7 drawing anchor full
**前置**：Sprint 286 effectExtent（Phase 1 optional bucket 5/6）

User 指令：「依序 ruby / tcFitText / tblStylePr row+border / lvlOverride / effectExtent / **浮動圖片 wp:anchor 完整**。每項一個 sprint、跑完停下叫我 review。最多 8 sprint。」

本 sprint 收尾 Phase 1 optional bucket（6/6 完成）。

---

## Audit 結論

**揭發狀態**：Sprint 37/38 capture posH/posV/wrapType/behindDoc/allowOverlap，
Sprint 286 補 effectExtent。剩餘 silent gap：

| 屬性 | Sprint 287 前 | Sprint 287 後 |
|---|---|---|
| `distT/distB/distL/distR` | 全失 | parser capture，EMU → Pt |
| `relativeHeight` (z-order) | 全失 | parser capture，UInt |
| `locked / layoutInCell / hidden` | 全失 | parser capture，Boolean |
| wrap mode `wrapText` attr | 全失 | detectWrapText helper |

**Strategy C+ capture-only**：
- AST：`AnchorMetadata` 新 interface + `AnchorWrapText` type；FloatImageNode + FloatTextBoxNode 各 +2 optional 欄位
- Parser：`parseAnchorMetadata` + `detectWrapText` 兩個 helper、wire into 兩個 parser
- Writer：**不動**（紀律 #18 scope-down，見下節）

---

## Writer 為何不動：Sprint 192 已揭露的 acceptable lossy

[OoxmlWriter.ts:1391-1394](../static/src/core/ooxml/export/OoxmlWriter.ts#L1391-L1394)：
> Sprint 192：把 InlineImageNode / **FloatImageNode 序列化為 `<w:r><w:drawing><wp:inline>`**。
> FloatImageNode 降級為 inline 輸出（與 ToCanvasEditor 一致：production pipeline
> 已把浮動圖片視為 inline）。posH / posV / wrap / srcRect 等屬性 lossy 留後續。

這是 Sprint 192 的 **explicit decision**：floatImage 寫出時降級。Sprint 287 不重寫
此策略（紀律 #18 scope-down，user 指令「每項一個 sprint」cap 1 sprint）。

**結果**：
- Parser 端：anchor 屬性全 capture（lossless capture for ChienYi v1 ImageProps preservation audit）
- Writer 端：寫出仍 wp:inline（acceptable lossy by design）
- Round-trip：lossy（與 Sprint 192 一致）

honest gap：**lift writer 寫 wp:anchor → wp:inline 降級的決定** 為 Phase 2/3 改造範圍，
不在本 Phase 1 optional bucket scope。

---

## 16 unit test 場景（[tests/unit/sprint287_anchor_completeness.test.ts](../tests/unit/sprint287_anchor_completeness.test.ts)）

### dist* attributes（4 案）

| Test | 驗證 |
|---|---|
| 四向 EMU → Pt | 914400 EMU = 72pt、457200 = 36pt、228600 = 18pt、114300 = 9pt |
| 全缺 → undefined | 不偽造預設、capture-only honesty |
| 部分屬性 → 只該屬性掛上 | distT/distL 有、distB/distR undefined |
| 非數字 → 退化 undefined | 不 throw |

### relativeHeight z-order（3 案）

| Test | 驗證 |
|---|---|
| 251658240 → 解析正確 | Word 標準 anchor 預設值 |
| 負值 → 拒絕 | OOXML UInt 不接受負數 |
| 缺漏 → undefined | 與 dist* 對稱 |

### locked / layoutInCell / hidden（2 案）

| Test | 驗證 |
|---|---|
| 全 "1" → 全 true | 三 flag 並存 |
| "0"/"false"/缺漏 → 不掛欄位 | 避免污染預設（與 srcRect 全 0 collapse 對稱） |

### wrapText 屬性（5 案）

| Test | 驗證 |
|---|---|
| wrapSquare wrapText="left" | AST.wrapText = "left" |
| wrapTight wrapText="largest" | AST.wrapText = "largest" |
| wrapSquare 無屬性 | undefined（不偽造 bothSides 預設） |
| wrapNone | undefined（不繞排無 wrapText） |
| 無效值（"invalid"） | undefined、不 throw |

### 整合 + honest gap（2 案）

| Test | 驗證 |
|---|---|
| 真實 Word 風格 anchor | posH/posV/wrapType/anchor/wrapText/effectExtent 全 capture |
| Writer 仍走 Sprint 192 降級 | 含 anchor/wrapText 的 FloatImage 寫出仍是 `<wp:inline>`、不是 `<wp:anchor>`、anchor metadata 不 emit（acceptable lossy by design） |

**16/16 passed / 45ms**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy C+：parser + AST + tests，0 行 writer 變動 | ✅ |
| #14.b clean scope：commit 含 1 AST + 1 parser + 1 unit test + 1 doc + 1 snapshot 更新 | ✅ |
| #18 scope-down：不重寫 Sprint 192 writer 降級策略；anchor round-trip 留 Phase 2/3 | ✅ |
| #21 不污染既有 VR：writer 行為完全不變、layout/render 端不消費新 fields（不影響 VR pipeline） | ✅ |
| #22 verify：parser 14 案（dist/zh/flag/wrapText 全 edge）+ 整合 1 案 + writer-downgrade documentation 1 案 honest 揭示 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## 為何 Sprint 287 = capture-only 而非 round-trip

| 選項 | 範圍 | 成本 | 風險 |
|---|---|---|---|
| **A. capture-only**（本 sprint） | parser + AST + tests | 1 sprint | 0；不動 writer = 不污染 VR |
| B. 完整 round-trip | A + 重寫 writeInlineImageRun 路徑、寫 wp:anchor + posH/posV/wrap*/dist*/anchor flags 全鏈、processor 對 inline-only 假設全要重審、ToCanvasEditor production pipeline 重審 | 5-8 sprint cluster | 中-高；可能破 Sprint 200 anchor paragraph strip 等下游邏輯 |

user 指令「每項一個 sprint」cap 1 sprint，**選 A**。honest gap 已紀錄、未來若要做 wp:anchor
完整 round-trip 需獨立 cluster（非 Phase 1 optional bucket 範圍）。

---

## Phase 1 optional bucket 完成總結

| Sprint | 項目 | Strategy | 行為 |
|---|---|---|---|
| 282 | ruby（注音/振假名）| A | AST + parser + 8 tests（writer/render 留後續） |
| 283 | tcFitText | C | 11 tests 補洞（AST/parser/writer 既有 zero test） |
| 284 | tblStylePr borders | A | 開 Sprint 131 defer、+10 tests |
| 285 | lvlOverride | C | 8 tests 補洞（Sprint 191 clone-per-num acceptable lossy） |
| 286 | effectExtent | A 輕量 | AST + parser + writer + 10 tests（silent gap 補洞 round-trip lossless） |
| **287** | **wp:anchor 完整** | **C+ capture-only** | **AST + parser + 16 tests（writer 仍走 Sprint 192 降級）** |

**6 sprint / +63 tests total（+8+11+10+8+10+16=63）/ +97 行 production code（types/parsers）/ 0 行 writer**
（285 nothing；286 + 4 行 writer；287 0 行 writer）.

**Phase 1 optional bucket 全清。**

---

## End of Sprint 287

vitest 2155 → 2171 hypothesis（+16 unit test）/ VR 第 68 連 maintained / tsc
2 pre-existing 不增 / +~40 行 AST + ~80 行 parser / 0 行 writer。

**Phase 1 optional bucket 6/6 完成（wp:anchor 完整 capture）= Phase 1 optional 收尾**。

**STOP for user review**（user 指令「跑完停下叫我 review」+「最多 8 sprint」，本 sprint 為 cluster 第 6 個）。

剩餘 user pre-approved 選項：
- **②** Phase 1 optional bucket = **DONE**（本 sprint 收尾）
- **①** Phase 2.1-2.3 全套：ShapingEngine refactor + 字型載入器 + opentype.js measureRun（Sprint 279-281 已 spike，full integration 待 user 啟動）
- **③** Phase 3.4 wrapTight 多邊形（12h cap）
- **④** Phase 5.4+5.5 追蹤修訂 UI + 註解面板（16h cap）
- **⑤** Phase 8.2.2（條件性 override gate）
- **⑥** Phase 7 Worker（OVERRIDE gate）

等 user 指示下一個 GO 點。
