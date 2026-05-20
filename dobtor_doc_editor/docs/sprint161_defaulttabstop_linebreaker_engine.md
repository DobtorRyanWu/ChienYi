# Sprint 161 — `settings.defaultTabStop` → LineBreaker tab stop 解析引擎

**性質**: Phase 1/3 wire-up sprint、layout 引擎變動、低風險（Strategy C 預設路徑 byte-identical by construction）
**範圍**: 規畫書 §5 Phase 1 §1.3「tab stops」+ Phase 3 Layout Engine — `<w:tab/>` 從「當單一空白」升級為「推進到下一個 tab stop」
**前置 sprint**: [sprint160_v2_instrtext_render_wireup.md](sprint160_v2_instrtext_render_wireup.md)（§6.2 候選表列「settings.defaultTabStop → Layout.LineBreaker」為下一主軸）
**snappy-nova plan**: Sprint 156-158 原排程主項「settings.defaultTabStop → Layout.LineBreaker」（被 Sprint 158 P0 prep 推遲、159/160 走 docs follow-up、本 sprint 接續）

---

## 0. 開工前狀態（紀律 #14.b 第 0 步）

`git status -s .` = 空（Sprint 160 v2 commit `35be1d7` 已收口）。working tree clean、可開新 sprint。

---

## 1. Hypothesis

開工前 probe（紀律 #22）揭示**直覺 mental model 錯誤**：

- ParagraphParser 把 `<w:tab/>` 當 `"\t"` 字元併入 run text（§5 §1.3「tab stops、tabs」標 `[x]` 僅指 parse）。
- [BoxBuilder.ts](../static/src/core/layout/BoxBuilder.ts) `pushTextAsBoxes`：`\t`（0x09）與空白（0x20）**完全同處理** —— 吐一個 `spaceGlue(measureWidth(' '))`，render 出單一空白寬、**不推進到 tab stop**。
- 「把 `defaultTabStop` 接進 BoxBuilder」的直覺**行不通**：tab 寬度取決於「該行起點到 tab 的累積寬度」、而 BoxBuilder 在 line-break **之前**建扁平 item list、**不知道 x 座標**。正確解析必須在 **line 組成時（x 已知）** 做。
- fixture 掃描：42 fixture 中僅 9 份含 `<w:tab/>`（7 份監造會議記錄各 1 個、2 份缺失改善各 2 個）—— 影響面小但非零。

**Hypothesis**：把 tab 解析放在 LineBreaker `makeLine`（line 組成、x 可累積時），用 `defaultTabStop` 重算 isTab glue 寬度為「推進到下一個 tab stop」；以 **Strategy C** opt-in（caller 不傳 `defaultTabStop` → 維持 Sprint 0-160 空白寬行為），預設路徑 byte-identical。

---

## 2. Method

### 2.1 設計（為什麼 line 組成層）

| 選項 | 描述 | 評估 |
|---|---|---|
| A | BoxBuilder 直接算 tab 寬 | ✗ BoxBuilder 無 x 座標、mental model 錯誤 |
| B | Knuth-Plass item 內嵌動態寬 | ✗ K-P 需 item 寬上限已知、tab 動態寬破壞 DP |
| C | LineBreaker `makeLine` 內 post-pass、line items 已定、x 可左→右累積 | ⭐ 選 — x 已知、純函式、不動斷行核心 |

### 2.2 實作（3 檔、淨 production +約 75 行）

1. **[types.ts](../static/src/core/layout/types.ts)** `Glue` 加 `isTab?: boolean`。標記用、不帶任何寬度語意。

2. **[BoxBuilder.ts](../static/src/core/layout/BoxBuilder.ts)** `pushTextAsBoxes`：0x09 仍以 `spaceGlue(measureWidth(' '))` 建立（**寬度不變**）、但設 `glue.isTab = true`。
   - → BoxBuilder 階段 render 寬度與 Sprint 0-160 完全一致（baseline 不受影響）。

3. **[LineBreaker.ts](../static/src/core/layout/LineBreaker.ts)**：
   - `LineBreakOptions` 加 `defaultTabStop?: Pt`（undefined/0 → 不解析）。
   - `makeLine` 加第 5 參數 `defaultTabStop`、入口呼叫 `resolveTabStops()`。
   - `resolveTabStops(items, para, defaultTabStop)`：`defaultTabStop <= 0` 直接原樣回傳；否則左→右累積 x、對每個 isTab glue 把寬度重算為 `nextTabStop(x) - x`。
   - `nextTabStop(x, explicitStops, defaultTabStop)`：段落顯式 `props.tabs`（僅 `left` 對齊）優先；超過所有顯式 stop → 落 `defaultTabStop` 間距整數倍。
   - `breakParagraph` / `breakParagraphKP` 皆透傳 `defaultTabStop`（greedy + K-P 兩路徑一致）。

### 2.3 紀律 #18 scope-down（明確不做）

- **center / right / decimal / bar 對齊 tab**：不解析（罕用、`resolveTabStops` 只取 `align === 'left'`）。
- **firstLineIndent 與 tab stop 原點交互**：x 原點 = 行內容起點（不計首行縮排）。leader tab 多在行首/短標籤後、影響極小。
- **production 接線（Paginator 傳 `DocumentSettings.defaultTabStop`）+ frontend bundle rebuild + VR opt-in 量測**：留 Sprint 162（本 sprint 為「引擎層、無 production caller」、Sprint 157 FontLoader 同型）。
- **貪婪斷行 buf 累寬**：仍用 BoxBuilder 空白寬（未解析值）做斷行判斷、解析寬度只反映在 `makeLine` 後的 `Line.width`。近似 —— leader tab 多在行首、不觸發 reflow；誠實聲明。

### 2.4 新測試（11 個，`tests/unit/layout/LineBreaker.tabStop.test.ts`）

| 群組 | Test | 驗證 |
|---|---|---|
| BoxBuilder 標記 | `\t` glue 帶 isTab、寬度 > 0 | 標記正確、寬度仍空白寬 |
| | 一般空白 glue 不帶 isTab | 標記不誤觸 |
| 未傳 defaultTabStop | tab glue 維持空白寬 | Strategy C 預設路徑 |
| | `defaultTabStop = 0` 等同未傳 | 邊界 |
| 傳 defaultTabStop | 行首 tab → 推進到 36pt | 核心路徑 |
| | 短標籤後 tab → 結束位置 = 36pt | x>0 起算 |
| | 連續兩 tab → 36 → 72 | 多 tab 累進 |
| | tab 結束位置永遠落 default stop 整數倍 | 不變式 |
| 顯式 props.tabs | left stop pos=100 → 推進到 100 | 顯式優先 |
| | x 超過顯式 stop → 回落 default 整數倍 | fallback |
| | center 對齊 stop 不參與 | scope-down 驗證 |

---

## 3. Verification（三層 SOP）

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1342 → 1353 passed + 1 skipped**（+11 Sprint 161 test、BoxBuilder isTab 標記不破任何既有 test） |
| L2 VR v14 | ✅ **byte-identical 第 25 連** | rebuild `tools/dist/visual_regression_pipeline.iife.js` → 跑全 42 fixture × 126 page、`visual_regression_v14_report.json`（除 `runAt`/`bundlePath`）與 HEAD **byte-identical**；failedPages=0。Strategy C 預設路徑無 caller 傳 `defaultTabStop` → `resolveTabStops` no-op、`isTab` 標記不改寬度 → 渲染 pixel 不變 |
| L3 spot check | ✅ | LineBreaker +約 60 行（option + makeLine 參數 + resolveTabStops/nextTabStop）、BoxBuilder +5、types +9、test +約 150 行 |
| L4 Odoo backend | **跳過（誠實聲明）** | 純前端 TS、未改 controller / model |
| L5 frontend bundle | **跳過此 sprint（誠實聲明）** | `canvas-editor-custom.umd.js` 不 rebuild —— 無 production caller 傳 `defaultTabStop`、rebuild 對 production 行為 0 effect（Sprint 157 同型）；Sprint 162 接線時一併 rebuild |

### 3.1 typecheck 狀態

`npx tsc --noEmit`：**4 個 pre-existing error**（BoxBuilder fieldType ×2 / FontMetrics opentype.js / SettingsParser position），與 Sprint 160 v2 結尾相同。Sprint 161 新增 `Glue.isTab` / `LineBreakOptions.defaultTabStop` / `resolveTabStops` / `nextTabStop` 皆**不引入新 error**。

### 3.2 紀律應用

| 紀律 | 應用 |
|---|---|
| #1 / #1.a 改 layout 跑全 VR | ✅ 改 LineBreaker/BoxBuilder/types → rebuild VR pipeline + 跑全 42 fixture、確認 byte-identical |
| #1.b spike 翻車必完整 revert | N/A — 未翻車（Strategy C 預設路徑 by construction 不變） |
| #14 / #14.a docs 即時同步 | ✅ 本 audit doc + progress_snapshot + roadmap + INDEX 同 sprint |
| #14.b commit 前 working tree 清零 | ✅ 第 0 步檢查 clean；VR report timestamp churn `git checkout` 還原；commit 收口 |
| #18 PR-size + scope-down | ✅ 3 production 檔 + 1 test 檔；center/right/decimal tab、firstLineIndent 交互、production 接線、bundle rebuild 全明確 defer |
| #18.a「依規畫書繼續」是 scope 限制詞 | ✅ tab stop 是 §1.3 既列工項、未發明新 scope |
| #22 mental model 不確定先 probe | ✅ 開工前 probe 揭「BoxBuilder 無 x 座標」mental model 錯誤、改在 makeLine 解析 |
| Strategy C（Sprint 139 模式） | ✅ layout 引擎接通 + 預設路徑 opt-out（不傳 `defaultTabStop` → no-op）、baseline byte-identical |

---

## 4. Result

### 4.1 檔案變動

```
M  static/src/core/layout/types.ts          (+9：Glue.isTab)
M  static/src/core/layout/BoxBuilder.ts     (+5：0x09 → isTab 標記)
M  static/src/core/layout/LineBreaker.ts    (+約60：LineBreakOptions.defaultTabStop + makeLine 參數
                                              + resolveTabStops + nextTabStop + 兩路徑透傳)
A  tests/unit/layout/LineBreaker.tabStop.test.ts  (11 新 test)
A  docs/sprint161_defaulttabstop_linebreaker_engine.md  (本 audit doc)
M  docs/progress_snapshot.md / autonomous_roadmap.md / INDEX.md
```

### 4.2 累積指標

| 指標 | Sprint 160 v2 結尾 | Sprint 161 結尾 | 變動 |
|---|---|---|---|
| vitest | 1342 passed + 1 skipped | **1353 passed + 1 skipped** | +11 |
| VR mean | 0.073191（byte-identical 第 24 連） | **0.073191（byte-identical 第 25 連）** | 0 |
| Odoo backend | 31 passed | 31 passed（未跑、無 backend 變動） | 0 |
| Phase 1 §5 checklist | 52/65 [x] | 52/65 [x]（本 sprint 為引擎、無 checkbox flip） | 0 |
| Sprint audit doc | sprint160_v2 | **sprint161** | +1 |

> 本 sprint 不打 `[ ]`→`[x]`：§1.3「tab stops」既已 `[x]`（指 parse）、defaultTabStop wire-up 無專屬 checkbox；待 Sprint 162 production 接線後於 §5 加註記。

---

## 5. 與規畫書 / Plan 關係

- 規畫書 §5 Phase 1 §1.3 tab stops + Phase 3 Layout Engine：本 sprint 把 tab 從「parse-only」推進到「layout 引擎可解析 tab stop」。
- snappy-nova plan Sprint 156-158 原主項「settings.defaultTabStop → Layout.LineBreaker」：被 158 P0 prep 推遲、159/160 走 docs follow-up、Sprint 161 正式落地引擎層。
- Strategy C（Sprint 139 numbering 模式）：layout 接通、預設路徑 opt-out，破 baseline 風險由設計消除（不傳 `defaultTabStop` → no-op）。

---

## 6. 後續

### 6.1 Sprint 162 候選 — production 接線 + VR opt-in 量測

| 工作 | 說明 |
|---|---|
| Paginator / TableLayout 傳 `defaultTabStop` | 從 `DocumentNode.settings.defaultTabStop`（Sprint 146 capture）→ `LineBreakOptions.defaultTabStop` |
| 預設值 fallback | settings 無 `defaultTabStop` 時用 OOXML 預設 720 twip = 36pt |
| frontend bundle rebuild | 接線後 production 行為真的變、需 rebuild `canvas-editor-custom.umd.js` |
| VR opt-in 重跑 | 9 個含 tab fixture 預期位移；走 Strategy C「VR pipeline 顯式傳 → 量測 delta、誠實聲明」（Sprint 139 模式）|
| §5 規畫書加註記 | §1.3 tab stops 加「Sprint 161-162 defaultTabStop wire-up」註記 |

### 6.2 hypothesis — 貪婪斷行近似的影響上界

貪婪斷行用未解析的 tab 寬（空白寬 ≈ 3-5pt）判斷 buf 是否超寬、解析後實際 tab 寬可達一個 `defaultTabStop`（≈36pt）。若一行尾端剛好有 tab 且該行接近行寬上限、解析後可能 overflow。

- **影響等級**：low（9 fixture 的 tab 皆為行首/短標籤後 leader tab、距行寬上限遠）
- **重現條件**：建構「長文字 + 行尾 tab + 行寬恰好」的合成 fixture
- **正解**：Sprint 162 VR opt-in 量測時觀察 9 fixture 是否有非預期 reflow；若有、考慮把 tab 解析提前到斷行迴圈內（較大改動、屆時評估）

### 6.3 三個 user 決策仍在桌上（不自行開工）

- Sprint 141 (B)：階段 C goldens 重生（換 VR baseline anchor、需 user GO）
- Sprint 142 (C)：Phase 5 fixture（6 子功能 42 fixture 0 覆蓋、需 user 提供 fixture + 優先序）
- Sprint 140 (A)：textAlignment / framePr wire-up（< pixelmatch resolution、DEFER user 手動 GO）

---

## File-level summary

```
M  static/src/core/layout/types.ts                          (+9)
M  static/src/core/layout/BoxBuilder.ts                      (+5)
M  static/src/core/layout/LineBreaker.ts                     (+約60)
A  tests/unit/layout/LineBreaker.tabStop.test.ts             (11 test)
A  docs/sprint161_defaulttabstop_linebreaker_engine.md       (本 audit doc)
M  docs/progress_snapshot.md / autonomous_roadmap.md / INDEX.md
```

**淨 production code 變動 = +約 74 行**（tab stop 解析引擎、Strategy C opt-in）、vitest 1342 → 1353、VR mean 0.073191 byte-identical 第 25 連、無 checkbox flip（引擎層、production 接線留 Sprint 162）。
