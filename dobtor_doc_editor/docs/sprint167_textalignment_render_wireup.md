# Sprint 167 — `<w:textAlignment>` 行內垂直對齊 render 消費 wire-up

**日期**：2026-05-21
**類型**：wire-up（決策 A part 1/2、Strategy C）
**規畫書對應**：§5 Phase 4.4 L517 `<w:textAlignment>` 基線對齊
**前置**：Sprint 134（textAlignment capture-only）、Sprint 140（決策 A probe → DEFER、user 2026-05-21 GO）
**分支**：`sprint-160-v2-instrtext-fldchar-render`

---

## Hypothesis

Sprint 134 把 `<w:textAlignment w:val="...">`（ECMA-376 §17.3.1.36 行內垂直對齊）
capture 進 `ParagraphProps.textAlignment`，type 註解明寫「Layout 階段消費；parser 僅
capture」——但自 Sprint 134 起無任何 layout / render consumer，屬純 capture。

Sprint 140 probe 把決策 A（textAlignment / framePr wire-up）DEFER：理由是「預期收益
< pixelmatch resolution、canvas-editor 無對應、Layout 對應微弱」。user 於 2026-05-21
拍板 GO。本 sprint 為決策 A 的 part 1（textAlignment）；framePr 留 Sprint 168。

假設：textAlignment 的真實 consumer 是 renderer（一行內混排不同高度 run 時、決定各
run 的垂直擺放）。wire-up 後須能 grep 到真實 callsite、且對等高行 byte-identical。

---

## Method — probe（紀律 #22）

### 1. fixture 覆蓋與取值

```
42 docx fixture：textAlignment 4 份、framePr 1 份（與 Sprint 140 probe 一致）
4 份全在 04_with_image（環清表安全衛生抽查照片）、全部 w:val="center"、每份 18 次
```

逐段抽查 4 份 fixture 的 textAlignment 段落 run 字型大小：**16/18 段落 run 全
`w:sz="22"`（單一字型大小）**；2 段含 `w:sz="0"` 空 run（無可見文字）。

→ **行內所有可見 box 等高**。`center` 對齊在等高行 = `baseline` 對齊（OOXML 預設）。

### 2. renderer 現況（`CanvasRenderer.renderLine` L155-173）

```ts
const yBaseline = baseY + line.baseline;   // 全行單一 baseline
for (item of line.items) { ... this.renderBox(box, cursor, yBaseline, ...) }
```

每個 box 用同一個 `yBaseline` 繪製 = `baseline` 對齊（OOXML 預設值）。
`Line.paragraphProps` 已被 renderer 讀取（shading），讀 `textAlignment` 同模式。

### 3. canvas-editor mapper

Sprint 140 已確認 canvas-editor 無行內垂直對齊概念。`ToCanvasEditor` 不在本 sprint
scope——CanvasRenderer 才是 VR pipeline + layout 的真實 render consumer（紀律 #1.a
路徑）；canvas-editor 端比照 Sprint 164 bookmark / Sprint 127 FontMetricsAdapter 定位
（依賴 Phase 2 canvas-editor patch、decision 2B），非本 sprint。

---

## 修法

### 1. 新檔 `static/src/core/layout/verticalAlignShift.ts`（純函式、+74 行）

對映 `alignmentShift.ts`（Sprint 32 水平對齊）的垂直版本。
`computeVerticalAlignShift(textAlignment, boxHeight, maxBoxHeight) → Pt`：

| textAlignment | 位移公式（相對行 baseline、正 = 下） | delta = boxHeight − maxBoxHeight |
|---|---|---|
| baseline / auto / undefined | `0` | — |
| top | `0.8 × delta` | 較矮 box 頂端對齊最高 box 頂端 |
| bottom | `−0.2 × delta` | 較矮 box 底端對齊最高 box 底端 |
| center | `0.3 × delta` | 較矮 box 中心對齊最高 box 中心 |

`0.8` = `BASELINE_DROP_RATIO`，與 `LineBreaker.makeLine` 的 `baseline = height × 0.8`
一致（具名常數、紀律 #2 無 magic number）。**關鍵性質**：位移只與行內 box 高度差有
關，`delta === 0`（等高、含行內最高 box 自身、單一字型行）→ 位移恆 `0`。

### 2. `CanvasRenderer.renderLine` wire-up（+13 行）

textAlignment 非 baseline/auto 時掃一次行內最高 box，逐 box 算 `yShift` 套到文字與
image 的繪製 y。textAlignment 未設 / baseline / auto → `maxBoxHeight` 維持 0 → `yShift`
恆 0 → 與 Sprint 0-166 完全相同路徑。

### Strategy C（紀律 #1.a / #1.b）

caller 不傳 textAlignment、或傳 baseline/auto → byte-identical by construction。
即使傳 top/center/bottom，**等高行位移恆 0** → 現有 42 fixture（textAlignment 段落
全等高）render 輸出逐 pixel 不變。位移只在「真實混合不同高度 run」時生效——此情境
無 fixture 覆蓋，由 synthetic unit test 驗證。

---

## Verification — 三層 SOP

| 層 | 結果 |
|---|---|
| **L1 vitest** | **1371 → 1385 passed + 1 skipped**（+14：verticalAlignShift 9 + CanvasRenderer 5）。新增測試涵蓋預設路徑回傳 0 / 等高行 0 / top·center·bottom 位移方向與量 / 防禦邊界 / renderer 端較矮 box 上移而最高 box 不動 / 等高行標 center 仍 byte-identical |
| **L2 VR v14** | VR pipeline bundle 重建 → 跑全 42 fixture × 126 page、**0 failed**、aggregate mean **0.073191**（byte-identical 第 28 連）。textAlignment fixture 段落全等高 → 位移恆 0、驗證 Strategy C |
| **L3 spot check** | §5 L517 checkbox `[ ]→[x]`；audit doc / progress_snapshot / roadmap / state.json 四處一致 |
| **L4 Odoo backend** | 不適用（無 backend 變更） |

- `tsc --noEmit`：**2 個 pre-existing error**（FontMetrics opentype.js 宣告 / SettingsParser position enum）、無新增。
- frontend bundle（`canvas-editor-custom.umd.js`）**不重建**：`grep` 確認 CanvasRenderer 不在 frontend bundle（input `ooxml/index.ts` 不 import render 層）——比照 Sprint 162 Paginator「非 production render path」誠實聲明。
- flake8：不適用（0 行 Python 變更）。

---

## Root cause

**為什麼 textAlignment 一直沒接通**：

1. Sprint 134 設計上即 capture-only（type 註解寫「Layout 階段消費」但無 consumer）。
2. Sprint 140 probe DEFER：收益 < pixelmatch resolution——這判斷正確（4 fixture 全
   等高行、wire-up 後 VR 必 byte-identical），但「收益小」≠「不該接」。user GO 後本
   sprint 補上真實 callsite，使 textAlignment 從「宣告但無人讀」變為「renderer 真實
   consume」——未來混排不同字型大小 / 數學符號 / 圖片的文件即正確。
3. 真實 consumer 一直是 renderer 而非 layout——`textAlignment` 不改行高、不影響分頁，
   只改行內各 box 的 y。故 wire-up 落在 `CanvasRenderer` 而非 Paginator（對比 Sprint
   161-162 tab stop 影響 line.width、落在 LineBreaker/Paginator）。

---

## 紀律

- **#22（probe-first）**：開工前 probe 3 步（fixture 取值 / renderer 現況 / canvas-editor
  定位），確認 renderer 是真實 consumer、等高行位移為 0——寫 code 前即知 VR 必
  byte-identical，非事後解釋。
- **#1.a**：改 render 路徑、即使預期 byte-identical 仍跑全 42 fixture VR 驗證（第 28 連）。
- **#1.b / Strategy C**：caller 不觸發 → byte-identical by construction；位移公式設計成
  「等高 → 0」使現有 fixture 必不變。對比 Sprint 139 numbering / Sprint 162 tab stop。
- **#2**：`BASELINE_DROP_RATIO = 0.8` 具名常數、與 LineBreaker 一致、無 magic number。
- **#18 scope-down**：(a) 只做 textAlignment、framePr 留 Sprint 168；(b) canvas-editor
  mapper 端不碰（依賴 decision 2B）；(c) box 垂直 extent 以引擎既有 0.8/0.2 ascent/descent
  近似、不引入 per-font metric（與 renderer 既有 highlight/underline 同近似基礎）。
- **#14 / #14.b**：開工前補 commit 殘留 `docs/onboarding_prompt.md`、working tree 清零；
  docs 即時同步 4 處集中索引。

---

## 後續

- **Sprint 168**：決策 A part 2 —— `<w:framePr>` wire-up（§5 L514 / §4.4 段落框）。
  framePr 1/42 fixture、開工前同樣先 probe consumer。
- **canvas-editor patch（decision 2B、Sprint 166-170）**：若 canvas-editor 取得行內
  垂直對齊能力，`ToCanvasEditor` 可比照本 sprint 把 textAlignment 接到 production
  canvas-editor render path。
- textAlignment 對「混排數學符號（Phase 5.1 OMML）/ 圖片」的垂直對齊收益、待 Phase 5
  進階功能 fixture 到位後可由真實文件量化。

---

## Sprint 167 結尾累積指標

- vitest **1385 passed + 1 skipped**（+14）
- VR mean **0.073191**（byte-identical 第 28 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 166 → 167
- §5 Phase 4.4 L517 `<w:textAlignment>` `[ ]→[x]`
- 新檔 `verticalAlignShift.ts`（純函式 layer）
