# Sprint 301 — overlay_geometry multi-select / resize-by-handle ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy C+ extraction

**日期**：2026-05-27（週三）
**類型**：⑤ deeper — utility extraction + 21 tests
**前置**：Sprint 291 overlay_geometry pure-fn（clampPos / clampSize / computeAlignGuides / pickSnapTargets）

User 指令：「繼續執行」⑤ 推進 overlay 互動工具第二輪。

---

## 範圍

Sprint 291 補了 single rect 的 clamp + align guide pure-fn；本 sprint 補 multi-select
+ resize-by-handle：

| Module | Sprint | 角色 |
|---|---|---|
| `overlay_geometry.ts` | 291 | single rect clamp + align guide |
| **`overlay_geometry_multi.ts`** | **301** | **resizeRectByHandle / computeMultiSelectBounds / translateMultiSelect / alignMultiSelect / distributeMultiSelect** |

紀律 #18 scope-down：pure-fn + tests；doc_editor.js 未動（避免破 13 Playwright
E2E、同 Sprint 291 政策）。Future polish sprint 再接 utility。

---

## 設計細節

### resizeRectByHandle

8 handle（NW/N/NE/E/SE/S/SW/W）+ delta（mouse 移動量）→ 新 rect：

```
nw → x+=dx, y+=dy, w-=dx, h-=dy
n  → y+=dy, h-=dy
ne → y+=dy, w+=dx, h-=dy
e  → w+=dx
se → w+=dx, h+=dy
s  → h+=dy
sw → x+=dx, w-=dx, h+=dy
w  → x+=dx, w-=dx
```

接著套用 minW / minH（若 w 或 h 縮到下限、x / y 對應反向修正以維持原 anchor 邊）。
Aspect lock 時用 dx / dy 較大者主導另一軸（按 origin aspect）。
bounds 提供時最後套 clamp（消費 Sprint 291 clampPos / clampSize）。

### Multi-select 群組操作

- `computeMultiSelectBounds`：N rect 的 bounding box（min/max xy）
- `translateMultiSelect`：群組移動 with bounds clamp（各 rect 保持相對位置）
- `alignMultiSelect`：left / center-h / right / top / middle-v / bottom 六模式
- `distributeMultiSelect`：均勻分佈（horizontal / vertical 兩軸）

### Distribute 演算法

對中心點排序、首尾不動、中間按相等 center step 重排：
```
step = (lastCenter - firstCenter) / (n - 1)
中間 rect_k.center = firstCenter + step * k
```

---

## 21 unit test 場景（[tests/unit/sprint301_overlay_geometry_multi.test.ts](../tests/unit/sprint301_overlay_geometry_multi.test.ts)）

### resizeRectByHandle（7 案）
- 4 個 corner handles（nw / ne / sw / se）+ 3 個 edge（e / w / s）
- minW 套用 + anchor 反向修正
- preserveAspect lock
- bounds clamp

### computeMultiSelectBounds（3 案）
- N rect bbox
- 空陣列 → null
- 單一 rect 等於該 rect

### translateMultiSelect（2 案）
- 群組移動相對位置保留
- bounds clamp：群組 bbox 不超出 page

### alignMultiSelect（5 案）
- left / right / center-h
- top / bottom / middle-v
- < 2 rect 不對齊

### distributeMultiSelect（3 案）
- horizontal / vertical 均勻分佈
- < 3 rect 直接回原（不需分佈）

**21/21 passed / 13ms**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy C+ extraction：pure-fn + tests | ✅ |
| #14.b clean scope：commit 含 1 新 module + 1 test + 1 doc | ✅ |
| #18 scope-down：doc_editor.js 不動（避免破 13 Playwright E2E、同 Sprint 291 政策） | ✅ |
| #21 不污染既有 production module | ✅ |
| #22 verify：8 handle resize + multi-select 6 align + 2 distribute axis | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 301

vitest +21 / tsc 2 pre-existing 不增 / +~200 行 overlay_geometry_multi.ts / 0 行
doc_editor.js 變動。

下一步：Sprint 302 = ① canvas-editor measureText proxy PROBE。
