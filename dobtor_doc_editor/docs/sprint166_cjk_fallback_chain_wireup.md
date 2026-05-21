# Sprint 166 — CJK fallback chain → FontLoader wire-up

**日期**：2026-05-21
**類型**：wire-up（方向 A、production code 變動）
**規畫書對應**：§5 Phase 2 §2.2「CJK fallback 鏈：原字型 → 思源黑體 / 微軟正黑體 → 新細明體 → 預設字型」（L406）
**前置**：Sprint 147（FontTableParser capture、含 `charset`）、Sprint 157（fontTable.altName → FontLoader fallback wire-up）
**執行**：user 主導互動式 session（非 autopilot loop）

---

## 0. 開工前狀態（紀律 #14.b 第 0 步）

`git status -s dobtor_doc_editor/` = 空（Sprint 165 commit `d3f4bae` 已收口）。
working tree（dobtor_doc_editor 子樹）clean。

> 註：`addons` repo 其他模組（`construction_*`）有大量 pre-existing drift（.pyc /
> portal 模板等），非本 sprint 範圍、非 dobtor_doc_editor 子樹、不處理。紀律 #14.b
> 的檢查標的是 `dobtor_doc_editor/` 子樹、已 clean。

---

## 1. Hypothesis

規畫書 §5 Phase 2 §2.2 L406「CJK fallback 鏈」是 Phase 2 字型管線的明列工項、Sprint 156
checkbox audit 後仍 `[ ]`。

Sprint 157 已落地 FontLoader 的 fontTable.altName fallback（主 family fetch 失敗 →
試 `fontTable[family].altName` 一次）。CJK fallback chain 是同一條 fallback 路徑的
**第三層**：主 family → altName → **通用 CJK chain** → silent fallback。

**probe（紀律 #22）**：
- **consumer**：`grep` 確認 `font_loader.ts` 在 `static/src/` 內**無 import 來源**、
  只有 `tests/unit/FontLoader.test.ts` 引用。FontLoader 是「caller-side 載 fonts 的
  標準介面 infrastructure」、production canvas-editor 尚未消費（Sprint 64b / 157 已
  誠實註記、本 sprint 維持同定位）。VR pipeline 有獨立 font load 路徑、不經此 module。
- **CJK 判別子**：Sprint 147 FontTableParser 已 capture `FontEntry.charset`（OOXML
  `w:charset`、hex 字串）。CJK 語系 charset = `'80'` ShiftJIS（日）/ `'81'` Hangul
  （韓）/ `'86'` GB2312（簡中）/ `'88'` ChineseBig5（繁中）。拉丁 charset `'00'`
  ANSI 不在集合 → 不誤套。
- **mental model**：fallback chain 必須在主 + altName 都失敗後才試；註冊用「主
  family」name（caller 仍以原 family 查）；chain 成員若等於主 family / altName 須
  跳過避免重複 fetch。

**Hypothesis**：在 `loadFontsAndBuildAdapter` 的 altName retry 之後加一段——
若 `entry` 存在且 `isCjkFont(entry)`、依序 fetch `CJK_FALLBACK_CHAIN`、首個成功者
以主 family name 註冊。caller 不傳 fontTable / family 非 CJK → 行為與 Sprint 157
完全一致（backward compat、不破 baseline）。

---

## 2. Method

### 2.1 production code（`static/src/core/font_loader.ts`、+約 30 行）

新增模組級常數 + helper：

```ts
const CJK_FALLBACK_CHAIN: readonly string[] = ['思源黑體', '微軟正黑體', '新細明體'];
const CJK_CHARSETS: ReadonlySet<string> = new Set(['80', '81', '86', '88']);

function isCjkFont(entry: FontEntry): boolean {
  return entry.charset !== undefined && CJK_CHARSETS.has(entry.charset);
}
```

`loadFontsAndBuildAdapter` 內 fallback 段（Sprint 157 altName retry 之後）：

```ts
if (!bytes && fontTable) {
  const entry = fontTable.get(family);
  const altName = entry?.altName;
  if (altName && altName !== family) {
    bytes = await getOrFetchFontBytes(altName, endpoint, timeout);
  }
  // Sprint 166:主 + altName 都失敗、且 family 經 charset 判定為 CJK
  if (!bytes && entry && isCjkFont(entry)) {
    for (const fallback of CJK_FALLBACK_CHAIN) {
      if (fallback === family || fallback === altName) continue;
      bytes = await getOrFetchFontBytes(fallback, endpoint, timeout);
      if (bytes) break;
    }
  }
}
```

- import 加 `FontEntry`（型別）。
- 註冊維持 `adapter.registerFont(family, ...)`——用主 family name、caller 不需知道
  實際拿到的是哪個 fallback（同 Sprint 157）。
- chain 成員 `=== family || === altName` 跳過：避免「主 family 本身就是思源黑體」
  或「altName 本身就是微軟正黑體」時重複 fetch 同一 URL。

### 2.2 紀律 #18 scope-down

- **CJK 判別只用 `charset`**：`FontEntry` 另有 `sig`（FontSignature、含 codepage
  bits）可更精準判 Unicode 支援度——本 sprint **不用**、charset 已足夠且最直接。
  sig-based 判別列後續可選。
- **chain 固定 3 個**：嚴格照規畫書 §2.2 文字「思源黑體 / 微軟正黑體 → 新細明體」、
  不擴充 Noto / 平台別名。
- **不碰 §2.2 其他 `[ ]`**（字型載入器 WOFF2 CDN / 字元涵蓋檢測 / Glyph 快取）——
  各自獨立 sprint。
- **不動 production render 路徑**：FontLoader 無 production consumer（probe 確認）、
  本 sprint 維持「caller-side infrastructure」定位、不為了「接到 render」而擴 scope。

### 2.3 新測試（`tests/unit/FontLoader.test.ts`、+10 test、新 `describe` block）

新 helper `mkCjkFontTable`（含 `charset` 欄位、不動 Sprint 157 的 `mkFontTable`）：

| # | test | 驗證 |
|---|---|---|
| 1 | 主+altName 都 404、charset=88 → chain 第一個勝出、主 family 名註冊 | 繁中、3-tier 完整路徑 |
| 2 | 主 404、無 altName、charset=86 → chain 試 | 簡中、無 altName 分支 |
| 3 | 主 404、charset=80 → chain 試 | 日文 ShiftJIS、charset 集合涵蓋驗證 |
| 4 | charset=00（ANSI 拉丁）→ chain 不試 | 拉丁字型不誤套 CJK |
| 5 | 有 family 無 charset → chain 不試 | charset undefined 防禦 |
| 6 | family 不在 fontTable → chain 不試 | 與 Sprint 64b/157 一致 |
| 7 | charset=88 但 chain 全 404 → silent fallback | 「預設字型」= EstimateMetrics fallback |
| 8 | chain 成員 == 主 family / altName → 跳過不重複 fetch | 去重邏輯 |
| 9 | 主 200 → chain 不試 | fast path |
| 10 | 不傳 fontTable → chain 不套 | backward compat（Strategy C）|

---

## 3. Verification（三層 SOP）

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1361 → 1371 passed + 1 skipped**（+10 CJK fallback chain tests；FontLoader.test.ts 18→28）|
| L2 VR v14 | **跳過（誠實聲明）** | `font_loader.ts` 不在 VR pipeline、不在 render 路徑（probe 確認 0 import 來源、module 自身 doc 註明「VR pipeline 有獨立 font load 路徑、不經此 module」）。render 路徑 0 變更、baseline by construction 不變、維持 mean 0.073191。比照 Sprint 157 同型處理 |
| L3 spot check | ✅ | font_loader.ts +約 30 行（常數×2 + helper×1 + fallback 段）、FontLoader.test.ts +約 130 行；§2.2 L406 `[ ]`→`[x]` |
| L4 Odoo backend | **跳過（誠實聲明）** | 純前端 TS、未改 controller / model |
| L5 frontend bundle | **跳過（誠實聲明）** | `font_loader.ts` 無 production import 來源、不在 `canvas-editor-custom.umd.js` render bundle；同 Sprint 157 |

### 3.1 typecheck

`npx tsc --noEmit`：**2 個 pre-existing error**（FontMetrics opentype.js 宣告 /
SettingsParser position enum），Sprint 166 新增 `CJK_FALLBACK_CHAIN` /
`CJK_CHARSETS` / `isCjkFont` / `FontEntry` import **不引入新 error**。

### 3.2 紀律應用

| 紀律 | 應用 |
|---|---|
| #22 probe before action | 開工前 probe FontLoader consumer（確認無 production import、定位 infrastructure）+ CJK 判別子（charset 集合）+ mental model（3-tier fallback 順序、去重）|
| #18 PR-size + scope-down | 只做 CJK chain、charset-only 判別（不碰 sig）、chain 固定 3 個、不碰 §2.2 其他 `[ ]`、不擴 production render 整合 |
| #14.b 第 0 步 working tree | 開工前確認 dobtor_doc_editor 子樹 clean |
| Strategy C（Sprint 139/157 模式） | caller 不傳 fontTable / family 非 CJK → 行為與 Sprint 157 byte-identical；FontLoader 不在 VR/render 路徑、baseline by construction 不變 |
| #1.a 改 layout 跑全 VR | **不適用**——font_loader.ts 非 parser/style/layout、是 caller-side network/IDB 工具；同 Sprint 157 不跑 VR、誠實聲明 |

---

## 4. Result

### 4.1 檔案變動

```
M  static/src/core/font_loader.ts                   (+約 30：常數×2 + isCjkFont + fallback 段 + FontEntry import + 檔頭 doc)
M  tests/unit/FontLoader.test.ts                     (+約 130：mkCjkFontTable + 10 test)
M  dobtor_doc_editor_高保真匯入開發規劃.md            (§2.2 L406 [ ]→[x])
A  docs/sprint166_cjk_fallback_chain_wireup.md       (本 audit doc)
M  docs/progress_snapshot.md / autonomous_roadmap.md / INDEX.md
```

### 4.2 累積指標

| 指標 | Sprint 165 結尾 | Sprint 166 結尾 | 變動 |
|---|---|---|---|
| vitest | 1361 passed + 1 skipped | **1371 passed + 1 skipped** | +10 |
| VR mean | 0.073191（第 27 連 byte-identical）| 0.073191（未跑、font_loader 不在 VR 路徑）| 0 |
| Odoo backend | 31 passed | 31 passed（未跑、無 backend 變動）| 0 |
| `tsc --noEmit` | 2 pre-existing error | 2 pre-existing error（無新增）| 0 |
| 規畫書 §2.2 | 1/5 `[x]` | **2/5 `[x]`**（+CJK fallback 鏈）| +1 |
| Sprint audit doc | sprint165 | **sprint166** | +1 |

---

## 5. 與規畫書關係

§5 Phase 2 §2.2「CJK fallback 鏈」L406 `[ ]`→`[x]`。

Phase 2 字型管線的 fallback 路徑三段式收束（FontLoader 層）：
1. 主 family fetch（Sprint 64b）
2. fontTable.altName retry（Sprint 157、OOXML §17.8 官方建議替代）
3. **通用 CJK fallback chain（Sprint 166、charset 判別）**
4. 全失敗 → silent fallback EstimateMetrics（=「預設字型」）

§2.2 剩餘 `[ ]`：字型載入器 WOFF2 CDN 補字（L402）、字元涵蓋檢測（L407）、
Glyph 快取（L408）——各自獨立 sprint。

### 誠實定位（同 Sprint 157）

FontLoader 是 **caller-side 載 fonts 的標準介面 infrastructure**、production
canvas-editor 路徑**尚未消費**此 module。§2.2 的 `[x]` 是「FontLoader 層的 fallback
邏輯完整且測試覆蓋」、不等於「production render 端每個缺字都自動走 CJK chain」。
真實 production 整合須等自家 pipeline migration（Sprint 127 probe 揭示的
architectural migration、Strategy A/B/C/D 待 user 決策）。

---

## 6. 後續

- **§2.2 sig-based CJK 判別（可選精進）**：目前用 `charset`；`FontEntry.sig`
  （FontSignature codepage bits）可更精準判 Unicode 支援度、處理 charset 缺失但 sig
  有 CJK bit 的 docx。屬可選精進、非必要。
- **§2.2 字元涵蓋檢測（L407）**：「每個 codepoint 確認字型支援」——須 opentype.js
  glyph lookup、與 GlyphCache（L408）相關、獨立 sprint。
- **FontLoader production 整合**：Sprint 127 probe 揭示的 FontMetricsAdapter
  production migration（Strategy A/B/C/D）——待 user 決策、CJK chain 屆時隨之生效。
- **型別債 follow-up（Sprint 165 §後續沿用）**：SettingsParser `position` enum
  union 收緊、`tsc` error 2→1。

---

## Sprint 166 結尾累積指標

- vitest 1371 passed + 1 skipped（+10）
- VR mean 0.073191（未跑、font_loader 不在 VR 路徑、render 0 變更）
- Odoo backend 31 passed（未動）
- `tsc --noEmit` 2 個 pre-existing error（未動）
- Sprint audit doc 164 → 165
- 規畫書 §2.2 CJK fallback 鏈 `[ ]`→`[x]`（§2.2 2/5）
- 淨 production code 變動 = +約 30 行（font_loader.ts）
