# Sprint 202 — Phase 7 大檔 perf baseline（synthetic 50p text-heavy fixture 生成）

**日期**：2026-05-24（週日）
**類型**：fixture 生成 + perf 量測 audit（無 production code 變動）
**規畫書對應**：§Phase 7 perf 殘項追蹤、Sprint 197 final audit「合成 50p fixture」中 ROI 殘項
**前置**：Sprint 201（warm-cache −25.3% / cold→warm 9.98×、瓶頸落在 render 93.4%、最大 fixture 6p / ~53ms warm）

---

## Hypothesis

Sprint 201 量測對既有 60 fixture（42 原 ChienYi + 18 Phase 5 synthetic）做 cold/warm
對照、揭示**最大 fixture 6 頁**——但 ChienYi 監造系統實際文件為 20-50 頁範圍、
缺一個「大檔」對應 perf 量測點。

Sprint 197 final audit ROI 排序把「合成 50p fixture + benchmark」標為中 ROI、預估
2 sprint（合成 + benchmark）。本 sprint 落地該 cluster 前半——用 Phase 6（Sprint
185-196）落地的 `OoxmlWriter` 程式化合成 ~50p text-heavy `.docx`、入 git、讓
`scripts/perf_baseline.mjs` 能量測 cold/warm 數據對 ChienYi 大檔場景的影響。

---

## 修法

### 1. fixture 生成（integration test）

新檔 `tests/integration/sprint202_synthetic_50p_generator.test.ts`（+187 行）：

- 程式化 build `DocumentNode`：125 章 × (1 heading + 10 body) = **1375 段落**
- Heading run `props: { b: true, size: 14 }`；body run 預設 props
- 5 種 deterministic lorem-zh 段落模板（避免單一字串重複 → cache 失真）
- 透過 `OoxmlWriter.write(doc)` 序列化、寫入
  `tests/fixtures/11_perf_synthetic_large/text_50p.docx`
- 3 test 驗：
  1. 同進程連續呼叫 `writer.write(doc)` bytes byte-identical
     （跨進程 ZIP local file header 含 mtime、不保證 byte-identical、所以
     第 3 test 不檢查 byte-identical 改檢結構）
  2. round-trip：write → bytes → parser → 段落數 1375 對齊
  3. 已入 git 的 fixture → parser 段落數 1375 對齊（regression guard）

### 2. 既有 baseline 與 VR pipeline 排除 11_perf_synthetic_large

- `tests/integration/04_ast_snapshot.test.ts`：`PHASE5_FIXTURE_DIRS` 加
  `'11_perf_synthetic_large'`
- `tests/integration/08_render_ops_trace.test.ts`：同上
- `tests/integration/09_page_count_baseline.test.ts`：同上
- `scripts/visual_regression_v14.mjs`：同上（無 golden、不入 VR 比對）

排除原因：本 fixture **僅為 perf 量測用**、無對應 golden、不應污染 ast snapshot /
render ops trace / page count baseline / VR pixelmatch；perf_baseline 不在
排除集內、可正常 pick up。

---

## Result — Sprint 202 cold vs warm 量測

`node scripts/perf_baseline.mjs --filter 11_perf_synthetic_large [--full-warm]`、
每份 3 runs 取 median；report JSON 為單一 fixture 結果、不覆寫 Sprint 201 全 60
fixture baseline。

| 模式 | parse | layout | preload | render | total | 每頁 |
|---|---|---|---|---|---|---|
| cold | 42.3 ms | 32.4 ms | 0.0 ms | 1502.8 ms | **1577.5 ms** | 32.2 ms/p |
| warm（Sprint 58 full-warm） | 0.0 | 0.0 | 0.0 | 758.3 | **758.3 ms** | 15.5 ms/p |

- **fixture**：`11_perf_synthetic_large/text_50p.docx`、9.7 KB、49 頁、1375 段落
- **cold→warm 加速**：1577.5 → 758.3 = **2.08×**（vs Sprint 201 原 42 fixture 9.98×）
- **階段消除**：parse / layout / preload 100% 消除 ✅、render 不可消除（layout cache 1/1 hit ✅）
- **render 占比**：cold 95.3% / warm 100%

---

## 為何加速倍率比 Sprint 201 低（2.08× vs 9.98×）

Sprint 201 原 42 fixture 加速 9.98×、本合成 49p 加速 2.08×；差距來自**文檔組成
比例不同**：

| 組成 | 42 fixture | 49p synthetic |
|---|---|---|
| parse + layout + preload cold | 大占比 | 小占比（4.8%）|
| render cold | 中占比 | **大占比（95.3%）** |
| 圖片數 | 多（04_with_image 有 2MB 圖）| 0 |
| 表格數 | 多（02/03 全 table）| 0 |
| 純文字段落數 | 中等 | 1375（**極端純文字**）|

純文字大檔的 render 階段佔比天然偏高（無圖片 preload、無表格 layout 複雜度）、
而 render 是**唯一不可被 cache 消除**的階段（layout cache 五連發 + image cache
都消不掉 canvas drawText）。故加速倍率對 fixture 組成敏感。

> **結論**：本 fixture 加速倍率較低**不代表 cache 架構退化**、而是揭示
> 「render-dominant 場景下、cache 五連發收益自然遞減」。

---

## 為何 cold parse / layout 為 42.3 / 32.4 ms（vs Sprint 201 原 42 fixture cold 6019 / 326）

Sprint 201 原 42 fixture cold parse = 6019 ms（42 份加總）、本 49p 合成 cold
parse = 42.3 ms（1 份）：

- 42 fixture 平均每份 cold parse ~143 ms（含 docx 內外掛 styles/numbering/
  headers/footers/comments/footnotes 等多 part 解析）
- 本合成 fixture **只有 6 個必要 part**（無 headers/footers/numbering 有內容）、
  AST 樹狀只有 1375 paragraphs/2750 runs、cold parse 42 ms 屬合理

換算每段落 cold parse cost = 42.3 / 1375 = 0.03 ms/段落、parse 階段在
LineBreaker 引擎前已被 lite-parse 短路、屬 fast path。

---

## 為何 render warm 758 ms vs Sprint 201 原 42 fixture render warm 1033 ms

| 指標 | 原 42 fixture (Sprint 201) | 49p synthetic (Sprint 202) |
|---|---|---|
| pages | 126 | 49 |
| warm render total | 1033.5 ms | 758.3 ms |
| **per-page warm render** | **8.2 ms/p** | **15.5 ms/p** |

49p synthetic 每頁 warm render 較慢（15.5 ms/p vs 8.2 ms/p）原因：

1. 純文字段落每頁字數密度高（~28 段落/頁、每段 25-50 字）→ canvas drawText
   呼叫次數更多
2. 原 42 fixture 含部分圖片頁面、image render 走 `drawImage` 一次性繪製、
   per-page 成本相對低
3. 表格頁面的 cell 邊框繪製為固定常數成本、字數密度低時 per-page 攤平更低

15.5 ms/p warm 仍**遠低於 60fps frame budget（16.7 ms）**、單頁切換體感無延遲。

---

## 三層 SOP

| 層 | 結果 | 數據 |
|---|---|---|
| L1 vitest | ✅ 全綠 | **1944 passed + 1 skipped**（+3 sprint202 + 18 Phase 8 平行 sprint）；單跑 sprint202 3/3 綠 |
| L2 VR v14 | ✅ **byte-identical 第 58 連** | 11_perf_synthetic_large 已加入 PHASE5_FIXTURE_DIRS 排除集、不入 VR pipeline；42 fixture VR 完全不受影響、結構性 byte-identical |
| L3 perf | ✅ baseline JSON 復原 | Sprint 202 量測為單 fixture 過渡量測、用後 `git checkout perf_baseline_report.json` 復原 Sprint 201 全 60 fixture baseline；本 sprint 數據已記錄於本 audit |

---

## 紀律

- **#1.b / Strategy C**：本 sprint 0 行 production code 變動（writer/parser/render 皆不改）；
  只新增測試 + fixture + 4 處排除集 + audit doc
- **#2 magic number**：fixture 規格用 `SYNTHETIC_CHAPTERS` / `PARAGRAPHS_PER_CHAPTER` /
  `EXPECTED_PARAGRAPH_COUNT` / `HEADING_FONT_SIZE_PT` 具名常數；無 magic
- **#14.b clean scope**：commit = sprint202 test + fixture docx + 4 處排除集 +
  audit doc + INDEX/snapshot；**不含**平行 agent 在 worktree 的其他孤兒檔
  （Phase 8 work 已另由平行 commit 入 git、跨 module pyc 不屬本 commit）
- **#18 scope-down**：
  - 純文字 fixture 不混圖片/表格——簡化解讀
  - 49p 接近目標 50p、不過度調參求精準（pre-flight 125 章 = 49p 已足夠）
  - benchmark harness 不在本 sprint scope（屬 Sprint 197 後半「benchmark」、若 ROI 仍存留 Sprint 203）
- **#21**：本 fixture 不入 VR 與 ast snapshot / page count baseline /
  render ops trace（無 golden、不應影響既有對稱性保證）

---

## Phase 7 完成度更新

- Sprint 201 後 ~90%
- **Sprint 202 大檔 perf 量測點建立、跨「6p ChienYi 真實 + 49p synthetic」雙
  量測 anchor**、Phase 7 perf 量測覆蓋面完整 → **~91%**
- 殘項：50p+ 真實 ChienYi fixture audit（合成已驗結構正確、真實 fixture 補
  edge case） / benchmark harness（自動化 cold/warm 量測 + alert thresholds）/
  OffscreenCanvas worker（Sprint 197 + 201 雙驗不建議、不取）/ Web Worker
  parse（同上）

---

## 後續

- Sprint 203 候選：建 benchmark harness 把 cold/warm 對比 + 階段瓶頸量化
  自動化跑入 CI（取 perf regression alarm threshold）；或繼續 audit 50p+
  真實 ChienYi 案件 fixture
- Phase 8 polish 與本 sprint 並行進行中（多選對齊輔助線 / Inspector 鍵盤
  導航 / orphan record 清理；Sprint G-Q 已成功推進、不在本 sprint scope）

---

## File-level summary

```
A  tests/integration/sprint202_synthetic_50p_generator.test.ts   +187 行
A  tests/fixtures/11_perf_synthetic_large/text_50p.docx          9.7 KB / 49p / 1375 段落
M  tests/integration/04_ast_snapshot.test.ts                     +'11_perf_synthetic_large' 排除
M  tests/integration/08_render_ops_trace.test.ts                 同上
M  tests/integration/09_page_count_baseline.test.ts              同上
M  scripts/visual_regression_v14.mjs                             同上
A  docs/sprint202_synthetic_50p_baseline.md                      本 audit
M  docs/INDEX.md                                                 +Sprint 202 entry
M  docs/progress_snapshot.md                                     Sprint 202 區塊 + Phase 7 ~90%→~91%
```

**淨 production code 變動 = 0 行**、49p text-heavy synthetic fixture 入庫、
cold 1577.5 ms / warm 758.3 ms（render 占 95.3%+）、cold→warm 2.08×（render-
dominant 場景天然加速倍率低）、cache 五連發 + LayoutCache 1/1 layout cache
hit 驗證健康、Phase 7 完成度 ~90%→~91%、VR byte-identical 第 58 連 unchanged。
