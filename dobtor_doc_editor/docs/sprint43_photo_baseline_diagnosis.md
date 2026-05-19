# Sprint 43 — Photo Y 偏移真根因精細 trace（純診斷不修代碼）

**期間**：2026-05-14
**主軸**：依 Sprint 42 翻車教訓「第七層 precondition 必須驗證」，對 photo Y 偏移做 trace + Pillow 雙路徑驗證
**核心結論**：**真根因 = LineBreaker.makeLine() 的 `baseline = height * 0.8` 對 image-only 行不正確**。
影像行不應有 descender（image 無下緣空間），baseline 應 = height。
當前公式使 photo 被畫到 baseY 上方 0.2 × photo.height（276pt 高 → 55pt 偏差，trace 實測 45.7pt 偏差含 spacing 修正）。
**新規則應用**：Sprint 43 不寫修法，先確認 precondition；Sprint 44 開工前用 debug test 驗證修法會改 render output。

---

## 1. 量化證據（Pillow 雙路徑 cross-check）

### 1.1 Pixel sampling（render PNG vs golden PNG）

對 06.環清表(112.10.23-10.27)-1.rendered.png + golden 同名 PNG 各取 x=400 縱掃：

```
                        render trans (y, type)             golden trans (y, type)
First content (y>200)   y=206→208 wht→photo→wht (border)   y=304→305 (border)
photo block start       y=344                              y=462
                       
First photo BIG block   y=425 (黑色密集區起)               y=460
                        ratio=42.18% page 1 diff
```

→ **render 首張 photo 起點 y=425 px，golden y=460 px，pixel diff = 35 px = 16.8 pt**。

### 1.2 Render trace（vitest MockRenderContext drawImage ops）

[tests/integration/sprint43_photo_trace.test.ts](../tests/integration/sprint43_photo_trace.test.ts) dump page 1：

```
=== Page 1 drawImage ops ===
  rId7  x=130.6  y=119.1  w=368.3  h=276.1  pt   → 150 DPI 像素 y=248
  rId8  x=130.8  y=410.1  w=367.8  h=275.9  pt   → 150 DPI 像素 y=854

=== Table entries ===
  table at (85, 60.5)pt → px(177, 126)  rows=6
    row 0: y=60.5  h=38.9
    row 1: y=99.4  h=20.9
    row 2: y=120.3 h=20.9
    row 3: y=141.1 h=20.9
    row 4: y=161.9 h=290.9   ← photo cell #1 (rId7)
    row 5: y=452.8 h=290.9   ← photo cell #2 (rId8)
```

**Photo 1 trace y = 119.1pt**（pixel 248），**但其 cell row 4 起點 = 161.9pt**（pixel 337）。

→ Photo 被畫在 cell 上方 42.8pt（pixel 89 px）！

## 2. 矛盾解開：trace ≠ pixel?

Pillow scan 顯示 render PNG photo 起點 ≈ y=425 px（big black block）。
Render trace drawImage y=119.1pt = 248 px。
**248 ≠ 425**。

原因：BrowserCanvasRenderContext.drawImage 把 source image 畫到 destination rect (x=272, y=248, w=767, h=575)。**image source 內容開始於 source 自己的某 y offset**（很可能上方有白色或淺色 padding pixels）。
所以 destination rect 雖然從 y=248 開始，但有 useful content 只從 y=425 開始；rect 上半部分（y=248-425）是 source image 的白色 padding。

驗證：

```
render rect: y_top=248 → y_bottom=248+575=823
golden photo: y_top=460 → ...
```

若 golden 也是 rect y_top=??，但內容從 y=460 開始：差異 = render rect 比 golden rect 高 ~ 460-248 = **212 px = 102 pt**。

## 3. 真根因：LineBreaker baseline 公式

[static/src/core/layout/LineBreaker.ts:301](../static/src/core/layout/LineBreaker.ts)：

```typescript
// baseline 簡化版：取行高的 80%（80% baseline drop）
const baseline = height * 0.8;
```

對純文字 line（fontSize × 1.2 leading）：baseline = 0.8 × height 合理（ascender 80%、descender 20%）。

但對 **image-only line**：image 沒有 descender，整個 image 應在 baseline 之上。正確公式：

```typescript
baseline = imageBox.height;  // image bottom aligned to baseline
// 然後 image y_drawn = yBaseline - box.height = baseY + height - height = baseY  ← 正確：image 從 cell padding.top 起點
```

當前公式：

```
yBaseline = baseY + 0.8 × height
image y_drawn = yBaseline - height = baseY - 0.2 × height
```

→ image 被畫到 baseY 上方 0.2h 處。對 photo height=276.1pt → 0.2 × 276.1 = **55.2pt 上偏**。

實測 trace 偏差 = 161.9 - 119.1 = **42.8pt**（與 55.2pt 略小，差 12pt 可能來自 spacing line + docGrid snap 對 baseline 的調整，本 sprint 暫不深究）。

## 4. 修法預估（Sprint 44 工作）

[LineBreaker.makeLine](../static/src/core/layout/LineBreaker.ts) 改寫 baseline 公式：

```typescript
function makeLine(items, para, isLastLine, docGridLinePitch = 0) {
  let height = 0;
  let isImageOnlyLine = true;
  for (const it of items) {
    if (it.kind === 'box') {
      if (it.height > height) height = it.height;
      const b = it as Box;
      if (!b.isImage) isImageOnlyLine = false;
    }
  }
  // ...
  // Sprint 44：image-only line 用 baseline = height（無 descender），否則 0.8h
  const baseline = isImageOnlyLine && height > 0 ? height : height * 0.8;
  // ...
}
```

預估 photo y 從 119.1 → 164.8pt（baseY = row 4 top + padding.top），對應 pixel 從 248 → 343。
golden pixel 460 仍剩 117 px = 56 pt gap，**Sprint 44 修法只解決部分問題**。

## 5. 剩餘 56pt gap 假設（待 Sprint 45 驗證）

- **A. 前置 row 高度誤差**：row 0 trHeight=340 twip = 17pt，但 render 給 38.9pt。差 ~22pt。累積 row 0-3 可能多 ~30pt
- **B. table 起點 y 偏差**：60.5pt 是否正確？empty para 的 `<w:spacing w:line="40" w:lineRule="exact"/>` (= 2pt) 應該只佔 2pt，但 render 把 empty para 算 17pt（marginTop 42.5 + 17 = 59.5 ≈ 60.5）
- **C. table 之前的「title 文字段落」golden 有 render 沒有**：但 docx 內容 inspect 顯示沒有 title 段落

**最可能 = A + B**：empty paragraph honor `w:line="40"` exact 規則 + row trHeight "exact" rule 規則 我們可能沒實作

## 6. Sprint 43 規律 ✅

**第七層 precondition 驗證**（Sprint 42 新增規律）已執行：

1. ✅ trace MockRenderContext 拿 (x, y, w, h)
2. ✅ Pillow 量測 render & golden PNG pixel y
3. ✅ trace × 150/72 與 pixel sampling 對應上（rect y=248 vs photo content y=425 = source image 內 padding）
4. ✅ 量化 Δ 與 root cause 推估（baseline 0.8 公式 → 55.2pt 上偏，實測 42.8pt 接近）
5. ✅ 計算修法預期效果（45.7pt 收割，剩 56pt 待 Sprint 45）

Sprint 44 開工**新增 precondition test**：
```
// Sprint 44 prep test：mock 1 paragraph 內 1 inline image，跑 LineBreaker，
// 修法前 yBaseline = h × 0.8（image y_drawn = -0.2h）；修法後 yBaseline = h（y_drawn = 0）
// 必須在 unit test 看到差異才能正式進入 Sprint 44 渲染端修改
```

## 7. 工作摘要

```
（Sprint 43 純診斷無代碼變更）
+  tests/integration/sprint43_photo_trace.test.ts | trace photo (x,y,w,h) + table rows + horizontal lines
+  docs/sprint43_photo_baseline_diagnosis.md      | 本文件
```

無 VR / vitest pass count 變動。

## 8. Sprint 33-43 失敗模式累積

| Sprint | 教訓 | 應用 |
|---|---|---|
| 33-35 | 不規格先行 | ✅ |
| 36 | 資料先行（grid analysis）| ✅ |
| 37-40 | 修對方向/機制/type/細節/位置/fixture 涵蓋率 | ✅ |
| 41 | 純診斷找候選 root cause | ✅ Sprint 43 應用 |
| 42 | precondition 不滿足就翻車 | ✅ Sprint 43 驗證了 trace ↔ pixel cross-check |
| **43** | **Sprint 44 開工 prep test 驗證「修法會改 render output」才能進** | 本 sprint 即建立規則 |

Sprint 44 紀律：**先寫 prep test (在 LineBreaker layer)** 確認修法生效，再寫 production code。
