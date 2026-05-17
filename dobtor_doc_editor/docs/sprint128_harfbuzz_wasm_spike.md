# Sprint 128 — HarfBuzz WASM 整合 spike + GO/NO-GO autonomous decision

**日期**：2026-05-17
**類型**：probe sprint（紀律 #3）+ autonomous decision
**規畫書對應**：§Phase 2.1 HarfBuzz WASM 整合（規畫書原列 1-2 週）+ autonomous_roadmap.md 階段 B 行 3 cluster 3（前移自 Sprint 129）
**前置**：Sprint 127 FontMetrics production migration probe（同 cluster 3 第 2 個 probe sprint）+ Phase D.2 已有基礎 spike

---

## Hypothesis（驗證對象）

規畫書 §4.2 / §Phase 2.1 列 HarfBuzz WASM 作為 Google Docs 級字型 shaping 核心。當前狀態：

- `harfbuzzjs@0.10.3` 已在 `package.json`、node_modules 已裝
- `tests/unit/HarfBuzzSpike.test.ts` Phase D.2 落地 5 test（load / face / shape / 中英混排）全綠
- 但 production code（FontMetricsAdapter / LayoutEngine / VR pipeline）**完全沒整合**
- FontMetricsAdapter 註解寫「HarfBuzz shape 是 async、無法 sync 接入」

Sprint 128 extends Phase D.2 spike with **進階能力驗證**（kerning / ligature / CJK 純函式）+ **整合成本估算**（bundle size / async vs sync）+ **GO/NO-GO autonomous decision**。

---

## Method

### 1. Sprint 128 新增 spike test（5 條、繼承 Phase D.2 a-d）

| Test | 鎖定能力 | 結果 |
|---|---|---|
| (e) kerning：AV ≤ AB | kerning pair 至少不擴張寬度（弱條件、容忍字型不帶 kern 表）| ✅ |
| (f) ligature "fi"：1-2 glyph 合理區間 | liga feature 預設開、不同字型寬度容忍 | ✅ |
| (g) CJK「中」shape 有效 advance | 即使是 .notdef glyph、advance 仍非負 | ✅ |
| (h) shape 純函式（兩次同輸入 → byte-identical 輸出）| **可 cache** 前提證明（紀律 #1 / #6 教訓）| ✅ |
| (i) harfbuzzjs module 可 require | 模組可用基本 sanity | ✅ |

**10/10 test 全綠**（5 既有 + 5 新）、103ms。

### 2. Bundle size 測量

```
node_modules/harfbuzzjs/
├── hb.wasm     388K  ← 核心 shaping
├── hbjs.js      53K  ← 高層 API
├── hb.js        24K  ← loader
└── hb-subset.wasm  621K  ← 字型 subsetting（選用、本 spike 不需要）
總 minimum 整合：388K + 53K + 24K ≈ 465K
```

對比當前 IIFE bundle（`canvas-editor-custom.umd.js`）：

| 階段 | bundle size | HarfBuzz 影響 |
|---|---|---|
| 當前（Sprint 126 結尾）| ~126KB（gzipped 估）| 0 |
| 整合 HarfBuzz core only | ~590KB（+465KB） | **+369%**（極大）|
| 整合 HarfBuzz core + subset | ~1.2MB | **+877%** |

→ **Bundle 影響顯著**。Production canvas-editor + HarfBuzz core 加 +465KB 不合理（user 每次載 page 都要下載）。**VR pipeline 整合可接受**（test-only、puppeteer 已 cache）。

### 3. Async vs Sync 整合分析

| 操作 | 同步 / 非同步 | 整合難度 |
|---|---|---|
| `await loadHarfBuzz()` | async | init-time 一次性、可 await |
| `hb.createBlob / createFace / createFont` | sync | 字型載入後 sync |
| `hb.shape(font, buffer)` | **sync** | 每次 measureWidth() 可同步 call |
| `buffer.json()` | sync | sync |

→ **FontMetricsAdapter.ts 註解「HarfBuzz shape 是 async」實際上不完全正確**。shape 本身 sync、只是 hb instance 載入 async。整合方案：

```ts
// 整合 sketch
class HarfBuzzMetrics implements TextMetrics {
  private hb: HBInstance;  // 預先 await load
  private fontCache = new Map<string, HBFont>();

  measureWidth(text: string, props: RunProps): Pt {
    const font = this.getOrLoadFont(props.fontFamily);  // sync, from cache
    const buf = this.hb.createBuffer();
    buf.addText(text);
    buf.guessSegmentProperties();
    this.hb.shape(font, buf);
    return buf.json().reduce((s, g) => s + g.ax, 0);  // sync
  }
}
```

整合複雜度：**中等**（pre-load + cache pattern、與 FontLoader.ts opentype.js 整合手法類似）。

### 4. 與既有 pipeline 衝突點

| 衝突項 | 狀況 |
|---|---|
| TextMetrics interface | sync measureWidth — HarfBuzz shape 是 sync、無衝突 |
| FontMetricsAdapter | 目前用 opentype.js metrics-only；可加 HarfBuzz width path、共存 |
| LayoutCache（Sprint 58）| 整合 HarfBuzz 後 cache key 需加 hb-version；可重用 |
| Bundle 大小 | **VR pipeline 可接受、production canvas-editor 不可接受** |
| Sprint 127 結論 | Production canvas-editor 不走自家 pipeline、HarfBuzz 在 production 無消費者 |

### 5. Autonomous GO/NO-GO decision

候選 outcome：

| 決策 | scope | 收益 | 風險 |
|---|---|---|---|
| **GO-1：整合到 VR pipeline only** | 3-5 sprint（HarfBuzzMetrics class + integration test + VR pipeline 注入 + per-fixture delta + promote default-on）| VR 收斂預期 -1~3%（kerning / 字距精準）| HarfBuzzMetrics 與 opentype.js 雙路徑維護成本、可能撞 Sprint 62 IIFE bundle 同類陷阱 |
| **GO-2：整合到 production**（依賴 Sprint 127 Strategy A）| 8-12 sprint（含 Sprint 127 Strategy A 5-8 sprint）| production user 享受 kerning / ligature 改善 | Bundle +465KB、production user 流量大、Sprint 127 已決策 defer production 路徑 |
| **NO-GO：維持現狀**（HarfBuzz spike 留 reference、不整合）| 0 sprint | 0 收益 | 預期 VR -1~3% 失去 |
| **DEFER-1：列為階段 D 候選**（Phase 5 之後考慮）| defer | 待 A 級 Phase 3 重生 goldens 後再評估 | 階段 B 主軸不被打斷 |

**autonomous 決策：DEFER-1（列為階段 D 候選）**。理由：

1. **VR mean 已在 A- 級邊緣**（0.073191、A- 標準 ≤ 0.10）；HarfBuzz 整合預期 -1~3% 收益、屬「邊緣優化」
2. **階段 C（Sprint 136-145）重生 goldens 用 Word desktop 渲染** = 換 metric anchor、會打亂 VR baseline；HarfBuzz 整合若在階段 C 前做、可能要重做兩次
3. **Sprint 127 已 defer production migration**；GO-2 失去其依賴；GO-1 only-VR 收益已被 Sprint 65 FontMetricsAdapter default-on 部分達成
4. **規畫書 §Phase 5 列 OMML / SmartArt / Charts**（屬「未開始」）優先級更高、scope 5 sprint+
5. 階段 B 主軸（Phase 1-4 漏項）尚未做完（cluster 4 Sprint 130-131 Phase 4 Style 才開工）

**這個決策可逆**：未來如階段 C 完成、goldens 已 word-anchor、可重啟 HarfBuzz 整合作為「精準 kerning」收尾項目（屬階段 D 末或階段 E 內）。

### 6. Spike 落地

Sprint 128 spike test 10 條留在 `tests/unit/HarfBuzzSpike.test.ts`、作為「整合可行性已驗」的 reference。未來如重啟整合、可從 spike test 出發直接設計 HarfBuzzMetrics class。

### 7. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **1033 passed + 1 skipped**（從 1028+1 起、+5 新 Sprint 128 spike test）|
| L2 VR v14 | **跳過**（spike test 不動 production code、未動 bundle / pipeline）|
| L3 Spot check | ✅ harfbuzzjs module size 量測完成、async/sync 分析完成、autonomous 決策有 rationale |
| L4 Odoo backend | **跳過** |

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `tests/unit/HarfBuzzSpike.test.ts` | +95 行 / 5 新 spike test（continuation of Phase D.2）| 進階能力驗證 + 純函式驗證 |
| `docs/sprint128_harfbuzz_wasm_spike.md` | 本 audit doc | 紀錄 spike findings + bundle size + autonomous DEFER-1 決策 |
| `docs/autonomous_roadmap.md` | Sprint 128 ✅ + 階段 B cluster 3 (127-128) 完成 + 進度表 | 進度同步 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | 標頭最後更新 + §Phase 2 註記 HarfBuzz defer 到階段 D 候選 | 同步 |

### Test 數變動

- Sprint 127 結尾：vitest 1028 + 1 skipped
- Sprint 128 結尾：vitest **1033 + 1 skipped**（+5）/ Odoo backend 31（未動）

### VR 數變動

不跑（spike test only、無 production code 變動）。VR mean 0.073191（Sprint 126 結尾）。

### 規畫書 §0.2 Phase 完成度

- Phase 2 字型：仍「部分」（FontMetricsAdapter opt-in）；Sprint 128 確認 HarfBuzz 技術可行但 defer 階段 D 後
- 新增 explicit 狀態：「HarfBuzz spike 完整、整合 deferred autonomous 決策」

---

## Root cause

**為什麼 HarfBuzz 整合到現在還沒做**：

1. Phase D.2（Sprint 50+ era）已落地 5 條基本 spike test、證明技術可行
2. 後續 Sprint 51-65 走 cache 五連發 + FontMetricsAdapter（opentype.js 路徑）、HarfBuzz 整合需求被「opentype.js metrics-only 路徑」滿足
3. FontMetricsAdapter.ts 註解「HarfBuzz shape 是 async」**部分不正確**（shape 本身 sync、只是 load async）、可能誤導後續 sprint 不接
4. Sprint 128 第一次正式 audit、修正 mental model、做 GO/NO-GO 決策

**為什麼 DEFER-1 是正解**：

- 整合 GO-1 / GO-2 都需要 scope 5+ sprint、超過 cluster 3 (127-128) budget
- 階段 C 重生 goldens 會打亂 VR baseline、整合放階段 C 後更划算
- VR mean 已 A- 級邊緣、HarfBuzz 邊際收益相對於工程量低
- 階段 D / E 仍有 Phase 5 高優先項（OMML / 追蹤修訂）

---

## 紀律

### 紀律 #3 應用（Sprint 128）

> 高風險改造前先 probe sprint 收集事實。

Sprint 128 完整應用 — 5 條新 spike test 驗證進階能力、量 bundle size、分析 async/sync、列 4 candidate decisions。**沒貿然開整合工程**。

### 紀律 #4 應用（Sprint 128）

> 負面結果 sprint 仍有結構價值；揭示隱性 assumption 是真實學習。

Sprint 128 揭示：

1. FontMetricsAdapter 註解「HarfBuzz shape 是 async」**部分不正確**、shape 本身 sync
2. Bundle size 影響極大（+465KB）、production 整合不只是 sync/async 問題
3. Sprint 127 production defer 影響 GO-2 可行性

### 紀律 #22 候選跨 sprint 驗證進展 1 → 2（Sprint 127 → 128）

紀律 #22 候選「external 候選 ≠ scope 小、開工前 probe」連續 2 sprint 應用：

- Sprint 127 probe production migration、autonomous Strategy D
- Sprint 128 probe HarfBuzz integration、autonomous DEFER-1

兩 sprint 都成功 catch「mental model vs 實況」差距、避免貿然開大型工程。

跨 sprint 驗證 2 次、Sprint 130+ 若同類 probe 模式可完成 3 次驗證、升正式紀律 #22.a。

### 紀律 #18.d 持續

> 「待 user 決策」候選的 autonomous 收口必須讀原始設計意圖後才決。

Sprint 128 讀規畫書 §Phase 2.1 + §11.3 心理建設「12-36 個月旅程」+ Sprint 65 promote FontMetricsAdapter 歷史後、autonomous 決策 DEFER-1。decision rationale 寫進 audit doc。

---

## 後續

### Sprint 129（原排：階段 B Phase 4 Style 卡 130 起、Sprint 129 為 HarfBuzz；Sprint 127 swap 後修正）

**Sprint 129 = 階段 B cluster 4 開工：Phase 4.1 Theme tint/shade 演算法（HSL luminance）**（原排 Sprint 130 提前一格）。

### Sprint 128+ 候選（defer to user 或 階段 D 後）

- **HarfBuzz GO-1**（VR pipeline only 整合）：3-5 sprint、預期 VR -1~3%；建議階段 C 重生 goldens 後評估
- **HarfBuzz GO-2**（production 整合）：依賴 Sprint 127 Strategy A、defer 給 user
- **`hb-subset.wasm` 整合**：字型 subsetting 可減小 bundle、但本 sprint 不需

---

## Sprint 128 結尾累積指標

- vitest **1033 passed + 1 skipped**（+5）
- VR mean 0.073191（未跑）/ failed 0 / compared 126
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 1 OOXML 78% / Phase 2 字型 部分（HarfBuzz spike 完整、整合 deferred）
- 21 ADR / 19 條紀律 + 6 子 + 3 候選（無新增、#22 候選跨 sprint 驗證進展 2/3）
- Sprint audit doc 數 127 → **128**
- 階段 B cluster 3 (127-128) **完成**、皆為 probe sprint + autonomous decision、皆 defer 真正執行給 user 或階段 D 後

---

## File-level summary

```
M  addons/dobtor_doc_editor/tests/unit/HarfBuzzSpike.test.ts  (+95 行 / 5 新 spike test)
A  addons/dobtor_doc_editor/docs/sprint128_harfbuzz_wasm_spike.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 128 ✅ + cluster 3 完成 + 進度表)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (Phase 2 註記 HarfBuzz defer)
```

無 production code / model / view / ACL / bundle 變動。Sprint 128 spike + autonomous DEFER 決策。
