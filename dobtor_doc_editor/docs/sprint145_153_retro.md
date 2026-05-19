# Sprint 145-153 方法論回顧 — Phase 1 capture-only 九連 cluster + 整數里程碑

**Sprint 154 落地 / 2026-05-19**
**範圍**:Sprint 145(Footnotes 開頭)→ Sprint 153(latentStyles 收尾)、跳過 149 retro、9 個 production sprint
**性質**:方法論 retro。和 [sprint121_142_retro.md](sprint121_142_retro.md)(22 sprint)、[sprint143_148_retro.md](sprint143_148_retro.md)(6 sprint) 互補。

---

## 0. 為什麼需要這份 retro

Sprint 149 retro(範圍 Sprint 143-148、6 sprint)已 explicit 三個成熟模式:
- 紀律 #1.b 升正 + catch-up
- Phase 1 capture-only 四連 archetype(9-step)
- retro 短週期觸發

Sprint 150-153 延長為**九連 cluster**(跳過 149 retro 為 docs sprint),揭示**進階變體模式**:
1. **「最薄」capture-only sprint**(Sprint 152、+0 行新 parser code)— 紀律 #14 DRY 應用峰值
2. **discriminated union variant capture**(Sprint 151、TypeScript 型別系統運用)
3. **紀律 #21 例外判斷**(Sprint 153 latent exception 全空仍掛 key)— mental model 主導非機械式應用
4. **autonomous-friendly backlog 真正耗盡**邊界揭示(Sprint 153)

本 retro 把這四個新變體 explicit、為 Sprint 154+ 必須改變方向(wire-up 或 user 介入)提供依據。

---

## 1. 九連 cluster 全貌

### 1.1 Sprint × Part 對照表

| Sprint | Part | 新 parser code | Test | Phase 1 進度 | VR byte-identical 連 | 特殊 |
|---|---|---|---|---|---|---|
| 145 | footnotes + endnotes | +135 | +12 | 80% → 82% | 第 16 連 | 同 parser 雙 root |
| 146 | settings | +187 | +27 | 82% → 84% | 第 17 連 | probe 升級為跨 part 統計 |
| 147 | fontTable | +150 | +20 | 84% → 86% | 第 18 連 | 與 FontMetricsAdapter 互補 |
| 148 | webSettings | +95 | +14 | 86% → 87% | 第 19 連 | 紀律 #18 scope-down 案例 |
| **149** | **(retro)** | **0** | **0** | **不變** | **不跑** | **短週期 retro** |
| 150 | app.xml | +189 | +20 | 87% → 88% | 第 20 連 | doc-props 子目錄開幕 |
| 151 | custom.xml | +179 | +29 | 88% → 89% | 第 21 連 | **discriminated union variant** |
| 152 | [Content_Types].xml | **+0(expose)** | +14 | 89% → 89.5% | 第 22 連 | **「最薄」capture-only** |
| 153 | latentStyles | +156 | +19 | 89.5% → **90%** | 第 23 連 | 紀律 #21 例外判斷 |
| **合計(production sprint)** | **9 parts** | **+1091** | **+155** | **+10pp** | **8 連** | — |

### 1.2 整數里程碑:Phase 1 80→90%

從 Sprint 144 retro 結尾 Phase 1 ~80%(Sprint 142 終點)、到 Sprint 153 終點 90%、共 +10pp。

對照表:
- Sprint 121-142(22 sprint)Phase 1 進度 +2pp(78→80%)— 那期間主要做 Phase 4 wire-up
- Sprint 143-148(6 sprint)Phase 1 進度 +7pp(80→87%)— 四連 capture-only
- **Sprint 150-153(4 sprint)Phase 1 進度 +3pp(87→90%)— 收尾**

→ Phase 1 後期 capture-only 路線收益曲線:
- 早期(80→87%):平均 1.75pp/sprint
- 末期(87→90%):平均 0.75pp/sprint(報酬遞減)
- Sprint 153 後:剩餘 10% Phase 1 = 進階 elements 拒絕 capture-only 路線(需 wire-up 或 user GO)

---

## 2. 新變體模式:Sprint 152「最薄」capture-only

### 2.1 變體定義

> Capture-only sprint 中、無需新 parser code、僅暴露既有 internal 結構至 DocumentNode 的 sprint 變體。

Sprint 152 [Content_Types].xml 是典型範例:
- PackageReader L72-79 已 internal `parseContentTypes`
- 結果為 internal `ParsedContentTypes`、未暴露至 `OoxmlPackage` interface
- 本 sprint 只擴 `OoxmlPackage.contentTypes: PackageContentTypes` + DocumentNode 1 新欄位

### 2.2 與 Sprint 145-151 對照

| 維度 | 標準 capture-only(145-151)| **「最薄」(152)** |
|---|---|---|
| 新 Parser code | +135 ~ +189 行 | **+0 行** |
| Test code | +12 ~ +29 行 | +14 行 |
| 紀律應用 | #21 + #18 + #22 | **#14 DRY(主要) + #18** |
| 防禦邊界 | 4-8 個自寫 | **沿用 internal 既有** |
| ROI | 高(新功能 / Phase 1 +1-2pp)| 中(復用、Phase 1 +0.5pp)|

### 2.3 觸發條件

「最薄」變體出現的條件:
1. PackageReader / 既有 parser 已內部處理但未對外暴露
2. 紀律 #14 DRY 嚴格 — 不重新實作既存解析邏輯
3. scope 純為 interface widening + DocumentNode forward(無 logic 改變)
4. 在 cluster 中扮演「收尾或 polish」角色(非 milestone breakthrough)

### 2.4 對 wire-up 階段的啟示

未來 wire-up 階段(Sprint 154+ if user GO)、相同模式可應用於:
- ParsedContentTypes 對應 Phase 6 docx export validate(已 capture、export 端複用、紀律 #14)
- PackagePart.contentType 已存在於每個 part(無需 docTree-level lookup)
- 設計原則:capture 暴露 → export consume、避免「export 端重新 parse」反模式

---

## 3. 新變體模式:Sprint 151「discriminated union variant」

### 3.1 變體定義

> Capture variant 值(OOXML §22.4 vt:* / §17.x val-type 等)使用 TypeScript discriminated union 型別、`kind` 屬性 narrow + 未知 variant 降級 unknown。

Sprint 151 custom.xml 是典型範例:
```ts
type CustomPropertyValue =
  | { kind: 'string'; value: string }
  | { kind: 'int'; value: number }
  | { kind: 'bool'; value: boolean }
  | { kind: 'real'; value: number }
  | { kind: 'filetime'; value: string }
  | { kind: 'unknown'; raw: string };
```

### 3.2 設計優勢

| 維度 | 收益 |
|---|---|
| TypeScript 型別狹窄化 | caller 用 `value.kind` switch、編譯期保證 case exhaustive |
| 未來擴充友善 | 加新 variant 在 switch 加 case、不破 existing test |
| scope-down 範本 | 紀律 #18:只實作出現 variant + unknown 降級 |
| 與 export 對稱 | Phase 6 docx export 端可逆向匹配 variant kind 寫回 vt:* |

### 3.3 適用範圍

未來 capture-only sprint 遇到「值有多種 variant」時應採此模式:
- Settings.compat 元素子值(可能多種 hash)
- field code 結果(string / int / formatted)
- Trait values(future OOXML §17.x extensions)

避免反例:
- 用 union(`string | number | boolean`)— 失去 narrow、caller 必須 typeof 檢查
- 用 enum + 純 string value — 失去型別保證、parse 失敗難偵測

---

## 4. 新變體模式:Sprint 153 「紀律 #21 例外判斷」

### 4.1 紀律 #21 標準應用 vs Sprint 153 例外

**標準應用**(Sprint 145-152、紀律 #21 機械式):
> optional 欄位空集合不掛 key

實作:屬性 / 元素 / value 為空 → undefined / 不掛 key。

**Sprint 153 例外**(LatentStylesParser):
- exception 無 name → 跳過(標準應用)
- exception 全空屬性 → **仍掛 key**(value = `{}`)

理由:
> name 本身已是資訊(區分「Word 已知 latent style」vs「未知 latent style」)、空屬性是「user 未 override」的合法 semantic、不是缺失

### 4.2 為何不機械式應用

紀律 #21 設立目的 = 避免 noise(空 key 提供 0 資訊)、但 Sprint 153 情境:
- `latentStyles.exceptions.has("Index 1")` 是「Word 知道 Index 1 latent style 存在」的 signal
- value 全空 = 「user 沒 override default」(default 在 latentStyles root attrs)

→ name(key)本身已是 binary signal(存在 / 不存在)、value 全空不破壞 signal。

### 4.3 mental model 主導非機械式

retro 啟示:
- 紀律 #21 設計初衷是「不要 noise」、不是「機械式不掛空 key」
- 遇到「key 本身就是 binary signal」時、value 全空合法
- 對照 Sprint 151 custom.xml 「property 全空跳過」:property name 是 user-defined、空 value 確實是 noise(沒 name 也沒 value、整 entry 該 drop)

→ 紀律應用需 mental model 判斷、不是純機械式。

### 4.4 對未來紀律演進的啟示

紀律 #21 可考慮升正子原則:
> 紀律 #21.a:當 key 本身已是 binary signal(存在 / 不存在)時、value 全空仍掛 key

但此子原則僅 1 sprint 案例、按紀律升正規範(3+ sprint 跨類型驗證)、暫列「**潛在候選**」、不立即升正。

---

## 5. 數據總覽(Sprint 145-153)

### 5.1 累計指標變動

| 指標 | Sprint 144 終點 | Sprint 153 終點 | 變動 |
|---|---|---|---|
| vitest | 1176 + 1 skipped | 1331 + 1 skipped | **+155** |
| VR mean | 0.073191 | 0.073191 | **0(第 23 連 byte-identical、跨 8 個 production sprint)** |
| Phase 1 OOXML | ~80% | **90% 整數里程碑** | **+10pp** |
| Phase 4 Style | 90% | 90% | 0(本 cluster 不動 Phase 4)|
| 正式紀律 | 22 條 | 22 條 | 0 |
| 候選紀律 | 1(#20)| 1(#20)+ 1 潛在(#21.a) | +1 潛在 |
| Sprint audit doc | 144 | 153 | +9 |

### 5.2 Sprint 類型分布(9 production sprint、跳過 149 retro)

| 類型 | 數量 | 比例 |
|---|---|---|
| Code change(capture-only 標準)| 7 | 78% |
| Code change(「最薄」+0 parser variant)| 1(Sprint 152)| 11% |
| Code change(discriminated union variant)| 1(Sprint 151)| 11% |
| Probe-only / Revert / Mechanical | 0 | 0% |

→ Sprint 145-153 是「**穩定生產 + 模式變體探索期**」:純 code 累積 + 2 個新變體 explicit、無翻車無 revert。

### 5.3 紀律驗證

| 紀律 | 應用次數(Sprint 145-153)| 累計次數(歷史總計)|
|---|---|---|
| #1.a(parser / layout 跑全 VR)| 8 次 | 23 次 |
| #21(optional 空集合不掛 key)| 8 次(含 1 次例外判斷)| 12 次 |
| #22(probe sprint)| 8 次 | 17 次 |
| #1.b(scope-down 或 revert)| 8 次正面驗證 | 16 次 |
| #18(PR-size + scope-down)| 持續、Sprint 148/151/152/153 新 scope-down 案例 | - |
| #14(DRY、模組化)| 持續、Sprint 152 主要應用 | - |
| #14.a(集中索引即時同步)| 0 需求(本 cluster 無紀律升正)| - |

---

## 6. 跨 retro 對照(第 4 次 retro)

| 維度 | Sprint 120(50-66)| Sprint 144(121-142)| Sprint 149(143-148)| **Sprint 154(145-153)** |
|---|---|---|---|---|
| 範圍 | 17 sprint | 22 sprint | 6 sprint | **9 sprint(production)+ 1 中間 retro** |
| 主要主題 | cache / FontMetricsAdapter | wire-up + autonomous 邊界 | capture-only 模式成熟 | **整數里程碑 + 進階變體 explicit** |
| 翻車次數 | 1(Sprint 57 memoize)| 1(Sprint 136 isInTableCell)| 0 | **0** |
| 紀律生成 | 6 條 | 4 條升正 | 0 條 | **0 條 + 1 潛在子原則(#21.a)** |
| autonomous 邊界 | 未碰到 | 第一次碰到 | 維持邊界清單 | **§11.2 backlog 真的耗盡** |
| Phase 1 進度 | n/a | 78→80%(+2pp)| 80→87%(+7pp)| **87→90%(+3pp、整數里程碑)** |
| 新模式 | Stable platform / Probe-Negative-Positive-Delta-Drift-Promote | probe-only 例行化 / Strategy C / autonomous 邊界 | capture-only 四連 archetype / scope-down 新案例 / retro 短週期 | **「最薄」capture-only variant / discriminated union variant / 紀律 #21 例外判斷** |
| 報酬遞減 | n/a | n/a | 高(2pp/sprint 平均)| **顯著(0.75pp/sprint、autonomous 邊界揭示)** |

→ Sprint 145-153 是「**收尾期**」:Sprint 121-142 + Sprint 143-148 累積的方法論在更小範圍重複應用、產生整數里程碑、無新探索、無翻車、無紀律升正。

---

## 7. 未來 cluster checklist 更新(從 Sprint 145-153 補強)

新加 2 項到 Sprint 149 retro §6 既有 8 項:

```
原 8 項(Sprint 149 列):
[ ] 1. 規畫書 scope 對齊?(紀律 #18)
[ ] 2. capture-without-consumer? → wire-up 三段式評估
[ ] 3. mental model 確定? → 不確定 → probe sprint(紀律 #22)
[ ] 4. probe 結論:autonomous GO / DEFER / user GO?(autonomous 邊界 3 維度)
[ ] 5. 實作後 VR:byte-identical / 改善 / 退化? → 退化走紀律 #1.b
[ ] 6. cluster 紀律新升正? → 同 sprint 更新集中索引(紀律 #14.a)
[ ] 7. 「儀式性收尾」是否該 scope-down?(紀律 #18 + Sprint 148 案例)
[ ] 8. cluster 模式重複 ≥ 3 次成熟? → 寫短週期 retro(紀律 #14)

Sprint 154 新加:
[ ] 9. 既有 internal 結構未暴露? → 用「最薄」variant、紀律 #14 DRY 嚴格守
       (Sprint 152 案例:PackageReader.parseContentTypes 已存在、直接 expose)
[ ] 10. capture 值有多種 variant? → discriminated union 設計、scope-down + unknown 降級
       (Sprint 151 案例:custom.xml vt:* variant、5 常見 + unknown)
```

---

## 8. autonomous 邊界:第二次 explicit「真的耗盡」

### 8.1 Sprint 144 vs Sprint 153

| 維度 | Sprint 144(autonomous 邊界第一次揭示)| **Sprint 153(autonomous 邊界第二次)** |
|---|---|---|
| 揭示位置 | Sprint 141 階段 C 重生 goldens DEFER user GO | Sprint 153 §11.2 backlog 真的耗盡 |
| 邊界類型 | 「需 user 業務優先」(baseline 改變)| 「剩餘候選 ROI 過低不適 capture-only」 |
| 後續路徑 | retro + 等 user | retro + 等 user OR 進入 wire-up(走 Strategy C) |

### 8.2 剩餘 §11.2 + autonomous 評估候選

| 候選 | autonomous 評估 | 為何不適 |
|---|---|---|
| `stylesWithEffects.xml` | ❌ defer | 6/42 legacy IE compat、retro 明示 |
| `customXml/item*.xml` | ❌ defer | SDT databind、Sprint 124 已 unwrap、wire-up 才用 |
| `theme1.xml` 子元素 | ❌ 不適 | fmtScheme / fillStyleLst 內部結構極複雜(gradFill / blipFill / pattFill)|
| `numbering.xml` 進階元素 | ✅ 已 wire-up | Sprint 137-139 |
| `document.xml` 主流程 | ✅ 已 capture | Sprint 0-30 |
| `header/footer*.xml` | ✅ 已 wire-up | Sprint 11 |
| `styles.xml` 其他 | ✅ 已 wire-up + 本 cluster | StyleResolver + LatentStylesParser |

→ autonomous-friendly 候選 = **0**(本 cluster 結束、capture-only 路線真的耗盡)。

### 8.3 Sprint 154+ 三個方向

| 方向 | autonomous 可獨立做 | 需 user 介入 |
|---|---|---|
| A. wire-up 階段(Strategy C 折衷)| ⚠️ 需 user 同意接受 baseline 破壞 | settings.defaultTabStop / fontTable.altName / characterSpacingControl |
| B. 等 user 決策 | ✅ 預設路徑 | textAlignment / Phase 5 fixture / 階段 C goldens |
| C. autonomous docs sprint | ✅ retro / glossary / archive | 報酬遞減、本 sprint 已做 retro |

→ **Sprint 154 retro 後、autonomous 報酬遞減顯著**、預期 Sprint 155+ 需 user 介入(B 路徑)或 user 同意 wire-up(A 路徑、走 Strategy C)。

---

## 9. 結論

Sprint 145-153 九連 cluster(跳過 149 retro)累積:
- **Phase 1 OOXML 整數里程碑(80→90%)**
- 8 連 byte-identical(Sprint 16-23 連、跨九 production sprint 維持)
- 9 個 OOXML part capture(footnotes/endnotes/settings/fontTable/webSettings/app/custom/[Content_Types]/latentStyles)
- 4 個新變體模式 explicit(短週期 retro 觸發 / 「最薄」+0 parser variant / discriminated union variant / 紀律 #21 例外判斷)
- 0 翻車 / 0 紀律升正 / 0 探索性實驗

下一階段(Sprint 154+)選項受限:
- **§11.2 backlog 真的耗盡**(autonomous 第二次邊界揭示)
- 三個路徑均需 user 介入或預設路徑(等待)

本 retro 為「**capture-only 收尾期完成宣告**」、後續 sprint 性質將從「autonomous 累積進度」轉為「等 user 決策 / wire-up 探索」。

---

## Sprint 154 結尾累積指標

- vitest **1331 passed + 1 skipped**(未動、純 docs)
- VR mean **0.073191** / failed 0 / compared 126(未跑、**第 23 次連續 byte-identical 維持**)
- Odoo backend local 31 passed(未動)
- CI gate v1 12 passed(未動)
- Phase 1 OOXML **90%**(整數里程碑、未變)
- 22 ADR / 紀律 **22 條** + 6 子 + 1 候選(#20)+ **1 潛在子原則(#21.a)**
- Sprint audit doc 153 → **154**

---

## File-level summary

```
A  addons/dobtor_doc_editor/docs/sprint145_153_retro.md  (本 retro doc、第 4 次 retro)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (Sprint 154 ✅)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新)
```

**淨 production code 變動 = 0**(pure docs retro)、Sprint 145-153 九連 cluster 方法論 explicit、為 Sprint 154+ 必須改變方向提供決策依據。
