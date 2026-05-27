# Sprint 290 — ④ Phase 5.4+5.5：moveFrom / moveTo revision capture ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy C+ capture-only

**日期**：2026-05-27（週三）
**類型**：④ cluster 第 1 sprint — parser/AST 補完整、UI 留 future
**規畫書對應**：§Phase 5.4 追蹤修訂 + §5.5 註解
**前置**：Sprint 174 ins/del capture、Sprint 236-238 comments writer audit

User 指令：「繼續執行 1-6」cluster ④（16h cap）。

---

## Scope decision

User 原 ④ 規格：「追蹤修訂 accept/reject UI + 5.5 註解互動面板」（UI 重點）。
單 sprint 無法完成 OWL Component UI；本 sprint 走 backend/AST/parser 補完整、
為未來 UI cluster 鋪資料層（紀律 #18 scope-down）。

### 揭發狀態

| 項目 | 狀態 | Sprint 290 動作 |
|---|---|---|
| `<w:ins>` 插入 capture | Sprint 174 done | — |
| `<w:del>` 刪除 capture | Sprint 174 done | — |
| `<w:moveFrom>` 移動來源 capture | **未做** | 本 sprint 補 |
| `<w:moveTo>` 移動目的 capture | **未做** | 本 sprint 補 |
| `<w:pPrChange>` 段落屬性修訂 | 未做 | future cluster |
| `<w:rPrChange>` run 屬性修訂 | 未做 | future cluster |
| `<w:cellIns>` / `<w:cellDel>` / `<w:cellMerge>` 表格修訂 | 未做 | future cluster |
| Comments AST + parser | Sprint 177 / 236-238 done | — |
| Comments accept/reject UI | 未做 | future cluster |
| Comments 互動面板 | 未做 | future cluster |

---

## 設計細節

### AST 擴張（[types.ts](../static/src/core/ooxml/ast/types.ts)）

```typescript
export interface RunRevision {
  type: 'ins' | 'del' | 'moveFrom' | 'moveTo';  // +2 種
  author?: string;
  date?: string;
  id?: number;
}
```

`moveFrom` / `moveTo` 對應同一 `w:id` — caller 可用此關聯「同一移動操作的兩端」。

### Parser（[ParagraphParser.ts](../static/src/core/ooxml/document/ParagraphParser.ts)）

擴 `case 'w:ins' | 'w:del'` switch 涵蓋 `w:moveFrom` + `w:moveTo`，共用同一展平
+ revision 標記邏輯。`<w:moveFrom>` 內的 run 文字在 `<w:delText>` —— 與 del
規格一致、parseRun 既有支援。

`parseRevision` 簽名拓寬到 `RunRevision['type']`、其餘邏輯不變。

---

## 6 unit test 場景（[tests/unit/sprint290_move_revisions.test.ts](../tests/unit/sprint290_move_revisions.test.ts)）

| Test | 驗證 |
|---|---|
| w:moveFrom 單 run | type/author/date/id 全 capture |
| w:moveFrom 多 run | 全部 run 標 moveFrom revision、屬性一致 |
| w:moveTo 單 run | type/id 正確 |
| w:moveTo 屬性全缺 | type 仍 moveTo、其他 undefined |
| 段落混合 normal + ins + del + moveFrom + moveTo | 5 run 各自 revision 正確、moveFrom/moveTo 同 id |
| TypeScript 編譯期型別 | RunRevision.type union 含 4 值 |

**6/6 passed / 17ms**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy C+：AST union 擴張 + 1 case 擴 parser + 6 tests | ✅ |
| #14.b clean scope：commit 含 1 AST + 1 parser + 1 test + 1 doc + snapshot | ✅ |
| #18 scope-down：pPrChange/rPrChange/cellIns/Del/Merge + UI accept/reject 面板留 future cluster | ✅ |
| #21 不污染既有 VR：writer/render 不消費 new revision type；layout 不變 | ✅ |
| #22 verify：4 種 revision type 並存 + edge case 屬性全缺 + 編譯期型別檢查 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## End of Sprint 290

vitest 2191 → 2197（+6）/ tsc 2 pre-existing 不增 / +~10 行 AST + ~15 行 parser / 0 行 writer。

下一步：Sprint 291 = ⑤ Phase 8.2.2（條件性 override gate）— user 「繼續執行 1-6」
語句 = explicit override authorized。
