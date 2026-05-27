# Sprint 288 — ① Phase 2.1-2.3 整合 façade `LayoutPipeline` ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy A

**日期**：2026-05-27（週三）
**類型**：① cluster 第 1 sprint — production-grade façade
**規畫書對應**：§Phase 2.1-2.3 整合
**前置**：Sprint 277-281 LineBreaker MVP + ShapingEngine browser-compat + ShapingFontChain spike

User 指令：「啟動。Phase 2.1-2.3 全套：ShapingEngine 封裝 + 字型載入器 + opentype.js 取代 measureRun。每完成一小段 commit、最多 24 小時、每 5 sprint 暫停 30 分鐘。」

---

## 範圍

把先前 spike 階段各自獨立的 Phase 2 子模組接成單一 production-grade façade：

```
ShapingEngine (Sprint 265-268)
ShapingFontChain (Sprint 280)
FontMetrics (Sprint 268)        ─┬─→ LayoutPipeline (Sprint 288)
LineBreaker (Sprint 277)         │
                                 ▼
                          Phase 6 自寫 Layout 消費
```

### 新增 API

```typescript
// 基本：caller 自管 engine + fontBytes
async function layoutParagraph(
  engine: ShapingEngine,
  opts: LayoutParagraphOptions,
): Promise<ParagraphLayoutResult>;

// 進階：fontChain + URL fetch 自動化
async function layoutParagraphWithFontChain(
  engine: ShapingEngine,
  opts: LayoutParagraphWithFontChainOptions,
): Promise<ParagraphLayoutWithChainResult>;
```

### `ParagraphLayoutResult`

| 欄位 | 來源 |
|---|---|
| `lines: BrokenLine[]` | breakParagraph (LineBreaker) |
| `maxLineWidthPt` | breakParagraph |
| `totalLines` | breakParagraph |
| `lineHeightPt` | resolveOoxmlLineHeight |
| `lineHeight: OoxmlLineHeightResult` | resolveOoxmlLineHeight（含 rule / naturalHeightPt / lineValue） |
| `baselineOffsetPt` | baselineOffsetPt |
| `fontMetrics: FontMetricsResult` | readFontMetrics |

---

## 設計決策

1. **純函式 façade、無內部全域狀態**：caller 自管 engine lifecycle（避免泄漏、避免測試干擾）
2. **`fontBytes` 與 `engine` 解耦**：engine 內部把 bytes 餵給 hb-wasm 後不保留可讀副本；readFontMetrics 仍需原始 bytes
3. **`lineRule` 完整支援 OOXML 規格**：natural / auto / exact / atLeast 四種、與 Sprint 267 `resolveOoxmlLineHeight` 對齊
4. **`spaceWidthPt` 可注入**：caller 已知 metrics 時避免每次 await wasm
5. **fontChain 進階入口可選**：基本 layout 不強制走 chain（避免 single-font test 過度複雜）

---

## 9 unit test 場景（[tests/unit/sprint288_layout_pipeline.test.ts](../tests/unit/sprint288_layout_pipeline.test.ts)）

### layoutParagraph（7 案）

| Test | 驗證 |
|---|---|
| 整合 layout 全欄位 | lines + lineHeight + baseline + fontMetrics 都拿到 |
| lineRule=auto 2.0 | 行高 = natural × 2、與 natural 對照 |
| lineRule=exact 30pt | 固定 30pt、忽略 natural |
| lineRule=atLeast < natural | 取 natural（下限不觸發） |
| lineRule=atLeast > natural | 取 value（下限觸發） |
| 空字串 | lines [] / maxLineWidthPt 0 / metrics 仍能讀 |
| spaceWidthPt 注入 | 結果與不注入一致 |

### layoutParagraphWithFontChain（2 案）

| Test | 驗證 |
|---|---|
| primary 成功 | attemptedCount=1、無 fallback warn |
| primary 失敗 + fallback 成功 | attemptedCount=2、warn 觸發、loadedAs 仍 primary 名 |

**9/9 passed / 1.29s（含 wasm shape + opentype parse）**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A：production code 擴張 façade + 9 tests | ✅ |
| #14.b clean scope：commit 含 1 新 module + 1 index 更新 + 1 test + 1 doc + snapshot | ✅ |
| #18 scope-down：façade 不接 canvas-editor / 不取代 ctx.measureText / mixed run 等留 Phase 6 完整 Layout | ✅ |
| #21 不污染既有 VR：façade 為 read-only API、無 side effect、不入 VR pipeline | ✅ |
| #22 verify：4 種 lineRule 全覆蓋 + 空字串 edge + chain primary/fallback 雙路 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 288

vitest 2171 → 2180 hypothesis（+9 integration test）/ VR 第 68 連 maintained / tsc
2 pre-existing 不增 / +~180 行 LayoutPipeline.ts production code + 14 行 index.ts barrel。

**① cluster 第 1 sprint 完成（Phase 2.1-2.3 整合 façade）**。

下一步候選（① 還可繼續推、依 user「每完成一小段 commit、最多 24 小時、每 5 sprint
暫停 30 分鐘」指令繼續執行 1-6）：
- Sprint 289 = ③ Phase 3.4 wrapTight 多邊形 capture（continuing 1-6 sequence）

依 user 「繼續執行 1-6」指令 — 不停下 review、直接推進到 ③。
