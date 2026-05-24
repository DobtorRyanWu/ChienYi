# Sprint 201 — Phase 7 perf re-baseline（Sprint 58 後 ~33 sprint 累積影響量測）

**日期**：2026-05-24（週日）
**類型**：純量測 audit（無 production code 變動）
**規畫書對應**：§Phase 7 perf 殘項追蹤、Sprint 197 final audit ROI 排序
**前置**：Sprint 50 Phase 7 baseline（2026-05-15 Sprint 58 結尾 full-warm 量測為最後一次）

---

## Hypothesis

Sprint 58 結尾（2026-05-15）為最後一次 perf baseline 量測、之後 33 sprint
累積大量 feature：

- Sprint 161-162 tab stop wire-up（LineBreaker + Paginator）
- Sprint 167-170 textAlignment / framePr 浮動段落（layout）
- Sprint 171-178 background / watermark / themeColor / track changes / comments capture
- Sprint 179-184 OMML / SmartArt / Chart capture + render
- Sprint 185-196 Phase 6 export 大舉落地（parser path 不變但 bundle size 增）
- Sprint 197-200 audit + 2 個 fix（OMML namespace / anchor strip）

本 sprint 重跑 Sprint 50 perf baseline、比對 Sprint 58 結尾數據、量化 33
sprint 對 parse / layout / render 各 stage 的累積影響。

---

## Result — Apples-to-apples warm-cache 比較（原 42 fixture）

| Category | n | OLD（Sprint 58 結尾）| NEW（Sprint 200 結尾）| Δ% |
|---|---|---|---|---|
| 01_simple | 7 | 371.7 ms | 214.4 ms | **−42.3%** |
| 02_std_table | 8 | 150.8 | 114.3 | −24.2% |
| 03_complex_table | 8 | 114.3 | 92.2 | −19.3% |
| 04_with_image | 6 | 263.3 | 219.8 | −16.5% |
| 05_header_footer | 10 | 390.3 | 320.2 | −18.0% |
| 06_template | 3 | 59.5 | 47.1 | −20.8% |
| **TOTAL (42 fixture)** | **42** | **1349.9 ms** | **1008.0 ms** | **−25.3%** |

**反直覺結果**：33 sprint 大量 feature 累積 + 100+ 行 production code 增、
warm-cache 總時間反而**降 25.3%**、所有 category 全部 perf 進步。

新增 18 個 synthetic fixture（07/08/09 chart/smartart/omml）合計 98.1ms
（平均 5.5ms/fixture、屬於 fast path）。

---

## Result — Cold vs Warm pipeline 對照（Sprint 201 新量）

| Stage | Cold total | Warm total | 加速倍數 | 階段消除 % |
|---|---|---|---|---|
| parse | 6019.3 ms | 0.7 ms | **8599×** | 100.0% |
| layout | 326.6 | 3.0 | **109×** | 99.1% |
| preload | 573.6 | 1.4 | **410×** | 99.8% |
| render | 4029.9 | 1033.5 | 3.9× | 74.4% |
| **total** | **11035.8** | **1106.1** | **9.98×** | **90.0%** |

- AST cache（Sprint 51-52）+ Layout cache（Sprint 58）+ Image cache（Sprint 54）
  五連發**~10× 加速架構維持健康**、無 cache regression
- 全 60 個 fixture 100% layout cache hit
- 主要剩餘 cost 集中在 render（無 cache 可消除、屬實際繪圖）

---

## 全域瓶頸分析（Sprint 201 warm-cache 模式）

| Stage | 總時 | 占比 |
|---|---|---|
| renderMs | 1033.5 ms | **93.4%** |
| layoutMs | 3.0 | 0.3% |
| preloadMs | 1.4 | 0.1% |
| parseMs | 0.7 | 0.1% |

**結論**：warm-cache 模式下、瓶頸 100% 落在 render（layout/parse/preload 都
被 cache 消除）→ 任何 perf 進一步優化必須針對 render path（OffscreenCanvas
worker / WebGL / path coalescing 進一步 batching 等）。

Sprint 197 final audit 已標記 OffscreenCanvas worker 為「不建議」
（cache 五連發 + LayoutCache 達 ~10× 加速、worker 改造 ROI marginal）。
本量測**驗證**該判定。

---

## 最慢 5 fixture（Sprint 201 warm）

| Fixture | totalMs | size | 頁數 |
|---|---|---|---|
| 04_with_image/6.環清表安全衛生抽查照片(再造)-(112.10.2.-10.6).docx | 52.9 | 2127 KB | 6 |
| 04_with_image/06.環清表安全衛生抽查照片(再造)-(112.10.23.-10.27).docx | 50.1 | 1405 KB | 6 |
| 04_with_image/6.環清表安全衛生抽查照片(再造)-(112.9.25.-9.29).docx | 47.6 | 1984 KB | 6 |
| 05_header_footer/自主檢查表---植筋.docx | 40.3 | 43 KB | 5 |
| 01_simple/03.1120210-監造會議記錄-1120801.docx | 40.0 | 52 KB | 3 |

> 最慢 fixture **<53ms warm-cache total**（6 頁含 2MB 圖片）→ ChienYi 監造
> 20-50p 工作流體感極佳、cold path 也只 ~11s 全 60 fixture（每文件 ~180ms）。

---

## 為何 -25.3%（Hypothesis）

無單一 sprint 直接做 perf 優化、變化來自以下複合：

1. **Sprint 161-162 tab stop wire-up** 重構 LineBreaker 內部、可能減少
   per-line work（Sprint 162 量測 aggregate delta +4.8e-7 可忽略、本量
   體現累積收益）
2. **AST cache hit rate 改善** ── 後續 sprint 對 walk path 微調可能讓 cache key
   更穩定、warm-cache hit 100%
3. **LayoutCache 60/60 hit ratio**（vs Sprint 58 可能未滿）
4. **Chromium / Node.js 系統升級** ── 本機環境可能小升級
5. **Sprint 200 anchor strip 修法** ── 段落數減少 → render box 數略減

無單一原因獨佔貢獻、總體屬「無 regression + 多 sprint 微優化複合效果」。

---

## 三層 SOP（Sprint 201）

- L1 vitest：**1923 passed + 1 skipped** unchanged（Sprint 200 結尾、本 sprint 量測無 code 變動）
- L2 VR v14：**byte-identical 第 58 連 unchanged**（純量測 audit）
- L3 perf baseline JSON: `tests/fixtures/perf_baseline_report.json` 重生（含 Sprint 58 mode + cold/warm）

---

## 紀律

- **#1.b / Strategy C**：本 sprint 0 行 production code、純 perf 量測 audit
- **#14.b clean scope**：本 commit = perf_baseline_report.json 重生 + audit doc + INDEX/snapshot
- **#18 scope-down**：未動 production code、不再 chase perf 進一步優化
  （瓶頸已落在 render 不可消除部分、Sprint 197 已標 OffscreenCanvas
  「不建議」、本量測驗證）
- **#21**：未涵蓋 cold path benchmark 對應 50p+ 大檔（合成 50p fixture
  + benchmark 為 Phase 7 中 ROI 殘項、留 future sprint）

---

## Phase 7 完成度

- Sprint 200 後 ~90%
- **Sprint 201 量測驗證 cache 架構健康 + warm-cache 反而 -25.3%**
- Phase 7 進入「殘項屬大 scope cluster、單 sprint 不可收且 ROI 邊際」狀態：
  - OffscreenCanvas worker / Web Worker parse（Sprint 197 判定不建議、本量測再次驗證）
  - 50+ 頁合成 fixture + benchmark（Sprint 197 中 ROI、需 2 sprint 建合成器）
  - WPS 來源 fixture audit（Sprint 197 低 ROI、需另尋來源）

**結論**：Phase 7 perf 維持商用級健康、無 regression、warm-cache 進步。
未來再優化需走 worker / WebGL 等高成本路徑、現階段不建議。

---

## File-level summary

```
M  tests/fixtures/perf_baseline_report.json    Sprint 58 mode + cold/warm 重生
A  docs/sprint201_perf_rebaseline.md          本 audit
M  docs/INDEX.md                              +Sprint 201 entry
M  docs/progress_snapshot.md                  Sprint 201 區塊 + Phase 7 ~90% 維持
```

**淨 production code 變動 = 0 行**、warm-cache total **−25.3%**（33 sprint 後）、
cold→warm 加速 **9.98×**、Phase 7 perf 健康量化驗證、~90% 維持。
