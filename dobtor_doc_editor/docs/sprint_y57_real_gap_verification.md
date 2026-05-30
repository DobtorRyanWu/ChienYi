# Sprint Y57 — FloatTextBox + wp:anchor 真實路徑 Gap 驗證

- **建立日期**：2026-05-30
- **狀態**：Audit only（不改 production code）
- **目標 fixture**：`tests/fixtures/01_simple/03.1120815-監造會議記錄.docx`
- **驗證路徑**：產品真實 controller `/dobtor_doc/import?engine=ts` 的核心 — 即 `controllers/doc_controller.py::_ts_parse_docx_to_elements()` 透過 subprocess 跑 `tools/dist/parse_docx_cli.cjs <in> <out> --elements --svg-graphics`

---

## 1. 結論（先答題）

> **gap 真實，但語意低價值** — 不建議把這份 fixture 當「FloatTextBox + wp:anchor 真實 gap」的代表性樣本。

### 1.1 從「IElement 樹是否有對應節點」這一層 → 真

- 原 docx 內 5 個 `<wp:anchor>` 與 5 個 `<v:textbox>`（DrawingML + VML 同物件，10 個 `<w:txbxContent>`）的**所有文字內容完全沒有出現在 IElement 樹中**
- CLI 抓到的 IElement 樹只覆蓋 body 的 2 個 `<w:tbl>` + 4 個換行 `<w:p>`，FloatTextBox 內容 0 命中

### 1.2 但從「使用者實質內容是否遺失」這一層 → 假

- 5 個 anchor / 5 個 textbox 的文字內容 **100% 是自動頁碼**：`第 1 頁，共 3 頁`、`第 2 頁，共 3 頁`、`第 3 頁，共 3 頁`、`第 4 頁，共 4 頁`，外加 1 個空 anchor
- 在 OOXML 中這是「PAGE / NUMPAGES 域 + 浮動文字框」的標準頁碼做法 — 文字串是 Word 算出來的暫存值，不是使用者輸入
- canvas-editor 是頁面式編輯器、本身會自算頁碼，所以 IElement 缺這些字串 **對使用者體感的「內容遺失」= 0**

→ 把這份 fixture 視為「FloatTextBox 真實內容代表性樣本」會誤導 sprint 投資方向。

---

## 2. 證據

### 2.1 原 docx XML（document.xml + 14 個 part）

| 來源 | wp:anchor | w:txbxContent | v:textbox | mc:AlternateContent |
|---|---|---|---|---|
| `word/document.xml` | **5** | **10** | **5** | 5 |
| `word/footer1.xml` | 0 | 0 | 0 | 0 |
| `word/header1.xml` | 0 | 0 | 0 | 0 |

5 個 `mc:AlternateContent` 包住 5 對「Choice=DrawingML anchor / Fallback=VML textbox」配對。所以實際語意上 = **5 個浮動文字框**。

#### wp:anchor 文字內容（document.xml）

```
anchor[0] texts=['第', '1', '頁，共', '3', '頁']    blips=[]   (空圖片)
anchor[1] texts=['第', '2', '頁，共', '3', '頁']    blips=[]
anchor[2] texts=['第', '4', '頁，共', '4', '頁']    blips=[]
anchor[3] texts=[]                                   blips=[]   (空文字+空圖片)
anchor[4] texts=['第', '3', '頁，共', '3', '頁']    blips=[]
```

#### w:txbxContent 文字內容（10 個 = anchor 5 + v:textbox 5 同字串）

```
txbx[0..1] = '第1頁，共3頁'
txbx[2..3] = '第2頁，共3頁'
txbx[4..5] = '第4頁，共4頁'
txbx[6..7] = (empty)
txbx[8..9] = '第3頁，共3頁'
```

#### 圖片

- `word/media/` 不存在
- `wp:anchor` 內 `a:blip` 計數 = 0
- `wp:inline` 計數 = 0
- → **本 fixture 本來就沒有任何嵌入圖片**

### 2.2 真實 CLI 輸出（out.json，261 KB）

執行：
```
node tools/dist/parse_docx_cli.cjs target.docx out.json --elements --svg-graphics
```

遞迴掃 `element + trList + tdList + valueList + value(list 形式)`，蒐集所有 leaf node 的 `value: str`：

| 指標 | 值 |
|---|---|
| top-level IElement 數 | 6 (2 table + 4 newline text) |
| 全樹 IElement 節點數 | 1,958 |
| type 分佈 | text=1953, table=2, pageBreak=2, tab=1 |
| 拼接後純文字總長 | 1,774 字 |
| image type 節點 | **0** |
| `"第X頁，共Y頁"` 正則匹配 | **0** |
| `"第"` 字總出現次數 | 3（全是內文「第3次工地」「第3頁」之類，與 anchor 無關） |

對比原 document.xml 的 461 個 `<w:t>` 共 1,646 字：CLI 抓到 1,774 字反而**多於**原文（因為 `w:tab` 也算 1 字、`w:cr/w:br` 進 pageBreak 等），表格 cell 內所有文字都正確抓進去。**唯一遺漏 = wp:anchor / v:textbox / w:txbxContent**。

### 2.3 IElement 樹外觀

```
top[0] type=table, 28 trList
top[1] type=text, value='\n'
top[2] type=text, value='\n'
top[3] type=table, X trList
top[4] type=text, value='\n'
top[5] type=text, value='\n'
```

兩個 table 對應 body 的 `<w:tbl>` × 2，剩下 4 個 `\n` 對應 top-level 兩個 `<w:p>` 各自 emit 一對 newline。沒有 anchor/textbox 對應節點。

---

## 3. 為什麼這份 fixture 不該當代表性樣本

| 標準 | 這份 fixture |
|---|---|
| 是否有 wp:anchor | ✅ 有 5 個 |
| anchor 內容是否為使用者實質輸入 | ❌ 全是自動頁碼 |
| 是否有嵌入圖片（blip / inline） | ❌ 0 個 |
| canvas-editor 是否需要從 anchor 抓內容 | ❌ canvas-editor 會自算頁碼 |
| 修復 gap 對 fidelity 評分增益 | 低（修了視覺一致性 +1，內容語意 0） |
| 修復 gap 對使用者價值 | 0 |

24 份「典型代表」抽樣，這份雖在分類上是 `01_simple` 的會議記錄，但它沒有真正的使用者實作浮動文字框 / 圖片浮動框 — anchor 純粹是 Word 自動排版的頁碼容器。

---

## 4. 下個候選的建議與初步抽樣

User 提出的下個候選方向：**multi-section 自主檢查表系列**（`tests/fixtures/05_header_footer/自主檢查表---*.docx`，共 10 份）。

我抽樣了 `自主檢查表---混凝土.docx` 的所有 XML part：

| 指標 | 值 |
|---|---|
| `<wp:anchor>` 數量 | **0** |
| `<w:txbxContent>` 數量 | **0** |
| `<v:textbox>` 數量 | **0** |
| `<mc:AlternateContent>` 數量 | **0** |
| `<w:sectPr>` 數量 | **3**（multi-section ✓） |
| `media/` 圖片 | 0 |

→ 自主檢查表系列**沒有 FloatTextBox**，它的特徵 gap 是 **multi-section（每節獨立頁面設定）**，不是 wp:anchor / floating text box。

→ 如果 sprint 主軸是「FloatTextBox + wp:anchor」，05_header_footer 系列**不是同一條 gap 的延伸**；如果主軸是「multi-section / 跨節版面」，那它是對的候選但 wp:anchor 已脫鉤。

### 4.1 可能更貼題的下個候選方向（待 user 決策）

1. **真正含使用者文字浮動框** → 找 `04_with_image`（會議照片）或 `02_std_table` 的週報 — 那種 doc 常有公司 logo + 機關識別文字塊浮在頁緣
2. **真正含嵌入圖片的 wp:anchor** → 同上 `04_with_image` 系列
3. **multi-section** → 已認定，但與 wp:anchor 是兩條不同 gap

建議先選一份 `04_with_image` 的 docx 重跑同一個 audit 流程，確認是否有「真的浮動圖片 + 真的使用者文字塊」。

---

## 5. 重現步驟

```bash
# 1. 解壓 docx 看原 XML
mkdir /tmp/gap_audit && cd /tmp/gap_audit
cp /mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/tests/fixtures/01_simple/03.1120815-監造會議記錄.docx target.docx
unzip -o target.docx -d unpacked

# 2. 跑真實 CLI（與 controller 內 subprocess 呼叫一致）
node /mnt/d/work/odoo18-docker/addons/dobtor_doc_editor/tools/dist/parse_docx_cli.cjs \
    target.docx out.json --elements --svg-graphics

# 3. 遞迴掃 out.json（見 §2.2）
python3 -c "..."
```

完整 Python 掃描腳本見本 sprint 對話紀錄。

---

## 6. 等待 user 決策

按 sprint 任務描述：
- 若 gap 真實 → 等 user 下決策做 ②
- 若 gap 假（內容已正確 emit）→ 找下一個候選（multi-section 自主檢查表系列）

本次驗證落在「**技術真、語意假**」的中間地帶，加上下個候選方向（multi-section）也已脫鉤 wp:anchor，需要 user 釐清：

- **A**：本次 fixture 雖然只是頁碼，但仍認定 wp:anchor 為「FloatTextBox 主軸真實 gap」、進入 ②（修 CLI 讓 anchor/textbox 內容也 emit）
- **B**：認定本次 fixture 不具代表性、改抽樣 `04_with_image` 系列確認是否有真正使用者浮動內容後再決定
- **C**：把 sprint 主軸改成「multi-section 跨節版面」，wp:anchor 押後

請 user 指示要走哪一條。
