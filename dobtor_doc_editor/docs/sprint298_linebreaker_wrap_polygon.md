# Sprint 298 — Phase 3.4 LineBreaker wrap-around polygon 整合 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy A integration spike

**日期**：2026-05-27（週三）
**類型**：③ deeper — LineBreaker + polygon 數學整合 + 9 tests
**前置**：Sprint 277 LineBreaker MVP、Sprint 296 wrap_polygon_math pure-fn

User 指令：「繼續執行」③ 推進 wrapPolygon render clip。

---

## 範圍

Sprint 296 補了 polygon 幾何 pure-fn（transformWrapPolygon / pointInPolygon /
rectIntersectsPolygon）；本 sprint 把它們接進 LineBreaker，產出帶位置的
`PositionedLine[]`：

```typescript
const polyAbs = transformWrapPolygon(image.wrapPolygon, imageRect);
const { lines, endY } = await breakParagraphAroundPolygon(engine, {
  text, startX: 0, startY: 0, lineHeightPt: 14,
  availableWidthPt: 595, fontFamily: 'DejaVuSans', sizePt: 12,
  polygonAbs: polyAbs,
});
// lines: Array<{ text, widthPt, words, x, y }>
```

---

## 設計細節

### 演算法（greedy line break + polygon avoid）

```
for each word in tokenize(text):
  measure wordWidth
  if cur line has no words & curAvailWidth <= 0:
    # 起點被 polygon 卡死 → advance X 到 polygon 右邊
    curX = polygonAbs.maxX + bufferPt
    curAvailWidth = availableWidthAt(curX, curY)
    if still <= 0:
      advance to next line (curY += lineHeight)
  if wordFitsCurAvail:
    add to cur line
  else:
    advance to next line
    retry placement (含 polygon-aware)
```

### `availableWidthAt(x, y)`

- 完全在 polygon Y 範圍外 → 全 availableWidthPt 可用
- line box rect 撞 polygon → 可用寬度 = polygon.minX - x - bufferPt（左邊剩餘空間）
- 否則 → 全寬

### `rectIntersectsPolygon`（從 Sprint 296）

保守 SAT-lite：bbox 快篩 + 角點檢查 + 邊相交。

### 紀律 #18 scope-down

- **單一 polygon**：多 polygon 重疊場景留 future（polygon 並集 / 序列檢查未做）
- **polygon 內部空隙不穿插**：rect 撞 polygon → 整行 advance 至右邊；不做精細
  「polygon 凹陷處塞字」（OOXML 規格實作大多不做此細節）
- **與 LineBreaker MVP 相容**：caller opt-in 才用此函式，既有 `breakParagraph` 不變

---

## 9 unit test 場景（[tests/unit/sprint298_linebreaker_wrap_polygon.test.ts](../tests/unit/sprint298_linebreaker_wrap_polygon.test.ts)）

| Test | 驗證 |
|---|---|
| 無 polygon 影響（Y 不重疊） | 與普通 LineBreaker 一致、全 x=0 |
| Y 完全重疊 → 文字推到右邊 | x > polygon.maxX |
| 多行段落、前後不同 polygon 影響 | 前 affected x>0、後 unaffected x=0 |
| 空字串 | lines=[]、endY=startY |
| endY 公式 | 最後行 y + lineHeight |
| spaceWidthPt 注入 | 結果一致 |
| AST WrapPolygon → transformWrapPolygon → wrap end-to-end | 整合無誤 |
| startX≠0 與 polygon X 範圍重疊 | 推到 polygon 右邊 |
| bufferPt 控制 | polygon.maxX + 10 |

**9/9 passed / 1.33s（含 wasm shape）**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A integration spike：~150 行新模組 + 9 tests | ✅ |
| #14.b clean scope：commit 含 1 新 module + 1 index 更新 + 1 test + 1 doc + snapshot | ✅ |
| #18 scope-down：單一 polygon / 凹陷處不穿插 / caller opt-in / LineBreaker MVP 不動 | ✅ |
| #21 不污染既有 VR：新模組獨立、既有 LineBreaker / Layout / render 不消費、零 regression 風險 | ✅ |
| #22 verify：6 種 polygon scenario + 整合場景 + edge case | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 298

vitest 2281 → 2290 hypothesis（+9）/ tsc 2 pre-existing 不增 / +~155 行 LineBreakerWithPolygon / 0 行 Paginator / Render 變動。

下一步：Sprint 299 = ⑥ BrowserWorkerDispatcher 真實實作（user「繼續執行」honest gap）。
