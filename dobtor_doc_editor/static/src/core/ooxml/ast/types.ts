/**
 * OOXML AST 型別定義
 *
 * 設計原則：
 * - Parser 輸出已解析完畢的扁平結構，所有樣式繼承鏈已展開
 * - 所有長度單位統一為 pt（點），Renderer 根據 DPI 換算 px
 * - Table Cell 的 gridCol / gridSpan / rowSpan 由 GridResolver 預先計算
 * - LineMetrics 介面在 Phase 1 預留，Phase 2 由 HarfBuzz WASM 實作
 */

// ── 基礎單位型別 ──────────────────────────────────────────────────────────────

export type Pt = number;      // 點（points），所有長度的標準單位
export type HexColor = string; // "RRGGBB"（不含 #），或 "auto"

// ── 邊框 ──────────────────────────────────────────────────────────────────────

export type BorderStyle =
  | 'none' | 'single' | 'double' | 'thick'
  | 'dashed' | 'dotted' | 'dashDot' | 'dashDotDot'
  | 'triple' | 'thinThickSmallGap' | 'thickThinSmallGap'
  | string;

export interface BorderDef {
  style: BorderStyle;
  width: Pt;        // w:sz / 8（原始單位為 1/8 pt）
  color: HexColor;
  space?: Pt;       // w:space
}

export interface CellBorders {
  top?: BorderDef;
  bottom?: BorderDef;
  left?: BorderDef;
  right?: BorderDef;
  insideH?: BorderDef;
  insideV?: BorderDef;
}

// ── 行高度量介面（Phase 1 預留，Phase 2 由 HarfBuzz WASM 精確實作）────────────
//
// 重要：Layout Engine 必須只透過此介面取得字型度量，
// 不可直接呼叫 ctx.measureText()，確保 Phase 2 切換時不需重寫 Layout Engine。

export interface LineMetrics {
  fontFamily: string;
  fontSize: Pt;
  ascender: Pt;     // 基線以上高度
  descender: Pt;    // 基線以下深度（正值）
  lineGap: Pt;      // 字型建議的額外行距
  // Phase 1：以 ctx.measureText() 近似填入
  // Phase 2：改由 opentype.js 或 HarfBuzz WASM 從字型檔直接讀取
}

// ── Run（文字片段）屬性 ───────────────────────────────────────────────────────

export type VertAlign = 'baseline' | 'superscript' | 'subscript';
export type Underline =
  | 'none' | 'single' | 'double' | 'dotted' | 'dashed'
  | 'words' | 'thick' | 'wave'
  | string;

export interface RunProps {
  fontFamily?: string;          // w:ascii — 西文字型
  fontFamilyEastAsia?: string;  // w:eastAsia — CJK 字型
  fontFamilyHAnsi?: string;     // w:hAnsi — High ANSI 字型（西方擴展字符集）
  fontFamilyCs?: string;        // w:cs — Complex Script 字型（阿拉伯/希伯來等）
  fontSize?: Pt;
  bold?: boolean;
  italic?: boolean;
  underline?: Underline;
  strike?: boolean;
  dstrike?: boolean;            // 雙刪除線
  color?: HexColor;
  highlight?: HexColor;
  vertAlign?: VertAlign;
  spacing?: Pt;                 // 字元間距 w:spacing
  lang?: string;                // w:lang val
}

// ── 段落屬性 ──────────────────────────────────────────────────────────────────

export type Alignment = 'left' | 'center' | 'right' | 'justify' | 'distribute';
export type LineSpacingRule = 'auto' | 'exact' | 'atLeast';

export interface ParagraphProps {
  alignment?: Alignment;
  indent?: {
    left?: Pt;
    right?: Pt;
    firstLine?: Pt;   // 正值 = 縮排，負值 = 懸掛
    hanging?: Pt;     // w:hanging（等同負 firstLine）
  };
  spacing?: {
    before?: Pt;
    after?: Pt;
    line?: { rule: LineSpacingRule; value: Pt; };
  };
  borders?: {
    top?: BorderDef;
    bottom?: BorderDef;
    left?: BorderDef;
    right?: BorderDef;
  };
  shading?: {
    fill?: HexColor;
    color?: HexColor;
    pattern?: string;
  };
  keepNext?: boolean;
  keepLines?: boolean;
  pageBreakBefore?: boolean;
  /**
   * Sprint 29：`<w:snapToGrid w:val="0"/>` 顯式關閉時 false；
   * 未設或 val=1 為 true（OOXML §17.3.1.32 預設）。
   * 僅當 section.docGrid.type !== 'default' 時對 line 高度產生影響。
   */
  snapToGrid?: boolean;
  numId?: number;    // 清單編號 ID（來自 numbering.xml）
  ilvl?: number;     // 清單縮排層級（0-based）
  tabs?: Array<{ pos: Pt; align: 'left' | 'right' | 'center' | 'decimal'; leader?: string; }>;
  /**
   * Sprint 134：`<w:textAlignment w:val="..."/>` 文字行內垂直對齊（ECMA-376 §17.3.1.36）。
   *
   *   - 'auto'：依字型 metric 自動（預設）
   *   - 'top'：頂部對齊
   *   - 'center'：垂直置中
   *   - 'baseline'：基線對齊
   *   - 'bottom'：底部對齊
   *
   * 影響行內混合不同字型大小 / 數學符號 / 圖片時 baseline 位置。
   * Layout 階段消費；parser 僅 capture。
   */
  textAlignment?: 'auto' | 'top' | 'center' | 'baseline' | 'bottom';
  /**
   * Sprint 134：`<w:framePr/>` 段落框基礎屬性（ECMA-376 §17.3.1.11）。
   *
   * Word 「位置與大小固定的浮動段落」（如 drop cap、邊欄注釋）。
   * 罕見於 ChienYi 監造文件、但若 fixture 出現需 capture 避免遺失資料。
   *
   * 當前只 capture 主流位置 / 大小 / 環繞屬性；w:dropCap / w:lines / w:anchorLock 等進階 defer。
   */
  framePr?: {
    width?: Pt;
    height?: Pt;
    hRule?: 'auto' | 'atLeast' | 'exact';
    hSpace?: Pt;
    vSpace?: Pt;
    /** w:wrap：around / notBeside / through / tight / none */
    wrap?: 'around' | 'notBeside' | 'through' | 'tight' | 'none';
    /** w:hAnchor：margin / page / text */
    hAnchor?: 'margin' | 'page' | 'text';
    /** w:vAnchor：margin / page / text */
    vAnchor?: 'margin' | 'page' | 'text';
    /** w:xAlign：left / center / right / inside / outside */
    xAlign?: 'left' | 'center' | 'right' | 'inside' | 'outside';
    /** w:yAlign：top / center / bottom / inside / outside / inline */
    yAlign?: 'top' | 'center' | 'bottom' | 'inside' | 'outside' | 'inline';
    x?: Pt;   // w:x 絕對位置（與 xAlign 互斥）
    y?: Pt;   // w:y 絕對位置（與 yAlign 互斥）
  };
}

// ── 文件內嵌元素（Inline Nodes）──────────────────────────────────────────────

/**
 * 超連結資訊（OOXML w:hyperlink 元素的解析結果，ECMA-376 §17.16.22）。
 *
 * 來源組合：
 *   - External URL（rId 透過 .rels 解析為 http(s):// URL）：url 有值
 *   - 文件內 anchor（w:anchor="bookmarkName"）：anchor 有值，url 通常無
 *   - External + anchor 共存：跨文件指定位置（rare 但合法）
 *   - rels 損壞時：url 為 undefined、rId 保留供下游診斷
 *
 * Sprint 126 — 擴充 hyperlink rels 完整覆蓋：
 *   - tgtFrame：HTML 風格 target frame（_blank / _self / _parent / _top / 自訂 frame 名）
 *   - history：是否計入瀏覽歷史（Word 視為「已造訪」）
 *   - docLocation：替代文件位置（早期 Word 跨文件連結）
 */
export interface HyperlinkInfo {
  rId?: string;          // 原始關係 ID（External 連結時有）
  url?: string;          // 從 document.xml.rels 解析的 External URL
  anchor?: string;       // 文件內 bookmark 名稱（w:anchor）
  tooltip?: string;      // w:tooltip 滑鼠提示
  tgtFrame?: string;     // Sprint 126 — w:tgtFrame target 視窗
  history?: boolean;     // Sprint 126 — w:history（"1" / "true" → true，"0" / "false" → false）
  docLocation?: string;  // Sprint 126 — w:docLocation 跨文件位置
}

/** 文字 Run */
export interface RunNode {
  type: 'run';
  text: string;
  props: RunProps;
  metrics?: LineMetrics; // Phase 1 為 undefined，Phase 2 填入
  hyperlink?: HyperlinkInfo; // 此 Run 被 <w:hyperlink> 包裹時填入
}

/** 欄位（PAGE、DATE、SEQ、TOC 等）*/
export interface FieldNode {
  type: 'field';
  instruction: string;  // 原始 field instruction，例如 " PAGE " 或 " DATE \\@ \"yyyy/MM/dd\" "
  // Sprint 123：擴充 SEQ / TOC / REF / HYPERLINK / STYLEREF 五型（涵蓋規畫書 §11.1 條列）
  fieldType:
    | 'PAGE' | 'NUMPAGES'
    | 'DATE' | 'TIME'
    | 'AUTHOR' | 'FILENAME'
    | 'SEQ' | 'TOC' | 'REF' | 'HYPERLINK' | 'STYLEREF'
    | 'unknown';
  cachedValue?: string; // w:fldSimple 內 / fldChar 複合的 w:t 快取值
}

/** 換行 */
export interface BreakNode {
  type: 'break';
  breakType: 'line' | 'page' | 'column';
}

/**
 * Sprint 40：DrawingML 圖片裁切（`<a:srcRect l="..." t="..." r="..." b="..."/>`）。
 *
 * OOXML §20.1.10.40 ST_PositiveFixedPercentage：原始值 = 千分比 × 1000，
 * 即 `t="4066"` 表示「從 source 上方裁切 4.066%」。
 *
 * 此處統一以 **0–1 分數** 表示（已 ÷ 100000）：
 *   - leftPct + rightPct < 1（otherwise 整張圖被裁光）
 *   - 同理 topPct + bottomPct
 *
 * 缺漏（無 srcRect 或空 `<a:srcRect/>`）→ undefined，視為「不裁切」。
 */
export interface ImageSrcRect {
  leftPct: number;   // 0–1
  topPct: number;
  rightPct: number;
  bottomPct: number;
}

/** 內嵌圖片（wp:inline）*/
export interface InlineImageNode {
  type: 'inlineImage';
  rId: string;      // 關係 ID，Renderer 解析為 blob URL
  width: Pt;
  height: Pt;
  altText?: string;
  /**
   * Sprint 40：DrawingML `<a:srcRect>` 裁切（如有）。
   * Renderer 將透過 RenderContext.drawImage 第 6 參數傳入做 9-arg drawImage。
   */
  srcRect?: ImageSrcRect;
}

/** 浮動圖片（wp:anchor）*/
export interface FloatImageNode {
  type: 'floatImage';
  rId: string;
  width: Pt;
  height: Pt;
  posH: {
    relativeFrom: 'margin' | 'page' | 'column' | 'character'
      | 'leftMargin' | 'rightMargin' | 'insideMargin' | 'outsideMargin';
    align?: 'left' | 'right' | 'center' | 'inside' | 'outside';
    posOffset?: Pt;
  };
  posV: {
    relativeFrom: 'margin' | 'page' | 'paragraph' | 'line'
      | 'topMargin' | 'bottomMargin' | 'insideMargin' | 'outsideMargin';
    align?: 'top' | 'bottom' | 'center' | 'inside' | 'outside';
    posOffset?: Pt;
  };
  wrapType: 'none' | 'square' | 'tight' | 'through' | 'topAndBottom'
    | 'behindText' | 'inFrontOfText';
  behindDoc?: boolean;
  allowOverlap?: boolean;
  altText?: string;
  /** Sprint 40：DrawingML `<a:srcRect>` 裁切（如有）— 與 InlineImageNode 同型別 */
  srcRect?: ImageSrcRect;
}

/**
 * Sprint 38：浮動文字框（`<wp:anchor>` 含 `<wps:wsp>/<wps:txbx>`）。
 *
 * 與 FloatImageNode 共用 posH/posV/wrapType 結構，但內容是 paragraphs 而非 rId。
 * 03_complex_table 全套管 fixture 的 "112.12.29" 日期戳印與監造會議記錄等
 * 文檔的位置標籤用此節點型別。
 *
 * 渲染：Layout 端把 textbox 內 paragraphs 走 LineBreaker（lineWidth = textbox.width）
 * 後逐 line 在 abs position fillText。
 */
export interface FloatTextBoxNode {
  type: 'floatTextBox';
  width: Pt;
  height: Pt;
  posH: FloatImageNode['posH'];
  posV: FloatImageNode['posV'];
  wrapType: FloatImageNode['wrapType'];
  behindDoc?: boolean;
  allowOverlap?: boolean;
  /** Text box 內 paragraphs（由 DrawingParser 透過 paragraphFactory callback 解析）*/
  paragraphs: ParagraphNode[];
  /**
   * Sprint 39：`<wps:bodyPr lIns/tIns/rIns/bIns>` text box 內部 padding（EMU → Pt）。
   * OOXML 預設值（Office）：l=91440 EMU=7.2pt、t=45720 EMU=3.6pt、r=91440=7.2pt、b=45720=3.6pt。
   * 未設 → 使用 Office 預設值。
   */
  bodyPr?: {
    leftInset: Pt;
    topInset: Pt;
    rightInset: Pt;
    bottomInset: Pt;
  };
  /**
   * Sprint 39：`<wps:spPr><a:solidFill><a:srgbClr val="RRGGBB"/></a:solidFill>` 背景色。
   * `<a:noFill/>` 或缺漏 → undefined（不畫背景）。
   */
  fill?: HexColor;
  /**
   * Sprint 39：`<wps:spPr><a:ln w="..."><a:solidFill><a:srgbClr val="RRGGBB"/></a:solidFill></a:ln>` 邊框。
   * `<a:noFill/>` 在 `<a:ln>` 內 → undefined（不畫邊框）。
   * width 從 EMU 轉 Pt（1 pt = 12700 EMU）。
   */
  border?: {
    width: Pt;
    color: HexColor;
  };
}

export type InlineNode = RunNode | FieldNode | BreakNode | InlineImageNode | FloatImageNode | FloatTextBoxNode;

/** 段落 */
export interface ParagraphNode {
  type: 'paragraph';
  props: ParagraphProps;
  runs: InlineNode[];
  styleId?: string;   // w:pStyle 參照的樣式 ID
  /**
   * Sprint 125 — 此段落內 `<w:bookmarkStart w:name="...">` 收集的名稱列表（去重）。
   * 包含：段落直屬 bookmarkStart + 段落內任一 w:r 內含的 bookmarkStart。
   * 用於：未來 hyperlink `w:anchor="..."` 反向查詢段落定位（規畫書 §1.9）、
   * REF field 解析、PDF 內部跳轉錨點。
   * Word 自動生成的 `_GoBack` 也會被捕捉、屬正常行為（不影響 render）。
   */
  bookmarks?: string[];
}

// ── 表格 ──────────────────────────────────────────────────────────────────────

export interface CellNode {
  type: 'cell';

  // ── Grid 位置（由 GridResolver 預計算，不可直接使用陣列索引）──
  gridCol: number;         // 0-based，此格起始的 grid column
  gridSpan: number;        // 橫向佔據的 grid column 數
  rowSpan: number;         // 縱向佔據的 row 數（由 vMerge 鏈推算）

  // ── 跨頁 vMerge 處理 ──────────────────────────────────────────────────────
  // isContinuation = true：此格是上方 vMerge 的延續
  //   Renderer 跳過繪製內容，但必須記錄此格以供跨頁邊框抑制判斷：
  //   當 vMerge 跨分頁邊界時，第一頁底部省略 Cell 下邊框、
  //   第二頁頂部省略 Cell 上邊框，形成視覺連通效果。
  isContinuation: boolean;

  /**
   * Cell 內容。Sprint 5 起改為 BlockNode[]（= ParagraphNode | TableNode），
   * 支援巢狀表格。Sprint 4 之前限定 ParagraphNode[]。
   *
   * 大多數 fixture 仍只是 ParagraphNode 序列；只有少數監造文件會有
   * 「cell 內又有小表格」的設計。Renderer / Layout 必須逐一檢查 type。
   */
  content: BlockNode[];
  props: {
    width?: Pt;
    borders?: CellBorders;
    shading?: { fill?: HexColor; color?: HexColor; pattern?: string; };
    margins?: { top?: Pt; bottom?: Pt; left?: Pt; right?: Pt; };
    vAlign?: 'top' | 'center' | 'bottom';
    noWrap?: boolean;
    fitText?: boolean;
    // OOXML §17.18.93 ST_TextDirection 完整 6 種：
    //   水平：lrTb (default)
    //   垂直但 glyph 不轉：tbRl, btLr（少用）
    //   垂直 + glyph 旋轉（V suffix）：lrTbV / tbRlV / tbLrV — Sprint 34 加入
    //   tbRlV 最常見（中文表單第一欄直書「工程名稱」「抽查地點」）
    textDirection?: 'lrTb' | 'tbRl' | 'btLr' | 'lrTbV' | 'tbRlV' | 'tbLrV';
  };
}

export interface RowNode {
  type: 'row';
  cells: CellNode[];
  props: {
    height?: Pt;
    heightRule?: 'auto' | 'atLeast' | 'exact';
    isHeader: boolean;   // w:tblHeader — 換頁後重複標題列
    cantSplit: boolean;  // w:cantSplit — 此列不可跨頁斷裂
  };
}

export interface TableNode {
  type: 'table';
  grid: Pt[];             // 每個 grid column 的寬度，長度 = 總 grid column 數
  rows: RowNode[];
  styleId?: string;       // w:tblStyle
  props: {
    width?: Pt;
    widthType?: 'auto' | 'dxa' | 'pct' | 'nil';
    alignment?: 'left' | 'center' | 'right';
    indent?: Pt;
    cellMargins?: { top?: Pt; bottom?: Pt; left?: Pt; right?: Pt; };
    borders?: CellBorders;
    look?: string;        // w:tblLook hex flags（控制預設樣式套用範圍）
  };
}

export type BlockNode = ParagraphNode | TableNode;

// ── 節（Section）─────────────────────────────────────────────────────────────

export interface SectionNode {
  type: 'section';
  page: {
    width: Pt;
    height: Pt;
    orientation: 'portrait' | 'landscape';
  };
  margins: {
    top: Pt;
    bottom: Pt;
    left: Pt;
    right: Pt;
    header: Pt;   // 頁首距頁面頂端
    footer: Pt;   // 頁尾距頁面底端
    gutter?: Pt;  // 裝訂邊距
  };
  columns?: {
    count: number;
    space?: Pt;
    equalWidth?: boolean;
    /**
     * Sprint 6：個別欄寬（Pt 為單位）。
     *
     * 來自 OOXML `<w:cols><w:col w:w="..." w:space="..."/>...</w:cols>`。
     * 只有當 `equalWidth=false` 且至少一個 `<w:col>` 帶 `w:w` 時填入。
     * 長度應 = `count`。Paginator 使用此陣列覆寫等寬計算。
     */
    colWidths?: Pt[];
    /** 個別欄之間的間距（colWidths 對應）；length = count - 1 */
    colSpaces?: Pt[];
    /**
     * Sprint 10：欄分隔線（OOXML `<w:cols w:sep="true"/>`）。
     *
     * true 時 Renderer 在欄之間 colSpace 中央畫一條垂直線（黑色細線）。
     * 預設 false / undefined 不畫。
     */
    separator?: boolean;
  };
  headerRefs: {
    default?: string;  // rId → word/headerN.xml
    first?: string;
    even?: string;
  };
  footerRefs: {
    default?: string;
    first?: string;
    even?: string;
  };
  titlePage: boolean;            // w:titlePg
  evenAndOddHeaders: boolean;    // 來自 w:settings 的文件層級設定
  body: BlockNode[];             // 此節在 sectPr 之前的所有段落與表格
  /**
   * Section break 類型（OOXML w:type val）。
   *
   * Sprint 4 起 SectionParser 抓出此欄位；
   * undefined 視為預設 'nextPage'（OOXML 規格）。
   *
   * 影響 Paginator 在多 section 文件中如何銜接下一節：
   *   - nextPage  : 跳到下一頁（預設）
   *   - continuous: 在當前頁繼續（不換頁）
   *   - evenPage  : 跳到下一個偶數頁（必要時插入空白頁）
   *   - oddPage   : 跳到下一個奇數頁
   */
  sectionBreakType?: 'nextPage' | 'continuous' | 'evenPage' | 'oddPage';
  /**
   * Document grid（OOXML §17.6.5 w:docGrid）。
   *
   * Sprint 29 引入：中文文件常用 `<w:docGrid w:type="lines" w:linePitch="364"/>`
   * 強制每行 baseline 對齊 grid，line height 因此被 ceil 到 linePitch 的整數倍。
   *
   * - type='lines'：line baseline 落 grid（vertical only）
   * - type='linesAndChars' / 'snapToChars'：暫只用 lines 行為（chars 部分不影響行高）
   * - type='default'：無 grid（不 snap）
   *
   * linePitch 為 Pt（已從 twip 轉換）；未設或為 0 時不 snap。
   */
  docGrid?: {
    type: 'lines' | 'linesAndChars' | 'snapToChars' | 'default';
    linePitch: Pt;
  };
}

// ── 頁首 / 頁尾內容 ───────────────────────────────────────────────────────────

export interface HeaderFooterContent {
  rId: string;
  content: BlockNode[];
}

// ── 文件設定（Sprint 146、word/settings.xml capture-only）────────────────────

/**
 * 文件級設定（OOXML §17.15 settings.xml）。
 *
 * Sprint 146 capture-only:42/42 fixture 都有 settings.xml、但 layout/render 端
 * 暫時不消費。為將來 wire-up（如 defaultTabStop 用於 tab stop 排版、zoom 用於
 * UI 預設縮放、compat 用於 Word 版本相容）鋪路。
 *
 * 欄位皆 optional;capture-only 階段不掛 key 的欄位由 caller 用 `??` 提供 fallback。
 */
export interface DocumentSettings {
  /** w:zoom w:percent：UI 預設縮放百分比（如 100 = 100%）*/
  zoomPercent?: number;
  /** w:defaultTabStop w:val：預設 tab stop 距離（pt、來自 twip 轉換）*/
  defaultTabStop?: Pt;
  /**
   * w:characterSpacingControl w:val:字距控制策略
   *
   * - 'doNotCompress':西文預設、不壓縮標點
   * - 'compressPunctuation':中日韓文預設、壓縮全形標點
   * - 'compressPunctuationAndJapaneseKana':中日韓進階、額外壓縮日文假名
   */
  characterSpacingControl?:
    | 'doNotCompress'
    | 'compressPunctuation'
    | 'compressPunctuationAndJapaneseKana';
  /** w:autoHyphenation:自動斷字開啟 */
  autoHyphenation?: boolean;
  /** w:evenAndOddHeaders:奇偶頁 header/footer 差異化 */
  evenAndOddHeaders?: boolean;
  /** w:trackChanges:追蹤修訂模式啟用 */
  trackChanges?: boolean;
  /** w:proofState:拼字 / 文法檢查狀態 */
  proofState?: {
    spelling?: 'clean' | 'dirty';
    grammar?: 'clean' | 'dirty';
  };
  /** w:footnotePr:footnote 編號 / 位置設定 */
  footnotePr?: {
    /** numRestart:eachPage / eachSect / continuous（未設）*/
    numRestart?: 'continuous' | 'eachPage' | 'eachSect';
    /** numFmt:decimal / lowerLetter / lowerRoman 等 */
    numFmt?: string;
    /** position:pageBottom / beneathText / sectEnd / docEnd */
    position?: 'pageBottom' | 'beneathText' | 'sectEnd' | 'docEnd';
    /** numStart:起始序號（預設 1）*/
    numStart?: number;
  };
  /** w:endnotePr:endnote 編號 / 位置設定（結構同 footnotePr）*/
  endnotePr?: {
    numRestart?: 'continuous' | 'eachPage' | 'eachSect';
    numFmt?: string;
    position?: 'sectEnd' | 'docEnd';
    numStart?: number;
  };
  /**
   * w:compat:相容性設定子元素的名稱列表（如 'spaceForUL' / 'balanceSingleByteDoubleByteWidth'）
   *
   * 不解析每個子元素的詳細參數、僅記錄存在;對應 OOXML §17.15.1.x 各 compat 元素。
   * Wire-up 時 caller 用 `settings.compat?.includes('xxx')` 判定。
   */
  compat?: string[];
}

// ── 註腳 / 尾註內容（Sprint 145、Phase 3.6 capture-only）──────────────────────

/**
 * 單一 footnote / endnote 條目。
 *
 * - id:OOXML w:id 整數(-1 = separator、0 = continuationSeparator、1+ = 普通內容)
 * - type:undefined = 普通 footnote(被 footnoteReference 引用)
 *        'separator' / 'continuationSeparator' / 'continuationNotice' = 預設裝飾
 * - content:footnote 內部段落 + 表格(重用 BlockNode、與 header/footer 結構相同)
 *
 * 本 sprint(145)只做 capture、不 wire-up:42 fixture footnoteReference 0 出現,
 * VR 視覺收益 = 0;留 hook 給 user 提供含 footnoteReference 的 fixture 後 wire-up。
 */
export interface FootnoteContent {
  id: number;
  type?: 'separator' | 'continuationSeparator' | 'continuationNotice';
  content: BlockNode[];
}

// ── 清單編號（Numbering）─────────────────────────────────────────────────────

export interface NumberingLevel {
  ilvl: number;
  numFmt: string;       // 'decimal' | 'bullet' | 'lowerLetter' | 'upperLetter'
                        // | 'lowerRoman' | 'upperRoman' | 'chineseCounting' | ...
  text: string;         // w:lvlText val，例如 "%1." 或 "•"
  start: number;        // w:start val
  lvlRestart?: number;  // w:lvlRestart：0 = 不重啟，N = 遇到 ilvl < N 時重啟
  indent?: { left?: Pt; hanging?: Pt; };
  runProps?: RunProps;
  pProps?: Partial<ParagraphProps>;
  isLegal?: boolean;    // w:isLgl：強制所有層級以十進位顯示
}

export interface AbstractNumbering {
  abstractNumId: number;
  levels: NumberingLevel[];  // index = ilvl（0–8）
}

// ── 樣式 / 編號索引表 ─────────────────────────────────────────────────────────

/**
 * 表格條件樣式 type（OOXML §17.7.6 w:tblStylePr 的 w:type 列舉，共 13–15 種）。
 *
 * 用於 `<w:tblStylePr w:type="firstRow">` 等：套用條件依列/欄位置決定。
 */
export type TableConditionalType =
  | 'wholeTable'
  | 'firstRow' | 'lastRow'
  | 'firstCol' | 'lastCol'
  | 'band1Vert' | 'band2Vert'
  | 'band1Horz' | 'band2Horz'
  | 'neCell' | 'nwCell' | 'seCell' | 'swCell'
  | string;

export interface StyleEntry {
  pProps?: ParagraphProps;
  rProps?: RunProps;
  basedOn?: string;   // 父樣式 ID，繼承鏈由 StyleResolver 展開後不再需要追蹤
  /**
   * 表格條件樣式（type → { pProps, rProps, cProps }）。
   *
   * 僅 `<w:style w:type="table">` 的 entry 會有此欄位。
   * 由 Renderer/Layout Engine 依列/欄位位置選擇套用。
   * StyleResolver 不對其做 basedOn flatten — 條件樣式內容直接保留。
   *
   * Sprint 131：新增 `cProps`（cell-level conditional props）。
   *   subset of CellNode['props']：當前支援 `shading` + `vAlign`（最常用的兩個）。
   *   borders / margins / textDirection 需 BorderConflictResolver 整合、defer 未來 sprint。
   */
  conditional?: Map<
    TableConditionalType,
    {
      pProps?: ParagraphProps;
      rProps?: RunProps;
      cProps?: TableConditionalCellProps;
    }
  >;
}

/**
 * Sprint 131：tblStylePr 的 w:tcPr 內可套用的 cell-level 條件 props 子集。
 *
 * 目前實作的 OOXML §17.7.6.4 (tblStylePr) 子元素：
 *   - `w:shd` → shading（header row 背景填色最常見）
 *   - `w:vAlign` → 垂直對齊（標題列置中常用）
 *
 * 暫不實作（defer to future sprint）：
 *   - `w:tcBorders`（需與 BorderConflictResolver 互動、複雜度高）
 *   - `w:tcMar`（margins）
 *   - `w:noWrap` / `w:textDirection`（罕見於條件樣式）
 */
export interface TableConditionalCellProps {
  shading?: { fill?: HexColor; color?: HexColor; pattern?: string };
  vAlign?: 'top' | 'center' | 'bottom';
}

export type StyleMap = Map<string, StyleEntry>;

export type NumberingMap = Map<number, AbstractNumbering>; // numId → resolved abstract numbering

// ── 文件根節點 ────────────────────────────────────────────────────────────────

export interface DocumentNode {
  type: 'document';
  sections: SectionNode[];
  headers: Map<string, HeaderFooterContent>;  // rId → 內容
  footers: Map<string, HeaderFooterContent>;  // rId → 內容
  /** Sprint 145：footnotes.xml 解析結果（id → 內容）；fixture 0 覆蓋時為空 Map */
  footnotes: Map<number, FootnoteContent>;
  /** Sprint 145：endnotes.xml 解析結果（id → 內容）；fixture 0 覆蓋時為空 Map */
  endnotes: Map<number, FootnoteContent>;
  /** Sprint 146：settings.xml 解析結果（capture-only、欄位皆 optional、空物件代表「無設定 part」）*/
  settings: DocumentSettings;
  styles: StyleMap;
  numbering: NumberingMap;
  media: Map<string, string>;  // rId → blob URL 或 base64 data URL（圖片）
  /**
   * Sprint 13：docProps/core.xml 解析結果。
   *
   * 欄位來源（OOXML §22.2 / Dublin Core + cp namespace）：
   *   - title       ← `<dc:title>`
   *   - creator     ← `<dc:creator>` （第一作者）
   *   - subject     ← `<dc:subject>`
   *   - description ← `<dc:description>`
   *   - keywords    ← `<cp:keywords>`
   *   - lastModifiedBy ← `<cp:lastModifiedBy>`
   *   - created     ← `<dcterms:created>` （ISO datetime）
   *   - modified    ← `<dcterms:modified>`
   *
   * 缺檔 / 解析失敗 → docProps 為空物件 `{}`，欄位 undefined。
   * Layout caller 可把這些值對應到 LayoutOptions.documentMetadata。
   */
  docProps: DocProps;
}

export interface DocProps {
  title?: string;
  creator?: string;
  subject?: string;
  description?: string;
  keywords?: string;
  lastModifiedBy?: string;
  created?: string;   // ISO datetime
  modified?: string;  // ISO datetime
}
