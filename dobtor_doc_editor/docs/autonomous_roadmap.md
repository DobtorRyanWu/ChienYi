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
| 121-123 | Phase 1 OOXML | 1.5 進階 row height(`<w:trHeight calcInternal>`)、1.8 OLE objects 降級渲染、1.9 field code 完整覆蓋(PAGE / DATE / SEQ / TOC) | 🟢 121 ✅ / 122-123 ⏳ |
| 124-126 | Phase 1 OOXML | 1.9 SDT 結構化標籤、1.9 bookmark range、1.9 hyperlink rels 完整 | ⏳ |
| 127-128 | Phase 2 字型 | 把 FontMetricsAdapter 推到 production(目前 opt-in、Sprint 64b external 候選 — Claude 自主執行 migrate doc_editor.js 走自家 pipeline) | ⏳ |
| 129 | Phase 2 字型 | HarfBuzz WASM 整合 spike(規畫書原列 1-2 週) | ⏳ |
| 130-131 | Phase 4 Style | 4.1 Theme tint/shade 演算法(HSL luminance)、4.2 tblStylePr 15 種條件完整 | ⏳ |
| 132 | Phase 4 Style | 4.3 中文編號格式 chineseCounting / ideographDigital / japaneseCounting 完整 | ⏳ |
| 133-134 | Phase 4 Style | 4.4 段落進階(`<w:pBdr>` 邊框 + 陰影 / tab stop leader+decimal / textAlignment) | ⏳ |
| 135 | Phase 3 漏項 | docGrid snap 段落層級判別子(規畫書 §0.1 列為長期 backlog;Sprint 46+49 全域翻車、需段落條件式) | ⏳ |

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

---

**Document End** — Autonomous Roadmap v1 / 建於 Sprint 113
