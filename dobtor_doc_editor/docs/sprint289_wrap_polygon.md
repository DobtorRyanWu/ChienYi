# Sprint 289 — ③ Phase 3.4 wrapTight 多邊形 capture ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy A capture-only

**日期**：2026-05-27（週三）
**類型**：③ cluster — wrapPolygon parser + AST + 11 tests
**前置**：Sprint 287 wp:anchor 完整 capture

User 指令：「繼續執行 1-6」cluster ③（原 ③ 為 12h cap、本 sprint 為 capture-only 第 1 步）。

---

## 範圍

Sprint 287 補了 anchor metadata + wrapText，但 wp:wrapTight / wp:wrapThrough 內的
`<wp:wrapPolygon>` 多邊形輪廓仍未 capture。本 sprint 補：

| 元素 | Sprint 289 前 | Sprint 289 後 |
|---|---|---|
| `<wp:wrapPolygon>` | 完全未讀 | capture |
| `<wp:start x y/>` | — | WrapPolygonPoint |
| `<wp:lineTo x y/>` | — | WrapPolygonPoint[] |
| `edited` 屬性 | — | Boolean (truthy only) |

Strategy A capture-only：parser + AST，**render 端 polygon clip 不做**（Phase 3.4
完整 wrapTight 需走 polygon point-in-test、render layout 重寫，留 future cluster；
紀律 #18 scope-down）。

---

## 設計細節

### AST（[types.ts](../static/src/core/ooxml/ast/types.ts)）

```typescript
export interface WrapPolygonPoint {
  x: number;  // raw drawing coordinate (OOXML §20.4.2.17 ST_Coordinate)
  y: number;
}

export interface WrapPolygon {
  edited?: boolean;
  start: WrapPolygonPoint;
  lineTo: WrapPolygonPoint[];
}
```

座標單位 = drawing coordinates（不直接是 EMU）。Office 慣例 21600 ≈ 圖片全寬/高，
caller 拿 raw int、render 時配合 image extent 縮放。

FloatImageNode + FloatTextBoxNode 各 +1 optional 欄位：`wrapPolygon?: WrapPolygon`。

### Parser

`parseWrapPolygon(anchorEl)`：
1. 在 anchor 子節點找 `wp:wrapTight` 或 `wp:wrapThrough`
2. 找其內 `wp:wrapPolygon`
3. 解 `<wp:start>` 必須存在、x/y 必為有效 int → 否則整體 undefined
4. 解 `<wp:lineTo>` 至少 1 個有效點 → 否則整體 undefined
5. 缺屬性 / 非數字 → 該點 skip、其餘保留

---

## 11 unit test 場景（[tests/unit/sprint289_wrap_polygon.test.ts](../tests/unit/sprint289_wrap_polygon.test.ts)）

### wrapTight（7 案）

| Test | 驗證 |
|---|---|
| 完整四角矩形 + edited="1" | start + 4 lineTo 全 capture、順序保留 |
| 不規則 8 點多邊形 | 全部 capture、座標精準 |
| 無 edited 屬性 | polygon 存在、edited undefined |
| 無 wrapPolygon 子元素 | wrapPolygon undefined |
| wrapPolygon 缺 start | undefined（不算合法 polygon） |
| wrapPolygon 有 start 但無 lineTo | undefined |
| 點屬性缺/非數字 | 該點略過、其餘保留 |

### wrapThrough（1 案）

| Test | 驗證 |
|---|---|
| wrapThrough + polygon | capture（與 wrapTight 對稱）、edited="0" 視為 undefined |

### 其他 wrap mode 不 capture（3 案）

| Test | 驗證 |
|---|---|
| wrapSquare | wrapPolygon undefined |
| wrapNone | wrapPolygon undefined |
| wrapTopAndBottom | wrapPolygon undefined |

**11/11 passed / 24ms**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A：parser + AST + tests、capture-only | ✅ |
| #14.b clean scope：commit 含 1 AST + 1 parser + 1 test + 1 doc + snapshot | ✅ |
| #18 scope-down：render polygon clip 留 Phase 3.4 完整 wrapTight；不寫 writer（Sprint 192 wp:inline 降級延用） | ✅ |
| #21 不污染既有 VR：writer 不動、render 不消費新 field、layout 不變 | ✅ |
| #22 verify：8 個 happy/edge 案 + 3 個負面對照 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 289

vitest 2180 → 2191（+11）/ tsc 2 pre-existing 不增 / +~40 行 AST + ~50 行 parser / 0 行 writer。

下一步：Sprint 290 = ④ Phase 5.4+5.5 追蹤修訂 + 註解（backend / AST / parser
side、UI 不在本 cluster 範圍 — UI 端需 OWL Component 重寫超出單 sprint scope）。
