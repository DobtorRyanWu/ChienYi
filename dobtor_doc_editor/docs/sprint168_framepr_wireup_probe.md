# Sprint 168 — `<w:framePr>` wire-up 可行性 probe

**日期**：2026-05-21
**類型**：probe（docs-only、0 行 production code）
**規畫書對應**：§5 Phase 4.4 L514 `<w:frame>` 段落框 / §1 ParagraphProps.framePr
**前置**：Sprint 134（framePr capture-only）、Sprint 140（決策 A probe DEFER）、Sprint 167（決策 A part 1 textAlignment wire-up done）
**分支**：`sprint-160-v2-instrtext-fldchar-render`

---

## Hypothesis

決策 A（user 2026-05-21 GO）含兩項：textAlignment（Sprint 167 已 done）+ framePr。
本 sprint 為 part 2。開工前 probe（紀律 #22）：確認 framePr 的真實 consumer、wire-up
是否同 Sprint 167 可走 Strategy C（byte-identical by construction）、PR-size 是否單
sprint 可閉合。

---

## Method — probe

### 1. fixture 覆蓋與取值

```
42 docx fixture：framePr 僅 1 份 —— 06_template/檢(試)驗管制(預設樣板).docx、2 次
兩段 framePr 完全相同：
  <w:framePr w:hSpace="181" w:wrap="around" w:vAnchor="text" w:hAnchor="margin" w:y="166"/>
```

該 2 段為文件最前的標題塊（body 頂層 w:p 序列 idx 1、2、彼此相鄰）：

| idx | framePr | 文字 | rPr |
|---|---|---|---|
| 1 | Y | `+++INS contractor+++`（樣板插值佔位） | 標楷體 bold sz=32、jc=center |
| 2 | Y | `材料設備檢（試）驗管制總表`（總表標題） | 標楷體 bold sz=32、jc=center |

idx 3-6 為內文行（工程名稱 / 契約編號 / 監造單位 / 施工廠商）、idx 7+ 為主表格。

### 2. framePr 語意（ECMA-376 §17.3.1.11）

`<w:framePr>` 把段落變成**浮動定位的框**（floating frame、類似 text box）。
連續且 framePr 相同的段落由 Word 合併為**單一 frame**。本 fixture：

- `wrap="around"`：周圍內文繞排此 frame
- `vAnchor="text"` + `y="166"`：垂直錨點 = 段落文字位置、下移 166 twip（≈8.3pt）
- `hAnchor="margin"`：水平錨點 = 頁邊
- 無 `w:w`：frame 寬度 = 內容自然寬度
- 無 `xAlign` / `x`：水平預設位置

→ 正確渲染 = idx 1+2 合併為一個浮動標題塊、idx 3-6 內文繞排其旁/下。

### 3. layout / render 現況

```
grep framePr static/src/core/layout/ static/src/core/render/  → 0 命中
```

framePr 自 Sprint 134 起**完全未被 layout / render 引用**（純 capture）。
目前 idx 1、2 被當**一般 inline 段落**排版（forced 進正常垂直流、忽略浮動）。

Paginator 既有浮動基礎建設：`activeFloats` 排除區 + `exclusionAtY` per-line callback
（Sprint 6 wrapSquare）+ `placeFloatImage` / floatImage·floatTextBox 抽取（Sprint 37/38）。
框段落理論上可複用此機制，但**目前無任何 framePr → 浮動的接線**。

---

## Result — framePr ≠ Sprint 167 textAlignment、是 layout-changing 特性

### 關鍵差異：framePr 無法走 Strategy C

| 維度 | Sprint 167 textAlignment | 本 sprint framePr |
|---|---|---|
| 影響面 | 行內各 box 的 y（不改行高 / 分頁） | 段落**移出正常流**、改變後續段落排版 + 分頁 |
| 等高 / 預設時 | 位移恆 0 → byte-identical by construction | 框段落**必須移動**（浮動才是正解）→ 無 byte-identical 路徑 |
| consumer | renderer（單點、CanvasRenderer.renderLine） | Paginator 浮動系統（多點：抽取 / 定位 / 排除區 / 分頁 / 渲染） |
| fixture VR | 42 份全等高 → wire-up 後 VR 不變 | 唯一 fixture（mean 0.0263）排版**會變**、改善 or 退化未知 |
| PR-size | 單 sprint 閉合（+74 純函式 +13 renderer） | 多點 Paginator 手術、跨段落合併 + 排除區 + 分頁互動 |

textAlignment 能 byte-identical 是因為「等高 → 位移 0」是設計性質；framePr 的本質
就是「把段落從正常流挪到浮動位置」——**挪動本身就是功能**，不存在「不挪也對」的
預設路徑。任何真實 framePr wire-up 都會改 `06_template/檢(試)驗管制(預設樣板).docx`
的排版。

### golden baseline 依賴 decision B

唯一 framePr fixture 的 golden 由 **LibreOffice → PDF → PNG** 產生（Sprint 141 probe
確認）。LibreOffice 對 framePr 浮動的詮釋是否與本引擎一致**未知**。在 golden 未經
decision B（OnlyOffice goldens 重生）對齊前、即使實作出「規格正確」的 framePr 浮動，
也無法用 VR 判定是改善還是退化——正是 Sprint 136 翻車模式（unit test 過、VR 全域翻、
revert）的高風險場景。

### PR-size 評估

「完整且正確」的 framePr 浮動需：(a) 連續同 framePr 段落合併為 frame；(b) frame 內容
子排版求寬高；(c) 依 hAnchor/vAnchor/xAlign/yAlign/x/y 算絕對位置；(d) 註冊 `activeFloats`
排除區；(e) 發 float entry 供 renderer 繪；(f) 跨頁 / 跨節互動。即使複用 Sprint 6/37/38
浮動機制，仍是 2-3 sprint 的 Paginator cluster、非單一 PR-size sprint（紀律 #18）。

---

## 建議路徑（待 user 決策）

framePr 不適合像 Sprint 167 textAlignment 那樣「一個 clean sprint 收口」。三個可行
選項、各有取捨：

**選項 1 — opt-in flag 實作（Sprint 161-162 Strategy C 模式）**
Paginator 加 framePr 浮動實作、gate 在 `LayoutOptions.enableFramePr`（預設 false）。
預設關 → byte-identical；goldens 重生後再開 opt-in 量測 delta。
估 2-3 sprint。優點：現在就交付程式碼、預設零風險；缺點：功能「在但未啟用」、
真正生效仍等 decision B。

**選項 2 — 排在 decision B 之後**
先做 decision B（OnlyOffice goldens 重生），再以新 golden 為 anchor 直接實作
framePr（VR 可即時驗證對錯）。優點：實作即可 VR 驗證、不需 opt-in 中間態；
缺點：framePr 交付時間延後到 decision B 之後。

**選項 3 — 立即直接實作、接受 VR 變動**
現在直接做 framePr 浮動、跑 VR、若該 fixture 退化就分析。風險最高（Sprint 136
模式）、且 golden 本身 framePr 保真度未知 → 不建議。

→ **autopilot 不自行選**。framePr 的 wire-up 性質（layout-changing + golden baseline
依賴）與 user 下指令時的心智模型（「textAlignment / framePr 同類、1-2 sprint」）
不一致——屬紀律 #22「mental model vs 實況差距」+ 紀律 #18「scope 重分類走 user
認可」，**停下請 user 拍板選項 1 / 2 / 3**。

---

## Root cause

**為什麼 framePr 不能比照 textAlignment 一個 sprint 做完**：

1. textAlignment 是「行內微調」——OOXML 預設值（baseline）正好 = 引擎既有行為，
   wire-up 只需在「非預設」時加位移，預設路徑天然 byte-identical。
2. framePr 是「把段落抽離正常流」——沒有「不抽離也對」的預設，wire-up 必然改排版。
3. Sprint 140 把 textAlignment + framePr 綁成「決策 A」一起 DEFER，user GO 時也一起
   GO；但兩者工程性質差異大，probe 後才顯現——這正是紀律 #22 要求「開工前 probe」
   的價值（避免把 framePr 當 textAlignment 硬做、撞 Sprint 136 翻車）。

---

## 紀律

- **#22（probe-first）**：probe 3 步（fixture 取值 / framePr 語意 / layout 現況）在寫
  任何 code 前完成、識別「framePr ≠ Strategy C」「golden baseline 依賴 decision B」
  「非 PR-size」三項——0 行 production code、0 翻車風險。對比 Sprint 136（未充分評估
  layout 全域影響就改、VR 翻車 revert）。
- **#18（PR-size + scope 重分類）**：framePr 完整實作 2-3 sprint > 單 PR-size；scope
  從「決策 A 一個 sprint 做完」重分類為「需 user 選 sequencing」、走 user 認可。
- **#1.b（Sprint 136 翻車教訓）**：layout-changing 特性在 golden baseline 未對齊前
  實作 = 高風險；probe 主動識別、不硬做。
- **#8（架構發現也是 sprint 產出）**：「framePr 是 layout-changing、不可 Strategy C」
  「golden baseline 依賴 decision B」是本 sprint 的架構發現、為 user sequencing 決策
  提供明確輸入——docs-only sprint 仍有實質產出。

---

## 三層 SOP

| 層 | 結果 |
|---|---|
| L1 vitest | 不適用（docs-only、0 行 .ts/.js 變更、維持 1385 passed + 1 skipped） |
| L2 VR | 不適用（layout / render 路徑 0 變更、維持 mean 0.073191） |
| L3 spot check | docs 內容自審：probe 結論與 §5 L514 / progress_snapshot / state.json 一致 |
| L4 Odoo backend | 不適用 |

---

## 後續

- **等 user 決策**：framePr sequencing 選項 1（opt-in 實作）/ 2（排 decision B 後）/ 3（立即實作）。
- §5 L514 `<w:frame>` checkbox 維持 `[ ]`（probe DEFER、不打 `[x]`、比照 Sprint 164 bookmark）。
- 決策 A 狀態：part 1 textAlignment **done（Sprint 167）**；part 2 framePr **待 user sequencing**。

---

## Sprint 168 結尾累積指標

- vitest 1385 passed + 1 skipped（未動）
- VR mean 0.073191（未動、byte-identical 第 28 連）
- Odoo backend 31 passed（未動）
- Sprint audit doc 167 → 168
- §5 Phase 4.4 L514 framePr 維持 `[ ]`（probe DEFER）
- 0 行 production code 變更
