# Sprint 50-66 方法論回顧 — cache 五連發 + FontMetricsAdapter

**Sprint 120 落地 / 2026-05-17**
**範圍**：Sprint 50（perf baseline）→ Sprint 66（font_serve backend tests），17 sprint
**性質**：方法論 retro。和 [sprint50_72_retro.md](sprint50_72_retro.md)（23 sprint 橫向高層數字）互補，本文聚焦兩個 sprint cluster 的**做事方式**。

---

## 0. 為什麼需要這份 retro

`sprint50_72_retro.md` 已有橫向高層數字（VR mean、test 數、紀律生成軌跡）。但兩個 cluster 的**方法論**沒被提煉：

1. **Cache 五連發**（Sprint 51-58）：8 個 sprint 連續加 5 種 cache、VR mean **完全沒動**。為什麼還算成功？
2. **FontMetricsAdapter**（Sprint 60-65）：6 個 sprint 走 probe → negative → positive → delta → drift → promote、命中 -1.7%。這個 pipeline 為什麼有效？

Sprint 120 把這兩個 cluster 的方法論 explicit、供未來新 cluster 套用。

---

## 1. Cache 五連發方法論（Sprint 51-58）

### 1.1 連發清單

| Sprint | Cache 類型 | 層級 | 命中對象 | VR 變動 | Test 變動 |
|---|---|---|---|---|---|
| 51 | AstCache | L1 in-memory LRU | parse 結果 | 0 | +11 |
| 52 | IdbAstCache | L2 IndexedDB | parse 結果跨 page reload | 0 | +9 |
| 54 | ImageDecodeCache | L1 | `Image.decode()` 結果 | 0 | +10 |
| 56 | ImageBitmapIdbCache | L1+L2 | ImageBitmap blob | 0 | +12 |
| 57 | Memoize render fast path | （翻車 + revert）| — | 0 | +13 (revert 後保留) |
| 58 | LayoutCache | L1 | layout 引擎結果 | 0 | +19 |

5 sprint 加 5 種 cache（57 翻車不計）、+74 vitest、**VR mean 0 變動**。

### 1.2 為什麼還算成功

從表面看：「VR mean 沒動 = cache 沒有給 user 看見的改善」。**這是錯誤判讀**。Cache 的價值不在 VR mean，而在：

| 衡量維度 | Cache 前 | Cache 後 |
|---|---|---|
| Full-warm benchmark（Sprint 55） | 基線 | **7×** parse + render 加速 |
| Cross-page reload（Sprint 52） | 全 parse | **2.38×** 快（IDB hit）|
| Image-heavy fixture render | 每 page decode | **94.1%** ImageBitmap hit（warm）|
| Layout 重算次數 | 每 page 全算 | LayoutCache 命中 |

Cache 五連發是**為了 Phase 7 效能 + 為了 Sprint 60-65 字型 metric 改造提供 stable platform**。如果同時改 cache + metric、無法歸因。

### 1.3 方法論：「Stable platform → 高風險改造」

```
階段 1: 量測為先（Sprint 50）
  - parse 60.7% 是主要 latency
  - 不是「先優化」、是「先知道優化什麼」

階段 2: 連續加 cache、stage-by-stage 驗證（Sprint 51-58）
  - 每個 cache 加完跑全 vitest + per-fixture VR
  - 任何 cache 影響 VR mean → 一定是 bug、立刻 revert（Sprint 57 翻車模板）

階段 3: Stable platform 達成（Sprint 58）
  - VR mean、page count、fingerprint 全部 unchanged
  - 5 種 cache 全部命中、warm path 7×
  - 平台可以開始接「為了改善 VR」的改造
```

**為何不混做**：
- 改 cache 動 retain path、改 metric 動 measure path、兩者錯誤都可能影響 VR mean
- 同時動 → VR mean 變化無法歸因
- 分開動 → 確認 cache 不動 VR、確認 metric 才動 VR

### 1.4 Sprint 57 翻車的紀律意義

Sprint 57「aggressive memoize render fast path」翻車 → revert。但 revert 後 +13 test 保留、揭示了：

- **紀律 #1**：改 BrowserCanvasRenderContext / CanvasRenderer 後強制跑全 42-fixture VR
- **紀律 #2**：單元測試 spy 驗 API、VR 驗 pixels — 兩者都綠才算過

如果沒有 Sprint 57 翻車、紀律 #1/#2 不會被 explicit 化。**「翻車 sprint 也是有產出的 sprint」是 cache 五連發學到的 meta 教訓**。

### 1.5 對未來 cluster 的適用條件

Cache 五連發方法論適用於：

- ✅ 新 cluster 是「retain / measure 分離」、可以 stable platform 一段時間
- ✅ 新 cluster 期望「VR 不變」是正常結果（非預期改善）
- ✅ 新 cluster 是 6+ sprint 連續工作、需要中途量點 stability

不適用於：

- ❌ Bug fix sprint（單一 root cause、應該命中 VR）
- ❌ Phase exit report（多個 sub-feature 合報、stage 已切）

---

## 2. FontMetricsAdapter 方法論（Sprint 60-65）

### 2.1 連發清單

| Sprint | 動作 | 類型 | 結果 | VR 變動 |
|---|---|---|---|---|
| 60 | OffscreenCanvas probe | Probe | GREEN (puppeteer 4/4 features、postMessage ~5ms)| 0 |
| 61 | BrowserTextMetrics negative | Negative result | 揭示 goldens = LO render anchor、1.15em empirical 校準 | +0.0013（regression、屬意外揭示）|
| 62 | FontMetricsAdapter positive | Code change（改善）| opentype.js metric、IIFE bundle 47-sprint blocker 修復 | -0.0030（命中）|
| 63 | per-fixture delta probe | 純診斷 | 確認 -0.0030 不是 single-fixture lucky | 0（probe 不動）|
| 64 | baseline drift probe | 純診斷 | feature flag 切換對 page count / ops count 影響量 | 0 |
| 65 | Promote default | Mechanical commit | 1 行 flag 變動、新 VR baseline 0.0732 | 0（已知必然）|

6 sprint 命中 -1.7%。

### 2.2 方法論：「Probe → Negative → Positive → Delta → Drift → Promote」

```
階段 1: Probe（Sprint 60）
  目的: 收集事實、確認改造方向技術可行
  輸出: 「OffscreenCanvas 4/4 features GREEN、puppeteer 可行」
  不上線

階段 2: Negative（Sprint 61）
  目的: 嘗試 naive 路徑、看會不會壞掉
  輸出: BrowserTextMetrics 取代 → VR mean +0.0013、揭示 LO anchor 校準
  意外收穫: 47 個 sprint 沒人意識到 goldens 是 LO 渲染、Sprint 28 1.15em 是校準
  不上線

階段 3: Positive（Sprint 62）
  目的: 套用揭示後的真正改造（opentype.js + LO 系統 fallback fonts）
  輸出: VR mean -0.0030、命中
  順帶: 修 IIFE bundle 47-sprint blocker（nodeModuleStub、揭示紀律 #5）
  上線 (opt-in flag)

階段 4: Delta（Sprint 63）
  目的: 確認改善是 broad-based 不是 single-fixture lucky
  輸出: per-fixture delta 分布、紀律 #6 explicit
  不上線（已上線）

階段 5: Drift（Sprint 64）
  目的: 量化 feature flag 對 ops count / fingerprint 的二階影響
  輸出: drift 在 noise floor 內、可 promote
  不上線

階段 6: Promote（Sprint 65）
  目的: 1 行 mechanical commit 升 default、新 VR baseline 0.0732
  揭示紀律 #7: mechanical commit 是多 sprint 紀律的內化
```

### 2.3 為什麼 6 階段是必要的

剪掉任何一階段都有風險：

| 跳過 | 風險 |
|---|---|
| Probe（60）| 直接做 OffscreenCanvas 改造、撞 worker postMessage 才知不可行、浪費 1-2 sprint |
| Negative（61）| 直接做 positive、可能踩 BrowserTextMetrics naive 陷阱、規模性 VR regression |
| Positive（62）| — 這是核心 |
| Delta（63）| promote 後發現某 fixture lucky、整體 VR mean 反而劣化 |
| Drift（64）| ops count 暴漲、fingerprint 大量變動、下游 cache 失效 |
| Promote（65）| 一直 opt-in、新 baseline 沒寫死、未來改造易誤判 |

### 2.4 揭示鏈（meta 收益）

6 階段不只命中 -1.7%、揭示 4 條紀律 + 1 個 blocker：

- 紀律 #3（Sprint 60）：高風險改造前先 probe
- 紀律 #4（Sprint 61）：負面結果 sprint 仍有結構價值、揭示隱性 assumption
- 紀律 #5（Sprint 62）：vitest 通過不保證 IIFE bundle 同 code 也 work
- 紀律 #6（Sprint 63）：promote default 前先做 per-fixture delta
- 紀律 #7（Sprint 65）：mechanical commit 是多 sprint 紀律的內化
- Blocker：47-sprint IIFE bundle nodeModuleStub（Sprint 14 埋、Sprint 62 修）

**單一 sprint 的 ROI 算進 inflection 才公平**。Sprint 62 的 -0.0030 是 6 sprint 累積 ROI。

### 2.5 對未來 cluster 的適用條件

Probe → Negative → Positive → Delta → Drift → Promote 適用於：

- ✅ 高風險改造（會動 VR mean、影響 cache、改 IIFE bundle）
- ✅ 預期改善但結果未知
- ✅ 至少有一個「以為對、其實不對」的隱性 assumption（probe 找）

不適用於：

- ❌ Trivial bug fix（不需 probe）
- ❌ Pure docs / catch-up sprint（無 measure 對象）

---

## 3. 兩個 cluster 之間的互動

Cache 五連發（Sprint 51-58）→ FontMetricsAdapter（Sprint 60-65）**不是無關**：

- Sprint 51-58 把 VR mean 鎖在 0.0749、stable platform 達成
- Sprint 61 negative 看到 +0.0013 regression → **平台 stable 才能歸因為 metric 而非 cache 漂移**
- Sprint 62 positive 命中 -0.0030 → **同樣依賴 platform stable 才能確認**

**沒有 Sprint 51-58 stable platform、Sprint 60-65 probe → promote 鏈無法 explicit 驗證、可能在 noise 中誤判**。

---

## 4. 方法論套用到 Sprint 113-118

Sprint 113-118 場景不同（純 docs 多、無 VR 變動）、但 cache 五連發 / FontMetricsAdapter 的部分方法論仍適用：

| 方法論元素 | Sprint 113-118 對應 |
|---|---|
| Stable platform → 改造 | Sprint 113 autonomous_roadmap 建立 = stable scope platform → 後續 sprint 才能 enforce 紀律 #18 scope drift |
| Probe → Negative → Positive | Sprint 115 廣域 audit（probe）→ 揭示 null byte critical（negative）→ Sprint 116 fix（positive）|
| Mechanical commit 紀律內化 | Sprint 117 cross-company 決策落 ADR-021、Sprint 119 紀律 #20 候選跨 2 sprint 驗證 |

**結論**：方法論層級是跨 cluster 通用的。具體機制（cache 類型 / metric anchor）是 cluster-specific。

---

## 5. Sprint 50-66 紀律生成總圖（萃取版）

```
量測為先 ──→ Stable platform ──→ Probe → Negative → Positive → Delta → Drift → Promote
   (50)        (51-58)              (60)    (61)       (62)       (63)    (64)    (65)
                                                                                      │
                                                                                      ↓
                                                                            Catch-up / 廣域應用
                                                                                  (66-72+)
```

紀律編號對映：

- 階段 1 量測為先：揭示 紀律 #3 種子（probe 概念）
- 階段 2 Stable platform：揭示 紀律 #1 / #2（Sprint 57 翻車）
- 階段 3 Probe：紀律 #3 explicit
- 階段 4 Negative：紀律 #4 explicit
- 階段 5 Positive：紀律 #5 explicit（+ IIFE blocker 修）
- 階段 6 Delta：紀律 #6 explicit
- 階段 7 Promote：紀律 #7 explicit

7 條紀律從 17 sprint 萃取 = 平均 ~2.4 sprint / 條（比 Sprint 50-72 全段的 1.77 sprint / 條稍慢、因 cache 五連發 sprint 多但紀律密度低）。

---

## 6. 未來 cluster 套用 checklist

開新 cluster 時、用本 retro 對齊方法論：

- [ ] 有沒有先量測現況？（避免 Sprint 50 之前式的「優化想像」）
- [ ] 改造前平台是否 stable？（VR / fingerprint / page count 是否 baseline 全綠）
- [ ] 高風險改造前是否有 probe sprint？
- [ ] 是否預留 negative result sprint 的可能？（不視為失敗）
- [ ] Positive 後是否 delta + drift 驗證？
- [ ] 結束時是否 1 行 mechanical commit promote default？
- [ ] Audit doc 是否揭示新紀律候選？

7 個 checkbox 全綠 = 跑完一個健康 cluster。

---

## 7. 三層 SOP

| 層 | 結果 |
|---|---|
| L1 Vitest | **跳過**（純 docs、0 行 source code 變動）|
| L2 VR v14 | **跳過**（純 docs、0 行 pipeline 變動）|
| L3 Spot check | ✅ 17 個 sprint audit doc 名稱對齊（Sprint 51-58 + 60-65 + 66）/ retro 圖表數據對齊 sprint50_72_retro.md §4.1 / §4.2 |
| L4 Odoo backend | **跳過**（純 docs）|

---

## 8. 紀律候選驗證進展（Sprint 120）

紀律 #20 候選「集中索引文件 §0 段」跨 sprint 驗證：

- Sprint 118：ADR §0 索引（首次應用）
- Sprint 119：glossary §0 索引（第二次應用）
- Sprint 120：本 retro 沒有 §0 索引（本檔規模 < 10 entry 表，符合「超過 10 entry」門檻、不必加）

→ **跨 3 sprint 驗證不在 Sprint 120 完成**。紀律 #20 仍在候選、需待 CONTRIBUTING.md 補 §0 索引才完成第 3 sprint 驗證。

---

## 9. 一句話結論

**Sprint 50-66 17 sprint 從 perf baseline → cache 五連發 stable platform → FontMetricsAdapter 6 階段命中 -1.7% → catch-up 收尾**。方法論：**Stable platform → Probe → Negative → Positive → Delta → Drift → Promote**。7 條紀律 explicit 化是 meta 收益、單一 sprint ROI 應算進整個 inflection chain 才公平。

---

## File-level summary

```
A  addons/dobtor_doc_editor/docs/sprint50_66_retro.md  (本 retro doc)
M  addons/dobtor_doc_editor/docs/autonomous_roadmap.md  (階段 A 行 7 ⏳→✅ + 進度表 Sprint 120 + 階段 A 完成標記)
M  addons/dobtor_doc_editor/dobtor_doc_editor_高保真匯入開發規劃.md  (標頭最後更新)
```

無 code / model / view / ACL / rule / test 變動。純 docs sprint。
