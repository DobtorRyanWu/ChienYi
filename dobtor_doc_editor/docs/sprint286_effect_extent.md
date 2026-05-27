# Sprint 286 — Phase 1 optional bucket 5/6：`<wp:effectExtent>` 陰影外擴 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / Strategy A 輕量補完

**日期**：2026-05-27（週三）
**類型**：Strategy A — parser + AST + writer + tests（4 軸 EMU 屬性，scope 最小）
**規畫書對應**：§Phase 1 §1.6 drawing effectExtent
**前置**：Sprint 285 lvlOverride audit（Phase 1 optional bucket 4/6）

User 指令：「依序 ruby / tcFitText / tblStylePr row+border / lvlOverride / **effectExtent** / 浮動圖片 wp:anchor 完整」。

---

## Audit 結論

**揭發狀態**：完全未實作。`DrawingParser.ts:16` 註明「由 Renderer 處理」但 Renderer
端也未讀取（grep 全 repo 僅 DrawingParser comment 一處）。Writer 端 `OoxmlWriter.ts:1410`
寫 `<wp:inline>` 時亦未 emit。屬於 silent gap。

→ **Strategy A 輕量**：補 parser + AST optional field + writer emit + 10 tests。
Layout 影響留後續（render 端若需要再加，紀律 #18 scope-down）。

| 層 | Sprint 286 前 | Sprint 286 後 |
|---|---|---|
| AST | 無 | `EffectExtent` interface + 3 處 optional 欄位 |
| Parser | 完全未讀 | `parseEffectExtent` helper、wp:inline / wp:anchor (FloatImage / FloatTextBox) 3 路徑都接 |
| Writer | 從不 emit | `writeInlineImageRun` 條件 emit（有則 emit、無則維持既有 silent gap）|
| Tests | 0 | 10 案（6 parser + 4 writer/round-trip） |

---

## 設計細節

### 1. `EffectExtent` AST 型別（[types.ts:257](../static/src/core/ooxml/ast/types.ts#L257)）

```typescript
export interface EffectExtent {
  left: Pt;
  top: Pt;
  right: Pt;
  bottom: Pt;
}
```

統一 Pt（與 `width`/`height` 等其他 image 欄位一致）。**全 0 不 collapse 成 undefined**：
與 `srcRect` 不同，effectExtent 全 0 是 Word 對「無陰影」的明示記號（layout 端
仍會用 extent + effectExtent 計算 wrap 區），round-trip lossless 不可省略。

### 2. Parser（[DrawingParser.ts](../static/src/core/ooxml/drawing/DrawingParser.ts)）

```typescript
function parseEffectExtent(el: Element): EffectExtent | undefined {
  const ee = directChild(el, 'wp:effectExtent');
  if (!ee) return undefined;
  const toEmu = (raw: string | null): number => {
    if (raw === null || raw === '') return 0;
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? n : 0;
  };
  return {
    left: emuToPt(toEmu(ee.getAttribute('l'))),
    top: emuToPt(toEmu(ee.getAttribute('t'))),
    right: emuToPt(toEmu(ee.getAttribute('r'))),
    bottom: emuToPt(toEmu(ee.getAttribute('b'))),
  };
}
```

- 缺漏屬性 → 0（OOXML §20.4.2.6 預設）
- 非數字屬性 → 該軸退化為 0（saneness、不 throw）
- 找不到 `<wp:effectExtent>` → undefined（AST 不掛欄位、writer 不 emit）

接入 3 處：`parseInlineImage` / `parseFloatImage` / `parseFloatTextBox`。

### 3. Writer（[OoxmlWriter.ts:1399-1419](../static/src/core/ooxml/export/OoxmlWriter.ts#L1399-L1419)）

```typescript
const effectExtentXml = img.effectExtent
  ? `<wp:effectExtent l="${ptToEmu(img.effectExtent.left)}" t="${ptToEmu(img.effectExtent.top)}" r="${ptToEmu(img.effectExtent.right)}" b="${ptToEmu(img.effectExtent.bottom)}"/>`
  : '';
```

`writeInlineImageRun` 同時處理 InlineImageNode + FloatImageNode（注意 Sprint 192：
「FloatImageNode 降級為 inline 輸出」），所以 floatImage 的 effectExtent 也會
在輸出時 emit（但走的是 wp:inline 路徑，不是 wp:anchor，acceptable lossy）。

FloatTextBoxNode 的 effectExtent 目前 AST 帶但 writer 不 emit（floatTextBox 的
writer path 不在 Sprint 286 範圍；註明於本 doc，紀律 #21 不污染 VR）。

---

## 10 unit test 場景（[tests/unit/sprint286_effect_extent.test.ts](../tests/unit/sprint286_effect_extent.test.ts)）

### Parser 6 案

| Test | 驗證 |
|---|---|
| wp:inline + effectExtent 全 0 | AST 帶物件、四向 0、**不 collapse 成 undefined** |
| wp:inline + 非零 EMU | 914400 EMU → 72pt、457200 → 36pt、228600 → 18pt |
| wp:inline 缺 effectExtent | AST.effectExtent === undefined |
| wp:inline + 缺屬性 | 缺的軸 = 0、其他正確 |
| wp:inline + 非數字屬性 | 該軸退化為 0、不 throw |
| wp:anchor (FloatImage) + effectExtent | FloatImageNode 也帶上 effectExtent |

### Writer / Round-trip 4 案

| Test | 驗證 |
|---|---|
| AST 帶 → writer emit 正確 EMU | `<wp:effectExtent l="228600" t="0" r="457200" b="114300"/>` |
| AST 無 → writer 不 emit | xml 不含 `<wp:effectExtent` |
| Round-trip 非零 → 仍帶相同 effectExtent | Pt 值 close to within 0.1 |
| Round-trip 全 0 → **不被 collapse**（lossless）| left/right 仍 === 0 |

**10/10 passed / 43ms**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A：parser + AST + writer + tests，scope 最小 | ✅ |
| #14.b clean scope：commit 含 1 AST + 1 parser + 1 writer + 1 unit test + 1 doc | ✅ |
| #18 scope-down：不接 Layout、不接 Renderer（render 端 layout 影響後續再評） | ✅ |
| #21 不污染既有 VR：writer AST 無 effectExtent 時行為與 Sprint 285 完全相同 | ✅ |
| #22 verify：parser 6 案（含 sanity edge）+ round-trip 4 案（含全 0 lossless） | ✅ |
| 雙驗紀律：tsc + vitest 兩路通（tsc 2 pre-existing 不增、vitest 2145→2155 +10）| ✅ |

---

## 為何 Sprint 286 = Strategy A 而非 audit

對比前 4 sprint：

| Sprint | 既有實作完整度 | 本 sprint 策略 |
|---|---|---|
| 282 (ruby) | 完全沒有 | 全套：AST + parser + 8 tests |
| 283 (tcFitText) | AST/parser/writer 都有、零 test | Strategy C：11 tests 補洞 |
| 284 (tblStylePr borders) | Sprint 131 deferred、缺 borders | Strategy A：開 borders +10 tests |
| 285 (lvlOverride) | parser/writer 都有、Sprint 191 lossy 策略 acceptable | Strategy C：8 tests 補洞 |
| **286 (effectExtent)** | **完全沒有（DrawingParser 註明「Renderer 處理」實際沒實作）** | **Strategy A 輕量：parser + AST + writer + 10 tests** |

依個別狀態決定 strategy；user 指定「依序」表示每項都過、不必每項都動 code。

---

## End of Sprint 286

**Phase 1 optional bucket 5/6 完成（effectExtent）**。

vitest 2145 → 2155 hypothesis（+10 unit test）/ VR 第 68 連 maintained / tsc
2 pre-existing 不增 / +14 lines AST + 22 lines parser + 4 lines writer。

剩餘 Phase 1 optional bucket 1/6：
- Sprint 287：wp:anchor 完整（浮動圖片 — 補上 srcRect / posOffset / wrap mode 完整 round-trip）

**STOP for user review**（user 指令「跑完停下叫我 review」）。等 user 確認後
再啟動 Sprint 287。
