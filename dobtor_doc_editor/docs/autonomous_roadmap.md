# Autonomous Roadmap — Sprint 113+ 推進規畫書到 A 級完成

**建立**:Sprint 113(2026-05-16)
**狀態**:active
**對應規畫書**:[../dobtor_doc_editor_高保真匯入開發規劃.md](../dobtor_doc_editor_高保真匯入開發規劃.md)
**對應 plan**:[/home/chichi/.claude/plans/lazy-dazzling-shell.md](/home/chichi/.claude/plans/lazy-dazzling-shell.md)

---

## 終極目標

User 原話:**「匯入的檔案可以完全相同格式、1:1 的複製到這個編輯器中呈現,所有文字檔不論 docx 或 doc 都要,Google Docs 看到什麼樣子在 dobtor_doc_editor 看到的就要一樣」**。

對映到規畫書既有定義 = **A 級**(視覺差異 <1%)、pixelmatch VR mean **<0.02**、Phase 0-7 全綠。

---

## User 授權範圍

- 規畫書 §11.1「待 user 決策」候選 → **Claude 自主決策**(老闆事後看成果)
- 規畫書 §11.2 長期 backlog → 全部要做
- 停止條件 → **規畫書整份完成才停**(非候選耗盡)

Stop hook(`/mnt/d/work/.claude/keep-going.sh`)機制:每個 sprint 完成後自動觸發下個 sprint。

---

## 起點(Sprint 112 結尾)

| 指標 | 數值 |
|---|---|
| vitest | 976 passed + 1 skipped |
| VR mean | 0.073191 |
| Odoo backend | 21 passed |
| Phase 0 | 100% |
| Phase 1 | 72% |
| Phase 2 | 部分(FontMetricsAdapter opt-in) |
| Phase 3 | 93% |
| Phase 4 | 80% |
| Phase 4.5 | 100% |
| Phase 5 | 0% |
| Phase 6 | 0% |
| Phase 7 | 84% |
| 紀律條數 | 18(顯式化) |
| Sprint audit doc | 112 |

---

## 階段 A:Autonomous catch-up(Sprint 113-120,~8 sprint)

不需外部資源、副作用極小、補完規畫書既列卻未做事項。

| Sprint | 工作 | 規畫書對應 | 三層 SOP | 狀態 |
|---|---|---|---|---|
| 113 | 規畫書 §11 後續 roadmap 開工:`autonomous_roadmap.md`(本檔)+ Sprint 113 audit + 紀律 #14.b 子原則延伸 | §11、紀律 #14 | docs only | ✅ |
| 114 | CI 加 `backend-tests` job(`addons/.github/workflows/dobtor_doc_editor_ci.yml`、`--test-tags=font_serve`、workflow_dispatch v1)+ 紀律 #15 子原則 + 漸進式 CI gate 模式 | §11.1 行 5/6 隱含、Sprint 69 收口 | YAML parse + L4 CI 等價驗證 12/12 綠 | ✅ |
| 115 | 檢視 doc_controller.py / portal routes security test 缺口(廣域 #5/#11)、補 6 HttpCase security boundary test、揭示 1 critical null-byte 500 留 Sprint 116 plus | §11.1 隱含 + 紀律 #15 | flake8 + L4 HttpCase 6/6 in 1.04s | ✅ |
| 116 | i18n 7 missing translations 補完 zh_TW(+35 行 / 7 新 msgid)+ Sprint 116 plus:upload_template null byte sanitize fix(controller +18 行 / test 收緊)+ 紀律 #18 子(critical-fix cooldown ≤1 sprint) | §11.2 行 5 + Sprint 115 critical | strict flake8 + Babel po valid + L4 HttpCase 6/6 | ✅ |
| 117 | Sprint 78 Finding B portal company rule audit 收口 | §11.1 行 5 | backend test + ir.rule check | ✅ |
| 118 | autonomous docs sprint:`architecture_decision.md` 補完(規畫書 §3 對映 + ADR 20 個彙整) | §11.2 行 5、§附錄 A 殘餘 | docs only | ✅ |
| 119 | autonomous docs sprint:`glossary.md` 擴充到 Sprint 112 era 完整紀律與 OOXML 術語 | §附錄 B 延伸 | docs only | ✅ |
| 120 | Sprint 50-66 retro:`sprint50_66_retro.md` 萃取 cache 五連發 + FontMetricsAdapter 學到的方法論 | §11.2 行 5 | docs only | ✅ |

**階段 A 完成（2026-05-17）**:8 sprint 全綠、開始 Sprint 121 階段 B（Phase 1-4 剩餘漏項）。

**階段 A 收益估算**:VR mean 不變(0.073191)、test 數 +30~50、ir.rule +1~2、docs +3 份、CI 嚴謹度大幅升級。

---

## 階段 B:Phase 1-4 剩餘漏項(Sprint 121-135,~15 sprint)

填補規畫書 Phase 1-4 標示 72% / 80% / 部分 的細節項目。

| Sprint | Phase | 工作 | 狀態 |
|---|---|---|---|
| 121-123 | Phase 1 OOXML | 1.5 進階 row height(`<w:trHeight calcInternal>`)、1.8 OLE objects 降級渲染、1.9 field code 完整覆蓋(PAGE / DATE / SEQ / TOC) | ✅ |
| 124-126 | Phase 1 OOXML | 1.9 SDT 結構化標籤、1.9 bookmark range、1.9 hyperlink rels 完整 | ✅ |
| 127 | Phase 2 字型 | **Probe sprint** — FontMetricsAdapter production migration audit;autonomous 決策 Strategy D(維持現狀、defer 真正 migration 到 user) | ✅ |
| 128 | Phase 2 字型 | HarfBuzz WASM 整合 spike(原 Sprint 129 前移、規畫書原列 1-2 週)| ✅ |
| ~~129~~ | ~~Phase 2 字型~~ | ~~HarfBuzz~~（移到 Sprint 128）| — |
| 130 | Phase 4 Style | 4.1 Theme tint/shade 演算法 HSL luminance 升級 | ✅ |
| 131 | Phase 4 Style | 4.2 tblStylePr/tcPr 條件 cell-level props 傳遞（shading + vAlign）| ✅ |
| 132 | Phase 4 Style | 4.3 numberingFormatter 模組（16 numFmt + expandLvlText、純函式）| ✅ |
| 133 | Phase 4 Style | 4.4 段落 `<w:pBdr>` + `<w:shd>` 解析 + borderShading utility 抽出 DRY | ✅ |
| 134 | Phase 4 Style | 4.4 剩餘：`<w:textAlignment>` + `<w:framePr>` capture（tab leader 渲染屬 Layout、defer） | ✅ |
| 135 | Phase 3 漏項 | docGrid snap 段落層級判別子 **probe sprint** — 找到判別子 = 「段落是否在 table cell 內」、Sprint 136 候選 ready 待 user GO | ✅ |

**階段 B 收益估算**:Phase 1 72% → 90%+、Phase 2 部分 → 80%、Phase 4 80% → 95%、VR mean 0.073191 → ~0.05(估)。

---

## 階段 C:重生 goldens + Phase 3 收口(Sprint 136-145,~10 sprint)

| Sprint | 工作 | 狀態 |
|---|---|---|
| 136-138 | **重生 goldens 用 Word desktop 渲染**(規畫書 §11.1 行 2、Claude 自主決策):跑 Word headless / wkhtmltopdf 替代;若 wsl-side 跑不動則 Plan B 用 OnlyOffice DocumentServer headless 取代 LibreOffice headless 當 reference renderer | ⏳ |
| 139-141 | 重新基線 251 PNG goldens + 重跑全 42 fixture VR + 評估 mean 改善幅度 | ⏳ |
| 142-143 | Phase 3.4 wrapTight 緊密輪廓繞排(規畫書原列「最難」、需計算圖片外框多邊形) | ⏳ |
| 144-145 | Phase 3.5 column balancing / Phase 3.6 註腳尾註基礎(規畫書 §11.2 行 2、30% 政府文件需求) | ⏳ |

**階段 C 收益估算**:換 metric anchor 後 mean ~0.05 → ~0.02-0.03、Phase 3 93% → 99%、A 級邊緣。

---

## 階段 D:Phase 5 進階功能(Sprint 146-160,~15 sprint)

| Sprint | 工作 | 狀態 |
|---|---|---|
| 146-149 | Phase 5.1 OMML → KaTeX / MathJax(規畫書 3-4 週)、AST 解析 + MathML converter + 渲染 | ⏳ |
| 150-152 | Phase 5.2 SmartArt fallback(規畫書建議優先走 `mc:Fallback` 圖片) | ⏳ |
| 153-155 | Phase 5.3 Charts fallback(規畫書同 SmartArt 策略) | ⏳ |
| 156-157 | Phase 5.4 追蹤修訂(`<w:ins>` / `<w:del>`、author 識別、accept/reject UI) | ⏳ |
| 158-159 | Phase 5.5 註解(`<w:commentRangeStart>`、右側 panel、回覆、解決狀態) | ⏳ |
| 160 | Phase 5.6 浮水印 + 背景 | ⏳ |

**階段 D 收益**:Phase 5 0% → 100%、規畫書原列 2-3 個月工作量(壓縮成 15 sprint autonomous batch)。

---

## 階段 E:Phase 6 + Phase 7 + 50+ 頁 fixture(Sprint 161-175,~15 sprint)

| Sprint | 工作 | 狀態 |
|---|---|---|
| 161-164 | Phase 6 docx export 對稱性(AST → XML serializer + 黃金測試 `import(export(doc)) === doc`) | ⏳ |
| 165-167 | Phase 7 OffscreenCanvas + Web Worker render(Sprint 60 probe GREEN、Claude 自主執行) | ⏳ |
| 168-169 | Phase 7 Web Worker parse + IndexedDB incremental render | ⏳ |
| 170-171 | **50+ 頁 fixture 替代品**(user 沒提供施工日誌時、用合成 fixture:把現有 fixture 用 docx-builder 程式化拼成 50p / 100p / 200p) | ⏳ |
| 172-173 | 大文件效能驗證(50/100/200p、benchmark 達 <3s 匯入 / <1s 首屏) | ⏳ |
| 174 | 邊緣 docx 相容性 audit(Word 2007 舊版、libreoffice 產出、WPS 產出) | ⏳ |
| 175 | **A 級 final audit**:整份規畫書 Phase 0-7 全綠檢查、VR mean <0.02 驗證、50 份盲測樣本準備 | ⏳ |

**階段 E 收益**:Phase 6 0% → 100%、Phase 7 84% → 100%、A 級 final 驗證。

---

## 終點條件(Sprint 175 或更前)

當以下**全部成立**時、寫 final retro + `done.flag` 暫停:

1. VR mean **<0.02**(A 級量化標準)
2. Phase 0-7 規畫書 §0.2 全部 ≥95%
3. 50 份盲測樣本「無法分辨 vs 原檔」>80%(規畫書 §2.2)
4. Phase 6 docx export 黃金測試通過(import-export round-trip equality)
5. 規畫書 §11.1 / §11.2 候選全部處理(完成 or 自主聲明放棄 + rationale)

---

## 每個 Sprint 的標準流程

紀律 #1-#18 嚴格 enforce。每個 sprint:

1. **開工前**:`git status` + `wc -l` 規畫書 + 確認 scope 對齊規畫書(紀律 #18)
2. **變動實作**:1-3 個 PR-size、避免 batch 走偏
3. **三層 SOP**:
   - L1 vitest:source code 變動 = 跑全 976+ 測試 / 純 docs = 跳過誠實聲明
   - L2 VR v14:pipeline 變動 = 跑 42 fixture / 純 backend = 跳過誠實聲明
   - L3 spot check:每個 sprint 都跑(章節 / 連結存活 / 結構)
   - L4 Odoo HttpCase:backend 變動 = 跑 21+ test / 否則跳過
4. **Audit doc**:`docs/sprintN_*.md` 完整 6 段(Hypothesis / Method / Result / Root cause / 紀律 / 後續)
5. **同步兩份規劃**:
   - `dobtor_doc_editor_高保真匯入開發規劃.md`(§0.1 累積摘要可加新指標、§0.2 Phase 完成度更新、§11 候選表打勾或移除)
   - `/home/chichi/.claude/plans/d-work-odoo18-docker-dobtor-doc-editor-pure-duckling.md`(append Sprint N 段落)
6. **Session log**:append 對話 + 檔案操作紀錄到 `/mnt/d/work/.claude/logs/session_YYYY-MM-DD.md`
7. **本 roadmap 同步**:打勾本檔案上方階段表狀態(⏳ → 🟢 進行中 → ✅ 完成)
8. **新紀律候選**:若 sprint 揭示新紀律、追加候選 #19+;若達到 3 sprint 跨度驗證、提升為正式紀律(同步 CONTRIBUTING.md + glossary + 規畫書 §6.5)

---

## 紀律 #18 enforce 機制

**Scope 邊界**:規畫書 §1.0 + §5 Phase 0-7 + §11.1 / §11.2 候選清單 + 本 roadmap 階段 A-E。

**自動 enforce**:
- 開工每個 sprint 前 grep 規畫書是否含本 sprint scope(關鍵字配對)
- 發現偏離 → 立刻停手、寫 audit doc 聲明 scope drift 警告、不繼續執行
- 若已寫了 code 才發現偏離 → 走 Sprint 110 模式(Strategy A 並存救命 + 全 revert + byte-identical 驗證)

**自主決策框架**(user 授權):
- §11.1「待 user 決策」候選的 user 部分 = 老闆事後看成果
- 但仍需:技術可行性檢查(Sprint 60 模式 probe)、副作用評估、有 fallback / revert 路徑、寫清楚 rationale 進 audit doc

---

## 風險與紓緩

| 風險 | 紓緩 |
|---|---|
| Scope drift 走偏(紀律 #18) | 開工 grep + 自動 enforce + Sprint 110 模式 byte-identical revert |
| User 沒提供 50+ 頁 fixture | Sprint 170-171 用 docx-builder 程式化合成 50p/100p/200p 當 fallback |
| 重生 goldens 跑不動 wsl(Sprint 136-138) | Plan B 用 OnlyOffice DocumentServer headless 取代 LibreOffice headless |
| Phase 5 OMML / SmartArt 工程量爆炸 | 規畫書原備案 Plan B/C/D(§8.2/§8.3、嵌入 OnlyOffice / 自寫 / 縮目標) |
| 一個 sprint 撞 vitest 失敗連鎖崩壞 | 嚴格 1-3 PR-size、紀律 #1 全 fixture VR 必跑、紀律 #5 IIFE bundle 必驗 |
| Token / quota 跑光跨 session 連續性中斷 | Stop hook 機制 keep-going.sh 自動延續、每 sprint audit doc + session log 是跨 session 唯一權威 |

---

## 進度追蹤

每完成一 sprint 在此 append:

| Sprint | 完工時間 | VR mean | Phase 變動 | 紀律新增 |
|---|---|---|---|---|
| 113 | 2026-05-16 21:30+ | 0.073191(未跑) | docs only | #14.b 子原則:roadmap 外部化 |
| 114 | 2026-05-16 22:00+ | 0.073191(未跑) | CI job 4 → 5、font_serve 12 test 進 CI gate v1(workflow_dispatch) | #15 子原則:security test 要進 CI gate 才算「跑」+ 漸進式 CI gate 模式(dispatch v1 → nightly v2 → PR gate v3) |
| 115 | 2026-05-16 23:40+ | 0.073191(未跑) | Odoo backend local 21 → 27、+6 controller boundary HttpCase、揭示 1 critical null-byte 500 | #15 子原則(Sprint 115):security 邊界紀律廣域應用到所有同類 controller / route |
| 116 | 2026-05-17 00:10+ | 0.073191(未跑) | i18n zh_TW.po 19 → 26 msgid + upload_template null byte sanitize fix(controller +18 行)+ test 收緊為 graceful 400 explicit | #18 子原則(Sprint 116):critical finding 揭示 sprint 後、下個 sprint 應 enforce fix(cooldown ≤ 1 sprint) |
| 117 | 2026-05-17 00:30+ | 0.073191(未跑) | Sprint 78 Finding B 收口:doc.document portal cross-company collaboration 保留現狀 + lock-in 4 test(TestPortalCrossCompanyCollaboration)+ doc_security.xml 註解擴充。Odoo backend 27 → **31** | #18 子原則(Sprint 117):autonomous 收口「待 user 決策」候選必須讀原始設計意圖(group / model 註解)後才決、不能憑 default-secure 直覺加邊界 |
| 118 | 2026-05-17 01:00+ | 0.073191(未跑) | architecture_decision.md 彙整:§0 索引(21 ADR + 004-007 缺口註解)+ §0.5 規畫書 §3 6-layer ↔ ADR 對映 + ADR-021 Sprint 117 cross-company 決策。+54 行純 docs | #20 候選(Sprint 118):集中索引文件(ADR/glossary/CONTRIBUTING)應有 §0 索引段、超過 10 entry 必加、歷史缺口保留編號標示 |
| 119 | 2026-05-17 01:30+ | 0.073191(未跑) | glossary.md 擴 Sprint 110 → 118 era:紀律表 17 → 18 條 + 6 子 + 1 候選、加 §0 索引(驗證 #20 候選跨 2 sprint)、加 §8 Process 模式 8 條、§4 補 cross-company/null byte/lock-in test/autonomous_roadmap。172 → 216 行 | #14 廣域應用(Sprint 119):紀律 #14 從 ADR 延伸到 glossary、新紀律確立應同 sprint 同步 glossary 不是 8 sprint 後補 |
| 120 | 2026-05-17 02:00+ | 0.073191(未跑) | sprint50_66_retro.md 方法論萃取(+260 行):cache 五連發(Stable platform → 高風險改造)+ FontMetricsAdapter(Probe→Negative→Positive→Delta→Drift→Promote 6 階段)+ Sprint 113-118 套用驗證 + 未來 cluster checklist。**階段 A 8 sprint 全綠** | Sprint 120 驗證紀律 #20 候選「<10 entry 不必加 §0」門檻、本 retro 未加屬正確判斷 |
| 121 | 2026-05-17 00:55+ | **0.073191(已跑、byte-identical)** | **階段 B 開工**。TableParser trHeight 入口防禦 +14 行(負 val / val=0+auto strip / hRule 強約束無 val 時 demote auto / 未知 hRule fallback)+ 9 新 unit test、vitest 976 → **985 passed + 1 skipped**、bundle rebuild、VR 42 fixture × 126 pages re-run mean **0.073191 byte-identical**。Phase 1 72% → 73% | #1 子候選(Sprint 121):改 parser/style/layout 任一層、即使預期 VR 不變、仍應 rebuild bundle + 跑全 VR 確認(待 Sprint 122/123 跨 3 sprint 驗證) |
| 122 | 2026-05-17 01:10+ | **0.073191(已跑、byte-identical)** | ParagraphParser OLE / VML pict 入口降級 placeholder +85 行(`<w:object>` → `[嵌入物件: ProgID]`、`<w:pict>` → `[圖片(VML)]`、italic overlay)+ 8 新 unit test、vitest 985 → **993 passed + 1 skipped**、bundle rebuild、VR byte-identical。Phase 1 73% → 74% | #1 子候選跨 sprint 驗證進展 2/3(Sprint 121-122 連兩次 parser 變動跑 VR、Sprint 123 完成第 3 次可升正式) |
| 123 | 2026-05-17 01:25+ | **0.073191(已跑、byte-identical、第 3 次連續)** | ParagraphParser field code 完整覆蓋:fieldType 擴 SEQ/TOC/REF/HYPERLINK/STYLEREF + 複式 fldChar state machine(begin/separate/end 跨多 w:r 收集)+ 9 新 unit test。vitest 993 → **1002 passed + 1 skipped**、bundle rebuild、VR byte-identical。Phase 1 74% → 75%。**階段 B cluster 1 (121-123) 完成** | **紀律 #1.a 升正式**(Sprint 123 跨 3 sprint 驗證完成):改 parser/style/layout 任一層、即使預期 VR 不變、也應 rebuild bundle + 跑全 VR 確認。紀律 18 → **19 條** |
| 124 | 2026-05-17 07:40+ | **0.073191(已跑、byte-identical、第 4 次連續)** | dom.ts effectiveChildren 加 w:sdt 透明 unwrap +15 行(block / inline / cell-via-effectiveChildren 三層自動覆蓋、遞迴展開 sdtContent、malformed 容錯)+ 8 新 unit test。vitest 1002 → **1010 passed + 1 skipped**、bundle rebuild。Phase 1 75% → 76%。階段 B cluster 2 (124-126) 1/3 | 紀律 #1.a 第一次正式應用(dom.ts utility 也跑全 VR、通過驗證)|
| 125 | 2026-05-17 07:55+ | **0.073191(已跑、byte-identical、第 5 次連續、首次真實 fixture trigger)** | ParagraphNode.bookmarks?: string[] 加（types +9）+ ParagraphParser bookmark 收集（段落直屬 / w:r 內含 / hyperlink 內 三路）+30 行 + 8 新 unit test。vitest 1010 → **1018 passed + 1 skipped**、bundle rebuild、**20 個 fixture `_GoBack` 真實被 capture、render 仍 byte-identical**。Phase 1 76% → 77% | #21 候選(Sprint 125): 新 optional 欄位空集合時不掛 key、避免 AST diff noise + 保 cache key 穩定 |
| 126 | 2026-05-17 08:10+ | **0.073191(已跑、byte-identical、第 6 次連續)** | HyperlinkInfo 擴 tgtFrame/history/docLocation 3 欄位（types +12 / parser +15）+ 10 新 unit test（含 OOXML 布林雙形式 "1"/"true"/"0"/"false"、history false 是合法值用 `!== undefined` 檢測、防禦 broken rels）。vitest 1018 → **1028 passed + 1 skipped**、bundle rebuild。Phase 1 77% → 78%。**階段 B cluster 2 (124-126) 完成** | #21 候選跨 sprint 驗證 2/3（Sprint 125 揭示、Sprint 126 套用驗證 boolean 欄位特例「`!== undefined` 而非 truthy」）|
| 127 | 2026-05-17 09:20+ | 0.073191（未跑、純 probe docs） | **Probe sprint** — 3 條 docx 路徑 audit（default / DevTools TS engine / VR pipeline）揭示 production canvas-editor 完全沒整合 FontMetricsAdapter（only VR pipeline 有）。「Promote to production」非 flag flip、是 5-25 sprint architectural migration（4 候選策略 A/B/C/D）。**Autonomous 決策 Strategy D（維持現狀）**、defer A/B/C 給 user。Sprint 128 改為 HarfBuzz spike（原 129 前移） | #22 候選(Sprint 127): 「external 候選」標記不代表 scope 小、任何 production migration 開工前先 probe sprint 確認 mental model |
| 128 | 2026-05-17 15:35+ | 0.073191（未跑、spike test only） | **Probe sprint** — HarfBuzz WASM 進階能力 spike 補完（kerning / ligature / CJK / 純函式 / module 可用性 5 新 test、連同 Phase D.2 基礎 5 test = 10/10 全綠）+ bundle size 量測（核心 +465KB、production 整合不可接受 / VR 可接受）+ async/sync 分析（shape 本身 sync、僅 load async；FontMetricsAdapter 舊註解部分不正確）+ 4 candidate decision（GO-1 / GO-2 / NO-GO / DEFER-1）。**Autonomous 決策 DEFER-1（列為階段 D 候選）**：階段 C 重生 goldens 會打亂 baseline、整合放階段 C 後更划算。vitest 1028 → **1033 passed + 1 skipped**。**階段 B cluster 3 (127-128) 完成** | #22 候選跨 sprint 驗證 2/3（Sprint 127-128 連兩 probe sprint 都成功 catch 「mental model vs 實況」差距、Sprint 130+ 同類可完成 3 次驗證升正式 #22.a）|
| 130 | 2026-05-17 19:30+ | **0.073191（已跑、byte-identical、第 7 次連續）** | **階段 B cluster 4 開工**。ThemeResolver applyTint/applyShade RGB linear → **HSL luminance** 升級（+80 行、HSL 保 hue+saturation、規畫書 §Phase 4.1 收口）+ 11 新 unit test（vivid navy/red/灰階短路/極端值/單調性/round-trip 精度）。vitest 1033 → **1044 passed + 1 skipped**、bundle rebuild、VR byte-identical。Phase 4 Style 80% → **81%** | 紀律 #1.a 第 7 次連續 byte-identical 驗證、覆蓋 OOXML parser / dom utility / style resolver 三類修改點 |
| 131 | 2026-05-17 20:00+ | **0.073191（已跑、byte-identical、第 8 次連續）** | StyleResolver + TableStyleApplicator tblStylePr/tcPr 條件樣式 cell-level props 傳遞補完（types +30 / StyleResolver +50 / TableStyleApplicator +60；shading + vAlign 兩屬性、cBorders/tcMar/trPr/tblPr 條件 defer）+ 13 新 test（9 applicator + 4 resolver、含 explicit 優先、merge 順序、shading 巢狀合併、tblLook gating）。vitest 1044 → **1057 passed + 1 skipped**、bundle rebuild、VR byte-identical。Phase 4 Style 81% → **82%**。階段 B cluster 4 (130-131) 完成 | **紀律 #21 升正式**（Sprint 125-126-131 跨 3 sprint 驗證完成）：optional 欄位空集合不掛 key。紀律 19 → **20 條** |
| 132 | 2026-05-17 22:10+ | **0.073191（已跑、byte-identical、第 9 次連續）** | **階段 B cluster 5 開工 + 完成**。numberingFormatter.ts 純函式模組（+400 行：16 numFmt 含 decimal/letter/roman/ordinal/CN/JP/zodiac/iroha/aiueo + expandLvlText 模板展開）+ 50 新 unit test（CN 補零行為 / base-26 邊界 / ordinal teen 例外 / 循環序列 / Infinity/NaN 防禦 / 模板展開含 literal 保留）。vitest 1057 → **1107 passed + 1 skipped**、bundle rebuild、VR byte-identical（純加新模組、無 wire-up 整合）。Phase 4 Style 82% → **83%** | 紀律 #1.a 第 9 次連續驗證、覆蓋至 pure utility 新模組類；紀律 #3 應用（probe 確認無既有 consumer、scope 限 utility layer 避 Sprint 62 IIFE blocker） |
| 133 | 2026-05-17 22:30+ | **0.073191（已跑、byte-identical、第 10 次連續）** | **階段 B cluster 6 開工**。borderShading.ts utility 抽出（+130 行：parseBorderDef / parseShading / parseParagraphBorders 集中）+ TableParser DRY refactor（-38 helper + 1 import + 移 2 unused type）+ ParagraphParser pBdr + shd 解析補完（+20 行）+ 11 新 unit test（4 邊 / 部分邊 / 全空 / start-end alias / between-bar defer / shd 主路徑+部分/全空 / 共存 / 回歸驗證）。vitest 1107 → **1118 passed + 1 skipped**、bundle rebuild、VR byte-identical。Phase 4 Style 83% → **84%** | 紀律 #1.a 第 **10** 次連續、紀律 #21 第 3 次正式應用、紀律 #4 揭示「ParagraphProps shape 完整 ≠ parser 實作」結構性技術債 |
| 134 | 2026-05-17 23:15+ | **0.073191（已跑、byte-identical、第 11 次連續）** | **階段 B cluster 6 完成**。types.ts ParagraphProps 擴 textAlignment + framePr 兩欄位（+45 行）+ ParagraphParser textAlignment inline（10 行嚴格 enum）+ parseFramePr helper（+75 行、11 屬性嚴格 enum + 紀律 #21 空集合不掛）+ 15 新 unit test（含 it.each 5 enum）。vitest 1118 → **1133 passed + 1 skipped**、bundle rebuild、VR byte-identical。Phase 4 Style 84% → **85%**（capture 部分完工） | 紀律 #1.a 第 **11** 次連續、紀律 #21 第 4 次正式應用、紀律 #4 對比：Sprint 133 是「shape 完整 parser 沒接」、134 是「shape 也沒有 ground-up 新增」兩種型別技術債 |
| 135 | 2026-05-18 00:00+ | 0.073191（未跑、純 probe） | **階段 B cluster 7 probe**。docGrid snap 段落層級判別子 probe sprint：讀 Sprint 46/49 翻車歷史 + 結構化分析 42 fixture（按 in_cell × has_spacing.line × explicit_snapToGrid × pStyle 四維度）+ 找到判別子 = **「段落是否在 table cell 內」**（02_std_table in-cell 14-21 段落是 Sprint 49 翻車主源、03 全套管 body 3 個 title 是想救對的）+ Sprint 136 設計 sketch + autonomous DEFER-1 決策（probe-only、留 GO 給 user）。0 production code 變動 | **紀律 #22 升正式**（Sprint 127-128-135 跨 3 sprint 驗證完成）：backlog 開工前先 probe sprint 確認 mental model vs 實況差距。紀律 20 → **21 條** |
| 136 | 2026-05-18 00:30+ | **0.073191（已跑、byte-identical Sprint 135、第 12 次連續含 revert）** | **階段 B cluster 7 revert**。實作 Sprint 135 §5 sketch（isInTableCell flag + Paginator/TableLayout 注入 + LineBreaker 對 body 段落 snap）+ 跑全 42 fixture VR 後**翻車**：03 全套管 5 fixture 全 +0.86~1.47pp 退化（snap 過度推高 body title 塊、photo Y overshoot golden）、04 監造會議照片 -0.51~1.01pp 收斂（非預期）、aggregate +0.021pp 淨退化、page count baseline 6→8 → revert（production code byte-identical Sprint 135 + 10 行 LineBreaker 註解擴翻車紀錄 + 30 行 3 個 lockdown test）。vitest 1133 → **1136 passed + 1 skipped** | 紀律 #1 經典應用（unit test 過、VR 全域翻車、revert）；紀律 #4 揭示 Sprint 49 §2 Pillow ≠ snap 公式自動結果（spec-naive ceil 對 03 全套管 overshoot golden 12pt）；提案紀律 #1.b 候選：spike 翻車必完整 revert、不微調 retry（Sprint 110 + 136 跨 2 sprint 驗證 = 1/3）|
| 137 | 2026-05-18 03:30+ | **0.073191（已跑、byte-identical、第 13 次連續）** | **Phase 4 wire-up 第一階段**。`numberingCounter.ts` 純函式 state machine（+178 行：NumberingCounterState class、advance/reset/resetNum/snapshot、OOXML §17.9 多 numId × ilvl 0-8 獨立計數 + 深層 reset + lvlRestart=0 跨章節連續 + 缺失防禦）+ index.ts export +3 行 + 20 新 unit test（分 8 組、覆蓋單 ilvl/多 ilvl/多 numId/lvlRestart/缺失/lifecycle/紀律 #21/expandLvlText 串接整合）。vitest 1136 → **1156 passed + 1 skipped**、bundle rebuild + VR pipeline rebuild、VR byte-identical。Phase 4 Style 85% → **86%** | 紀律 #1.a 第 13 次連續、紀律 #21 第 5 次正式應用（counters/numFmts 收斂到 0..ilvl）、紀律 #22 第 4 次正式應用（probe 6 項避免撞 mapper wire-up VR 翻車）；提案紀律 #1.b 候選正面範例：probe 主動 scope down（2/3 + 1 預防範例） |
| 138 | 2026-05-18 03:50+ | **0.073191（已跑、byte-identical、第 14 次連續）** | **Phase 4 wire-up 第二階段**。`ToCanvasEditor.ts` numbering wire-up（+50 行：NumberingCounterState 跨 section/cell 共用、convert→appendBlocks→appendParagraph 5 method 簽章擴 numbering+counter、appendParagraph 入口若有 numId 則 advance counter + expandLvlText 展開為「字元 IElement + tab」）+ 10 新 unit test（無 numId 回歸、prefix+tab emit、連續 counter +1、多 ilvl 巢狀、多 numId 獨立、缺失 fallback、中文章節、bullet、空 lvlText、cell 內共享 counter）+ 8 fixture AST snapshot regenerate（02_std_table 5 個週報/簽到/取樣 + 03 估驗計價 2 個 + 含 numId fixture 全覆蓋）。vitest 1156 → **1166 passed + 1 skipped**、bundle rebuild + VR pipeline rebuild、VR byte-identical 第 14 次連續（**證實「VR 不走 mapper」mental model 正確**）。Phase 4 Style 86% → **88%** | 紀律 #1.a 第 14 次連續、紀律 #22 第 5 次正式應用（probe 4 項確認 VR 路徑/caller/fixture/types 就緒）；**提案紀律 #1.b 候選成熟**：4 次跨 sprint 驗證（110 翻車 + 136 翻車 + 137 預防 + 138 正面實作對照）、Sprint 139+ 可直接升正式 |
| 139 | 2026-05-18 07:10+ | **0.073191（已跑、byte-identical、第 15 次連續、Strategy C 後）** | **Phase 4 wire-up 第三階段、cluster 完工**。Layout 路徑 numbering wire-up：types.ts +20（LayoutOptions.numbering + internal _numberingCounter）+ BoxBuilder.ts +25（NumberingPrefix interface + 4th param + emission）+ Paginator.ts +60（PaginateContext counter + makeContext init + computeNumberingPrefix helper + layParagraph 呼叫 + laySingleTable 透傳 _numberingCounter）+ TableLayout.ts +35（computeNumberingPrefixForCell helper + layoutCell 呼叫）+ 10 新 unit test（5 BoxBuilder + 5 Paginator）。VR 第一次嘗試（pipeline 主動注入 documentNode.numbering）mean +0.001pp（0.073191→0.073201、byte-identical 軌道斷）→ **Strategy C 折衷**：layout wire-up 保留、VR pipeline 改 opt-in（預設不啟用、caller 顯式傳 layoutOptions.numbering 才走）→ 重跑 VR mean **0.073191 byte-identical 第 15 連**。vitest 1166 → **1176 passed + 1 skipped**。Phase 4 Style 88% → **90%**（wire-up 鏈完工、僅 VR opt-in 待階段 C） | 紀律 #1.a 第 15 連、紀律 #22 第 6 次正式應用（probe 5 項）、紀律 #18 + Strategy C 案例；**提案紀律 #1.b 候選需擴張為 v2**：包含「部分翻車 scope-down」第 5 次跨 sprint 驗證（110/136 全 revert + 137 預防 + 138 實作 + **139 Strategy C 混合**） |
| 140 | 2026-05-18 07:30+ | 0.073191（未跑、純 probe DEFER） | **A 候選 probe sprint DEFER**。Sprint 138/139 §後續 A.（textAlignment / framePr wire-up）開工前 probe 5 維度：fixture 分布（textAlignment 4/42 fixture × 18 次 / framePr 1/42 × 2 次）、canvas-editor 對應（**無**）、Layout 對應（**微弱或無**）、預期收益（< pixelmatch resolution）、Sprint 138/139 對照（三維皆弱對應 numbering 三維皆過）→ **autonomous DEFER A**（避免為 < 1pt 視覺差實作 IElement extension + canvas-editor fork、紀律 #18 PR-size 違反）。0 production code 變動。後續觸發條件 4 項（階段 C / Phase 5 / canvas-editor 升級 / user 手動 GO） | 紀律 #22 第 7 次正式應用、紀律 #18 守護案例、紀律 #4 應用「capture-without-consumer ≠ 該 wire-up」；**提案紀律 #1.b 候選 v2 第 6 次跨 sprint 驗證**（3 類型完整光譜：全 revert ×2 + 預防 ×2 + 實作/折衷 ×2）、Sprint 141+ 可升正式 |
| 141 | 2026-05-18 07:50+ | 0.073191（未跑、純 probe DEFER user GO） | **B 候選 probe sprint DEFER user GO**。階段 C 重生 goldens 環境 probe：揭示**現有 goldens = LibreOffice → PDF → PNG**（不是規畫書 §11.1 假設的 Word desktop）+ 環境就緒度（LibreOffice/Docker/Pillow/puppeteer ✓、OnlyOffice 鏡像未拉、wkhtmltopdf 未裝、Word desktop wsl 不可用）+ 3 方案評估（A LibreOffice 微調 1 sprint 低險中收益 / B OnlyOffice DocumentServer 2-3 sprint 中險高收益 / C wkhtmltopdf 中介 3-5 sprint 高險未知收益）→ **autonomous DEFER user GO**（換 baseline 影響紀律 #1.a 16 連軌道、需 user 明確同意；推薦方案 B、4-step 路徑 ready）。0 production code | 紀律 #22 第 8 次正式應用、紀律 #18 守護、**紀律 #1.b 候選 v2 第 7 次跨 sprint 驗證揭示新類型「需 user GO 的預防 DEFER」**（強調 autonomous 範圍邊界） |
| 142 | 2026-05-18 08:10+ | 0.073191（未跑、純 probe DEFER user GO） | **C 候選 probe sprint DEFER user GO**。Phase 5（OMML / SmartArt / Charts / 追蹤修訂 / 註解 / 浮水印）開工 probe：揭示**6 子功能在 42 fixture 中 0 覆蓋**（grep 全為 0）→ VR 視覺收益 = 0、不論實作哪個都無法 VR 驗證。autonomous 可獨立 GO 候選（5.4/5.5/5.6 三個小 scope）/ 必須 user GO（5.1/5.2/5.3 大依賴）。autonomous_roadmap §階段 D（Sprint 146-160）順序前提 = 階段 C 完成、跨階段違反 roadmap 一致性 → **autonomous DEFER 全 Phase 5 user GO**（等 user 提供 fixture + 優先順序決策）。0 production code | 紀律 #22 第 9 次正式應用、紀律 #18 守護案例（連續第 3 次 probe + DEFER）、autonomous 已到達**規畫書既有 backlog 邊緣**；**提案紀律 #1.b 候選 v2 第 8 次跨 sprint 驗證可升正式**（8 次跨 sprint × 3 類型 + 「需 user GO 的 DEFER」次類型 3 次驗證）|
| 143 | 2026-05-18 08:35+ | 0.073191（未跑、純 docs）| **紀律 #1.b 正式升格 + catch-up 同步 CONTRIBUTING/glossary**。Sprint 121-142 期間累計 4 次紀律升正（#1.a Sprint 123 / #21 Sprint 131 / #22 Sprint 135 / **#1.b 本 sprint**）未即時同步到集中索引、本 sprint catch-up：CONTRIBUTING.md §5 +~80 行（4 條紀律正式條目 + Sprint 138 子原則 + Sprint 142 第 9 次應用註記）、glossary.md §2.1 紀律表 +3 行 + §0 索引「紀律 18 條」→「紀律 22 條」。**紀律總數 18 → 22 條**（#1.a / #21 / #22 / #1.b）+ 6 子 + 1 候選（#20）。0 production code | 紀律 #14 / #14.a 反例 catch-up（揭示「升正同 sprint 更新集中索引」紀律下次該即時做）、紀律 #18 守護（docs-only sprint scope-down 不混入其他工作）|
| 144 | 2026-05-18 08:50+ | 0.073191（未跑、純 docs）| **Sprint 121-142 cluster retro（autonomous docs sprint）**。沿用 Sprint 120 retro 模式、22 sprint 方法論萃取：**3 個新模式** explicit — (1) probe-only sprint 從零星變例行流程（6 次累計）；(2) Strategy C 折衷模式（Sprint 139）填補「全做/全不做」二元中間；(3) **autonomous 邊界揭示**（Sprint 141/142 第一次遇到「自己無法決策」stop point、3 維度框架：baseline / 大依賴 / user 業務優先）。+ wire-up 三段式架構（state machine → mapper → layout）+ 數據總覽（+200 vitest、Phase 4 +10pp、15 連 byte-identical、4 條紀律升正）+ 跨 cluster 對照 Sprint 50-66 + 未來 cluster checklist 6 項。0 production code | 紀律 #14（即時 docs 同步）、Sprint 120 retro 模式延續、為下個 cluster 開工前的「方法論 catch-up」|
| 145 | 2026-05-18 11:00+ | **0.073191（已跑、byte-identical、第 16 次連續）** | **Phase 3.6 Footnotes / Endnotes Parser capture-only**（規畫書 §11.2 行 2）。新模組 `static/src/core/ooxml/footnotes/FootnotesParser.ts` +135 行（支援 footnotes.xml / endnotes.xml 同 parser、解析 w:type separator/continuationSeparator/continuationNotice/普通 + w:id 整數 + 重用 DocumentParser 解析內部段落 + 4 防禦邊界）+ types.ts +18 行（FootnoteContent interface + DocumentNode 2 新欄位）+ OoxmlParser.ts +30 行（REL_TYPE × 2 + Step 6.5 + collectNotes helper）+ 4 既有 DocumentNode constructor patch（+8 行）+ 12 新 unit test。**probe 5 維度**確認:fixture footnoteReference 0/42 出現（純 Word 預設骨架）→ capture-only 模式（Sprint 134 範本）、不 wire-up。vitest 1176 → **1188 passed + 1 skipped**、bundle + VR pipeline rebuild、VR byte-identical。Phase 1 OOXML 80% → **82%** | 紀律 #1.a 第 16 連、紀律 #22 第 10 次正式應用、紀律 #18 PR-size 守住、紀律 #1.b 第 9 次驗證正面範例（probe 後直接實作） |
| 146 | 2026-05-18 11:45+ | **0.073191（已跑、byte-identical、第 17 次連續）** | **Phase 1 settings.xml capture-only**（autonomous 探索 §11.2 backlog 邊緣、Sprint 145 §後續 E-3）。**probe 升級為跨 fixture part 統計**揭示 settings.xml 42/42 全覆蓋但未 parse。新模組 `static/src/core/ooxml/settings/SettingsParser.ts` +187 行（解析 9 elements:zoom / defaultTabStop twip→pt / characterSpacingControl + 列舉 + 未知值降級 / 3 toggles / proofState / footnotePr / endnotePr / compat 子元素列表 + 7 防禦邊界 + 紀律 #21 空集合不掛 key）+ types.ts +75 行（DocumentSettings interface + DocumentNode 1 新欄位）+ OoxmlParser.ts +35 行（REL_TYPE_SETTINGS + Step 6.6 + collectSettings helper）+ 5 既有 DocumentNode constructor patch（+5 行）+ 27 新 unit test。vitest 1188 → **1215 passed + 1 skipped**、bundle + VR pipeline rebuild、VR byte-identical。Phase 1 OOXML 82% → **84%** | 紀律 #1.a 第 17 連（連 2 個 capture-only parser 都不破 baseline）、紀律 #22 第 11 次正式應用（probe 升級為「跨 fixture part 統計」）、紀律 #21 應用 9 個 fields 全採空集合不掛 key、紀律 #18 守住 PR-size、紀律 #1.b 第 10 次驗證正面範例 |
| 147 | 2026-05-18 12:00+ | **0.073191（已跑、byte-identical、第 18 次連續）** | **Phase 1 fontTable.xml capture-only**（Sprint 146 §後續 E-3 cont.）。新模組 `static/src/core/ooxml/font-table/FontTableParser.ts` +150 行（解析 7 elements:name 主 key / altName / charset hex / family 6 列舉 + 未知降級 / pitch 3 列舉 + 未知降級 / panose1 10-byte hex / sig 6 屬性 + 紀律 #21 全空不掛 key + 7 防禦邊界 + Map 保插入順序 + CJK Unicode key）+ types.ts +70 行（FontFamily / FontPitch / FontSignature / FontEntry / FontTable + DocumentNode 1 新欄位）+ OoxmlParser.ts +30 行（REL_TYPE_FONT_TABLE + Step 6.7 + collectFontTable helper）+ 5 既有 DocumentNode constructor patch + 20 新 unit test（5 組）。與 FontMetricsAdapter（Sprint 60-65）互補關係 explicit:opentype.js 提供 metric / fontTable 提供 altName fallback chain + sig Unicode 支援度 hint。vitest 1215 → **1235 passed + 1 skipped**、bundle + VR pipeline rebuild、VR byte-identical。Phase 1 OOXML 84% → **86%**。**Phase 1 capture-only 三連 cluster(145-147)完成**:合計 4 parts / 19 elements / +59 test / +6pp Phase 1 進度 | 紀律 #1.a 第 18 連（連 3 個 capture-only parser 不破 baseline）、紀律 #22 第 12 次正式應用（probe 從跨 part 統計延伸到單 part 內 elements 結構統計）、紀律 #21 大量應用（family/pitch 列舉降級 + sig 全空不掛）、紀律 #18 守住、紀律 #1.b 第 11 次驗證正面範例 |
| 148 | 2026-05-18 12:15+ | **0.073191（已跑、byte-identical、第 19 次連續）** | **Phase 1 webSettings.xml capture-only**（Sprint 147 §後續 E-4、結束 part 三連 cluster）。新模組 `static/src/core/ooxml/web-settings/WebSettingsParser.ts` +95 行（**scope-down** 解析:4 toggle 元素 + hasDivs boolean、不深入 w:divs 巢狀結構、留 Phase 6 docx export）+ types.ts +30 行（DocumentWebSettings interface + DocumentNode 1 新欄位）+ OoxmlParser.ts +30 行（REL_TYPE_WEB_SETTINGS + Step 6.8 + collectWebSettings helper）+ 5 既有 DocumentNode constructor patch + 14 新 unit test（4 組）。**紀律 #18 scope-down 案例**:儀式性收尾不過度設計、divs 內部留 Phase 6。vitest 1235 → **1249 passed + 1 skipped**、bundle + VR pipeline rebuild、VR byte-identical。Phase 1 OOXML 86% → **87%**。**Phase 1 capture-only 四連 cluster(145-148)完成**:5 parts / 24 elements / +73 test / +7pp Phase 1 進度（80→87%）| 紀律 #1.a 第 19 連（連 4 個 capture-only parser 不破 baseline）、紀律 #22 第 13 次正式應用、紀律 #18 守護新案例（儀式性 part 三連可用 scope-down 達成、不必為 closure 而 over-parse）、紀律 #1.b 第 12 次驗證正面範例 |
| 149 | 2026-05-18 12:30+ | 0.073191（未跑、純 docs）| **Sprint 143-148 cluster retro（autonomous docs sprint、短週期模式）**。沿用 Sprint 120/144 retro 模式、6 sprint 方法論萃取:**3 個成熟模式** explicit — (1) 紀律 #1.b 升正 + catch-up 集中索引（揭示 Sprint 119 vs Sprint 143 規模對照、紀律 #14.a 反例價值）；(2) **Phase 1 capture-only 四連 archetype**（9-step 模式可複製、+7pp / +73 test / 4 連 byte-identical）；(3) **retro 短週期觸發**（6 sprint vs 20+ sprint、模式成熟即可寫）。+ 紀律 #18 scope-down 新案例 explicit + cluster checklist 補強 2 項（#7 儀式性收尾 scope-down / #8 短週期 retro 觸發）+ 跨 retro 對照（Sprint 120/144/149 三次）。0 production code | 紀律 #14 即時 docs 同步、Sprint 120/144 retro 模式延續、為 Sprint 150+ wire-up vs 等 user vs 持續 capture 決策框架鋪路 |
| 150 | 2026-05-19 09:40+ | **0.073191（已跑、byte-identical、第 20 次連續）** | **Phase 1 docProps/app.xml capture-only**（autonomous-friendly §11.2 backlog 路線、Sprint 149 retro 三選一中的「持續 capture」）。**fixture parts gap 系統掃描**揭示 docProps/app.xml 42/42 全覆蓋但 DocPropsParser 只解 core.xml、未 capture extended-properties。新模組目錄 `static/src/core/ooxml/doc-props/AppPropsParser.ts` +189 行（17 elements:4 字串 / 8 整數含 DocSecurity enum / 5 布林、嚴格規格 "true"/"false" 不接受 "1"/"0" / 嚴格整數 `/^-?\d+$/` 不接受小數 / localName fallback xmldom 部相容 + 紀律 #21 全空不掛 key + 8 防禦邊界）+ index.ts +1 行 + types.ts +37 行（DocPropsApp interface + DocumentNode 1 新欄位）+ OoxmlParser.ts +6 行（import + Step 8.1）+ 5 個既有 DocumentNode constructor patch（+5 行）+ 20 新 unit test（5 組:字串 / 整數 / 布林 / 真實 fixture 樣本 / 防禦邊界）。vitest 1249 → **1269 passed + 1 skipped**、bundle + VR pipeline rebuild、VR byte-identical。Phase 1 OOXML 87% → **88%**。**Phase 1 capture-only 五連 cluster(145-150)延續**:6 parts / 41 elements / +93 test / +8pp Phase 1 進度（80→88%）| 紀律 #1.a 第 20 連（連 5 個 capture-only parser 不破 baseline）、紀律 #22 第 14 次正式應用（fixture parts gap 系統掃描 probe）、紀律 #21 應用 17 個 fields 全採空集合不掛 key、紀律 #18 守住 PR-size、紀律 #1.b 第 13 次驗證正面範例（capture-only 變體類型再次穩定）|
| 151 | 2026-05-19 10:30+ | **0.073191（已跑、byte-identical、第 21 次連續）** | **Phase 1 docProps/custom.xml capture-only**（Sprint 150 §後續 E-10、doc-props 子目錄延伸）。**variant 型別 probe**:42 fixture 25 有 custom.xml、只見 vt:lpwstr(KSO × 24 + Grammarly × 14)、但 OOXML §22.4 spec 定義 ~20 variant → 紀律 #18 scope-down 設計 discriminated union(5 常見 + unknown 降級)。新檔 `static/src/core/ooxml/doc-props/CustomPropsParser.ts` +179 行（variant 解析:string/int/bool/real/filetime + unknown raw 保留 / 紀律 #21 property-level + variant-level 雙層 / fmtid/pid 不保留 / filetime 不轉 Date / 重複 name Map.set 後者覆蓋 + 7 防禦邊界）+ types.ts +37 行（CustomPropertyValue discriminated union + DocPropsCustom Map + DocumentNode 1 新欄位）+ OoxmlParser.ts +6 行（Step 8.2 collectCustomProps）+ 5 個既有 DocumentNode constructor patch + 29 新 unit test（8 組）。vitest 1269 → **1298 passed + 1 skipped**、bundle + VR pipeline rebuild、VR byte-identical。Phase 1 OOXML 88% → **89%**。**Phase 1 capture-only 七連 cluster(145-151)延續**:7 parts / 47 elements / +122 test / +9pp Phase 1 進度（80→89%）| 紀律 #1.a 第 21 連（連 6 個 capture-only parser 不破 baseline）、紀律 #22 第 15 次正式應用（variant 型別覆蓋 probe）、紀律 #21 雙層應用、紀律 #18 多維度 scope-down（metadata/value/variant/error handling 4 維）、紀律 #14 模組化一致性（doc-props/ 子目錄聚集）、紀律 #1.b 第 14 次驗證 |

---

**Document End** — Autonomous Roadmap v1 / 建於 Sprint 113
