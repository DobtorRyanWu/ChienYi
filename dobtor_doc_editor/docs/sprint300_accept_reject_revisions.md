# Sprint 300 — AST accept/reject revision helpers ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy A pure-fn

**日期**：2026-05-27（週三）
**類型**：④ deeper — pure-fn AST transform + 14 tests
**前置**：Sprint 290 moveFrom/moveTo capture、Sprint 293 pPrChange/rPrChange/cellIns/Del/Merge capture

User 指令：「繼續執行」④ 推進 UI accept/reject 面板基礎層（pure-fn）。

---

## 範圍

Sprint 290+293 已把 OOXML §17.13.5 9 種規格類型的 track change 全 capture 進
AST；本 sprint 補 **accept/reject pure-fn transform**（caller 給 DocumentNode、
回新樹）：

| Module | Sprint | 角色 |
|---|---|---|
| ParagraphParser case 擴展 | 290 | `<w:ins>` / `<w:del>` / `<w:moveFrom>` / `<w:moveTo>` 包裹 |
| TrackChangeMeta 共用 type | 293 | `<w:pPrChange>` / `<w:rPrChange>` / `<w:cellIns>` / `<w:cellDel>` / `<w:cellMerge>` |
| **revision/accept_reject.ts** | **300** | **acceptRevisions / rejectRevisions / listRevisions + 細粒度 helpers** |

未來 UI accept/reject 面板（accept-all / accept-selected / reject-all 按鈕）
為 follow-up sprint；本層為 UI 與 production save 都可消費的 building block。

---

## 設計細節

### Run-level revision 行為矩陣

|             | accept | reject |
|-------------|--------|--------|
| `ins`       | KEEP   | REMOVE |
| `del`       | REMOVE | KEEP   |
| `moveFrom`  | REMOVE | KEEP   |
| `moveTo`    | KEEP   | REMOVE |

KEEP = 保留 run，移除 revision metadata；REMOVE = 從 runs[] 移除整個 run。

### Props *Change accept/reject

`rPrChange` / `pPrChange` / `cellIns` / `cellDel` / `cellMerge`：

- **accept**：drop metadata（變更已接受、不需保留歷史）
- **reject**：scope-down **僅 drop metadata**

紀律 #18 scope-down 說明：完整 reject 需「還原 previous-state pPr/rPr」內容，
但目前 parser 只 capture `<w:pPrChange>` / `<w:rPrChange>` 的 author/date/id
（不展開 previous-state inner content；OOXML 規格中這些元素內含一份 previous
`<w:pPr>` / `<w:rPr>`、但 parser 未保存）。完整 reject 路徑要先擴 AST 把
previous state 也存進來，留 future sprint。

### Predicate API

```typescript
acceptRevisions(doc, {
  predicate: (meta) => meta.author === 'Alice',
});
```

不帶 predicate = accept/reject ALL；caller 可依 id / author / date 過濾。

### Immutability

整棵樹 immutable transform、原 doc 不被 mutate。

---

## 14 unit test 場景（[tests/unit/sprint300_accept_reject_revisions.test.ts](../tests/unit/sprint300_accept_reject_revisions.test.ts)）

### Run-level accept（3 案）
| Test | 驗證 |
|---|---|
| ins → keep | run 留下、revision metadata 移除 |
| del → remove | run 從 runs[] 移除 |
| moveFrom remove / moveTo keep | 對稱矩陣 |

### Run-level reject（2 案）
| Test | 驗證 |
|---|---|
| ins → remove | 對稱 |
| del/moveFrom keep / moveTo remove | 對稱 |

### Props *Change drop（3 案）
| Test | 驗證 |
|---|---|
| rPrChange accept drop | run.props.rPrChange 變 undefined |
| pPrChange accept drop | paragraph.props.pPrChange 變 undefined |
| reject 也 drop | scope-down：previous-state 還原為 future |

### Cell-level（1 案）
| Test | 驗證 |
|---|---|
| cellIns / cellDel / cellMerge accept drop | cell.props 3 metadata 變 undefined |

### Predicate 過濾（2 案）
| Test | 驗證 |
|---|---|
| id-based predicate | 只 accept id=5、其他不變 |
| author-based predicate | 只 accept Alice |

### Immutability（1 案）
| Test | 驗證 |
|---|---|
| 原 doc 不被 mutate | acceptRevisions 後原 revision metadata 仍在 |

### listRevisions（1 案）
| Test | 驗證 |
|---|---|
| 列舉 5 種 source | run-revision / pPrChange / rPrChange / cellIns / cellMerge |

### 細粒度 helpers（1 案）
| Test | 驗證 |
|---|---|
| acceptParagraphRevisions / rejectParagraphRevisions | 單一段落層級 |

**14/14 passed / 28ms**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A pure-fn：immutable transform helpers + 14 tests | ✅ |
| #14.b clean scope：commit 含 1 新 module + 1 barrel + 1 test + 1 doc | ✅ |
| #18 scope-down：props *Change reject 僅 drop metadata（previous-state 還原留 future） | ✅ |
| #21 不污染既有 parser/layout/render：pure-fn、caller 顯式呼叫才生效 | ✅ |
| #22 verify：accept/reject 行為矩陣 + predicate + immutability + listRevisions 全覆蓋 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 300

vitest +14（pure-fn module、無外部依賴）/ tsc 2 pre-existing 不增 / +~230 行
accept_reject.ts + ~15 行 barrel / 0 行 production parse/layout/render 變動。

下一步：Sprint 301 = ⑤ overlay_geometry multi-select + resize-by-handle 擴展。
