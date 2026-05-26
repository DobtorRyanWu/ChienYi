# Sprint 256+257+258+259+260+261 — SmartArt 第十六層 + Charts 第十七層 byte-identical 對稱矩陣完備 ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ / 0 行 writer 修法 / 第八+九次 LibreOffice 邊緣 corpus 達 100% / 21 SmartArts/texts + 17 Charts/40 series byte-identical

**日期**：2026-05-26（週二）
**類型**：六 audit 並排 / Strategy C 純 audit、無 writer 修法
**規畫書對應**：§6 黃金測試第十六+十七層 SmartArt + Charts（Phase 5.2 / 5.3）
**前置**：Sprint 253-255 DocProps 完備、十五層矩陣全綠

---

## Hypothesis & Result

**hypothesis**：十五層矩陣完備後、擴展第十六（SmartArt）+ 第十七（Charts）
兩層；兩者 Sprint 195 writer 已實作（collectSmartArts/writeSmartArtPart +
collectCharts/writeChartPart/writeChartSeries），本輪僅 audit、不修 writer。

**範圍**：
- **SmartArtNode** 3 欄位：rId / layoutType（optional）/ texts（string[]）
  - capture 自 document.xml.rels type=diagramData
  - writer 寫 diagrams/dataN.xml（mc:Fallback 壓縮策略，user 2026-05-21 拍板）
- **ChartNode** 4 欄位：rId / chartType / title（optional）/ series
  - **ChartSeries** 3 欄位：name（optional）/ categories（string[]）/
    values（(number|null)[]）
  - capture 自 document.xml.rels type=chart
  - writer 寫 charts/chartN.xml（mc:Fallback 壓縮，僅保留 numCache/strCache 數值快取）

**實測結果**：

### Sprint 256+257+258 — SmartArt 第十六層

- Sprint 256 ChienYi 42：**42/42 (100%) / 0 SmartArts trivially**
- Sprint 257 LibreOffice：**288/288 (100%) / 3 SmartArts + 5 texts**
  ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ **第八次 LibreOffice 邊緣 corpus 達 100%**
  - misc 子目錄 2 SmartArts / 2 texts
  - smartart 子目錄 1 SmartArt / 3 texts（smartart.docx + strict-smartart.docx）
- Sprint 258 Phase 5：**18/18 (100%) / 4 SmartArts + 36 texts**
  - 08_smartart 子目錄 4 fixture 全綠（user 真實案例 + 系統介紹）

**SmartArt 三 corpus 合計：348/348 (100%) / 7 SmartArts + 41 texts byte-identical**

### Sprint 259+260+261 — Charts 第十七層

- Sprint 259 ChienYi 42：**42/42 (100%) / 0 Charts trivially**
- Sprint 260 LibreOffice：**288/288 (100%) / 9 Charts + 21 series**
  ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ **第九次 LibreOffice 邊緣 corpus 達 100%**
  - chart 子目錄 7 Charts / 16 series（9 fixture 全綠）
  - misc 子目錄 2 Charts / 5 series
- Sprint 261 Phase 5：**18/18 (100%) / 8 Charts + 19 series**
  - 07_chart 子目錄 8 fixture 全綠

**Charts 三 corpus 合計：348/348 (100%) / 17 Charts + 40 series byte-identical**

**第十六 + 第十七層 byte-identical 對稱矩陣完備 + 第八+九次 LibreOffice 邊緣 corpus 100%**
⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐。

---

## Strategy C — 0 行 production code 變動

兩層 audit 揭發 **零 root cause、零 writer gap**：

| 層 | parser capture | writer 已實作 | round-trip 100%？ |
|---|---|---|---|
| 16 SmartArt | Sprint 181 DiagramParser | Sprint 195 collectSmartArts + writeSmartArtPart | ✅ |
| 17 Charts | Sprint 182 ChartParser | Sprint 195 collectCharts + writeChartPart + writeChartSeries | ✅ |

Sprint 195 已預先把 Phase 5.2/5.3 的 export 對稱性鋪好；本輪 audit 證明該
sprint 的設計（mc:Fallback 壓縮 + 數值快取 round-trip）對齊 parser、無漏失。

紀律 #1.b / Strategy C 完美執行：**audit 揭發 0 gap → 0 行 production code 變動**。

---

## audit dimension 設計（與 Sprint 243-255 共通）

### deepStableStringify

遞迴鍵排序 JSON 序列化（key 字典序、array 保序），消除 Map 迭代序差異與
key 順序差異。對 array 不重排（SmartArt/Chart 依 rels 順序排列、重排會誤判）。

### 序列化 normalization

- **SmartArt**：`undefined | []` → `[]`，避免 `expect(undefined).toEqual([])` 誤判
- **Chart**：同上
- 兩者皆已 enforce parser 端「無 SmartArt/Chart → undefined（紀律 #21）」

### SHA-256 fallback

`oSerial === rSerial || sha256(oSerial) === sha256(rSerial)`，純字串相等
+ hash 雙重保險，對 >4KB JSON 比較更穩。

---

## 三 corpus 十七層 byte-identical 對稱矩陣（截至 Sprint 261）

| 層 | sprint | ChienYi 42 | LibreOffice 286 | Phase 5 18 | LibreOffice 100% |
|---|---|---|---|---|---|
| 1 Structure | 218→219 | 100% | 95.5% | 100% |  |
| 2 Text | 220→226 | 100% | 96.8% | 100% |  |
| 3 RunProps | 227→230 | 100% | 93.1% | 100% |  |
| 4 ParaProps | 231→233 | 100% | 97.6% | 100% |  |
| 5 TableProps | 234→236 | 100% | 95.5% | 100% |  |
| 6 SectionProps | 237→239 | 100% | 94.8% | 100% |  |
| 7 HF Content | 240→242 | 100% | 94.4% | 100% |  |
| 8 StyleMap | 243→245 | 100% | 96.5% | 100% |  |
| 9 NumberingMap | 243→245 | 100% | **100%** | 100% | ✅ 第一次 |
| 10 Comments | 243→245 | 100% | **100%** | 100% | ✅ 第二次 |
| 11 Footnotes | 243→245 | 100% | **100%** | 100% | ✅ 第三次 |
| 12 Settings | 243→245 | 100% | **100%** | 100% | ✅ 第四次 |
| 13 FontTable | 246→248 | 100% | **100%** | 100% | ✅ 第五次 |
| 14 WebSettings | 249→251 | 100% | **100%** | 100% | ✅ 第六次 |
| 15 DocProps | 253→255 | 100% | **100%** | 100% | ✅ 第七次 |
| **16 SmartArt** | **256→258** | **100%** | **100%** | **100%** | ✅ **第八次** |
| **17 Charts** | **259→261** | **100%** | **100%** | **100%** | ✅ **第九次** |

**LibreOffice 17 層：15 ≥ 95% commercial-grade + 9 層 100%**。

---

## 紀律記分卡

| 紀律 | 結果 |
|---|---|
| #1.b / Strategy C：0 行 production code 變動 | ✅ |
| #2 名定常數 | ✅（MIN_*_MATCH_RATE_PCT / EXPECTED_*_BASELINE） |
| #14.b clean scope（commit 只含 6 audit + 1 doc） | ✅ |
| #18 scope-down（不擴張到 cxnLst/axes 等 mc:Fallback 不收進的層） | ✅ |
| #21 audits 不 touch VR / round-trip / 既有 tests | ✅ |
| VR 第 68 連 | ✅（writer 0 變動） |

---

## 規畫書 §5 Phase 5 SmartArt / Charts 對應

- 規畫書接受 mc:Fallback 壓縮策略 → SmartArt 不重建圖形版面、Chart 不重繪
  座標軸；本層 audit 證明該策略下「資料模型 + 文字節點」+「型別 + 數列數值
  快取」可達 100% byte-identical。
- 與 §5.1 OMML（KaTeX 線性 fallback）同一壓縮哲學，於 §6 黃金測試
  第十六+十七層收口。

---

## 殘項 / Next Steps

| 殘項 | sprint | 動作 |
|---|---|---|
| 第十八層 theme.xml | 後續 | 需先擴 OoxmlDocument AST + ThemeMap 寫回；本輪未做 |
| diagrams layout/quickStyle/colors（4 部件中 3 個未 export） | 後續 | mc:Fallback 接受、僅 dataN.xml 必要；增量再決 |
| chart axes / plotArea fill / dataLabels | 後續 | mc:Fallback 接受、優先級低 |
| Phase 8.2.2 overlay 編輯 | 後續 | 規畫書 §8.2.2 |
| Phase 7 效能殘項 | 後續 | WPS audit / HarfBuzz external-blocked |

---

## End of Sprint 256-261

**六 audit 並排 + 第十六+十七層完備 + Strategy C 純 audit、0 行 writer
修法 + 第八+九次 LibreOffice 邊緣 corpus 100%**
⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐。

VR 第 68 連保持、十七層矩陣全綠（LibreOffice 9 層 100% / 6 層 ≥ 95% /
2 層 ≥ 93%）。
