# Sprint 170 — `<w:framePr>` wrap 模式分派 + 側繞排除區（framePr cluster 2/2-3）

**日期**：2026-05-21
**類型**：wire-up（決策 A part 2、opt-in、Strategy C、framePr cluster 收尾）
**規畫書對應**：§5 Phase 4.4 L514 `<w:frame>` 段落框
**前置**：Sprint 169（framePr 浮動骨幹 + frameGroup.ts + layFramedParagraphs）
**分支**：`sprint-160-v2-instrtext-fldchar-render`

---

## Hypothesis

Sprint 169 落地 framePr 浮動骨幹：連續同 framePr 段落抽出正常流、子排版、依
vAnchor/hAnchor 定位、emit 絕對座標 LinePageEntry。但垂直空間策略只有一種——
topAndBottom-like「保留空間」（後續內文一律落框下方）。

本 sprint 補完 `framePr.wrap` 模式分派：`wrap=around` 時把框註冊為排除區、
後續內文 per-line 側繞（複用 Sprint 6 wrapSquare `activeFloats` 機制），
而非一律落框下方。

---

## 修法

### `layFramedParagraphs` 垂直空間策略改為 `wrap` 分派（Paginator.ts、+約 25 行）

Sprint 169 的單一「保留空間」尾段、改為依 `framePr.wrap` 三向分派：

| `framePr.wrap` | 行為 |
|---|---|
| `none` | 純浮動、不保留空間也不排除（框浮於內文上） |
| `notBeside` | 保留垂直空間（後續內文落框下方、Sprint 169 行為） |
| `around` / `tight` / `through` / 未設 | **側繞條件**成立 → 註冊 `activeFloats` 排除區；否則退回保留空間 |

**側繞條件（三者全成立）**：
1. `wrap !== 'notBeside'`
2. 顯式 `framePr.width`（auto-width 框退回保留空間 —— 見 scope-down）
3. `colWidth − frameWidth − hSpace ≥ FRAME_MIN_WRAP_TEXT_PT`（旁邊留得下內文）

側繞時：把框註冊為 `ActiveFloat`（`yTop/yBottom/xLeft/xRight` + `side` 依框中心
vs 欄中線判定 + `padding = framePr.hSpace ?? FRAME_DEFAULT_HSPACE_PT`），
`currentY` **不推進** —— 後續段落走 `layParagraph` 時、既有 `exclusionAtY`
per-line callback 自動把行寬縮減 + x 推移、過框底後 `purgeStaleFloats` 回全寬。

具名常數（紀律 #2）：`FRAME_DEFAULT_HSPACE_PT = 6`、`FRAME_MIN_WRAP_TEXT_PT = 72`。

### Strategy C（紀律 #1.b）

`enableFramePr` opt-in 未變；off → 整段路徑不走、byte-identical。
新增的側繞路徑**只對顯式 width 框生效**——唯一 framePr fixture 為 auto-width →
退回保留空間（Sprint 169 行為）→ 即使 opt-in 開、該 fixture 排版與 Sprint 169 一致。
VR pipeline 不傳 `enableFramePr` → 42 fixture byte-identical。

### Scope-down（紀律 #18）

- **auto-width 框不側繞、退回保留空間**：auto-width 框的「自然寬度 sizing + 側繞」
  語意需以 decision B golden 校準（Sprint 168 已標此依賴）。在 golden 未對齊前、
  auto-width 框維持保留空間（≈ Word 框過寬時內文自然落下方）。唯一 fixture 為
  auto-width → 不受新路徑影響。
- 框本身跨頁、`vAnchor=page/margin` 純浮動、`xAlign` 完整組合 → 留 Sprint 171。
- `tight`/`through` 比照 `around`（矩形排除區、不算 polygon、同 placeFloatImage Sprint 6）。

---

## Verification — 三層 SOP

| 層 | 結果 |
|---|---|
| **L1 vitest** | **1405 → 1410 passed + 1 skipped**（+5 Paginator.framePr：wrap=around 顯式窄框側繞 / wrap=notBeside 保留空間 / wrap=none 不保留不排除 / auto-width 退回保留 / 顯式框過寬退回保留） |
| **L2 VR v14** | VR pipeline bundle 重建 → 全 42 fixture × 126 page、**0 failed**、aggregate mean **0.073191**（byte-identical 第 30 連）。framePr fixture（auto-width）退回保留空間 → 與 Sprint 169 一致 |
| **L3 spot check** | §5 L514 `[ ]→[x]`（framePr layout wire-up 收尾）；audit doc / progress_snapshot / roadmap / state.json 一致 |
| **L4 Odoo backend** | 不適用 |

- `tsc --noEmit`：2 個 pre-existing error、無新增。
- frontend bundle 不重建（Paginator 非 production render path、同 Sprint 162/167/169）。
- flake8：不適用（0 行 Python）。

---

## Root cause

Sprint 169 的「保留空間」是 framePr 浮動的最小可行垂直策略、但 `wrap=around`
（framePr 預設 wrap 值）的真實語意是「內文側繞」。本 sprint 補上 wrap 分派、
複用 Sprint 6 為 wrapSquare floatImage 建的 `activeFloats` 排除區基礎建設——
framed paragraph 與 floatImage 在「佔據矩形區、內文 per-line 避讓」上同構、
共用同一機制（紀律 #14 DRY）。

側繞只對顯式 width 框開放、是因為 auto-width 框的自然寬度 sizing 會回頭改變
框寬與 jc 行為、且結果對錯需 golden 驗證（decision B）——在此之前限定顯式 width
是 honest 的 scope 邊界（紀律 #18）。

---

## 紀律

- **#1.b / Strategy C**：opt-in `enableFramePr`、側繞路徑僅顯式 width；off / auto-width
  → byte-identical。第 30 連。
- **#1.a**：改 layout 路徑跑全 42 fixture VR 驗證。
- **#14（DRY）**：側繞複用 Sprint 6 `activeFloats` + `exclusionAtY` + `purgeStaleFloats`，
  不另造排除區機制。
- **#2**：`FRAME_DEFAULT_HSPACE_PT` / `FRAME_MIN_WRAP_TEXT_PT` 具名常數。
- **#18 scope-down**：auto-width 側繞語意 / 框跨頁 / page·margin anchor / xAlign 完整
  組合 → Sprint 171；側繞限顯式 width 是 decision-B 依賴下的誠實邊界。

---

## 後續

- **決策 A 收尾**：part 1 textAlignment（Sprint 167）+ part 2 framePr（Sprint 169-170）
  皆完成 → **決策 A done**。
- **Sprint 171（optional 邊緣項）**：framePr 框跨頁、`vAnchor=page/margin` 絕對浮動、
  auto-width 自然寬度 sizing + 側繞、`xAlign` inside/outside 完整語意。皆為 opt-in
  路徑的邊緣強化、非阻斷項。
- **decision B 後**：開 framePr VR opt-in（如 `--frame-pr` flag、同 Sprint 162
  `--tab-stops` 模式）量測唯一 framePr fixture 排版改善 delta。

---

## Sprint 170 結尾累積指標

- vitest **1410 passed + 1 skipped**（+5）
- VR mean **0.073191**（byte-identical 第 30 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 169 → 170
- §5 Phase 4.4 L514 `<w:frame>` 段落框 `[ ]→[x]`（framePr layout wire-up 收尾）
- 決策 A（textAlignment + framePr）完成
