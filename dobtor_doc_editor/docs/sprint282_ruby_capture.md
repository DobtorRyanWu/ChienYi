# Sprint 282 — Phase 1 optional bucket 第 1 項：`<w:ruby>` 注音/振假名 capture ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 1/6 done

**日期**：2026-05-26（週二）
**類型**：Strategy A capture-only / 紀律 #18 scope-down
**規畫書對應**：§Phase 1 §1.x ruby 注音/振假名
**前置**：Phase 2.1-2.3 cluster 收口（Sprint 278-281）

User 指令：「**依序 ruby / tcFitText / tblStylePr row+border 條件樣式 /
lvlOverride / effectExtent / 浮動圖片 wp:anchor 完整。每項一個 sprint、跑完
停下叫我 review。最多 8 sprint。**」本 sprint = 第 1/6 = ruby。

---

## Hypothesis & Result

**hypothesis**：OOXML §17.3.3.25 `<w:ruby>` 結構（rubyPr + rt + rubyBase）可
完整 capture 進 AST、不影響既有 parser 行為。

**結論**：**verified、8/8 unit test 含 7 種場景、Sprint 145-153 capture-only
模式重現第 10 次**。

---

## 範圍（capture-only、紀律 #18 scope-down）

| 項 | 本 sprint | 留 follow-up |
|---|---|---|
| AST RubyNode + RubyProps | ✅ | — |
| parser w:ruby → RubyNode | ✅ | — |
| rubyPr 子元素全 capture（align / hps / hpsRaise / hpsBaseText / lid / dirty） | ✅ | — |
| annotation runs + base runs 遞迴 | ✅（用 parseRun 既有邏輯） | — |
| Render（canvas-editor 顯示注音） | — | canvas-editor 無 ruby 概念、Phase 6 自寫 Layout |
| Writer round-trip emit | — | 後續 sprint（user 決） |
| 黃金測試 byte-identical 接入 | — | 同上 |

---

## API 變更

### AST 新增 `static/src/core/ooxml/ast/types.ts`

```typescript
export type InlineNode = ... | RubyNode;

export interface RubyNode {
  type: 'ruby';
  annotationRuns: RunNode[];  // <w:rt> 內 runs
  baseRuns: RunNode[];        // <w:rubyBase> 內 runs
  props?: RubyProps;
}

export interface RubyProps {
  align?: 'center' | 'distributeLetter' | 'distributeSpace' | 'left' | 'right' | 'rightVertical';
  hps?: number;          // half-points raw
  hpsRaise?: number;
  hpsBaseText?: number;
  lid?: string;          // BCP 47-ish, e.g. zh-TW / ja-JP
  dirty?: boolean;
}
```

### Parser `static/src/core/ooxml/document/ParagraphParser.ts`

- `parseRun` switch case 加 `'w:ruby'`：flushText + 呼 `parseRubyNode`
- 新 helper `parseRubyNode(ruby: Element): RubyNode | undefined`：
  - 走 `<w:rubyPr>` / `<w:rt>` / `<w:rubyBase>` directChild
  - annotation runs / base runs 兩端皆空 → return undefined（避免污染 AST）
- 新 helper `parseRubyProps(rubyPr: Element): RubyProps | undefined`：
  - 六個欄位逐一解析、皆 optional
  - rubyAlign 嚴格驗 6 種合法值；非法 → 該欄 undefined（其他欄不受影響）
  - dirty：`val="1"` / `val="true"` / 缺 val attr → true；`val="0"` → false

---

## 8 unit test 場景（`tests/unit/sprint282_ruby_capture.test.ts`）

| Test | 驗證 |
|---|---|
| 中文注音「漢字」(ㄏㄢˋㄗˋ) + 完整 rubyPr | 6 props 全捕捉、annotation/base 文字正確 |
| 日文振假名「漢字」(かんじ) + align=center | 不同語言 lid 正確 |
| 缺 rubyPr → props 為 undefined | 不寫空 object（紀律 #21） |
| rt + rubyBase 皆空 → ruby node 不 emit | 避免污染 AST |
| rubyAlign 非法 val → align undefined、其他 props 仍解析 | 部分失敗不影響其他 |
| w:dirty val="1" → true / val="0" → false | 布林轉換正確 |
| Ruby 與 plain text 共存、順序保留 | 段內 InlineNode 順序對齊原 XML |
| 多字 base + 連續 annotation runs | annotationRuns / baseRuns 陣列保留全部 |

**8/8 passed / 17ms**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b Strategy A：capture-only、~100 行 production code（AST + parser）| ✅ |
| #14.b clean scope：commit 含 types.ts + ParagraphParser.ts + 1 unit test + 1 doc | ✅ |
| #18 scope-down：不 render / 不 writer round-trip / 不接 canvas-editor / 不接黃金測試 | ✅ |
| #21 與 Sprint 145-153 capture-only 9 連同模式重現第 10 次 | ✅ |
| #22 verify：unit test 8/8、含 negative case（缺 rubyPr / 非法 val / 空 ruby） | ✅ |
| 雙驗紀律：tsc + vitest 兩路通；無 browser 路徑需求（pure 結構 capture） | ✅ |

---

## End of Sprint 282

**Phase 1 optional bucket 1/6 完成（ruby）**。

vitest 2108 → 2116 hypothesis（+8 unit test）/ VR 第 68 連 maintained / tsc
2 pre-existing 不增。

剩餘 Phase 1 optional bucket 5/6（user 指令：每項一 sprint、跑完停下叫我 review）：
- Sprint 283：tcFitText（表格儲存格自動縮字）
- Sprint 284：tblStylePr row+border 條件樣式
- Sprint 285：lvlOverride（清單覆寫）
- Sprint 286：effectExtent（DrawingML 浮動圖效果範圍）
- Sprint 287：浮動圖片 wp:anchor 完整

**STOP for user review**（user 指令「跑完停下叫我 review」）。等 user 確認後
再啟動 Sprint 283。
