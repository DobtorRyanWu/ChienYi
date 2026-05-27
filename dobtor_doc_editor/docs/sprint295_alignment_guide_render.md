# Sprint 295 — alignment guide visual indicator (pure-fn render data) ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy C+ utility extraction

**日期**：2026-05-27（週三）
**類型**：⑤ follow-up — render-data module + 12 tests
**前置**：Sprint 291 overlay_geometry pure-fn utility

User 指令：「繼續執行」⑤ honest gap「alignment guide visual indicator 未做」。

---

## 範圍

Sprint 291 抽了 `computeAlignGuides` / `pickSnapTargets` 兩個對齊計算的 pure-fn；
本 sprint 補「拿到 guides 後怎麼視覺化」的 pure-fn 資料層：

| Module | 角色 |
|---|---|
| `overlay_geometry.ts`（Sprint 291）| `AlignGuide` 計算 / snap target 選擇 |
| **`alignment_guide_render.ts`（Sprint 295）**| **`buildGuideStyles` / `applySnapToRect` — guide → 樣式資料** |

caller（doc_editor.js OWL Component）拿到 `GuideStyle[]` 後 spread inline `style`
或映射 `className` 即可繪製，無需自己算座標。

紀律 #18 scope-down：**不接 doc_editor.js OWL Component**（避免破 13 Playwright
E2E）；未來 polish sprint 才 wire 進 doc_editor.js（opt-in feature flag）。

紀律 #21：純資料 transformation、無 side effect / DOM / RPC 依賴、不污染 VR pipeline。

---

## 設計細節

### `buildGuideStyles(guides, pageBounds, opts) → GuideStyle[]`

```typescript
interface GuideStyle {
  axis: 'x' | 'y';
  left: number;        // absolute X
  top: number;         // absolute Y
  width: number;       // X guide = lineThickness; Y guide = pageBounds.width
  height: number;      // X guide = pageBounds.height; Y guide = lineThickness
  className: string;   // 'guide-page' / 'guide-sibling' / 自訂
  siblingIndex?: number;
}
```

- X 軸 guide → 垂直線：寬度 = lineThickness、高度 = pageBounds.height
- Y 軸 guide → 水平線：寬度 = pageBounds.width、高度 = lineThickness
- **去重**：相同 axis + 相同 value 視為同一條（reason 不同也合併、避免重畫）
- className 區分 page guide（page-edge/page-center）與 sibling guide（sibling-edge/sibling-center）

### `applySnapToRect(rect, snapX?, snapY?) → { x, y }`

把 `pickSnapTargets` 的 snapX / snapY 套用到 rect.x / rect.y。
任一軸 undefined 時對應軸不變。caller 在 drag mousemove 時 inline 用。

### caller 整合範例（未來 wire 進 doc_editor.js 時）

```typescript
const guides = computeAlignGuides(moving, siblings, pageBounds, threshold);
const styles = buildGuideStyles(guides, pageBounds);
const { snapX, snapY } = pickSnapTargets(moving, guides);
const snapped = applySnapToRect(moving, snapX, snapY);

// render guides
for (const s of styles) {
  // <div style={s.left,top,width,height} class={s.className}/>
}

// apply snap to drag rect
overlayEl.style.left = `${snapped.x}px`;
overlayEl.style.top = `${snapped.y}px`;
```

---

## 12 unit test 場景（[tests/unit/sprint295_alignment_guide_render.test.ts](../tests/unit/sprint295_alignment_guide_render.test.ts)）

### buildGuideStyles X axis（2 案）
| Test | 驗證 |
|---|---|
| X 軸 guide 完整樣式 | left/top/width/height/className/siblingIndex 全對 |
| lineThickness=3 | width=3 |

### buildGuideStyles Y axis（1 案）
| Test | 驗證 |
|---|---|
| Y 軸 guide 完整樣式 | top=value、width=pageW、height=lineThickness |

### className 區分（3 案）
| Test | 驗證 |
|---|---|
| page-* reason | className = 'guide-page' |
| sibling-* reason | className = 'guide-sibling'、siblingIndex preserved |
| 自訂 className | pageClassName/siblingClassName 套用 |

### 去重（3 案）
| Test | 驗證 |
|---|---|
| 相同 axis+value 多 reason | 合併為 1 條（取第一個） |
| 同 value 不同 axis | 不合併（X + Y 各自） |
| 空 guides | 回空陣列 |

### applySnapToRect（3 案）
| Test | 驗證 |
|---|---|
| snapX + snapY 都有 | rect 完全採用 snap |
| 只 snapX | y 保留原值 |
| 都 undefined | rect 不變 |

**12/12 passed / 18ms**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy C+：pure-fn module + 12 tests、0 行 doc_editor.js 變動 | ✅ |
| #14.b clean scope：commit 含 1 新 module + 1 test + 1 doc + snapshot | ✅ |
| #18 scope-down：不接 doc_editor.js OWL Component；不寫 CSS classes 定義（caller 自管） | ✅ |
| #21 純資料：無 side effect / DOM / RPC、不污染 VR pipeline | ✅ |
| #22 verify：3 種 axis + 3 種 className + 3 種去重 + 3 種 snap apply | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 295

vitest 2251 → 2263 hypothesis（+12）/ tsc 2 pre-existing 不增 / +~95 行 utility / 0 行 OWL Component。

下一步：Sprint 296 = ③ point-in-polygon helper for wrapTight layout（user「繼續執行」honest gap）。
