# Sprint 296 — Phase 3.4 wrapTight polygon layout 數學工具 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy C+ utility extraction

**日期**：2026-05-27（週三）
**類型**：③ follow-up — pure-fn 幾何工具 + 18 tests
**前置**：Sprint 289 wrapPolygon AST capture

User 指令：「繼續執行」③ honest gap「wrapPolygon render clip 未做（Phase 3.4 完整 wrapTight 留 future）」。

---

## 範圍

Sprint 289 已 capture `<wp:wrapPolygon>` 到 AST（座標為 drawing coordinates raw int）；
本 sprint 補 Layout 端需要的幾何函式：

| 函式 | 用途 |
|---|---|
| `transformWrapPolygon(polygon, imageRect, drawingUnits?)` | drawing coords → 絕對 pt 座標（圖片位置 + 比例 scale） |
| `polygonBoundingBox(polygon)` | 計算 min/max XY |
| `pointInPolygon(point, polygon)` | ray-casting 演算法 |
| `rectIntersectsPolygon(rect, polygon)` | 矩形 ↔ 多邊形 相交（bbox 快篩 + 角點 + 邊相交） |

紀律 #18 scope-down：**不接 Layout engine**（Phase 3.4 完整 wrapTight 需重寫
LineBreaker 換行邏輯、超出單 sprint scope）；未來 polish sprint 才 wire 進
`LineBreaker` / `Paginator`。

紀律 #21：純函式、無 side effect、不污染 VR pipeline。

---

## 設計細節

### `transformWrapPolygon`

OOXML drawing coordinates 慣例 21600 ≈ 圖片全寬/高；本函式把 polygon 點從
drawing coords 轉成絕對 pt 座標：

```typescript
const transformed = transformWrapPolygon(polygon, { x: 100, y: 200, width: 144, height: 72 });
// drawing coord 21600 → 圖片右邊緣 → x = 100 + 21600 * 144/21600 = 244
```

### `rectIntersectsPolygon` 演算法

保守 SAT-lite（可能 false-positive 但不 miss）：
1. polygon bbox 與 rect 完全不相交 → 必不相交
2. polygon 任一頂點在 rect 內 → 相交
3. rect 四角任一在 polygon 內（用 pointInPolygon）→ 相交
4. polygon 邊 ↔ rect 邊 line-line intersection → 相交
5. 都沒命中 → 不相交

紀律 #18：不做精確 SAT（Separating Axis Theorem）；對 wrapTight UI 級精度足夠、
避免演算法複雜度爆炸。

### caller 整合範例（未來 wire 進 Layout 時）

```typescript
// Layout 換行決策時
const polyAbs = transformWrapPolygon(image.wrapPolygon, {
  x: image.posH.posOffset, y: image.posV.posOffset,
  width: image.width, height: image.height,
});

for (const lineBox of candidateLines) {
  if (rectIntersectsPolygon(lineBox, polyAbs)) {
    // line 與 polygon 撞 → 換到下一空白區
    advanceToFreeSlot(lineBox, polyAbs);
  }
}
```

---

## 18 unit test 場景（[tests/unit/sprint296_wrap_polygon_math.test.ts](../tests/unit/sprint296_wrap_polygon_math.test.ts)）

### transformWrapPolygon（3 案）
| Test | 驗證 |
|---|---|
| 21600 → 144×72 pt | scale + 位移正確 |
| drawingUnits=100 | scale 直接 = imageRect.width/100 |
| image at non-zero origin | 位移正確 |

### polygonBoundingBox（4 案）
| Test | 驗證 |
|---|---|
| 規則矩形 | minX/minY/maxX/maxY 全對 |
| 不規則多邊形 | bbox 涵蓋所有點 |
| 空 polygon | 0/0/0/0 |
| 單點 | minX=maxX、minY=maxY |

### pointInPolygon（5 案）
| Test | 驗證 |
|---|---|
| 點在矩形正中 | true |
| 點在矩形外右側 | false |
| 點在矩形左下 | false |
| < 3 點 polygon | 必 false |
| 三角形內外判定 | 內 true / 外 false |

### rectIntersectsPolygon（6 案）
| Test | 驗證 |
|---|---|
| rect 完全在 bbox 外 | false |
| rect 完全包住 polygon | true（polygon 點在 rect 內） |
| rect 完全在 polygon 內 | true（rect 角點在 polygon 內） |
| rect 與 polygon 邊重疊 | true |
| < 3 點 polygon | 必 false |
| L 形 polygon 凹角空隙 | false（rect 在凹角內、不碰邊） |

**18/18 passed / 11ms**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy C+：純函式 module + 18 tests、0 行 Layout engine 變動 | ✅ |
| #14.b clean scope：commit 含 1 新 module + 1 index 更新 + 1 test + 1 doc + snapshot | ✅ |
| #18 scope-down：不接 LineBreaker / Paginator；Phase 3.4 完整 wrapTight 留 future polish | ✅ |
| #21 純函式：無 side effect、不污染 VR pipeline | ✅ |
| #22 verify：4 種函式全覆蓋 + 多 polygon 形狀（矩形/三角形/L 形）+ edge case | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 296

vitest 2263 → 2281 hypothesis（+18）/ tsc 2 pre-existing 不增 / +~140 行 utility / 0 行 Layout engine。

下一步：Sprint 297 = ① canvas-editor integration audit doc（user「繼續執行」honest gap）。
