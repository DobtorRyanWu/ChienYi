# Sprint 169 — `<w:framePr>` 浮動段落框 layout wire-up（opt-in、cluster 1/2-3）

**日期**：2026-05-21
**類型**：wire-up（決策 A part 2、opt-in flag、Strategy C）
**規畫書對應**：§5 Phase 4.4 L514 `<w:frame>` 段落框 / §1 ParagraphProps.framePr
**前置**：Sprint 134（framePr capture）、Sprint 168（framePr probe）、user 2026-05-21 選「選項 1 — opt-in flag 實作」
**分支**：`sprint-160-v2-instrtext-fldchar-render`

---

## Hypothesis

Sprint 168 probe 確認 framePr 是 layout-changing 浮動特性、user 選 opt-in flag 路徑
（`LayoutOptions.enableFramePr` 預設 false → byte-identical、Strategy C 同 Sprint 161-162）。

本 sprint 為 framePr cluster 第 1 個 sprint：建立 framePr 偵測 / 分組 + Paginator
浮動排版骨幹。Sprint 170 升級為 `wrap=around` 排除區（後續內文側繞）。

---

## 修法

### 1. `LayoutOptions.enableFramePr`（types.ts、+15 行含註解）

opt-in 開關、預設 false。提供 `true` 後 Paginator 對連續同 framePr 段落啟動浮動排版。

### 2. 新檔 `static/src/core/layout/frameGroup.ts`（純函式、+57 行）

對映 Sprint 167 `verticalAlignShift.ts` —— 把可獨立測試的判別邏輯抽成純函式：

- `isFramedParagraph(block)`：block 是否為帶 framePr 的段落（type narrowing）
- `framePrEqual(a, b)`：兩 framePr 結構相等（12 欄位逐一比對）
- `frameGroupLength(body, startIdx)`：從 startIdx 起連續且 framePr 相等的框段落數

ECMA-376 §17.3.1.11：連續且 framePr 相同的段落由 Word 合併為單一 frame。

### 3. `Paginator` block loop wire-up + `layFramedParagraphs`（+約 140 行）

`paginate` 與 `layoutSectionInto` 兩處 block loop：`options.enableFramePr` 且 block
為框段落時、以 `frameGroupLength` 收集整組、交 `layFramedParagraphs`、跳過該組。
`enableFramePr` 關 → 永遠走原 `layParagraph` 路徑、與 Sprint 0-168 byte-identical。

`layFramedParagraphs`：
- **子排版**：逐段 `buildParagraph` + `breakParagraph`、收集各行框內相對座標
- **框寬**：`framePr.width` 顯式 → 用之；否則 auto → 用欄寬（內容 `jc` 在框內生效）
- **垂直錨點**：`vAnchor` text（預設、相對文字流）/ margin / page + `y` 偏移
- **水平錨點**：`computeFrameX` —— `xAlign` 優先（center/right/left/inside/outside），
  否則 `x` 偏移、基準依 `hAnchor`（page = 絕對 / margin·text = 相對欄左）
- **emit**：各行以絕對座標 emit 為 `LinePageEntry`（複用既有 renderer line entry 路徑、
  無需新 entry type）
- **垂直空間**：Sprint 169 對 `vAnchor=text` 採 topAndBottom-like「保留空間」
  （`currentY += yOffset + frameHeight`、後續內文落框下方不重疊）

### Strategy C（紀律 #1.b）

`enableFramePr` 未傳 / false → block loop 永走原路徑 → byte-identical by construction。
VR pipeline 不傳 `enableFramePr` → 42 fixture VR 不變（含唯一 framePr fixture
`06_template/檢(試)驗管制(預設樣板).docx`、mean 0.0263 未動）。

### Scope-down（紀律 #18）

- **wrap=around 排除區留 Sprint 170**：Sprint 169 採「保留垂直空間」（內文落框下方），
  非真正側繞。fixture 框為文件頂端標題塊、保留空間即非重疊、視覺可接受的中間態。
- 框內 floatImage / floatTextBox 過濾掉當純內文（罕見、發 warning）。
- 框內 numbering 前綴不展開（`buildParagraph` 第 4 參數傳 undefined）。
- 框本身跨頁不支援（放不下當前頁則先 flush、留 Sprint 171）。
- `vAnchor=page/margin` 不保留垂直空間（純浮動、可能與內文重疊、發 warning）；
  唯一 fixture 為 `vAnchor=text`、主路徑完整。

---

## Verification — 三層 SOP

| 層 | 結果 |
|---|---|
| **L1 vitest** | **1385 → 1405 passed + 1 skipped**（+20：frameGroup 14 + Paginator.framePr 6）。涵蓋 isFramedParagraph / framePrEqual / frameGroupLength 分組邏輯；enableFramePr 關 → byte-identical；開 → vAnchor=text y 偏移、框後內文不重疊、連續同 framePr 合併、不同 framePr 不合併、auto 框寬 jc=center 置中 |
| **L2 VR v14** | VR pipeline bundle 重建 → 全 42 fixture × 126 page、**0 failed**、aggregate mean **0.073191**（byte-identical 第 29 連）。framePr fixture `06_template/檢(試)驗管制(預設樣板).docx` mean 0.0263 未動 → 證實 Strategy C（VR pipeline 不傳 enableFramePr） |
| **L3 spot check** | §5 L514 維持 `[ ]`（cluster 未完工、Sprint 170 排除區完成後再評估）；audit doc / progress_snapshot / roadmap / state.json 一致 |
| **L4 Odoo backend** | 不適用（無 backend 變更） |

- `tsc --noEmit`：**2 個 pre-existing error**（FontMetrics opentype.js / SettingsParser position enum）、無新增。
- frontend bundle 不重建：`grep` 確認 `layFramedParagraphs` / `enableFramePr` 不在 `canvas-editor-custom.umd.js`（Paginator 非 production render path、同 Sprint 162/167）。
- flake8：不適用（0 行 Python）。

---

## Root cause

framePr 自 Sprint 134 capture 後無 layout consumer。Sprint 168 probe 確認其為
layout-changing 浮動特性、user 選 opt-in 路徑。本 sprint 複用既有基礎建設把它接通：

- framePr frame = 浮動定位的段落塊 → 複用 `buildParagraph` + `breakParagraph` 子排版
- frame 各行 = 絕對座標內容 → 複用 `LinePageEntry`（renderer 既有 line entry 路徑）、
  不需新 entry type
- frame 抽離正常流 → 在 block loop 攔截、不進 `layParagraph`

opt-in flag 使本 sprint 與 Sprint 161-162 tab stop 同模式：layout wire-up 落地、
預設關保 byte-identical、真正生效（VR opt-in 量測）待 decision B goldens 重生。

---

## 紀律

- **#22（probe-first）**：Sprint 168 probe 已建立 mental model（framePr = layout-changing
  浮動、需 opt-in）；本 sprint 直接實作、無翻車。
- **#1.b / Strategy C**：`enableFramePr` opt-in、block loop 預設走原路徑 → byte-identical
  by construction（同 Sprint 139 numbering / 161-162 tab stop）。
- **#1.a**：改 layout 路徑、即使預期 byte-identical 仍跑全 42 fixture VR（第 29 連）。
- **#14（模組化）**：framePr 判別純函式聚集於 `frameGroup.ts`、與 Paginator 有狀態流程分離。
- **#18（PR-size + scope-down）**：cluster 切分 —— Sprint 169 浮動骨幹（保留空間）、
  Sprint 170 排除區（側繞）；框內 floatImage / numbering / 跨頁 / page·margin anchor
  皆 scope-down 並 honest declare。

---

## 後續

- **Sprint 170**：framePr cluster 第 2 個 sprint —— `wrap=around` 排除區。把框註冊為
  `activeFloats` 排除區（複用 Sprint 6 wrapSquare 機制）、後續內文 per-line 側繞而非
  落框下方。完成後 §5 L514 評估 `[x]`。
- **Sprint 171（如需要）**：框跨頁、`vAnchor=page/margin` anchor、`xAlign` 完整組合。
- **decision B 後**：開 VR opt-in（如 `--frame-pr` flag）量測唯一 framePr fixture 的
  排版改善 delta（同 Sprint 162 `--tab-stops` 模式）。

---

## Sprint 169 結尾累積指標

- vitest **1405 passed + 1 skipped**（+20）
- VR mean **0.073191**（byte-identical 第 29 連）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（無新增）
- Sprint audit doc 168 → 169
- 新檔 `frameGroup.ts`（純函式 layer）
- §5 Phase 4.4 L514 framePr 維持 `[ ]`（cluster 進行中、Sprint 170 完工後評估）
