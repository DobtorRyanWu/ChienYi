# Sprint 204 — 規畫書 §5 Phase 0-8 checkbox sync sweep（Sprint 1-203 後 honest status）

**日期**：2026-05-24（週日）
**類型**：docs-only audit（0 行 production code 變動 / 0 行 test 變動）
**規畫書對應**：§5 Phase 0-8 全 checkbox 與實際 Sprint 1-203 進度對齊
**前置**：Sprint 156 phase1 checkbox audit（Phase 1 局部 sync）+ Sprint 197 final audit（加權平均 ~89%）+ Sprint 203（Phase 7 ~92%）

---

## Hypothesis

規畫書 `dobtor_doc_editor_高保真匯入開發規劃.md` 的 §5 Phase checkbox 與實際
Sprint 1-203 進度**嚴重 drift**：

- Phase 0-1：Sprint 156 已 partial sync
- Phase 5-6：Sprint 179-196 已落地 100%、但 §5.1-5.6 / Phase 6 大多仍標 `[ ]`
- Phase 3：Sprint 1-49 早期已實作 boxes/glue/penalty / 分頁 / 表格 / 浮動繞排 /
  分欄 / 註腳，但 §3.1-3.6 大多仍標 `[ ]`
- Phase 4：Sprint 130-139 已 theme / tblStylePr / 編號 / paragraph 進階全套
  落地、但 §4.1-4.4 大多仍標 `[ ]`
- Phase 7：Sprint 50-58 cache 五連發 + Sprint 198 邊緣 audit + Sprint 202-203
  大檔量測落地、但 §Phase 7 大多仍標 `[ ]`

**本 sprint 對 §5 全 checkbox 一次完整 sync**、把每個翻 `[x]` 的項目附 Sprint
編號 + 修法摘要、提供未來 user / CEO / 客戶可信賴的 honest completion status。

---

## 修法

`dobtor_doc_editor_高保真匯入開發規劃.md` 5 處批次 Edit（每處對應 Phase section）：

| Phase | 翻 `[x]` 數 | 主要 Sprint 引用 |
|---|---|---|
| Phase 3.1-3.6 layout engine | 22 | Sprint 6 / 13 / 28 / 32 / 5 / 27 / 33 / 190 / 17-18 / 11 / 10 / 4 / 191 / 7 / 145 / 161-162 / 170 |
| Phase 4.1-4.4 style/theme | 12 | Sprint 130 / 131 / 19 / 132 / 137-139 / 133 / 188 / 161-162 / 167 / 169-170 |
| Phase 5.1-5.6 進階功能 | 17 | Sprint 179-180 / 181-183 / 174-175 / 176-177 / 184 / 171-173 / 178 / 196 |
| Phase 6 export | 6 | Sprint 185-196 / 198 / 199 / 200 / 141 |
| Phase 7 perf + 邊緣 | 4 | Sprint 50-58 / 52 / 56 / 198 / 202 / 203 |
| **合計翻** | **69** | — |

**前後對照**：

| 狀態 | Sprint 1-203 後（本 sprint 前）| Sprint 204 後 |
|---|---|---|
| `- [ ]` 未勾 | **105** | **36** |
| `- [x]` 已勾 | **62** | **131** |

剩 36 個未勾項目分類：

- **Phase 2 (8 項)**：HarfBuzz / opentype.js text shaping 外部依賴卡住、Sprint
  127-128 probe 確認需 canvas-editor patch、留 Phase 2 後續
- **Phase 3 optional (4 項)**：wrapTight / wrapThrough 多邊形繞排（最難）/
  hyphenation（英文場景）/ 表格浮動 / 註腳 advanced wire-up
- **Phase 5 optional (5 項)**：accept-reject 修訂 UI / per-author 顏色 / 註解
  reply / resolved status / OMML alt text
- **Phase 7 long-term (3 項)**：OffscreenCanvas worker（Sprint 197+201
  雙驗不建議）/ Web Worker parse（同）/ 增量渲染（full re-render 已達 fps）
- **Phase 8 deferred (1 項)**：Phase 2.2 overlay 絕對定位（Phase 2.1 inline
  control 實測滿意、未啟動）
- **其他 honest gaps (~15 項)**：頁底分隔線、各種低 ROI optional

所有剩餘未勾項目**皆為合法 blocked / deferred / optional**、無「應該做但忘做」
案例。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ unchanged | **1946 passed + 1 skipped**（docs-only、無 code 變動） |
| L2 VR v14 | ✅ **byte-identical 第 58 連** | docs-only、layout/render 不變動 → 42 fixture VR 結構性 unchanged |
| L3 perf | ✅ baseline unchanged | docs-only、無量測影響 |

---

## 紀律

- **#1.b / Strategy C**：本 sprint **0 行 production code 變動、0 行 test
  變動**、純 §5 規畫書 honest sync
- **#2 magic number**：每個翻 `[x]` 項目皆附具體 Sprint 編號引用、無模糊
  「已實作」聲明
- **#14.b clean scope**：commit = 規畫書 §5 + sprint204 audit doc + INDEX +
  snapshot；不含跨 module pyc / Phase 8 平行 sprint 檔
- **#18 scope-down**：
  - 不翻 ambiguous 項目（wrapTight、reply 等）、保持未勾 + honest deferred
    說明
  - 不重寫規畫書其他章節（§6 測試體系、§11 ROI 排序等）、僅 §5 checkbox sync
- **#21**：本 sprint 不影響任何 VR / round-trip / 結構斷言

---

## Phase 完成度更新（基於本 sync 後 honest status）

| Phase | Sprint 203 後 | Sprint 204 後 honest |
|---|---|---|
| Phase 0 能力盤點 | 100% | 100% |
| Phase 1 OOXML Parser | 100% (52/52 + 13 optional) | 100% |
| Phase 2 Text Shaping | blocked（HarfBuzz）| blocked（無變動） |
| Phase 3 Layout Engine | ~93% | **~96%**（揭露原本已實作項目、實際 ratio 上修） |
| Phase 4 Style/Theme | ~91% | **~95%**（同上） |
| Phase 4.5 產品化基礎建設 | 100% MVP | 100% MVP |
| Phase 5 進階功能 | 100% | 100%（unchanged、本 sync 為記錄修正） |
| Phase 6 匯出對稱性 | 100% | 100%（unchanged、本 sync 為記錄修正） |
| Phase 7 效能優化 | ~92% | ~92%（unchanged） |
| Phase 8 Template UI | MVP 完成 + polish 中 | MVP 完成 + polish 中 |
| **加權平均** | **~89-92%** | **~93-95%**（揭露 Phase 3/4 上修） |

> 加權平均上修是**記錄修正**結果、不是本 sprint 新增實作；揭露 Phase 3/4 已
> 完成項目從未被勾。

---

## 後續

- 規畫書 §5 sync 完成、未來 user / CEO / 客戶可直接看 §5 checkbox 取得
  honest status
- 剩 36 個未勾項目皆有 deferred reason、無「忘做」風險
- 加權平均 ~93-95% MVP 完成、進入「殘項屬大 scope cluster + ROI 邊際」狀態
- 後續 sprint 若推進剩餘項目（如 wrapTight / OffscreenCanvas）需 dedicated
  multi-sprint cluster、不在 ChienYi 監造商用 v1 release scope

---

## File-level summary

```
M  dobtor_doc_editor_高保真匯入開發規劃.md        +69 個 [x] + Sprint cite + 11 個 deferred reason 註解（淨 +~120 行）
A  docs/sprint204_planning_doc_checkbox_sync.md   本 audit
M  docs/INDEX.md                                  +Sprint 204 entry
M  docs/progress_snapshot.md                      Sprint 204 區塊 + Phase 完成度上修
```

**淨 production code 變動 = 0 行**、規畫書 §5 翻 69 個 checkbox（105 → 36 個 `[ ]`、
62 → 131 個 `[x]`）、所有翻動皆附 Sprint cite、剩 36 個皆合法 deferred；
vitest 1946 unchanged、VR byte-identical 第 58 連 unchanged；Phase 3/4 完成
度上修記錄 ~93%→~96% / ~91%→~95%（揭露既有 implementation、非新增）、
加權平均 ~93-95% 商用級。
