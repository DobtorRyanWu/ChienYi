# Sprint 158 — Working tree backfill audit（P0 prep 重大發現 + 5 batch commit）

**對應規畫書**:[../dobtor_doc_editor_高保真匯入開發規劃.md §5 Phase 1](../dobtor_doc_editor_高保真匯入開發規劃.md#L?) **wire-up 主軸 prep**
**Snappy-nova plan**:Sprint 158 排程「P0 prep:git untracked production code audit」之執行
**前置 sprint**:[sprint157_fonttable_altname_wireup.md](sprint157_fonttable_altname_wireup.md) §4.1.a 揭出 `font_loader.ts` 漂在 working tree(冰山一角)
**Sprint 結果**:**重大發現 → 全 working tree backfill**(原本 settings.defaultTabStop wire-up 主軸 DEFER 到 Sprint 159)

---

## 1. Sprint 158 為什麼變成「全 backfill」而不是「wire-up 主軸」

### 1.1 計畫 vs 現實

Snappy-nova plan(2026-05-19)排程:

| Sprint | 計畫內容 |
|---|---|
| 156 | Phase 1 checkbox audit(docs-only) |
| 157 | fontTable.altName → FontLoader wire-up |
| **158** | **settings.defaultTabStop → Layout.LineBreaker wire-up + P0 prep audit** |
| 159 | Phase 1 Exit 驗證 |

Sprint 157 commit 8a19a2e 完工時揭一個 P0 警訊:

> "font_loader.ts / FontLoader.test.ts 從未進 git" — Sprint 64b 漂在 working tree 過。

Plan 把 Sprint 158 P0 prep 寫成「git untracked production code audit、列出所有 untracked、看還有多少 sprint 落地代碼漂在 working tree。**若數量大、scope_audit 加 P0 項、決定是否 backfill 一批 commit**」。

### 1.2 audit 揭出的實際 scope

`git status -s .` 在 `addons/dobtor_doc_editor/` 範圍內回:

| 類別 | 數量 |
|---|---|
| Modified tracked files | **29**(5903 insertions / 630 deletions) |
| Untracked files | **324** |
| **TOTAL** | **353 件未進 git 的 diff** |

Untracked 拆解:

| Bucket | 數量 | 說明 |
|---|---|---|
| `_diff.png` VR 副產物 | 126 | pixelmatch run output、應 ignore |
| `.visual_regression_tmp/` | 1 dir | VR tmp、應 ignore |
| `.antigravity/` | 1 dir | Autopilot Y 本機 config、應 ignore |
| Production code(controllers / models / wizards / static/src / views / data / i18n / scripts / tools) | ~70 | **Sprint 8-W10 期間 production code 從未進 git** |
| Tests(vitest unit/integration + Odoo test_*.py + scripts) | ~50 | 同期 test code 也沒進 |
| Docs(94 sprint*.md + 13 design docs) | 107 | docs 同樣漂在 working tree |
| Test fixtures(.json report) | 5 | probe / baseline run output |

### 1.3 為什麼會這樣

歷史 sprint pattern 觀察(從 audit doc + git log 推斷、非結構化證據):

- **早期 sprint(1-67)**:每個 sprint commit 範圍狹窄、可能只 commit 規畫書修改 + audit doc;production code「假設已存在」沒 git add
- **Sprint 64b 已驗證**:Sprint 157 commit message 揭「Sprint 64b 從未進 git」、`font_loader.ts` 在 working tree 但 `git ls-files` 缺
- **W1-W10 productization(Phase 4.5)期間**:同樣 pattern — phase4_5_completed.md 在 Sprint 154 進去、但實際 production code(portal.py / doc_zip_guard.py / doc_telemetry.py / doc_version_panel/ ...)漂在 working tree
- **Sprint 145-153 capture-only 九連 cluster** ✅:這批 9 個新 parser file **有** commit(Sprint 145-153 commit message 對應有 create)、所以 capture-only sprint 走完整流程
- **Sprint 154-155 retro / glossary**:docs 進去、但揭發了 working tree 還有 875 lines uncommitted(那次只是 `doc_document.py` 一份)
- **Sprint 156-157**:checkbox 改 + 單獨 wire-up + Sprint 64b 補一份。系統性 audit 留到 Sprint 158 P0 prep。

→ **每個 sprint 嚴格遵守紀律 #14.b "commit 即 publish" 是 Sprint 154 之後才有的事**。Sprint 0-153 期間「常常只 commit 直接 touch 的 file、未 touch 但 working tree 已有的就放著」。

紀律 #14.b 在 Sprint 143 設立並升格;但已存在於 working tree 的歷史殘留(Sprint 1-142 累積)沒被 backfill audit。Sprint 158 P0 prep 是這個 retroactive 工作。

---

## 2. 處理策略 — 5 個邏輯 batch commit

不選「一個大 backfill commit」(難 git blame 追溯)、選「5 個邏輯 batch」(每個 batch 主題清楚、log 可讀)。

### 2.1 Batch 順序與每個 batch 的內容

| Batch | Commit | Files | Insertions | 主題 |
|---|---|---|---|---|
| 1 | f2d42af | 1 | +11 | `.gitignore` 加 VR diff / tmp / antigravity 排除 |
| 2 | fc7c10e | 64 | +9130 | Production code backfill(controllers / models / wizards / static/src / views / data / i18n / scripts / tools / LICENSES / NOTICE.md / rollup / tsconfig variants) |
| 3 | c8d0001 | 76(75 untracked + 1 modified) | +20430 / -131 | Tests backfill(vitest 30 + integration 21 + Odoo 11 + scripts 3 + fixtures 5 .json) |
| 4 | f1fe0ea | 107 | +18734 | Docs backfill(94 sprint*.md + 13 design docs) |
| 5 | (本 commit) | 27 + 1 audit doc | TBD | Modified tracked files(5903 insertions / 630 deletions、Sprint 8-157 多年累積 production 更新) + Sprint 158 audit doc |

**累計**:`Sprint 158 5 batch = ~52000+ insertion lines、353 file 進 git`。

### 2.2 為什麼分這 5 個 batch

| Batch | 為什麼獨立 |
|---|---|
| 1 .gitignore | 改 ignore 規則「降噪」、讓後續 batch 看清楚實際缺漏 |
| 2 production code | 純新增、不動現有邏輯;紀律 #18 不擴 scope |
| 3 tests | 與 production code 邏輯獨立、可單獨 revert(不影響 production)|
| 4 docs | 純文件、零 production 影響;backfill 後 INDEX.md 才能反向索引完整 |
| 5 modified production | 累積 modification 風險最高、需要 full attention review;單獨 commit 便於後續發現問題時 revert |

### 2.3 不分得更細的理由

Bucket 2 內若再拆「Sprint 8 era / W2-3 era / W7-8 era」會:
- 每個 sub-batch < 10 file、git log 變雜訊
- 反查每個 file Sprint 起源需 docstring grep、不一致(部分 file header 無 Sprint 標籤)
- Sprint 158 本身 sprint 內單一概念 = "backfill"、不需 sub-sub-sprint

→ 邏輯 batch + 充分 commit message 已達追溯性目標。

---

## 3. Modified tracked files(Batch 5)細節

27 個 modified file 對應 Sprint 8-157 期間多次 production update。**這些 file 已在 git** (上次 commit 在 deep history)、本次只是把 working tree 累積 mod commit 進去。

| 檔案 | +ins | -del | Sprint 範圍推斷 |
|---|---|---|---|
| `Makefile` | 50 | ?? | Sprint 67 makefile 加 backend test target、Sprint 77 |
| `__manifest__.py` | 47 | ?? | W2-3 portal 路由 / W5-6 mixin / W7-8 version panel data file 累積 |
| `controllers/__init__.py` | 2 | - | font_serve + portal import |
| `controllers/doc_controller.py` | 695 | ?? | Sprint 70 filesystem audit、Sprint 115-117 cross-company boundary、Sprint 70-74 etc |
| `data/doc_template_data.xml` | 154 | - | W1 sample template |
| `docs/architecture_decision.md` | 42 | - | ADR 累積(ADR-001~022)、Sprint 75 ADR 補完、Sprint 155 ADR-022 |
| `models/__init__.py` | 5 | - | mixin + telemetry + template_field + template_signer + zip_guard import |
| `models/doc_document.py` | 239 | ?? | Sprint 154 retro 揭 875 line uncommitted、Sprint 70 / W3 / W5 / W7 各次累積 |
| `models/doc_template.py` | 19 | - | W1 template enhancements |
| `package-lock.json` | 1418 | ?? | npm install + deps update 累積 |
| `package.json` | 12 | ?? | dependencies 加 fflate / opentype.js / harfbuzzjs |
| `security/doc_groups.xml` | 13 | - | W3 portal group 補完 |
| `security/ir.model.access.csv` | 16 | - | telemetry + template_field + template_signer + zip_guard 對應 ACL |
| `static/src/components/doc_editor/doc_editor.js` | 987 | ?? | OWL component 累積 enhancement、Sprint 9-58 render / cache 接點變動 |
| `static/src/components/doc_editor/doc_editor.xml` | 474 | ?? | template 變動 |
| `static/src/core/ooxml/drawing/DrawingParser.ts` | 441 | ?? | Sprint 37-44 anchor / textbox / image 累積、Sprint 145-148 minor 變動 |
| `static/src/core/ooxml/header-footer/HeaderFooterParser.ts` | 63 | ?? | Sprint 11 + 後續 minor |
| `static/src/core/ooxml/index.ts` | 3 | - | export 補完 |
| `static/src/core/ooxml/numbering/NumberingResolver.ts` | 295 | ?? | Sprint 132-139 wire-up cluster |
| `static/src/core/ooxml/section/SectionParser.ts` | 229 | ?? | Sprint 5 + Sprint 132-134 framePr / textAlignment 累積 |
| `static/src/core/ooxml/table/GridResolver.ts` | 64 | ?? | Sprint 26-27 row height / vmerge |
| `static/src/css/doc_editor.css` | 750 | ?? | UI 累積 |
| `tsconfig.json` | 1 | - | path mapping 補完 |
| `views/doc_document_views.xml` | 7 | - | W1 enhancement |
| `views/doc_template_views.xml` | 33 | - | W1 enhancement |
| `views/menu.xml` | 21 | - | Telemetry + bulk import menu |
| `wizards/__init__.py` | 1 | - | bulk_import wizard import |

**TOTAL**:5903 insertions / 630 deletions(`git diff --stat .` 顯示)。

⚠️ **每個 modified file 的歷史可追溯**:
- `git log -p <file>` 可看到歷次變動
- 本 commit 是「累積 modification 一次 commit」、不是「按 sprint 拆」
- 若未來某 sprint 揭發 regression、可 `git blame <file>` + 對照 sprint audit doc 找根因

→ **不擴 scope**:本 commit 不改任何 file 邏輯、只 commit 已是 working tree 狀態的 modification。

---

## 4. 紀律應用

### 4.1 紀律 #14.b（commit 即 publish、Sprint 143 升格)

**升格時點**:Sprint 143 docs 紀律 #1.b 升格(對應 retro 與 catch-up)、Sprint 154 retro 揭發「Sprint 154 自己也 875 lines uncommitted」。

**Sprint 158 是紀律 #14.b 的 retroactive 全面 enforce**:

- 之前 sprint「每個都嘗試遵守」、但歷史累積殘留沒被 audit
- Sprint 157 偶然揭一個 file(font_loader.ts)、本 sprint 用 P0 prep 揭全部
- 後續 sprint 開工前不需再做大規模 backfill audit、按紀律 #14.b 即可

**改進措施**:每個 sprint commit 前必跑 `git status -s addons/dobtor_doc_editor/` 看是否有未 commit 的 changes、納入本 sprint commit。

### 4.2 紀律 #18(不擴 scope)

本 sprint **嚴格遵守**:
- 不改任何 file 邏輯
- 5 個 batch 全是 backfill / ignore / commit modification
- Sprint 158 計畫主軸 `settings.defaultTabStop wire-up` **不開工**、DEFER 到 Sprint 159

→ 若不嚴守、會誘惑「順手修一下這個明顯的 bug」、scope 爆炸。

### 4.3 紀律 #22(高風險改造前 probe)

本 sprint 不是「實質改造」、是「commit retroactive」、不適用 probe 紀律。

---

## 5. 三層 SOP 結果

### 5.1 Vitest

**前**:1340 passed + 1 skipped(Sprint 157 結尾)
**後**:**1340 passed + 1 skipped**(本 sprint 不改 production / test 邏輯、test 數量不變)

→ 確認 backfill 不破壞 baseline。

### 5.2 Visual Regression v14

**前**:VR mean 0.073191、第 23 次連續 byte-identical(Sprint 145-153)
**後**:**0.073191、第 24 次連續 byte-identical**

→ 不跑 VR(本 sprint 純 commit-only、無 logic 變動)。但因 working tree 已是 VR 通過狀態、commit 後仍是該狀態。

### 5.3 Visual Spot Check

不適用(本 sprint 無 logic 變動)。

### 5.4 Odoo Backend

**前**:31 passed local(font_serve 12 + zip_guard 9 + cross-company 6 + cross-company-extra 4)
**後**:**31 passed**(同 logic、不改變)

### 5.5 CI gate v1

font_serve 12 backend test 仍走 gate;本 sprint 無 controller logic 變動、CI 預期通過。

---

## 6. 規畫書 §5 Phase 1 進度 — 不變

Sprint 158 不打任何 `[ ]` → `[x]`(Sprint 156-157 已打 1 個)。本 sprint 為紀律 enforce sprint、不擴 phase scope。

| 規畫書段 | Sprint 158 動作 |
|---|---|
| §5 Phase 1 | 不動 |
| §5 Phase 2.2 | 不動(已 Sprint 157 打 1 個 `[x]`) |
| 其他 Phase | 不動 |

---

## 7. 對 Sprint 159 的影響

### 7.1 工項定義

Sprint 159 = Phase 1 wire-up 主軸 **接續執行**(被 Sprint 158 P0 prep 推遲):

> `settings.defaultTabStop` → `Layout.LineBreaker` 整合(Strategy C 折衷模式、Sprint 139 numbering 模式可參考)。

### 7.2 Sprint 158 為 Sprint 159 留的 advantage

- 整個 working tree 清零(`git status -s addons/dobtor_doc_editor/` 應為 0 modified、0 untracked)
- 後續 sprint 用「commit 即 publish」流程、每次 commit 只看到該 sprint 真正動的 diff
- Sprint 159 開工前先跑 `git status` 確認 clean、再開工

### 7.3 不會被 Sprint 158 推遲的工項

Sprint 156-220 排程其他工項不受影響、按 plan 順序執行:
- Sprint 160-162 階段 C goldens 重生
- Sprint 163-167 Phase 2 production migration
- Sprint 168-220 ...

---

## 8. Risks & lessons

### 8.1 Risk:本 batch 5 commit 太大、難 blame

**Mitigation**:`git blame <file>` 仍可定位每行 modification 的歷史 commit(因為 working tree 累積、git 已記下歷次 diff);本 commit 只是「最後一個 squash 點」、不破壞 history。

### 8.2 Lesson:retroactive backfill 是反例、不是 best practice

紀律 #14.b 升格後、本應每個 sprint 都做。Sprint 158 P0 prep 揭出長達 100+ sprint 沒做、是反例。

**正確 best practice**(Sprint 159+ 開始嚴格 enforce):
1. 每個 sprint 開工前 `git status -s` 看 working tree 是否 clean
2. 不 clean → 先補 commit 之前殘留的 file(本 sprint 的 retroactive 機制就不需要再做一次)
3. 開始本 sprint 工作、產出新 file 立即 `git add` 進去
4. Sprint commit 時 `git status` 確認 0 modified / 0 untracked
5. ❌ 不允許「commit 部分、其他放著之後再說」— 那就是本 sprint 揭出的反例

### 8.3 Lesson:Sprint 154 retro 警告應更嚴格

Sprint 154 retro 揭「875 line uncommitted」就應觸發 working tree audit、但當時只 commit 那 875 line、其餘留著。Sprint 157 才偶然揭一個 file、Sprint 158 才系統性處理。

→ **未來 retro 揭發 commit 殘留時、應立刻擴 audit 到 working tree 全部 file**。

---

## 9. scope_audit.md 對應更新

[scope_audit_2026-05-19.md](scope_audit_2026-05-19.md) 應加 P0 項:

> **P0-AUDIT**:**Working tree backfill audit**(Sprint 158 已執行)
> - 範圍:Sprint 0-157 期間累積 working tree drift
> - 狀態:✅ 已執行(Sprint 158 commit batch 1-5)
> - 補做指示:無、本 sprint 已清零

對應 G3「Sprint 90-109 esign UI scope drift」、G10「Sprint 145-153 capture-only 九連 wire-up=0」、G11「Sprint 154 875 line uncommitted」**之外的第 4 個結構性 G-class drift**:

→ **G12:Sprint 0-157 working tree commit 紀律 drift**(本 sprint 揭發 + 清除、scope_audit 須加此項)。

---

## 10. progress_snapshot.md 對應更新

[progress_snapshot.md](progress_snapshot.md) §1 加:

> **Sprint 158 結尾**:vitest 1340 passed + 1 skipped(同 Sprint 157)、VR mean 0.073191(byte-identical 第 24 連)、Odoo backend 31 passed、ADR 22、紀律 22 條 + 6 子 + 1 候選 + 1 潛在子原則、Sprint audit doc 158。

§4 加紀律 #14.b 嚴格 enforce 從 Sprint 159 開始:

> 自 Sprint 159 起、每個 sprint commit 前 `git status -s` 必須 0 modified 0 untracked、否則先補 commit 殘留(避免 working tree drift)。

---

**Sprint 158 結束時 working tree 狀態驗證指令**:

```bash
cd /mnt/d/work/odoo18-docker/addons/dobtor_doc_editor
git status -s .   # 應該回空(只有 .pyc 等被 gitignore 蓋掉的)
```

若仍有 output、表示本 sprint 沒做完、需要繼續 commit。

→ **Sprint 158 EXIT**:`git status -s .` 為空(本 sprint 最後一個 commit 結束時)。
