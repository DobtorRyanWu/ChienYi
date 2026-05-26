# Sprint 283 — Phase 1 optional bucket 2/6：`<w:tcFitText>` audit + tests ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy C 0 production code 變動

**日期**：2026-05-26（週二）
**類型**：Strategy C 純 audit / 紀律 #18 scope-down
**規畫書對應**：§Phase 1 §1.7 tcFitText 表格儲存格文字自動縮放
**前置**：Sprint 282 ruby capture（Phase 1 optional bucket 1/6）

User 指令：「**依序 ruby / tcFitText / tblStylePr ... 每項一個 sprint、跑完
停下叫我 review、最多 8 sprint。**」本 sprint = 2/6 = tcFitText。

---

## Audit 結論

**揭發 Sprint 282 前狀態：tcFitText 已 fully wire-up（AST + parser + writer
round-trip 都做完）、但無測試覆蓋**。本 sprint 補測試完成 audit。

| 層 | 既有實作位置 | 狀態 |
|---|---|---|
| AST | `types.ts:536` — `TableCellProps.fitText?: boolean` | ✓ 既有 |
| Parser | `TableParser.ts:262` — `boolFlag(directChild(tcPr, 'w:tcFitText'))` → `rc.fitText = true` | ✓ 既有 |
| Materializer | `TableParser.ts:303` — `if (rc.fitText) props.fitText = rc.fitText` | ✓ 既有 |
| Writer | `OoxmlWriter.ts:1190` — `if (p.fitText === true) parts.push('<w:tcFitText/>')` | ✓ 既有 |
| Tests | 無 | ✗ → 本 sprint 補 |
| Render（canvas-editor 端文字縮放）| 無 | — 不在 Phase 1 範圍（Phase 6 自寫 Layout 才做）|

**Strategy C 純 audit、0 行 production code 變動**。

---

## 11 個 audit test 場景（`tests/unit/sprint283_tcfittext_audit.test.ts`）

### Parser boolean variants（6 案）

OOXML ST_OnOff 的 5 種 boolean variant + 一種 absent：

| Input | Expected |
|---|---|
| `<w:tcFitText/>` 缺 val | `fitText=true` |
| `<w:tcFitText w:val="1"/>` | `fitText=true` |
| `<w:tcFitText w:val="true"/>` | `fitText=true` |
| `<w:tcFitText w:val="0"/>` | `fitText` undefined（AST 不寫 false） |
| `<w:tcFitText w:val="false"/>` | `fitText` undefined |
| `<w:tcPr/>` 完全缺 `tcFitText` | `fitText` undefined |
| 混合 row（cell1 有、cell2 無）| 分流正確 |

### Writer audit（3 案）

| AST input | Expected XML |
|---|---|
| `fitText: true` | `document.xml` 含 `<w:tcFitText/>` |
| `fitText: false` | 不 emit |
| `fitText: undefined`（缺 prop） | 不 emit |

### Full round-trip（1 案）

| Path | Verify |
|---|---|
| AST(fitText=true) → `OoxmlWriter.write` → `fflate.unzipSync` → `OoxmlParser.parse` → AST | re-parsed cell.props.fitText === true |

**11/11 passed / 53ms**。

---

## 關鍵實作細節（揭露既有行為）

### `boolFlag` helper（TableParser.ts:517）

```typescript
function boolFlag(el: Element | undefined): boolean {
  if (!el) return false;
  const v = el.getAttribute('w:val');
  if (v === null) return true;                          // 缺 val → OOXML 預設 1
  return v !== '0' && v.toLowerCase() !== 'false';       // "0" / "false" 大小寫不敏感 → false
}
```

對齊 OOXML §17.17.4 ST_OnOff（"1"、"true"、"on"、缺 val → true；"0"、"false"、
"off" → false）。本 helper 不處理 "on" / "off"、但 ChienYi corpus 未見此 variant。

### Writer 條件 emit（OoxmlWriter.ts:1190）

```typescript
if (p.fitText === true) parts.push('<w:tcFitText/>');
```

嚴格 `=== true` → `false` / `undefined` 都不 emit；對齊 OOXML 預設關閉的
spec 行為。

### Sprint 145-153 capture-only 模式對比

| Sprint | 範圍 | Render | Writer round-trip |
|---|---|---|---|
| 282（ruby）| capture-only | ✗ Phase 6 留 | ✗ follow-up 留 |
| **283（tcFitText）** | **既有 fully wire-up + 補 tests** | ✗ Phase 6 留 | ✓ 既有 |

tcFitText 之 wire-up 完整度比 ruby 高一階；本 sprint 只是補測試把 audit
狀態從「無覆蓋」改為「11 案覆蓋」。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy C：0 production code、純測試補洞 | ✅ |
| #14.b clean scope：commit 含 1 unit test + 1 doc（無 src 變動）| ✅ |
| #18 scope-down：不擴張 render / Sprint 145-153 模式不變 | ✅ |
| #21 audit 不 touch 既有 src、不 touch VR | ✅ |
| #22 verify：11 案 + full round-trip（write/unzip/re-parse byte-identical 行為）為硬數據 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通；無 browser 路徑需求（pure 結構 audit） | ✅ |

---

## End of Sprint 283

**Phase 1 optional bucket 2/6 完成（tcFitText）**。

vitest 2116 → 2127 hypothesis（+11 unit test）/ VR 第 68 連 maintained / tsc
2 pre-existing 不增 / 0 行 production code 變動。

剩餘 Phase 1 optional bucket 4/6：
- Sprint 284：tblStylePr row+border 條件樣式
- Sprint 285：lvlOverride
- Sprint 286：effectExtent
- Sprint 287：wp:anchor 完整

**STOP for user review**（user 指令「跑完停下叫我 review」）。等 user 確認後
再啟動 Sprint 284。
