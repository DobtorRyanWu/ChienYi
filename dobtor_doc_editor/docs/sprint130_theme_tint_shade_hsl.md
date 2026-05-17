# Sprint 130 — Theme tint/shade 演算法升級為 HSL luminance（Phase 4.1）

**日期**：2026-05-17
**類型**：code change（演算法升級 / Phase 4.1 Style Theme 收口）
**規畫書對應**：§Phase 4.1 Theme 系統「Tint/shade 演算法（HSL luminance 計算）」+ autonomous_roadmap.md 階段 B 行 4 cluster 4/4 起點
**前置 sprint**：Sprint 128 HarfBuzz spike + autonomous DEFER-1（cluster 3 收尾）

---

## Hypothesis（驗證對象）

`ThemeResolver.resolveThemeColor` 的 `applyTint` / `applyShade` 自 Sprint 1 起用 **RGB linear blend**（往白/黑線性插值）；ThemeResolver.ts 第 18-19 行原註解承認：

> tint/shade 演算法用 RGB linear 而非 HSL luminance（OOXML §20.1.2.3.20 的精確版要 HSL 轉換；linear 對 typical fixture 視覺差異 < 5pp，trade-off accuracy for code simplicity）

規畫書 §Phase 4.1 第 470 行明列「Tint/shade 演算法（HSL luminance 計算）」為待完工項目。

**Hypothesis A（功能正確性）**：HSL 版本對 vivid 色（如 deep navy `000080`）保留 hue+saturation、不再 wash out 為灰紫；對 mid-saturation 色（如 Office accent1 `4F81BD`）結果與 RGB linear 在 ±1 RGB 內。

**Hypothesis B（VR 穩定性）**：42 fixture 多數使用 Office 預設 accent 色（mid-saturation 4F81BD 系），HSL 與 linear 差異 < 5pp、VR 預期 byte-identical（紀律 #1.a 第 7 次連續驗證機會）。

---

## Method

### 1. Scope 對齊（紀律 #18）

- autonomous_roadmap.md 階段 B 行 4 cluster：「130-131 | Phase 4 Style | 4.1 Theme tint/shade 演算法(HSL luminance)、4.2 tblStylePr 15 種條件完整」
- 規畫書 §Phase 4.1 line 470：「Tint/shade 演算法(HSL luminance 計算)」
- 本 sprint scope = **只升級 applyTint/applyShade 內部演算法 + 加 11 個 HSL 驗證 test**
- 不在 scope（留 Sprint 131+）：
  - tblStylePr 15 種條件完整（Sprint 131）
  - 中文編號格式（Sprint 132）
  - 把 themeColor 換成 deferred resolve 給 BorderConflictResolver 共用（屬未來重構）
  - DrawingML §20.1.2.3.20 完整 luminance modulation/offset（lumMod/lumOff、屬 §Phase 5 OMML/SmartArt 之後再評估）
- PR-size：ThemeResolver.ts +80 行（含註解與 helper）/ ThemeResolver.test.ts +145 行 / 11 新 test / 1 audit / 1 bundle rebuild

### 2. 演算法設計

#### 2.1 OOXML themeTint/themeShade 語意（ECMA-376 §17.18.97/.85）

- `w:themeTint="00"` = 不變色；`w:themeTint="FF"` = 全白
- `w:themeShade="00"` = 不變色；`w:themeShade="FF"` = 全黑
- 解析為 0..1：`fraction = parseInt(hex, 16) / 255`

#### 2.2 RGB linear（原版）vs HSL luminance（Sprint 130）

| 演算法 | 公式 | hue/saturation | 缺點 |
|---|---|---|---|
| RGB linear（Sprint 1）| `out = base * (1-t) + 255 * t`（tint）/ `out = base * (1-s)`（shade）| **不保留**（往灰色拉）| vivid 色被 wash out（如 navy → 淡紫）|
| HSL luminance（Sprint 130、規畫書要求）| `L_new = L + (1-L) * t`（tint）/ `L_new = L * (1-s)`（shade）；h, s 保留 | **保留** | hue/saturation 完整保留、視覺更接近 Word |

#### 2.3 邊界值與舊版相容性

| 極端值 | RGB linear 結果 | HSL luminance 結果 | 相容？ |
|---|---|---|---|
| `tint=00` | base 不變 | `L_new = L + 0 = L` → base 不變（HSL→RGB roundtrip 精度足夠完美還原 4F81BD）| ✓ |
| `tint=FF` | white `FFFFFF` | `L_new = 1.0` → s 無論為何、所有通道=255 → white | ✓ |
| `shade=00` | base 不變 | `L_new = L * 1 = L` → base 不變 | ✓ |
| `shade=FF` | black `000000` | `L_new = 0` → s 無論為何、所有通道=0 → black | ✓ |
| 灰階 base（R=G=B）| 結果仍 R=G=B | s=0、HSL→RGB 走 grayscale short-circuit、結果仍 R=G=B | ✓（無 hue artifact）|

### 3. 修法

#### 3.1 ThemeResolver.ts（+80 行、純內部 helper）

```ts
// Tint：L_new = L + (1 - L) * t，HSL 保 hue+saturation
function applyTint(hex: HexColor, t: number): HexColor {
  const tt = clamp01(t);
  const [r, g, b] = hexToRgb(hex);
  const [h, s, l] = rgbToHsl(r, g, b);
  const lNew = l + (1 - l) * tt;
  const [nr, ng, nb] = hslToRgb(h, s, lNew);
  return rgbToHex([Math.round(nr), Math.round(ng), Math.round(nb)]);
}

// Shade：L_new = L * (1 - s)
function applyShade(hex: HexColor, s: number): HexColor { /* 對稱 */ }

// 標準 RGB↔HSL 公式（caller 自行 round）
function rgbToHsl(r, g, b): [h, s, l] { /* max==min → [0, 0, l] grayscale */ }
function hslToRgb(h, s, l): [r, g, b] { /* s==0 → [L*255, L*255, L*255] grayscale */ }
function hueToRgb(p, q, t): number { /* 標準 6-segment */ }
```

設計細節：

- **公共 API 完全不變**：`resolveThemeColor` 簽章與行為對所有 `(themeColor, tint, shade)` 組合的最終 hex 與舊版在 mid-saturation 色差異 ≤ 1 RGB；對 vivid 色不同（更符 OOXML 規範）
- **Grayscale short-circuit**：`max === min` 時 hue 無定義、回 `[0, 0, l]`；`s === 0` 時 HSL→RGB 不走 hueToRgb 直接回 `[L*255, L*255, L*255]`；避免 NaN/除零
- **Floating-point 穩定性**：HSL→RGB roundtrip 對 base color 在 mid 色域可 exact 還原（如 4F81BD → tint=00 → 4F81BD），是 unit test 鎖定的 invariant

#### 3.2 註解同步

頭部 JSDoc 第 13-19 行原「linear 對 typical fixture 視覺差異 < 5pp」段落更新為「Sprint 130 升級為 HSL luminance（規畫書 §Phase 4.1）」；列出原版 trade-off 與升級理由。

### 4. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | ✅ **1044 passed + 1 skipped**（從 1033+1 起、+11 新 Sprint 130 HSL test）|
| L2 VR v14 | ✅ **0.073191 mean / 0 failed / 126 pages**（byte-identical、**第 7 次連續**、紀律 #1.a 應用）|
| L3 Spot check | ✅ TypeScript build PASS（pre-existing warning 同前、bundle rebuild 31.9s）|
| L4 Odoo backend | **跳過**（無 backend / model / ACL 變動）|

### 5. Unit test 設計（11 個新 test + 1 個更新）

| Test | 鎖定行為 |
|---|---|
| (更新) themeTint 把顏色推向白（HSL luminance）| 補充 hue 保留斷言：`B > G > R`（accent1 為藍色）|
| 深藍 (000080) tint=80 保留藍色相、不 wash out 為灰色 | **HSL vs Linear 最大差異情境**：vivid navy → HSL 仍 saturated blue (B>220, R<100)、Linear 變淡紫 (R=G=128) |
| 純紅 (FF0000) tint=80 維持紅色相、不變灰 | R 仍 saturated (>240)、G=B（純紅 hue 對稱保留）|
| 純灰 (808080) tint=80 維持灰階、無 hue artifact | R=G=B 不變、L 變亮（避免 grayscale short-circuit 失效）|
| 純灰 (808080) shade=80 維持灰階、無 hue artifact | R=G=B 不變、L 變暗 |
| tint=00 round-trip 完美還原 | HSL 轉換鏈無精度漂移（4F81BD → tint=00 → 4F81BD exact）|
| shade=00 round-trip 完美還原 | 同上、shade 路徑 |
| tint 單調性：tint 值愈大、L 愈接近 1.0 | tint=20/60/C0 三點 R 通道應 monotonic 上升 |
| shade 單調性：shade 值愈大、L 愈接近 0 | shade=20/60/C0 三點 R 通道應 monotonic 下降 |
| 白色 base tint=80/FF 仍為白 | L=1.0 上限 saturation、tint 無作用 |
| 黑色 base shade=80/FF 仍為黑 | L=0 下限 saturation、shade 無作用 |
| 黑色 base tint=80 推向白（L 從 0 上升）| L=0 + 0.502 = 0.502 → 中灰 ≈ 128、R=G=B（黑無 hue source）|

---

## Result

### 檔案變動

| 檔 | Δ | 用途 |
|---|---|---|
| `static/src/core/ooxml/styles/ThemeResolver.ts` | +80 / -10 行（applyTint/applyShade 演算法替換 + rgbToHsl/hslToRgb/hueToRgb helper + JSDoc 更新）| 演算法升級 |
| `tests/unit/ThemeResolver.test.ts` | +145 行 / 11 新 test + 1 既有 test 補強 | 鎖定 HSL 行為 |
| `static/src/lib/canvas_editor/canvas-editor-custom.umd.js` | rebuild（紀律 #1.a）| IIFE bundle 同步 |
| `tests/fixtures/visual_regression_v14_report.json` | timestamp re-run、數值 byte-identical | VR confirm |
| `docs/sprint130_theme_tint_shade_hsl.md` | 本 audit doc | 紀錄演算法升級設計 |
| `docs/autonomous_roadmap.md` | cluster 4 (130-131) 開工 + Sprint 130 ✅ + 進度表 | cluster 4 啟動 |
| `dobtor_doc_editor_高保真匯入開發規劃.md` | §0.2 Phase 4 80% → 81% + §Phase 4.1 標 Sprint 130 收口 | 同步 |

### Test 數變動

- Sprint 128 結尾：vitest 1033 + 1 skipped
- Sprint 130 結尾：vitest **1044 + 1 skipped**（+11）/ Odoo backend 31（未動）

### VR 數變動

- Sprint 128 結尾：mean 0.073191（未跑、spike test only）
- Sprint 126 結尾：mean 0.073191（最後一次正式跑）
- Sprint 130 結尾：mean **0.073191**（byte-identical、**第 7 次連續** 121→122→123→124→125→126→130）

### 規畫書 §0.2 Phase 完成度

- Phase 4 Style Theme：80% → **81%**（+1%、4.1 tint/shade 演算法升級 HSL luminance、規畫書原列待完工項目收口）

---

## Root cause

**為什麼 RGB linear 跑 1-129 sprint 沒升級**：

1. Sprint 1 落地 ThemeResolver 時優先實作 color resolution 主路徑（themeColor lookup + tint/shade application）；演算法本身選 RGB linear 為 simplicity 並在註解承認 trade-off
2. 42 fixture 多用 Office 預設 accent 色（mid-saturation 如 4F81BD），HSL vs RGB linear 結果 ±1 RGB、無 VR signal trigger 強迫升級
3. 規畫書 §Phase 4.1 一直列為待完工，但 Phase 1-3 OOXML/Layout 主軸優先、Phase 4 排在後段
4. autonomous_roadmap.md 階段 B cluster 4 開工 = 第一次有結構化機會把 §Phase 4.1 收口
5. 紀律 #21 候選驗證進展 + cluster 3 (127-128) 完成後、自然進入 cluster 4

**為什麼 VR byte-identical**：

42 fixture 用色狀況（spot survey）：

- 黑色文字（`val=000000` 或預設）：**主要**
- 預設 accent1 `4F81BD`（mid-saturation 藍）：表格邊框、標題顏色
- accent 系列 tint=20/40：少量強調文字
- 深 vivid 色：**幾乎沒有**

mid-saturation + 小幅 tint = HSL 與 Linear 差 ±1 RGB、PNG 像素化後通常無 visible diff。預期未來如 fixture 含 vivid 色（如紅色警告印章、深藍標題），HSL 升級會顯示 VR drift +/- 0.5pp（小但 detectable）。

---

## 紀律

### 紀律 #1.a 第 7 次連續驗證（Sprint 130）

連續 7 sprint code change 都跑全 VR 並維持 byte-identical：

| Sprint | 改動 | VR |
|---|---|---|
| 121 | TableParser trHeight defensive | 0.073191 |
| 122 | ParagraphParser OLE/pict fallback | 0.073191 |
| 123 | ParagraphParser field code 完整覆蓋 | 0.073191 |
| 124 | dom.ts effectiveChildren sdt unwrap | 0.073191 |
| 125 | ParagraphParser bookmark capture（首次真實 trigger）| 0.073191 |
| 126 | parseHyperlinkInfo 擴 3 屬性 | 0.073191 |
| **130** | **applyTint/applyShade HSL 升級** | **0.073191** |

紀律 #1.a 穩固、7 次連續 byte-identical、覆蓋 OOXML parser / dom utility / style resolver 三類修改點。

### 紀律 #4 應用（Sprint 130）

> 負面結果 sprint 仍有結構價值；揭示隱性 assumption 是真實學習。

Sprint 130 揭示：

1. **fixture 用色集中在 mid-saturation + 黑色**：HSL 升級的「正確性」收益對當前 42 fixture 不顯著、但對未來 vivid 色（紅章/深藍 logo）關鍵
2. **演算法升級 ≠ VR mean 改善**：HSL 是 spec correctness、不是 fidelity improvement metric；VR mean 改善要靠 metric anchor 換（階段 C 重生 goldens 用 Word desktop）
3. **規畫書 §Phase 4.1 列為 1 週工作量、實際 1 sprint 完成**：因有 Sprint 1 既有 colorResolver 基礎、不需重寫；證實 Phase 4 剩餘工作量被高估

### 紀律 #18 持續

PR-size 守住：ThemeResolver.ts +80 / test +145 / 1 audit / 1 bundle rebuild。明示 4 項不在 scope：tblStylePr / 中文編號 / deferred resolve / DrawingML lumMod/lumOff。

### 紀律 #21 候選跨 sprint 驗證進展 2 → 2（持平）

Sprint 125-126 揭示「optional 欄位空集合不掛 key」、Sprint 130 不涉 optional 欄位掛 key 場景（純內部演算法）、候選持平 2/3。下次涉 AST 欄位擴充再驗第 3 次。

---

## 後續

### Sprint 131（cluster 4 第 2 個、規畫書 §Phase 4.2）

階段 B cluster 4 第 2 個：**Phase 4.2 tblStylePr 15 種條件完整**（規畫書原列 1 週）。

當前 tblStylePr 部分支援（StyleResolver 中），Sprint 131 補完 15 種：
- `firstRow` / `lastRow` / `firstCol` / `lastCol`
- `band1Vert` / `band2Vert` / `band1Horz` / `band2Horz`
- `neCell` / `nwCell` / `seCell` / `swCell`
- `wholeTable`
- `band1` / `band2`（雙欄帶狀條件）

預期 PR-size 中等：StyleResolver / TableMapper 各 +30~60 行、unit test +60~80 行。

### Sprint 130+ 候選

- **DrawingML 完整 luminance modulation/offset**（`lumMod` / `lumOff`）：Office 進階 chart / SmartArt 用、屬 §Phase 5 範圍、defer
- **deferred theme resolve**：把 themeColor 留到 mapper 階段才解析、為 export round-trip 鋪路、屬 §Phase 6 範圍、defer
- **更精準 HSL（如 HSY luminance 替代 HSL）**：學術差別、視覺差異 << 1pp、defer

---

## Sprint 130 結尾累積指標

- vitest **1044 passed + 1 skipped**（+11）
- VR mean **0.073191** / failed 0 / compared 126（byte-identical、**第 7 次連續**）
- Odoo backend local 31 passed（未動）
- CI gate v1 12 passed（未動）
- Phase 4 Style Theme 80% → **81%**
- 21 ADR / 19 條紀律 + 6 子 + 3 候選（無新增、#22 候選持平 2/3、#21 候選持平 2/3）
- Sprint audit doc 數 128 → **130**（129 留空、Sprint 128 audit 釐清）
- 階段 B cluster 4 (130-131) **開工**、cluster 3 (127-128) 已完成

---

## File-level summary

```
M  addons/dobtor_doc_editor/static/src/core/ooxml/styles/ThemeResolver.ts  (+80/-10 行 HSL 演算法 + 註解更新)
M  addons/dobtor_doc_editor/tests/unit/ThemeResolver.test.ts  (+145 行 / 11 新 test + 1 既有補強)
M  addons/dobtor_doc_editor/static/src/lib/canvas_editor/canvas-editor-custom.umd.js  (rebuild)
M  addons/dobtor_doc_editor/tests/fixtures/visual_regression_v14_report.json  (re-run、byte-identical)
A  addons/dobtor_doc_editor/docs/sprint130_theme_tint_shade_hsl.md  (本 audit doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (cluster 4 開工 + Sprint 130 ✅)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (Phase 4 80→81%)
```

無 model / view / ACL / rule / controller / backend 變動。階段 B cluster 4 開工、Phase 4 規畫書收口進度推進。
