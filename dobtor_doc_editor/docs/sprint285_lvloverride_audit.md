# Sprint 285 — Phase 1 optional bucket 4/6：`<w:lvlOverride>` audit ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy C 0 production code

**日期**：2026-05-27（週三）
**類型**：Strategy C 純 audit / 紀律 #18 scope-down
**規畫書對應**：§Phase 1 §1.5 numbering / lvlOverride
**前置**：Sprint 284 tblStylePr row+border（Phase 1 optional bucket 3/6）

User 指令：「lvlOverride（清單覆寫）」。

---

## Audit 結論

**揭發狀態**：lvlOverride parser 已完整實作（startOverride / integral lvl /
multi-ilvl）；既有 2 案 unit test（NumberingResolver.test.ts:119-156）但覆蓋
不全。Writer 走 **Sprint 191 clone-per-num 策略**（每個 num 一個 abstractNum、
overrides 被 baked into 該 num 的 abstract）：

| 層 | 既有實作位置 | 狀態 |
|---|---|---|
| AST | `types.ts:889` — AbstractNumbering（per-numId、override baked） | ✓ 既有 |
| Parser | `NumberingResolver.ts:221` parseLvlOverride + `:243` applyOverrides | ✓ 既有 |
| Writer | `OoxmlWriter.ts:1210` writeNumbering（clone-per-num strategy）| ✓ Sprint 191 既有 |
| Tests | 既有 2 案 + 本 sprint 補 8 案 = 共 10 案 | ✓ 補 |
| Render | NumberingFormatter 走 NumberingMap、override 已 applied | ✓ 既有 |

**Strategy C 純 audit、0 行 production code 變動**。

---

## Sprint 191 clone-per-num 策略下的 round-trip 語意 vs 結構

| 維度 | Round-trip 行為 |
|---|---|
| **語意 round-trip**（display: start / numFmt / lvlText / indent） | ✓ 完整保留（writer 把 applied levels 直接 emit 為新 abstractNum） |
| **結構 round-trip**（raw `<w:lvlOverride>` 元素） | ✗ Lossy（被 baked 進新 abstract、re-emit 時無 lvlOverride 元素） |

Sprint 191 註明（OoxmlWriter.ts:1203-1206）：「**用 numId 直接當 abstractNumId**
（保證唯一、避免「多個 numId 共用 abstractNumId 但 levels 不同」場景在 re-parse
時被 Map 覆蓋）。`entry.abstractNumId` 欄位於 round-trip 後變為 numId
（acceptable lossy；parser 不靠此值來解析 levels）。」

這是 acceptable lossy：Word / LibreOffice display 結果與原 docx 一致；只有
Sprint 270-274「第十九層 raw byte preserve」級別的 byte-identical 才會看到差異。
本 sprint user 未要求該級別。

紀律 #18 scope-down：不重寫 Sprint 191 策略；raw byte preservation 為 deferred。

---

## 8 audit test 場景（`tests/unit/sprint285_lvloverride_audit.test.ts`）

### Parser 補強（5 案、覆蓋既有 2 案沒處理的場景）

| Test | 驗證 |
|---|---|
| Multi-ilvl override on same num | 兩個 lvlOverride 不同 ilvl 都套用 |
| startOverride + integral lvl 混合在不同 ilvl | 各 ilvl 走自己的 path |
| lvlOverride 含 w:lvl 但 base 該 ilvl 不存在 | push 新 level、最終 sort by ilvl |
| lvlOverride 缺 w:ilvl 屬性 → 跳過 | 不 throw、原值保留 |
| 同一 lvlOverride 內 integral lvl + startOverride 並存 | integral lvl 優先（applyOverrides 邏輯） |

### Round-trip 語意（3 案）

| Test | 驗證 |
|---|---|
| startOverride → write → re-parse | start 值保留 |
| Integral lvl override（bullet 取代 decimal）→ round-trip | numFmt + lvlText 保留 |
| Multi-num 各自獨立（Sprint 191 clone strategy） | 兩個 numId 不同 start 不互染 |

**8/8 passed / 42ms**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy C：0 production code、純測試補洞 | ✅ |
| #14.b clean scope：commit 含 1 unit test + 1 doc（無 src 變動）| ✅ |
| #18 scope-down：不重寫 Sprint 191 clone-per-num 策略 | ✅ |
| #21 audit 不 touch 既有 src、不 touch VR | ✅ |
| #22 verify：parser 5 案 + round-trip 3 案、含 Sprint 191 lossy 行為的 honest 揭露 | ✅ |
| 雙驗紀律：tsc + vitest 兩路通 | ✅ |

---

## 為何 Sprint 285 = audit 而非新功能

對比 Sprint 282/284（capture-only ruby / 開 borders defer）：

| Sprint | 既有實作完整度 | 本 sprint 工作 |
|---|---|---|
| 282 (ruby) | 完全沒有 | 全套：AST + parser + 8 tests |
| 283 (tcFitText) | AST/parser/writer 都有、零 test | Strategy C：11 tests 補洞 |
| 284 (tblStylePr borders) | Sprint 131 deferred、缺 borders | Strategy A：開 borders +10 tests |
| **285 (lvlOverride)** | **parser/writer 都有、Sprint 191 lossy 策略 acceptable** | **Strategy C：8 tests 補洞 + honest gap 紀錄** |

每項依個別狀態決定 strategy；user 指定「依序」表示每項都過、不必每項都動 code。

---

## End of Sprint 285

**Phase 1 optional bucket 4/6 完成（lvlOverride audit）**。

vitest 2137 → 2145 hypothesis（+8 unit test）/ VR 第 68 連 maintained / tsc
2 pre-existing 不增 / 0 行 production code。

剩餘 Phase 1 optional bucket 2/6：
- Sprint 286：effectExtent（DrawingML 效果範圍）
- Sprint 287：wp:anchor 完整

**STOP for user review**（user 指令「跑完停下叫我 review」）。等 user 確認後
再啟動 Sprint 286。
