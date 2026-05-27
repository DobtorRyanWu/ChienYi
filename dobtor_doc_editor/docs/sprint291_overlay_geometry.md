# Sprint 291 — ⑤ Phase 8.2.2 overlay 幾何工具抽取 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy C+ utility extraction

**日期**：2026-05-27（週三）
**類型**：⑤ cluster — pure-fn utility module + 19 tests
**OVERRIDE**：user 「繼續執行 1-6」語句 = explicit OVERRIDE（原 ADR-022 條件啟動項已於 Sprint D MVP 落地）

User 指令：「繼續執行 1-6」cluster ⑤（Phase 8.2.2）。

---

## Scope decision

Phase 8.2.2 overlay 絕對定位於 Sprint D（2026-05-23）已 MVP 落地（layout_mode
Selection + overlay layer + drag + scale 聯動），Sprint F 補 resize 控制點 +
越界 clamp。**剩餘 polish 項目**：

| 項目 | 狀態 |
|---|---|
| layout_mode toggle | ✅ Sprint D |
| overlay layer 渲染 | ✅ Sprint D |
| 拖曳 mousedown/move/up | ✅ Sprint D |
| scale 縮放聯動 | ✅ Sprint D |
| resize 控制點（右下角） | ✅ Sprint F |
| 越界 clamp（拖曳） | ✅ Sprint F |
| **越界 clamp（resize）** | 部分（min 限制 done，越右下緣未 cap） |
| **對齊輔助線（page edge / center / sibling）** | ❌ 未做 |
| 多選 | ❌ 未做 |

本 sprint 不直接做 UI polish（doc_editor.js 動到 OWL Component 體積大、易破壞
現行 E2E）；改抽 **pure-fn 幾何工具** + **19 unit tests** 為未來 polish sprint
鋪基礎（Strategy C+ extraction）。

---

## 設計細節

### 新增模組：[overlay_geometry.ts](../static/src/components/doc_editor/overlay_geometry.ts)

```typescript
export interface Rect { x: number; y: number; width: number; height: number; }
export interface Bounds { width: number; height: number; }

export function clampPosToBounds(rect: Rect, bounds: Bounds): { x: number; y: number };
export function clampSizeToBounds(rect: Rect, bounds: Bounds, minW: number, minH: number): { width: number; height: number };
export function computeAlignGuides(moving: Rect, siblings: readonly Rect[], pageBounds: Bounds, threshold: number): AlignGuide[];
export function pickSnapTargets(moving: Rect, guides: readonly AlignGuide[]): { snapX?: AlignGuide; snapY?: AlignGuide };
```

### 對齊規則（computeAlignGuides）

對 X / Y 兩軸分別計算 6 種 candidate：
- page-edge-start（page 0 對齊）
- page-edge-end（page max 對齊）
- page-center（page 中線對齊）
- sibling-edge-start（其他 overlay 左/上緣對齊）
- sibling-edge-end（其他 overlay 右/下緣對齊）
- sibling-center（其他 overlay 中線對齊）

threshold 內全部回（caller 可同時 render 多條輔助線、`pickSnapTargets` 取最近一條做實際 snap）。

### 紀律 #21：不動 doc_editor.js 既有 inline clamp

本 sprint 為 utility extraction：utility 與既有 inline clamp 行為一致；doc_editor.js
未 refactor 接入（紀律 #21 不污染現行 OWL Component 行為、避免破 13 Playwright E2E）。
**未來 polish sprint** 才接 utility refactor、render alignment guide visual indicator。

---

## 19 unit test 場景（[tests/unit/sprint291_overlay_geometry.test.ts](../tests/unit/sprint291_overlay_geometry.test.ts)）

### clampPosToBounds（4 案）
| Test | 驗證 |
|---|---|
| 內部不變 | 100,200 + 50×30 → 100,200 |
| 負座標 clamp 0 | -10,-20 → 0,0 |
| 超出右下 clamp max | 600,900 → 545,812 |
| 寬高 > bounds | 位置 clamp 0（size 不在此函式範圍） |

### clampSizeToBounds（4 案）
| Test | 驗證 |
|---|---|
| 不超界 | 不變 |
| 超界 → cap | 200×200 在 (500,800) → 95×42 |
| < min → 提到 min | 10×5 → 40×20 |
| 剩餘 < min → 退化為剩餘 | min 40 但只剩 10 → 10 |

### computeAlignGuides page（3 案）
| Test | 驗證 |
|---|---|
| 靠近 page 左緣 | page-edge-start guide |
| 靠近 page 中線 | page-center guide |
| 遠離所有 guide | 空陣列 |

### computeAlignGuides sibling（4 案）
| Test | 驗證 |
|---|---|
| 左緣對齊 | sibling-edge-start + siblingIndex 0 |
| 右緣對齊 | sibling-edge-end |
| 中線對齊 | sibling-center |
| 多 sibling | siblingIndex 各自正確 |

### pickSnapTargets（3 案）
| Test | 驗證 |
|---|---|
| X/Y 各最近 | bestDx / bestDy 最小 |
| 無 guide | snapX/snapY undefined |
| 只 X guide | snapY undefined |

### 整合（1 案）
| Test | 驗證 |
|---|---|
| drag 越界 → clamp → guide | 鏈式套用正確、最終 page-edge-start guide 命中 |

**19/19 passed / 9ms**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy C+：純 utility module + 19 tests、0 行 doc_editor.js 變動 | ✅ |
| #14.b clean scope：commit 含 1 新 utility + 1 test + 1 doc + snapshot | ✅ |
| #18 scope-down：不接 doc_editor.js（OWL Component refactor 留 future polish sprint）；不寫 UI render of guides | ✅ |
| #21 不污染現行 OWL：13 Playwright E2E 不變、現行 inline clamp 邏輯保留 | ✅ |
| #22 verify：19 案 + 4 種函式全覆蓋 + integration scenario | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |
| ⑤ OVERRIDE：user「繼續執行 1-6」= explicit override；條件啟動項認定為 polish 範圍 | ✅ |

---

## End of Sprint 291

vitest 2197 → 2216（+19）/ tsc 2 pre-existing 不增 / +~110 行 utility / 0 行 OWL Component。

下一步：Sprint 292 = ⑥ Phase 7 Worker（user「繼續執行 1-6」= explicit OVERRIDE）。
