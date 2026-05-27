# Sprint 293 — Phase 5.4 追蹤修訂剩餘項 capture ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy C+ capture-only

**日期**：2026-05-27（週三）
**類型**：④ follow-up — pPrChange + rPrChange + cellIns/Del/Merge parser/AST 補完整
**前置**：Sprint 174（ins/del）、Sprint 290（moveFrom/moveTo）

User 指令：「繼續執行」④ honest gap「pPrChange/rPrChange/cellIns/cellDel/cellMerge 未做」。

---

## 揭發狀態

| 項目 | Sprint 293 前 | Sprint 293 後 |
|---|---|---|
| `<w:ins>` / `<w:del>` run 包裹 | Sprint 174 done | — |
| `<w:moveFrom>` / `<w:moveTo>` run 包裹 | Sprint 290 done | — |
| `<w:pPrChange>` 段落屬性修訂 | **未做** | parser capture |
| `<w:rPrChange>` run 屬性修訂 | **未做** | parser capture |
| `<w:cellIns>` cell 插入修訂 | **未做** | parser capture |
| `<w:cellDel>` cell 刪除修訂 | **未做** | parser capture |
| `<w:cellMerge>` cell 合併/拆分修訂 | **未做** | parser capture |
| UI accept/reject 面板 | 未做 | future cluster |
| Comments 互動面板 | 未做 | future cluster |

---

## 設計細節

### AST 新增（[types.ts](../static/src/core/ooxml/ast/types.ts)）

```typescript
/** 追蹤修訂共用 metadata */
export interface TrackChangeMeta {
  author?: string;
  date?: string;
  id?: number;
}

// 加入 RunProps
interface RunProps {
  // ...
  rPrChange?: TrackChangeMeta;
}

// 加入 ParagraphProps
interface ParagraphProps {
  // ...
  pPrChange?: TrackChangeMeta;
}

// 加入 CellNode.props
interface CellNode {
  props: {
    // ...
    cellIns?: TrackChangeMeta;
    cellDel?: TrackChangeMeta;
    cellMerge?: TrackChangeMeta & { val?: 'vert' | 'rest' | 'cont'; vMerge?: 'cont' | 'rest' };
  };
}
```

### Parser 變更

| 檔案 | 變更 |
|---|---|
| `ParagraphParser.ts` | `parseParagraphProps` 結尾加 `w:pPrChange` capture；`parseRunProps` 結尾加 `w:rPrChange` capture；新增 `parseTrackChangeAttrs` 私有 helper |
| `TableParser.ts` | `parseCell` 內 `w:tcPr` 區塊加 cellIns/cellDel/cellMerge capture（前先 let 宣告變數、後 propagate 到 RawCell → CellNode.props）；新增 `parseTrackChangeAttrsTbl` 私有 helper |

紀律 #18 scope-down：**不解 old pPr/rPr 子樹**（caller 只拿到「誰在何時改了」、
不拿到「改前的舊值」）。Old value 擷取為 future polish。

### 與 RunRevision 的差異

RunRevision（Sprint 174/290）= 包裹 run 的 `<w:ins>` / `<w:del>` / `<w:moveFrom>` / `<w:moveTo>`，
標記「這個 run 是被插入/刪除/移動」。

TrackChangeMeta（Sprint 293）= 「屬性級或結構級的修訂」，標記「這個段落/run/cell 的
屬性被改了 / cell 被插入/刪除/合併」，不展開 runs。

---

## 14 unit test 場景（[tests/unit/sprint293_track_change_extras.test.ts](../tests/unit/sprint293_track_change_extras.test.ts)）

### pPrChange（4 案）
| Test | 驗證 |
|---|---|
| 完整屬性 | author/date/id 都 capture |
| 全缺屬性 | pPrChange = {}（仍標記） |
| 無 pPrChange | pPrChange undefined |
| 非數字 id | id undefined、author/date 仍 capture |

### rPrChange（3 案）
| Test | 驗證 |
|---|---|
| 完整屬性 | author/date/id 全 capture |
| 與 bold 並存 | bold + rPrChange 同時 capture |
| 無 rPrChange | rPrChange undefined |

### cellIns（2 案）
| Test | 驗證 |
|---|---|
| 完整屬性 | cell.props.cellIns 全 capture |
| 無 cellIns | undefined |

### cellDel（1 案）
| Test | 驗證 |
|---|---|
| 完整屬性 | author/id capture |

### cellMerge（3 案）
| Test | 驗證 |
|---|---|
| val="vert" + vMerge="cont" | val/vMerge 都 capture |
| val="invalid" | val undefined、其他屬性仍可 |
| 全缺 val/vMerge | val/vMerge undefined、id 仍可 |

### 整合（1 案）
| Test | 驗證 |
|---|---|
| 多 cell 各自掛不同 tracked change | 互不干擾 |

**14/14 passed / 40ms**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy C+：parser + AST + 14 tests、0 行 writer/render 變動 | ✅ |
| #14.b clean scope：commit 含 1 AST + 2 parser + 1 test + 1 doc + snapshot | ✅ |
| #18 scope-down：不解 *Change 內含 old pPr/rPr 子樹；UI accept/reject 面板留 future cluster | ✅ |
| #21 capture-only：不污染 VR pipeline / writer / render | ✅ |
| #22 verify：5 個 *Change 全覆蓋 + edge case（全缺 / 非數字 / 並存 / 多 cell） | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 293

vitest 2228 → 2242（+14）/ tsc 2 pre-existing 不增 / +~50 行 AST + ~60 行 parser / 0 行 writer。

Phase 5.4 追蹤修訂 parser side **完整**（ins / del / moveFrom / moveTo / pPrChange / rPrChange / cellIns / cellDel / cellMerge — 9 種規格類型全 capture）。

下一步：Sprint 294 = ⑥ NodeWorkerThreadDispatcher 真實實作（user 「繼續執行」honest gap）。
