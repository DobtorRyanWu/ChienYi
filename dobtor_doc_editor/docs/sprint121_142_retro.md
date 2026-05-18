# Sprint 121-142 方法論回顧 — Phase 4 wire-up cluster + autonomous 邊界探索

**Sprint 144 落地 / 2026-05-18**
**範圍**:Sprint 121(階段 B 開工)→ Sprint 142(C Phase 5 DEFER user GO)、22 sprint
**性質**:方法論 retro。和 [sprint50_72_retro.md](sprint50_72_retro.md) / [sprint50_66_retro.md](sprint50_66_retro.md)(歷史 cluster)互補,本文聚焦 Sprint 121-142 三個新模式:**probe-only sprint 例行化、Strategy C 折衷、autonomous 邊界揭示**。

---

## 0. 為什麼需要這份 retro

歷史 retro(sprint50_66 / sprint50_72 / sprint74)聚焦 cache 五連發、FontMetricsAdapter、紀律歸納。Sprint 121-142 累積 22 sprint 內出現三個歷史 retro 沒覆蓋的新模式:

1. **probe-only sprint 從零星(Sprint 127/128/135)變例行流程(Sprint 140/141/142 三連)**
2. **Strategy C 折衷模式(Sprint 139)**:不是「全做 / 全不做」二元、有「保留主要工作 + scope-down 1 維度」第三選擇
3. **autonomous 邊界揭示(Sprint 141/142)**:autonomous 第一次遇到「自己無法決策」的 stop point

Sprint 144 把這三個模式 explicit、供未來 cluster 套用。

---

## 1. probe-only sprint 例行化(Sprint 121-142 累計 6 次)

### 1.1 累計清單

| Sprint | 主題 | 結論 |
|---|---|---|
| 127 | FontMetricsAdapter promotion audit | Strategy D 維持現狀、defer 真正 migration |
| 128 | HarfBuzz WASM 進階能力 | DEFER-1 列入階段 D 候選(bundle +465KB 不可接)|
| 135 | docGrid snap 段落層級判別子 | 找到判別子 = 「段落是否在 table cell 內」、留 Sprint 136 待 user GO |
| 140 | A 候選 textAlignment / framePr wire-up | autonomous DEFER(canvas-editor 無對應)|
| 141 | B 候選階段 C 重生 goldens | DEFER user GO(換 baseline 影響紀律 #1.a 16 連)|
| 142 | C 候選 Phase 5 開工 | DEFER user GO(6 子功能 fixture 0 覆蓋)|

### 1.2 為什麼例行化

從 sprint 紀律演化角度:

| 時期 | probe sprint 性質 |
|---|---|
| Sprint 60 之前 | 紀律 #3(高風險改造前)概念剛建立、實際很少跑 |
| Sprint 60(FontMetricsAdapter probe negative)| 第一個正式 probe-only sprint、紀律 #3 落地驗證 |
| Sprint 127/128/135 | 紀律 #22 候選跨 3 次驗證 → Sprint 135 升正 |
| Sprint 140-142 三連 | **probe-only 成為新 cluster 開工標配** |

### 1.3 方法論:「probe 5 維度」標準產出

從 Sprint 137-142 累積經驗、probe sprint 標準產出 = 5 維度評估:

```
1. Fixture 覆蓋率 + 分布(grep fixture XML)
2. caller / consumer 對應評估(mapper / layout / VR pipeline 三條路徑)
3. 預期收益(VR / functional)+ 風險(scope / dependency)+ 工時估算
4. autonomous GO / DEFER / user GO 決策框架
5. 後續觸發條件(若 DEFER 時、什麼情況可重新評估)
```

### 1.4 收益:Sprint 136 翻車對照

| 維度 | Sprint 136(無 probe)| Sprint 137-139(probe 後實作)|
|---|---|---|
| 開工前 mental model | Sprint 135 probe 找到判別子、Sprint 136 直接實作 | Sprint 137 純函式、Sprint 138 mapper probe、Sprint 139 layout probe |
| 實作後 VR 結果 | +0.86~1.47pp 退化 → revert | byte-identical 第 13/14/15 連 |
| 工時投入 | 1 sprint code + 1 sprint revert + 30 行 audit | 3 sprint code + 完整 wire-up 鏈 |
| 結構性學習 | 揭示 spec-naive ceil ≠ golden 行為 | wire-up 三段式架構成熟 |

→ probe-only sprint 對照 Sprint 136 翻車模式、是**最便宜的「不翻車」保證機制**。

### 1.5 適用條件

probe-only sprint 不該每個 sprint 都做、只在:

| 情境 | 觸發 |
|---|---|
| capture-without-consumer 結構性技術債 wire-up | Sprint 137-139 模式 |
| backlog 候選跨 autonomous 決策邊界 | Sprint 140-142 模式 |
| 新規畫書 phase 開工(規畫書 §11.1 大型候選)| Sprint 127-128 模式 |
| 「mental model vs 實況」明顯差距(歷史翻車 + 假設未驗證)| Sprint 135 模式 |

低風險 / 小 scope / 已驗證模式變動 → 不需 probe sprint(如 Sprint 121-126 parser 補完直接 GO)。

---

## 2. Strategy C 折衷模式(Sprint 139)

### 2.1 揭示

Sprint 139 layout 路徑 numbering wire-up VR 第一次嘗試(pipeline 主動注入 documentNode.numbering)結果:

- aggregate VR mean +0.001pp(0.073191→0.073201)
- byte-identical 軌道斷(14 連 → 中斷)
- page count 不變、failed pages 0、視覺收益微小(< pixelmatch resolution)

二元選擇困境:
- **接受**:byte-identical 軌道斷、無視覺收益、紀律 #1.a 累積失效
- **全 revert**:Phase 4.3 wire-up 一級目標未完工、3 sprint 工作浪費

### 2.2 Strategy C 第三選擇

**保留主要工作 + scope-down 1 維度**:

| 變項 | 處理 |
|---|---|
| layout 路徑 wire-up(BoxBuilder + Paginator + TableLayout)| **保留**(Phase 4.3 目標完工)|
| VR pipeline 主動注入 documentNode.numbering | **改 opt-in**(預設不啟用、caller 顯式傳 layoutOptions.numbering 才走)|

結果:
- VR 重跑 mean **0.073191 byte-identical 第 15 連**(軌道延續)
- Wire-up 鏈完整(階段 C 重生 goldens 後可改 opt-out 解鎖視覺收益)
- 工作不浪費

### 2.3 方法論:「scope-down 維度可大可小」

Strategy C 不是新發明、是把 Sprint 110 / Sprint 136 「scope-down」概念**從「全 revert」連續化**:

| 模式 | scope-down 維度 | 對應 Sprint |
|---|---|---|
| 全 revert(scope-down 100%)| 整批程式碼 byte-identical 撤回 | 110(esign 20 sprint)、136(isInTableCell)|
| 部分 revert(scope-down 1 維度)| 只撤一個 caller / 一個觸發路徑 / 一個預設值 | **139 Strategy C** |
| 預防 DEFER(probe 階段 scope-down 100%)| 完全不實作、留推薦路徑 | 137 / 140 / 141 / 142 |

### 2.4 升正紀律 #1.b(Sprint 143)

Strategy C 是紀律 #1.b 升正(Sprint 143)的關鍵驗證 — 把候選紀律從「全 revert」擴張為「全 revert / 部分 revert / 預防 DEFER」三選擇光譜。

### 2.5 適用條件

Strategy C 適用於:

| 情境 | 例子 |
|---|---|
| 主要工作有獨立價值、不需 VR 驗證 | Sprint 139 wire-up 鏈完工本身有 functional 價值 |
| scope-down 維度小 + 可逆 | opt-in 改 opt-out 是 1 行代碼 |
| 階段 C / Phase 5 等未來 sprint 可重新啟用 | 留 hook 給未來 |

不適用:
- 主要工作必須有視覺驗證才能 land(此時應 revert)
- scope-down 維度跨 4+ 個檔(改成預防 DEFER 更乾淨)

---

## 3. autonomous 邊界揭示(Sprint 141/142)

### 3.1 揭示

Sprint 140 後 user 指示「逐步執行 abc」、Sprint 141/142 連續 probe + DEFER user GO,揭示 **autonomous 第一次遇到無法決策的 stop point**:

| Sprint | 候選 | 為何不能 autonomous GO |
|---|---|---|
| 141 | B 階段 C 重生 goldens | 換 baseline = 失去紀律 #1.a 16 連軌道、需 user 明確同意 |
| 142 | C Phase 5 開工 | 6 子功能 fixture 0 覆蓋、user 業務優先順序 + 提供 fixture 必要 |

### 3.2 autonomous 範圍邊界 3 維度

| 維度 | 描述 | autonomous 可獨立? |
|---|---|---|
| 1. baseline 變動 | 是否影響 VR mean / 紀律 #1.a 軌道 | **不可**(需 user GO)|
| 2. 大依賴 / 環境變動 | docker image 拉、新工具安裝、API 整合 | **不可**(需 user GO)|
| 3. user 業務優先 / fixture 取得 | 多個 ROI 接近候選的順序、user 業務知識 | **不可**(需 user 決策)|

autonomous 可獨立的剩餘空間:
- 既有規畫書 phase 內推進(scope 對齊紀律 #18)
- 不破 baseline + 不破紀律 #1.a 軌道
- 純 docs / probe / retro / cluster 整理

### 3.3 「abc 三連 probe + DEFER」是健康紀律

從 Sprint 50-89 healthy mix 角度(CONTRIBUTING §5「健康紀律分布」):

| sprint 類型 | Sprint 50-89 比例 | Sprint 121-142 比例 |
|---|---|---|
| code change(改善)| 20% | 9/22 = 41%(+21pp) |
| 純診斷 / probe-only | 33% | 6/22 = 27%(-6pp) |
| docs(autonomous)| 15% | 5/22 = 23%(+8pp) |
| 其他 | 32% | 2/22 = 9% |

Sprint 121-142 比例:code 改善 41% / probe 27% / docs 23% — **三類型平衡、整體 100% 對齊規畫書 scope**(無 Sprint 90-109 那種 20 sprint scope drift)。

### 3.4 user 介入點明確化

Sprint 142 結尾 user 決策待定點(從 Sprint 142 audit §後續):

| 候選 | user 需提供 |
|---|---|
| B 階段 C 重生 goldens | 「換 baseline 失去紀律 #1.a 軌道」同意 + 接受 OnlyOffice docker 拉鏡像 |
| C Phase 5 任一子功能 | 提供含對應 feature 的 docx fixture + 指定優先順序 |
| A 候選微弱 wire-up | 確認可接受 < 1pt 視覺差實作 |

這是 autonomous 第一次**明確列出「自己做不到、要 user 介入」清單**、非常重要的邊界 explicit。

---

## 4. wire-up 三段式架構(Sprint 137-139)

### 4.1 三段式

Sprint 137-139 numbering wire-up cluster 形成「state machine → mapper → layout」三段架構:

```
Sprint 137: state machine (純函式、無 caller、無 VR 影響)
  ↓ 提供 advance() / reset() / snapshot() API
Sprint 138: mapper wire-up (ToCanvasEditor、canvas-editor 路徑)
  ↓ 不影響 VR(VR 不走 mapper)、但顯示真實編號
Sprint 139: layout wire-up (Paginator + TableLayout、VR 路徑)
  ↓ 影響 VR、Strategy C 折衷保 baseline
```

### 4.2 為什麼分三段、不是一個大 sprint

| 維度 | 三段式優勢 |
|---|---|
| PR-size(紀律 #18) | 每段 PR 100-200 行、可審 |
| 風險隔離 | Sprint 137 純函式無風險、Sprint 138 mapper 風險低(VR 不走)、Sprint 139 layout 風險高才需 Strategy C |
| 失敗 revert 粒度 | Sprint 139 翻車不影響 Sprint 137/138 |
| 紀律 #1.a 驗證 | 每段都跑全 VR、覆蓋不同類型(純函式 / mapper / layout)|

### 4.3 適用其他 capture-without-consumer 技術債

Sprint 121-142 累積 capture-without-consumer 清單:
- ✅ numbering(Sprint 137-139 已 wire-up)
- ❌ textAlignment / framePr(Sprint 140 DEFER、canvas-editor 無對應)
- ❌ pBdr / shd / tblStylePr 條件(Sprint 133 capture、未 wire-up、layout 端可能)

三段式適用 caller 端有對應的情境;canvas-editor / layout 端無對應時、應走 Sprint 140 DEFER 模式。

---

## 5. 數據總覽(Sprint 121-142)

### 5.1 累計指標變動

| 指標 | Sprint 121 起點 | Sprint 142 終點 | 變動 |
|---|---|---|---|
| vitest | 976 + 1 skipped | 1176 + 1 skipped | **+200** |
| VR mean | 0.073191 | 0.073191 | **0(15 連 byte-identical)** |
| Phase 1 OOXML | 72% | ~80% | +8pp |
| Phase 4 Style | 80% | 90% | +10pp |
| 正式紀律 | 18 條 | 22 條(Sprint 143 升正)| +4 |
| Sprint audit doc | 120 | 142 | +22 |

### 5.2 Sprint 類型分布(22 sprint)

| 類型 | 數量 | 比例 |
|---|---|---|
| Code change(parser / wire-up 完工)| 9 | 41% |
| Probe-only(autonomous DEFER 或 GO 決策)| 6 | 27% |
| Docs / retro / 紀律升正 | 5 | 23% |
| Revert(spike 翻車)| 1(Sprint 136)| 5% |
| Mechanical(無實質改動)| 1 | 5% |

### 5.3 紀律驗證

| 紀律 | 應用次數 |
|---|---|
| #1.a(parser / layout 跑全 VR) | 15 次連續驗證 |
| #21(optional 空集合不掛 key)| 5 次正式應用 |
| #22(probe sprint 確認 mental model)| 9 次正式應用 |
| #1.b(scope-down 或 revert byte-identical)| 8 次跨 sprint 驗證(Sprint 143 升正)|

---

## 6. 跨 cluster 對照(Sprint 50-66 vs Sprint 121-142)

| 維度 | Sprint 50-66(cache + FontMetricsAdapter)| Sprint 121-142(wire-up + autonomous 邊界)|
|---|---|---|
| 主要技術主題 | cache 加速 / 字型 metric | OOXML 完整性 / wire-up 鏈 |
| VR 軌道 | 0.0749 → 0.073191(-2.3%、命中)| 0.073191 byte-identical 15 連 |
| Sprint 數 | 17 | 22 |
| 翻車次數 | 1(Sprint 57 memoize)| 1(Sprint 136 isInTableCell)|
| 紀律生成 | 6 條(#1-#6)| 4 條升正(#1.a / #21 / #22 / #1.b)|
| autonomous 邊界 | 未碰到 | **第一次碰到(Sprint 141/142)** |
| 新模式 | Stable platform → 高風險改造 / Probe-Negative-Positive-Delta-Drift-Promote | probe-only 例行化 / Strategy C 折衷 / autonomous 邊界 explicit |

→ Sprint 121-142 cluster 是 sprint 50-66 模式的演化:
- 從「sprint 內探索」走向「sprint 內 probe + 跨 sprint 決策」
- 從「autonomous 主導」走向「autonomous 探索 + user 在邊界決策」
- 從「不要翻車」走向「翻車就 scope-down 三選擇光譜」

---

## 7. 未來 cluster checklist(從 Sprint 121-142 萃取)

新 cluster 開工前自查:

```
[ ] 1. 規畫書 scope 對齊?(紀律 #18)
[ ] 2. 是否屬「capture-without-consumer」技術債?
       → 是 → wire-up 三段式評估(state machine → caller A → caller B)
[ ] 3. mental model 確定?
       → 不確定 → 先 probe sprint(紀律 #22)
[ ] 4. probe 結論:autonomous GO / DEFER / user GO?(autonomous 邊界 3 維度)
[ ] 5. 實作後 VR 結果:byte-identical / 改善 / 退化?
       → 退化 → Strategy C 折衷 vs 全 revert vs 預防 DEFER(紀律 #1.b)
[ ] 6. wire-up 鏈完工後、cluster 紀律新升正?
       → 是 → 同 sprint 更新集中索引(紀律 #14.a)
```

---

## 8. 結論

Sprint 121-142 22 sprint 累積:**probe-only 例行化 + Strategy C 折衷 + autonomous 邊界揭示** 三個新模式進入紀律光譜。+200 vitest / +5pp Phase 4 / 15 連 byte-identical / 4 條紀律升正。

下個 cluster(Sprint 144+)若 user 提供決策(階段 C / Phase 5 / fixture):autonomous 已 ready 進入大規模 wire-up;若 user 無新指示:可繼續做 docs / probe / 規畫書 §11.2 backlog 探索。

「逐步執行 abc」3 連 probe + DEFER 是 autonomous 與 user 工作邊界**最有用的整理**、為下個 session 的 user 決策提供完整資訊。
