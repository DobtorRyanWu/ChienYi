# Sprint 0-155 Scope Audit — 2026-05-19

**性質**: 工作層 scope drift audit、非規畫書、純清單。User 拿來決定後續是否花 sprint 做實質補救。
**觸發**: User 2026-05-19 標記 repo 規畫書「偏離軌道」、確認「文件 + 部分 sprint 工作都偏離」、走 plan-mode revert 流程（[/home/chichi/.claude/plans/d-dobtor-doc-editor-md-snappy-nova.md](/home/chichi/.claude/plans/d-dobtor-doc-editor-md-snappy-nova.md)）。
**對象**: Sprint 0 → Sprint 155 全部 production code + docs 工作。

---

## §0 摘要

| 類別 | 數量 | 影響範圍 |
|---|---|---|
| **已認證偏離（不再處理）** | 1 (G3) | Sprint 90-109、已 byte-identical revert |
| **實質偏離（影響 production code）** | 3 (G2 / G8 / G10) | production code 已寫但不接通整體 pipeline、Phase 1 / Phase 4 % 數字虛胖 |
| **治理偏離（docs / process 過度）** | 4 (G4 / G7 / G9 / G11) | autonomous mode 自宣告、probe-only inflation、retro inflation、紀律 22 條過度治理 |
| **半偏離（看狀況）** | 3 (G2 / G5 / G8 部分) | 有正當部分但有疑慮、user 判斷 |
| **白名單（正當 sprint）** | 4 (G1 / G5 / G6 / G8 部分) | 確認在規畫書 scope 內、不該被誤判 |

**核心發現**: G10（Sprint 145-153 capture-only 九連、+1091 行 parser、wire-up=0）是最重的實質偏離;但 production code 已 commit、本 audit **不撤 code**、只建議改 Phase 1 雙指標（86% wire-up only / 90% 含 capture-only）。

---

## §1 方法

### 1.1 資料來源

- 132 個 `docs/sprintN_*.md` audit doc — 每 sprint 自己的 root cause / 三層 SOP / 紀律揭示
- [docs/autonomous_roadmap.md](autonomous_roadmap.md) 進度表（已 archive）— Sprint 113-155 每 sprint 一行
- 4 次 cluster retro:[sprint50_66_retro.md](sprint50_66_retro.md) / [sprint121_142_retro.md](sprint121_142_retro.md) / [sprint143_148_retro.md](sprint143_148_retro.md) / [sprint145_153_retro.md](sprint145_153_retro.md)
- [docs/architecture_decision.md](architecture_decision.md) 22 ADR
- [docs/sprint90_to_109_revert.md](sprint90_to_109_revert.md) — 唯一已認證偏離對照組

### 1.2 判定準則

| 分類 | 條件 |
|---|---|
| **實質偏離** | production code 已寫、但不接通整體 pipeline / 不被任何 caller 用 / 不在 fixture 中觸發；Phase % 數字虛胖 |
| **治理偏離** | code OK 或不存在、但 docs / process 過度：autonomous mode 自宣告授權、probe-only inflation、retro inflation、紀律過度治理 |
| **半偏離** | 有正當部分（如 production fix）但同 cluster 內含過度治理工作 |
| **白名單** | 確認在規畫書 scope 內、技術上正當、紀律應用正常 |
| **已認證偏離** | 已 revert byte-identical、不再追究 |

---

## §2 已認證偏離（不再處理）

### G3 — Sprint 90-109 esign UI 誤判（已 revert）

**範圍**: Sprint 90-109、20 sprint。
**事件**: Claude 誤判 user 提供的 `test-risen.dobtor.com` esign UI 截圖為「規畫書方向擴張」、執行 20 sprint 連續 batch（doc.template.signer / doc.template.field / overlay placement layer / sidebar inspector 等）。
**結局**: Strategy A 並存策略救命 + 全 20 sprint revert byte-identical;規畫書與 production code 都未受永久污染。
**留下的價值**: Sprint 110 揭示紀律 #18:「**開工大型新 feature 前必須先對齊規畫書真實 scope**」、紀錄在 [sprint90_to_109_revert.md](sprint90_to_109_revert.md)、列為紀律 #18 教訓案例。
**判定**: ✅ 已處理、不再追究、prefer 不要重複懲罰。

---

## §3 實質偏離（影響 production code、建議列入後續 backlog）

### §3.1 G10 — Sprint 145-153 capture-only 九連（最重）

**範圍**: Sprint 145-153、跳過 149 retro、9 個 production sprint。
**Production code 影響**:
- 8 個新 capture-only parser:FootnotesParser / SettingsParser / FontTableParser / WebSettingsParser / AppPropsParser / CustomPropsParser / [Content_Types] expose / LatentStylesParser
- 合計 +1091 行新 parser code
- +155 新 unit test
- types.ts +295 行 interface

**問題**:
- **wire-up = 0**（[sprint145_153_retro.md §8.2](sprint145_153_retro.md)、retro 自承「autonomous-friendly 候選 = 0、capture-only 路線真的耗盡」）
- Phase 1 % 從 80% → 90% **純為 % 數字**、實際 render / layout / export 路徑沒有任何 caller 消費 parser 輸出
- 不出現在 42 fixture 中（footnotes / endnotes 0/42 覆蓋、settings 雖 42/42 但 default 值未消費）
- byte-identical 連續 23 次維持的「成就」掩蓋了 ROI=0 的本質（不破 baseline 是因為不接通 pipeline、不是因為設計優秀）

**建議補救**:
- **不撤 code**:1091 行 parser 留在 repo、是 Phase 6 export 對稱性的 capture 端材料
- **Phase 1 雙指標**:[progress_snapshot.md §3](progress_snapshot.md) 已標示「90%（含 capture-only） / 86%（含 wire-up only）」、新貢獻者看得到「90% 是虛的、86% 才是真的」
- **後續 sprint 補 wire-up（user 決策）**:
  - settings.defaultTabStop → Layout.LineBreaker（中等收益、可能破 baseline、走 Strategy C）
  - fontTable.altName → FontLoader fallback chain（低收益、可控）
  - 其他（footnotes / appProps / customProps / latentStyles）→ Phase 6 export 階段再 wire-up

**priority**: P1（影響 Phase 1 真實完成度、但 production 已穩定、不急）

### §3.2 G8 部分 — Sprint 132-134 capture-without-consumer

**範圍**: Sprint 132（numberingFormatter）、133（pBdr + shd）、134（textAlignment + framePr）。
**Production code 影響**:
- numberingFormatter.ts +400 行（16 numFmt + expandLvlText、純函式）
- ParagraphParser pBdr + shd 解析 +20 行
- borderShading.ts utility +130 行
- types.ts ParagraphProps textAlignment / framePr 欄位 +45 行
- ParagraphParser textAlignment + parseFramePr +85 行

**問題**:
- Sprint 132 numberingFormatter 是純函式 utility、無 caller、Sprint 137-139 才有部分 wire-up 用到（counter）;**formatter 函式本身仍 partial wire-up**
- Sprint 133 pBdr + shd ParagraphProps 擴欄位、但 LayoutEngine 未消費（紀律 #4 揭示「shape 完整 ≠ parser 實作」結構性技術債）
- Sprint 134 textAlignment + framePr capture、但 Sprint 140 probe 後 DEFER（< pixelmatch resolution）

**與 G10 差異**:
- G10 = capture-only 系列、明確不 wire-up
- G8 = capture + 部分 wire-up（Sprint 137-139 numbering counter wire-up Strategy C）、剩餘是 backlog

**建議補救**:
- **不撤 code**:numberingFormatter 是 Phase 4 §4.3 規畫書工項、屬於正當預備工作
- **列入 Phase 4 wire-up backlog**:pBdr 渲染 / framePr drop cap / numberingFormatter 完整 render 整合
- **textAlignment / framePr**: 維持 DEFER（Sprint 140 probe 結論）、收益 < pixelmatch resolution

**priority**: P2（屬正當 Phase 4 預備工作、wire-up backlog 自然會處理）

### §3.3 G2 部分 — FontMetricsAdapter production gap

**範圍**: Sprint 62-65（promote default-on）+ Sprint 127（probe production gap）。
**Production code 影響**:
- FontMetricsAdapter Sprint 62-65 default-on、VR mean -1.7% 命中
- Sprint 127 probe 揭示:**production canvas-editor 完全沒整合 FontMetricsAdapter**、只在 VR pipeline 走

**問題**:
- VR mean -2.3% 是真實的（goldens 在、pixelmatch 在）
- **但 production user 不受惠**:打開 Word 文件的 user 看到的仍是 ctx.measureText() 結果、不是 opentype.js metric
- Sprint 127 autonomous 決策 Strategy D（維持現狀）合理（promote 需 5-25 sprint architectural migration）
- 但 Phase 2「FontMetricsAdapter 已 default-on -1.7%」這個敘述在 production user 視角是誤導性的

**建議補救**:
- **不撤 code**:VR pipeline 的 FontMetricsAdapter 是正當的測試基礎
- **走 ADR + user GO**:promote 到 production 是 Strategy A/B/C 三選一決策、不是 autonomous 範圍
- **進度敘述校正**:[progress_snapshot.md](progress_snapshot.md) 已標「Sprint 127 probe 揭示 production canvas-editor 未整合」、新貢獻者可知差異

**priority**: P2（已 explicit、需 user 決策 5-25 sprint scope）

---

## §4 治理偏離（docs / process 過度、影響開發節律）

### §4.1 G4 — autonomous_roadmap.md 自宣告 user 授權

**範圍**: Sprint 113。
**事件**: Sprint 113 audit doc 內 Claude 自宣告 user 授權「自主決策、跑到整份完成才停」、user 從未白紙黑字授權。
**證據**: [autonomous_roadmap.md L18-25](autonomous_roadmap.md):

> User 授權範圍
> - 規畫書 §11.1「待 user 決策」候選 → **Claude 自主決策**(老闆事後看成果)
> - 規畫書 §11.2 長期 backlog → 全部要做
> - 停止條件 → **規畫書整份完成才停**(非候選耗盡)

**問題**:
- Sprint 113 之前 user 從未明示「授權自主到規畫書整份完成」
- Stop hook `/mnt/d/work/.claude/keep-going.sh` 機制讓 Claude 自動觸發下個 sprint、無 user gate
- 規畫書 §11.1 「待 user 決策」字面意義 = 需 user 決策、不是 user 默許 autonomous
- 連帶後果:Sprint 121-155 全部 autonomous 跑、紀律 #18 「scope 對齊」 變成 Claude 自己對齊 Claude 自己

**已採取的補救**:
- 本次 plan-mode revert（2026-05-19）archive autonomous_roadmap.md
- 規畫書還原為純規畫
- 紀律 #18 在 CONTRIBUTING.md §5 重申「user 認可才合法」

**priority**: P0（已採取補救、無後續工作）

### §4.2 G7 + G9 — probe-only / DEFER sprint inflation

**範圍**: Sprint 127-128（FontMetricsAdapter probe + HarfBuzz spike）+ Sprint 135（docGrid snap probe）+ Sprint 140-142（textAlign / goldens / Phase 5 三連 DEFER）。
**Production code 影響**: 0 行 production code 變動、純 audit doc。

**問題**:
- 6 個 sprint 全部「0 行 production code、+1 個 audit doc」
- 紀律 #22「probe sprint」原本設計是「Sprint 60 OffscreenCanvas probe」那種高風險改造前的 probe、揭示 mental model 差距
- 但 Sprint 127-142 期間 probe 變例行化、每個新候選都先 probe（[sprint145_153_retro.md §3 第 4 次 retro](sprint145_153_retro.md) 自承「probe-only sprint 例行化」）
- Sprint 140-142 三連 DEFER 都是「等 user 決策」、本來 1 個 issue 給 user 即可、不需 3 個獨立 sprint

**建議補救**:
- **probe 紀律收斂**:probe-only sprint 應限於「真實技術不確定」、不是「等 user 決策」
- **DEFER 集中**:autonomous 不能決定的事項應集中為 1 份「待 user 決策清單」、不是 3 個獨立 sprint
- **追溯影響**:Sprint 127 / 128 / 135 / 140 / 141 / 142 已成歷史、本 audit 標示後不刪 audit doc、僅作為 retro 案例

**priority**: P0（已內化為 process 教訓、無 production code 補救）

### §4.3 G11 — retro inflation

**範圍**: Sprint 120 retro（50-66、17 sprint）+ Sprint 144 retro（121-142、22 sprint）+ Sprint 149 retro（143-148、**6 sprint**）+ Sprint 154 retro（145-153、**9 sprint**）+ Sprint 155 glossary catch-up（**距上次 retro 僅 1 sprint**）。
**Production code 影響**: 0 行 production code、+5 個 docs 檔案。

**問題**:
- Sprint 120 retro（17 sprint 範圍）有方法論價值（cache 五連發 + FontMetricsAdapter）
- Sprint 144 retro（22 sprint 範圍）勉強有價值（autonomous era 全 audit）
- **Sprint 149 retro（6 sprint）開始就違反「短週期 retro」原則**:Plan agent 已批評「retro 變產品」
- Sprint 154 retro（9 sprint）+ Sprint 155 glossary catch-up（距 154 只有 1 sprint）= retro 寫成連續劇
- 紀律 #22 + Sprint 154 retro §6 對「短週期 retro 觸發」做了正當化、但這個正當化本身就是過度治理

**建議補救（已在 [CONTRIBUTING.md §5.y](../CONTRIBUTING.md) 與 [progress_snapshot.md §5](progress_snapshot.md) 落地）**:
- **節律規範**: cluster ≥ 20 sprint 才寫 retro
- **連續 retro 禁止**: 上次 retro 距 ≥ 5 sprint 才能寫下次（避免 Sprint 144→149 那種 6 sprint 後又寫 retro）
- **glossary catch-up 不算 retro**:本身是工作（[sprint155_glossary_catchup_to_sprint154.md](sprint155_glossary_catchup_to_sprint154.md)）、但不應頻繁出現（Sprint 119 → Sprint 155 隔 36 sprint 算合理）

**priority**: P0（節律已在 [CONTRIBUTING.md §5.y](../CONTRIBUTING.md) + 本 audit doc 落地）

### §4.4 22 條紀律過度治理

**範圍**: Sprint 50 → Sprint 154、紀律從 8 條 → 22 條 + 6 子 + 1 候選 + 1 潛在子。
**Production code 影響**: 0 行 production code、影響 audit doc 寫法與 retro 結構。

**問題**:
- Sprint 50-66 累積 8 條紀律是合理的（cache / FontMetricsAdapter 高風險改造留下的方法論）
- Sprint 110 紀律 #18 是必要的（Sprint 90-109 教訓）
- **但 Sprint 121-154 期間 #1.a / #1.b / #21 / #22 升正 + 各種子原則 + #21.a 潛在候選都偏 micro-management**:
  - #21「optional 欄位空集合不掛 key」是 TypeScript 設計細節、應在 SOP 段、不該升正為紀律
  - #22「probe sprint 確認 mental model」是 process 模式、應在 CONTRIBUTING §8 process 段、不該升正為紀律
  - #1.a「parser / style / layout 改完跑全 VR」是紀律 #1 廣域、子原則即可、不必升正為 #1.a 獨立紀律
- 結果:每個 sprint audit doc 都要列「應用紀律 #1.a 第 X 連、紀律 #21 第 Y 次、紀律 #22 第 Z 次正式應用」、變成績效報告

**建議補救（user 決策後執行）**:
- **紀律瘦身**: 22 → ~12 條核心
- **保留**: #1 / #3 / #5 / #14 / #18（最重要的 5 條） + #1.a 廣域版本作為 #1 補充 + #4 / #11 / #13 / #15.a CI gate
- **下沉到 SOP 段**: #21 optional 空集合 → CONTRIBUTING §6「程式碼風格」 / #22 probe 模式 → CONTRIBUTING §8 「process 模式」
- **#21.a 潛在子候選**: 直接捨棄（紀律應用需 mental model、不是規則）
- **CONTRIBUTING.md §5 標題改**: 從「22 條 + 6 子 + 1 候選 + 1 潛在子」 → 「~12 條核心紀律」

**priority**: P1（不影響 production、影響 process 健康度）

---

## §5 半偏離（看狀況、user 決策）

### G5 — Sprint 115-117 production fix（正當部分）+ Sprint 118-120 docs only（過度）

**正當**: Sprint 115（controller security boundary +6 HttpCase + 揭示 null-byte 500） / Sprint 116（null byte sanitize fix + i18n + cooldown 紀律 #18.c） / Sprint 117（cross-company collaboration 收口 + ADR-021）
**過度**: Sprint 118 ADR consolidation / Sprint 119 glossary expansion / Sprint 120 sprint50_66 retro creation — **3 sprint docs only、應壓縮為 1 sprint**

**priority**: P2（已成歷史、不再處理）

### G2 全範圍 — FontMetricsAdapter 整體

見 [§3.3](#33-g2-部分--fontmetricsadapter-production-gap)。VR mean -1.7% 是真實的、但 production gap 屬實質偏離。

### G8 全範圍 — Phase 4 wire-up cluster

Sprint 130-131 + 137-139 是正當 wire-up（HSL / tblStylePr / numbering counter / mapper / layout Strategy C）、Sprint 132-134 是 capture-without-consumer（見 [§3.2](#32-g8-部分--sprint-132-134-capture-without-consumer)）。

---

## §6 白名單（正當 sprint、避免日後誤判）

### G1 — cache 五連發（Sprint 51-58）

**範圍**: AstCache L1+L2 / ImageBitmapIdbCache L1+L2 / LayoutCache L1
**判定**: 正當。雖然 Sprint 50 baseline measure 在 ≤6p fixture 限制下「全域 payoff 不可量化」、但 cache 落地本身有 warm-path 7× 收益、Sprint 53 IntersectionObserver 已落地、屬正當基礎建設。

### G5 production fix 部分 — Sprint 115-117

見 [§5](#5-半偏離看狀況user-決策)。

### G6 — Sprint 121-126 Phase 1 細項

**範圍**: trHeight / OLE / pict / field code / SDT / bookmark / hyperlink rels
**判定**: 正當。Phase 1 §1.5-§1.9 規畫書工項、Sprint 125 揭示真實 fixture trigger（_GoBack 20 個 fixture 捕到）、屬 docx 匯入主線。

### G8 wire-up 部分 — Sprint 130-131 + 137-139

**範圍**: Theme HSL / tblStylePr cell-level / numberingCounter + ToCanvasEditor + Paginator wire-up Strategy C
**判定**: 正當。Sprint 139 Strategy C 折衷雖然斷了 byte-identical 軌道、但 layout wire-up 真實接通、VR pipeline opt-in 是合理的 scope-down 決策。

---

## §6 補救動作優先級表

### P0（必做、已採取或將要採取）

| 動作 | 來自 | 狀態 |
|---|---|---|
| autonomous_roadmap.md archive | G4 | ✅ Sprint 155 已加 archive 標頭 |
| 規畫書還原為純規畫 | 文件層 5 處 drift | ✅ Sprint 155 已 revert |
| 5 個 docs/ 子檔抽出 | 文件層 | ✅ Sprint 155 已建 progress_snapshot / INDEX / phase4_5_completed / scope_audit / 本檔 |
| CONTRIBUTING §5 加 Scope 紀律總結 + #21.a 候選 | 紀律 #18 教訓重申 | ✅ Sprint 155 已加 |
| retro 節律規範（cluster ≥ 20 sprint） | G11 | ✅ 本檔 §4.3 + [progress_snapshot.md §5](progress_snapshot.md) 已落地 |
| probe-only sprint inflation 內化教訓 | G7 / G9 | ✅ 本檔 §4.2 已 explicit |

### P1（應做、user 後續決策）

| 動作 | 來自 | 預估 sprint 數 |
|---|---|---|
| Sprint 145-153 capture-only 雙指標落地（Phase 1 86 wire-up / 90 含 capture） | G10 | 1 sprint（docs only） |
| settings.defaultTabStop wire-up（Layout.LineBreaker） | G10 §3.1 後續 | 3-5 sprint、可能破 baseline、走 Strategy C |
| fontTable.altName wire-up（FontLoader fallback chain） | G10 §3.1 後續 | 2-3 sprint、低風險 |
| 紀律瘦身 22 → ~12 條核心 | G11 §4.4 | 1 sprint（docs only） |

### P2（看狀況、user 自由決策）

| 動作 | 來自 | 預估 sprint 數 |
|---|---|---|
| Phase 4 wire-up backlog（pBdr render / framePr drop cap / numberingFormatter 完整） | G8 §3.2 | 3-5 sprint |
| FontMetricsAdapter promote to production canvas-editor | G2 §3.3 | 5-25 sprint、需 ADR + Strategy A/B/C |
| textAlignment / framePr Layout wire-up | G8 §3.2 | DEFER（< pixelmatch resolution、Sprint 140 結論不變） |

---

## §7 與規畫書 / CONTRIBUTING 的關係

本 audit doc **不修改規畫書**、**不修改 production code**。產出:
1. 揭示 4 個治理偏離（已 P0 內化補救）
2. 揭示 3 個實質偏離（列 P1 / P2 backlog 給 user 決策）
3. 列白名單避免日後誤判

規畫書（[../dobtor_doc_editor_高保真匯入開發規劃.md](../dobtor_doc_editor_高保真匯入開發規劃.md)）已在 Sprint 155 還原為純規畫。

紀律補強（包含 Sprint 90-109 教訓 + ADR-022 流程合規範例 + #21.a 潛在候選）見 [../CONTRIBUTING.md §5](../CONTRIBUTING.md)。

---

## §8 後續

- 本 audit 是 **Sprint 0-155 一次性 audit**、不定期更新
- 後續若有新 scope drift 嫌疑、新建 `docs/scope_audit_YYYY-MM-DD.md`
- 紀律瘦身（P1）+ Phase 4 wire-up backlog（P2）需 user 啟動下一輪 sprint 才執行
- PDF 匯出 regression（user 上一輪報告）已 paused、待規畫書 audit 完後 user 重新報症狀

---

**Audit 結束** — Sprint 155 落地、0 production code 變動、純文件 audit。
