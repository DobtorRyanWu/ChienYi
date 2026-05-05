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
  fontFamily?: string;
  fontFamilyEastAsia?: string;  // w:eastAsia（CJK 字型）
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
  numId?: number;    // 清單編號 ID（來自 numbering.xml）
  ilvl?: number;     // 清單縮排層級（0-based）
  tabs?: Array<{ pos: Pt; align: 'left' | 'right' | 'center' | 'decimal'; leader?: string; }>;
}

// ── 文件內嵌元素（Inline Nodes）──────────────────────────────────────────────

/** 文字 Run */
export interface RunNode {
  type: 'run';
  text: string;
  props: RunProps;
  metrics?: LineMetrics; // Phase 1 為 undefined，Phase 2 填入
}

/** 欄位（PAGE、DATE、AUTHOR 等）*/
export interface FieldNode {
  type: 'field';
  instruction: string;  // 原始 field instruction，例如 " PAGE " 或 " DATE \\@ \"yyyy/MM/dd\" "
  fieldType: 'PAGE' | 'NUMPAGES' | 'DATE' | 'TIME' | 'AUTHOR' | 'FILENAME' | 'unknown';
  cachedValue?: string; // w:fldSimple 內的 w:t 快取值
}

/** 換行 */
export interface BreakNode {
  type: 'break';
  breakType: 'line' | 'page' | 'column';
}

/** 內嵌圖片（wp:inline）*/
export interface InlineImageNode {
  type: 'inlineImage';
  rId: string;      // 關係 ID，Renderer 解析為 blob URL
  width: Pt;
  height: Pt;
  altText?: string;
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
}

export type InlineNode = RunNode | FieldNode | BreakNode | InlineImageNode | FloatImageNode;

/** 段落 */
export interface ParagraphNode {
  type: 'paragraph';
  props: ParagraphProps;
  runs: InlineNode[];
  styleId?: string;   // w:pStyle 參照的樣式 ID
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

  content: ParagraphNode[];
  props: {
    width?: Pt;
    borders?: CellBorders;
    shading?: { fill?: HexColor; color?: HexColor; pattern?: string; };
    margins?: { top?: Pt; bottom?: Pt; left?: Pt; right?: Pt; };
    vAlign?: 'top' | 'center' | 'bottom';
    noWrap?: boolean;
    fitText?: boolean;
    textDirection?: 'lrTb' | 'tbRl' | 'btLr'; // 文字方向
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
}

// ── 頁首 / 頁尾內容 ───────────────────────────────────────────────────────────

export interface HeaderFooterContent {
  rId: string;
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

export type StyleMap = Map<string, {
  pProps?: ParagraphProps;
  rProps?: RunProps;
  basedOn?: string;   // 父樣式 ID，繼承鏈由 StyleResolver 展開後不再需要追蹤
}>;

export type NumberingMap = Map<number, AbstractNumbering>; // numId → resolved abstract numbering

// ── 文件根節點 ────────────────────────────────────────────────────────────────

export interface DocumentNode {
  type: 'document';
  sections: SectionNode[];
  headers: Map<string, HeaderFooterContent>;  // rId → 內容
  footers: Map<string, HeaderFooterContent>;  // rId → 內容
  styles: StyleMap;
  numbering: NumberingMap;
  media: Map<string, string>;  // rId → blob URL 或 base64 data URL（圖片）
}
