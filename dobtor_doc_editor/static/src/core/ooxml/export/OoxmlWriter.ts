/**
 * OoxmlWriter — DocumentNode → .docx ArrayBuffer / Uint8Array（Phase 6 docx export）
 *
 * Sprint 185 — Phase 6 minimum viable slice（MVS）：
 *   把 OoxmlParser 的「parse」反向：DocumentNode → ZIP package。本 sprint 走通
 *   end-to-end 骨架，覆蓋率最小但 round-trip 可驗證（規畫書 §6 黃金測試
 *   `import(export(doc))` ≅ `doc`）。
 *
 * MVS 覆蓋（scope-down 紀律 #18）：
 *   - paragraph + run（純文字）
 *   - 單 section 的 pgSz / pgMar（pt → twips）
 *   - `[Content_Types].xml` / `_rels/.rels` / `word/_rels/document.xml.rels` /
 *     `word/styles.xml`（空骨架）/ `word/document.xml`
 *
 * MVS 不覆蓋（後續 sprint 逐步補）：
 *   - RunProps / ParagraphProps（粗體/斜體/字級/顏色/對齊/縮排等）
 *   - 樣式繼承（styles.xml 完整輸出）/ numbering / 多 section
 *   - 表格 / 圖片 / 頁首頁尾 / 註腳 / 註解
 *   - Phase 5 子功能（OMML / SmartArt / Chart / 浮水印 / 追蹤修訂）
 *   - docProps / appProps / customProps / fontTable / settings / webSettings
 *
 * 架構：per-part writer 函式（鏡像 parser 的 per-part class）、
 * 主流程 `write()` orchestrator 組裝 + fflate `zipSync` 打包。
 */

import { zipSync, strToU8 } from 'fflate';
import type {
  BlockNode,
  CellBorders,
  CellNode,
  DocumentNode,
  ParagraphNode,
  ParagraphProps,
  RowNode,
  RunNode,
  RunProps,
  SectionNode,
  TableNode,
} from '../ast/types';

/** OOXML wordprocessingml 命名空間 URI。 */
const W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';
/** Package relationships 命名空間 URI。 */
const REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships';
/** Content Types 命名空間 URI。 */
const CT_NS = 'http://schemas.openxmlformats.org/package/2006/content-types';
/** officeDocument 關係型別（root rels → word/document.xml）。 */
const REL_TYPE_OFFICE_DOCUMENT =
  'http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument';
/** styles 關係型別（document.xml.rels → styles.xml）。 */
const REL_TYPE_STYLES =
  'http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles';

/** 1 pt = 20 twips（OOXML 度量單位、§17.18.85）。 */
const TWIPS_PER_PT = 20;
/** 1 pt = 2 half-points（`<w:sz>` 用半 pt 單位、OOXML §17.3.2.39）。 */
const HALF_POINTS_PER_PT = 2;
/** `w:line` 的 auto 規則分母（240 = 單行、360 = 1.5 行；OOXML §17.3.1.33）。 */
const LINE_SPACING_AUTO_BASE = 240;
/** 邊框寬度單位：`<w:sz>` 為 1/8 pt（OOXML §17.3.1.23 CT_Border）。 */
const BORDER_EIGHTHS_PER_PT = 8;

/** A4 直式預設頁面尺寸（pt），section.page 缺漏時 fallback。 */
const DEFAULT_PAGE_WIDTH_PT = 595.3;
const DEFAULT_PAGE_HEIGHT_PT = 841.9;
/** Word 預設邊距（pt），section.margins 缺漏時 fallback（top/bottom 72pt = 2.54cm）。 */
const DEFAULT_MARGIN_TB_PT = 72;
const DEFAULT_MARGIN_LR_PT = 72;
const DEFAULT_MARGIN_HF_PT = 36;

export class OoxmlWriter {
  /**
   * 把 DocumentNode 序列化為 .docx（OPC ZIP package）位元組。
   *
   * @param doc 由 OoxmlParser.parse 產出（或 caller 手構）的 DocumentNode
   * @returns .docx 的 Uint8Array；caller 可 `.buffer` 取 ArrayBuffer 寫檔
   */
  write(doc: DocumentNode): Uint8Array {
    const parts: { [path: string]: Uint8Array } = {
      '[Content_Types].xml': strToU8(writeContentTypes()),
      '_rels/.rels': strToU8(writeRootRels()),
      'word/_rels/document.xml.rels': strToU8(writeDocumentRels()),
      'word/document.xml': strToU8(writeDocument(doc)),
      'word/styles.xml': strToU8(writeStyles(doc)),
    };
    return zipSync(parts);
  }
}

// ── 各 part 寫出函式 ─────────────────────────────────────────────────────────

/** `[Content_Types].xml`：宣告 MVS 範圍內的 part MIME 型別。 */
function writeContentTypes(): string {
  return xmlDecl() +
    `<Types xmlns="${CT_NS}">` +
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
    '<Default Extension="xml" ContentType="application/xml"/>' +
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>' +
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>' +
    '</Types>';
}

/** `_rels/.rels`：root 關係（→ word/document.xml）。 */
function writeRootRels(): string {
  return xmlDecl() +
    `<Relationships xmlns="${REL_NS}">` +
    `<Relationship Id="rId1" Type="${REL_TYPE_OFFICE_DOCUMENT}" Target="word/document.xml"/>` +
    '</Relationships>';
}

/** `word/_rels/document.xml.rels`：document 的關係（MVS 僅 styles）。 */
function writeDocumentRels(): string {
  return xmlDecl() +
    `<Relationships xmlns="${REL_NS}">` +
    `<Relationship Id="rId1" Type="${REL_TYPE_STYLES}" Target="styles.xml"/>` +
    '</Relationships>';
}

/**
 * `word/styles.xml`：Sprint 189 完整輸出 DocumentNode.styles。
 *
 * 序列化策略（與 parser StyleResolver 對稱）：
 *   - DocumentNode.styles 為 StyleMap = Map<styleId, StyleEntry>。
 *   - StyleResolver 在 parse 時把 docDefaults → basedOn 鏈 → current props 全部
 *     flatten 進 entry.pProps / entry.rProps，故 export **不需**輸出
 *     `<w:docDefaults>` 與 `<w:basedOn>`（re-parse 時 resolver 看不到 docDefaults
 *     與 basedOn、entry 的 flat props 原樣保留 → round-trip 等價）。
 *   - 每個 style 統一 `w:type="paragraph"`（StyleEntry 不保留 type、type 在
 *     re-parse 時不影響 pProps/rProps 解析結果）。
 *   - StyleEntry.name / conditional table styles 留後續 sprint。
 *
 * 空 StyleMap → 空 `<w:styles/>` 骨架（與 Sprint 185 MVS 相容）。
 */
function writeStyles(doc: DocumentNode): string {
  if (doc.styles.size === 0) {
    return xmlDecl() + `<w:styles xmlns:w="${W_NS}"/>`;
  }
  const entries: string[] = [];
  for (const [styleId, entry] of doc.styles) {
    entries.push(writeStyleEntry(styleId, entry));
  }
  return xmlDecl() +
    `<w:styles xmlns:w="${W_NS}">` +
    entries.join('') +
    '</w:styles>';
}

/**
 * Sprint 189：序列化單一 StyleEntry 為 `<w:style w:type="paragraph" w:styleId="...">`。
 *
 * 內容：可選 `<w:pPr>` + `<w:rPr>`。pProps / rProps 皆無 → 空 body（`<w:style/>`）；
 * 保持 styleId 鍵的存在性以便 round-trip Map 大小一致。
 */
function writeStyleEntry(styleId: string, entry: { pProps?: ParagraphProps; rProps?: RunProps }): string {
  const pPrXml = writePPr(entry.pProps ?? {}, undefined);
  const rPrXml = writeRPr(entry.rProps ?? {});
  const inner = pPrXml + rPrXml;
  const attrs = `w:type="paragraph" w:styleId="${escapeXml(styleId)}"`;
  return inner === ''
    ? `<w:style ${attrs}/>`
    : `<w:style ${attrs}>${inner}</w:style>`;
}

/**
 * `word/document.xml`：把 DocumentNode 序列化為 `<w:document>`。
 *
 * MVS 策略：把所有 section 的段落串成單一 body、用**最後一個** section 的
 * page/margins 作為 trailing `<w:sectPr>`。多 section 場景退化為單 section
 * （多 section 區隔資訊有損；後續 sprint 補）。
 */
function writeDocument(doc: DocumentNode): string {
  const blocks: string[] = [];
  for (const sec of doc.sections) {
    for (const block of sec.body) {
      blocks.push(writeBlock(block));
    }
  }
  const sectPr = writeSectPr(doc.sections[doc.sections.length - 1]);

  return xmlDecl() +
    `<w:document xmlns:w="${W_NS}">` +
    '<w:body>' +
    blocks.join('') +
    sectPr +
    '</w:body>' +
    '</w:document>';
}

/**
 * Sprint 190：把 BlockNode（paragraph / table）序列化。
 * 巢狀表格用 —— cell.content 內亦呼叫此函式遞迴處理。
 */
function writeBlock(block: BlockNode): string {
  return block.type === 'paragraph' ? writeParagraph(block) : writeTable(block);
}

/**
 * 單一段落 `<w:p>`：可選 `<w:pPr>` + 各 RunNode。
 *
 * Sprint 187：加 ParagraphProps + styleId 序列化、`<w:pPr>` 子元素依 CT_PPr
 * schema 順序輸出（pStyle → keepNext → keepLines → pageBreakBefore → numPr →
 * tabs → spacing → ind → jc → textAlignment → snapToGrid）。
 */
function writeParagraph(para: ParagraphNode): string {
  const pPr = writePPr(para.props, para.styleId);
  const runs: string[] = [];
  for (const node of para.runs) {
    if (node.type === 'run') runs.push(writeRun(node));
  }
  return `<w:p>${pPr}${runs.join('')}</w:p>`;
}

/**
 * Sprint 187：把 ParagraphProps + styleId 序列化為 `<w:pPr>` 屬性容器。
 *
 * 子元素順序依 OOXML CT_PPr schema（§17.3.1）大致排序。紀律 #21：欄位皆
 * optional、無值不掛子元素；props 全空且無 styleId → 回空字串
 * （不輸出 `<w:pPr>` 標籤、與 parser「無 pPr 視為無 props」對稱）。
 *
 * 本 sprint 覆蓋：pStyle / keepNext / keepLines / pageBreakBefore / numPr
 * (numId+ilvl) / tabs / spacing / ind / jc / textAlignment / snapToGrid。
 * 留後續：borders（pBdr）/ shading（shd）/ framePr。
 */
function writePPr(props: ParagraphProps, styleId: string | undefined): string {
  const parts: string[] = [];

  // 1. <w:pStyle> — 段落樣式 ID（CT_PPr schema 第一個子元素）
  if (styleId !== undefined && styleId !== '') {
    parts.push(`<w:pStyle w:val="${escapeXml(styleId)}"/>`);
  }

  // 2-4. toggle properties（true=空 element、false=w:val="0" 顯式覆蓋 style）
  if (props.keepNext === true) parts.push('<w:keepNext/>');
  else if (props.keepNext === false) parts.push('<w:keepNext w:val="0"/>');
  if (props.keepLines === true) parts.push('<w:keepLines/>');
  else if (props.keepLines === false) parts.push('<w:keepLines w:val="0"/>');
  if (props.pageBreakBefore === true) parts.push('<w:pageBreakBefore/>');
  else if (props.pageBreakBefore === false) parts.push('<w:pageBreakBefore w:val="0"/>');

  // 5. <w:framePr>：段落框（CT_PPr schema 在 pageBreakBefore 與 numPr 之間）
  const framePrXml = writeFramePr(props.framePr);
  if (framePrXml) parts.push(framePrXml);

  // 6. <w:numPr>：清單編號（ilvl + numId 兩子元素）
  if (props.numId !== undefined || props.ilvl !== undefined) {
    const inner: string[] = [];
    if (props.ilvl !== undefined) inner.push(`<w:ilvl w:val="${props.ilvl}"/>`);
    if (props.numId !== undefined) inner.push(`<w:numId w:val="${props.numId}"/>`);
    parts.push(`<w:numPr>${inner.join('')}</w:numPr>`);
  }

  // 7. <w:pBdr>：段落邊框（CT_PPr schema 在 numPr 之後、tabs 之前）
  const pBdrXml = writePBdr(props.borders);
  if (pBdrXml) parts.push(pBdrXml);

  // 8. <w:shd>：段落底色 / 圖案（CT_PPr schema 在 pBdr 之後）
  const shdXml = writeShd(props.shading);
  if (shdXml) parts.push(shdXml);

  // 9. <w:tabs>：tab stop 陣列
  if (props.tabs && props.tabs.length > 0) {
    const tabEls = props.tabs.map((t) => {
      const attrs = [`w:val="${t.align}"`, `w:pos="${ptToTwips(t.pos)}"`];
      if (t.leader) attrs.push(`w:leader="${escapeXml(t.leader)}"`);
      return `<w:tab ${attrs.join(' ')}/>`;
    });
    parts.push(`<w:tabs>${tabEls.join('')}</w:tabs>`);
  }

  // 10. <w:spacing>：段前 / 段後 / 行距
  if (props.spacing) {
    const attrs: string[] = [];
    if (props.spacing.before !== undefined) attrs.push(`w:before="${ptToTwips(props.spacing.before)}"`);
    if (props.spacing.after !== undefined) attrs.push(`w:after="${ptToTwips(props.spacing.after)}"`);
    if (props.spacing.line) {
      const { rule, value } = props.spacing.line;
      // auto 規則用 240 分母（Word 慣例）；其餘 rule = twips
      const lineVal = rule === 'auto'
        ? Math.round(value * LINE_SPACING_AUTO_BASE)
        : ptToTwips(value);
      attrs.push(`w:line="${lineVal}"`);
      attrs.push(`w:lineRule="${rule}"`);
    }
    if (attrs.length > 0) parts.push(`<w:spacing ${attrs.join(' ')}/>`);
  }

  // 11. <w:ind>：縮排
  if (props.indent) {
    const attrs: string[] = [];
    if (props.indent.left !== undefined) attrs.push(`w:left="${ptToTwips(props.indent.left)}"`);
    if (props.indent.right !== undefined) attrs.push(`w:right="${ptToTwips(props.indent.right)}"`);
    if (props.indent.firstLine !== undefined) attrs.push(`w:firstLine="${ptToTwips(props.indent.firstLine)}"`);
    if (props.indent.hanging !== undefined) attrs.push(`w:hanging="${ptToTwips(props.indent.hanging)}"`);
    if (attrs.length > 0) parts.push(`<w:ind ${attrs.join(' ')}/>`);
  }

  // 12. <w:jc>：水平對齊
  if (props.alignment !== undefined) {
    parts.push(`<w:jc w:val="${props.alignment}"/>`);
  }

  // 13. <w:textAlignment>：行內垂直對齊
  if (props.textAlignment !== undefined) {
    parts.push(`<w:textAlignment w:val="${props.textAlignment}"/>`);
  }

  // 14. <w:snapToGrid>：是否貼齊 docGrid
  if (props.snapToGrid === true) parts.push('<w:snapToGrid/>');
  else if (props.snapToGrid === false) parts.push('<w:snapToGrid w:val="0"/>');

  return parts.length > 0 ? `<w:pPr>${parts.join('')}</w:pPr>` : '';
}

/**
 * Sprint 188：把 `ParagraphProps.framePr` 序列化為 `<w:framePr/>`（自閉合）。
 *
 * 屬性順序對 Word reader 不重要、本實作依 OOXML §17.3.1.11 文件出現順序輸出
 * （w / h / hRule / hSpace / vSpace / wrap / hAnchor / vAnchor / xAlign /
 * yAlign / x / y）。w/h/hSpace/vSpace/x/y 為 twips、其餘列舉值原樣輸出。
 *
 * 紀律 #21：framePr undefined 或所有欄位皆空 → 回空字串、不輸出 `<w:framePr/>`。
 */
function writeFramePr(framePr: ParagraphProps['framePr']): string {
  if (!framePr) return '';
  const attrs: string[] = [];
  if (framePr.width !== undefined) attrs.push(`w:w="${ptToTwips(framePr.width)}"`);
  if (framePr.height !== undefined) attrs.push(`w:h="${ptToTwips(framePr.height)}"`);
  if (framePr.hRule !== undefined) attrs.push(`w:hRule="${framePr.hRule}"`);
  if (framePr.hSpace !== undefined) attrs.push(`w:hSpace="${ptToTwips(framePr.hSpace)}"`);
  if (framePr.vSpace !== undefined) attrs.push(`w:vSpace="${ptToTwips(framePr.vSpace)}"`);
  if (framePr.wrap !== undefined) attrs.push(`w:wrap="${framePr.wrap}"`);
  if (framePr.hAnchor !== undefined) attrs.push(`w:hAnchor="${framePr.hAnchor}"`);
  if (framePr.vAnchor !== undefined) attrs.push(`w:vAnchor="${framePr.vAnchor}"`);
  if (framePr.xAlign !== undefined) attrs.push(`w:xAlign="${framePr.xAlign}"`);
  if (framePr.yAlign !== undefined) attrs.push(`w:yAlign="${framePr.yAlign}"`);
  if (framePr.x !== undefined) attrs.push(`w:x="${ptToTwips(framePr.x)}"`);
  if (framePr.y !== undefined) attrs.push(`w:y="${ptToTwips(framePr.y)}"`);
  return attrs.length > 0 ? `<w:framePr ${attrs.join(' ')}/>` : '';
}

/**
 * Sprint 188：把 `ParagraphProps.borders` 序列化為 `<w:pBdr>`（OOXML §17.3.1.24）。
 *
 * 子元素：`<w:top w:val w:sz w:color w:space/>`、bottom / left / right 同結構。
 * `w:sz` 單位 = 1/8 pt（內部 `BorderDef.width: Pt` × 8、四捨五入）。
 * between / bar 子元素本 sprint 不支援（types.ts 也未含、後續若需要再補）。
 *
 * 紀律 #21：無 borders 或所有邊都 undefined → 回空字串。
 */
function writePBdr(borders: ParagraphProps['borders']): string {
  if (!borders) return '';
  const sides: Array<keyof NonNullable<ParagraphProps['borders']>> = ['top', 'bottom', 'left', 'right'];
  const inner: string[] = [];
  for (const side of sides) {
    const b = borders[side];
    if (!b) continue;
    const attrs = [
      `w:val="${escapeXml(b.style)}"`,
      `w:sz="${Math.round(b.width * BORDER_EIGHTHS_PER_PT)}"`,
      `w:color="${escapeXml(b.color)}"`,
    ];
    if (b.space !== undefined) attrs.push(`w:space="${Math.round(b.space)}"`);
    inner.push(`<w:${side} ${attrs.join(' ')}/>`);
  }
  return inner.length > 0 ? `<w:pBdr>${inner.join('')}</w:pBdr>` : '';
}

/**
 * Sprint 188：把 `ParagraphProps.shading` 序列化為 `<w:shd/>`（OOXML §17.3.5.34）。
 *
 * `shading.pattern` → `w:val`（"clear" / "solid" / "pct10" 等圖案）；
 * `shading.fill` → `w:fill`（背景 hex）；`shading.color` → `w:color`（前景 hex）。
 *
 * 紀律 #21：無 shading 或所有欄位空 → 回空字串。
 */
function writeShd(shading: ParagraphProps['shading']): string {
  if (!shading) return '';
  const attrs: string[] = [];
  if (shading.pattern !== undefined) attrs.push(`w:val="${escapeXml(shading.pattern)}"`);
  if (shading.fill !== undefined) attrs.push(`w:fill="${escapeXml(shading.fill)}"`);
  if (shading.color !== undefined) attrs.push(`w:color="${escapeXml(shading.color)}"`);
  return attrs.length > 0 ? `<w:shd ${attrs.join(' ')}/>` : '';
}

/**
 * 單一文字 run `<w:r>`：含可選 `<w:rPr>` + `<w:t>`。
 *
 * Sprint 186：加 RunProps 序列化（粗體 / 斜體 / 刪除線 / 底線 / 字級 / 顏色 /
 * 字型 / 高亮 / 上下標 / 字距 / 語言）。紀律 #21：無 props 時不輸出 `<w:rPr>`。
 */
function writeRun(run: RunNode): string {
  const rPr = writeRPr(run.props);
  // `xml:space="preserve"` 保留前後空白（OOXML §17.3.3.31）；一律帶上
  return `<w:r>${rPr}<w:t xml:space="preserve">${escapeXml(run.text)}</w:t></w:r>`;
}

/**
 * Sprint 186：把 RunProps 序列化為 `<w:rPr>` 屬性容器。
 *
 * 子元素順序大致依 OOXML CT_RPr schema（§17.3.2）：
 *   rFonts → b → i → strike → dstrike → color → spacing → sz → highlight →
 *   u → vertAlign → lang
 *
 * 紀律 #21：所有欄位皆 optional、無值不掛、props 全空 → 回空字串（不輸出
 * `<w:rPr/>` 標籤、與 parser 「無 rPr 就視為無 props」對稱）。
 */
function writeRPr(props: RunProps): string {
  if (!props || Object.keys(props).length === 0) return '';
  const parts: string[] = [];

  // w:rFonts ascii / eastAsia / hAnsi / cs（缺漏屬性跳過）
  const fontAttrs: string[] = [];
  if (props.fontFamily !== undefined) fontAttrs.push(`w:ascii="${escapeXml(props.fontFamily)}"`);
  if (props.fontFamilyEastAsia !== undefined) fontAttrs.push(`w:eastAsia="${escapeXml(props.fontFamilyEastAsia)}"`);
  if (props.fontFamilyHAnsi !== undefined) fontAttrs.push(`w:hAnsi="${escapeXml(props.fontFamilyHAnsi)}"`);
  if (props.fontFamilyCs !== undefined) fontAttrs.push(`w:cs="${escapeXml(props.fontFamilyCs)}"`);
  if (fontAttrs.length > 0) parts.push(`<w:rFonts ${fontAttrs.join(' ')}/>`);

  // toggle properties：true → 空 element、false → w:val="0"（顯式關閉、覆蓋 style）
  if (props.bold === true) parts.push('<w:b/>');
  else if (props.bold === false) parts.push('<w:b w:val="0"/>');
  if (props.italic === true) parts.push('<w:i/>');
  else if (props.italic === false) parts.push('<w:i w:val="0"/>');
  if (props.strike === true) parts.push('<w:strike/>');
  else if (props.strike === false) parts.push('<w:strike w:val="0"/>');
  if (props.dstrike === true) parts.push('<w:dstrike/>');
  else if (props.dstrike === false) parts.push('<w:dstrike w:val="0"/>');

  // w:color w:val="RRGGBB"（或 auto / themeColor、本 sprint 只支援具體 hex）
  if (props.color !== undefined) parts.push(`<w:color w:val="${escapeXml(props.color)}"/>`);

  // w:spacing w:val（字元間距、單位 = 20 倍 pt = twips；可正可負）
  if (props.spacing !== undefined) parts.push(`<w:spacing w:val="${ptToTwips(props.spacing)}"/>`);

  // w:sz w:val（half-points、12pt = 24）
  if (props.fontSize !== undefined) parts.push(`<w:sz w:val="${ptToHalfPoints(props.fontSize)}"/>`);

  // w:highlight w:val（具名色 yellow / cyan / red…；HexColor 型別也可能裝具名色字串）
  if (props.highlight !== undefined) parts.push(`<w:highlight w:val="${escapeXml(props.highlight)}"/>`);

  // w:u w:val（none / single / double / words / thick / wave / 自訂…）
  if (props.underline !== undefined) parts.push(`<w:u w:val="${escapeXml(props.underline)}"/>`);

  // w:vertAlign w:val（baseline / superscript / subscript）
  if (props.vertAlign !== undefined) parts.push(`<w:vertAlign w:val="${escapeXml(props.vertAlign)}"/>`);

  // w:lang w:val（zh-TW / en-US / ja-JP…）
  if (props.lang !== undefined) parts.push(`<w:lang w:val="${escapeXml(props.lang)}"/>`);

  return parts.length > 0 ? `<w:rPr>${parts.join('')}</w:rPr>` : '';
}

/**
 * `<w:sectPr>` 含 pgSz / pgMar（pt → twips）。section 缺漏 → A4 + Word 預設邊距。
 */
function writeSectPr(section: SectionNode | undefined): string {
  const page = section?.page;
  const margins = section?.margins;
  const w = ptToTwips(page?.width ?? DEFAULT_PAGE_WIDTH_PT);
  const h = ptToTwips(page?.height ?? DEFAULT_PAGE_HEIGHT_PT);
  const top = ptToTwips(margins?.top ?? DEFAULT_MARGIN_TB_PT);
  const right = ptToTwips(margins?.right ?? DEFAULT_MARGIN_LR_PT);
  const bottom = ptToTwips(margins?.bottom ?? DEFAULT_MARGIN_TB_PT);
  const left = ptToTwips(margins?.left ?? DEFAULT_MARGIN_LR_PT);
  const header = ptToTwips(margins?.header ?? DEFAULT_MARGIN_HF_PT);
  const footer = ptToTwips(margins?.footer ?? DEFAULT_MARGIN_HF_PT);
  return '<w:sectPr>' +
    `<w:pgSz w:w="${w}" w:h="${h}"/>` +
    `<w:pgMar w:top="${top}" w:right="${right}" w:bottom="${bottom}" w:left="${left}" w:header="${header}" w:footer="${footer}" w:gutter="0"/>` +
    '</w:sectPr>';
}

// ── Sprint 190：表格序列化 ────────────────────────────────────────────────────

/**
 * Sprint 190：把 TableNode 序列化為 `<w:tbl>`（OOXML §17.4）。
 *
 * 結構：`<w:tbl><w:tblPr>...</w:tblPr><w:tblGrid>...</w:tblGrid>0..N <w:tr>...</w:tr></w:tbl>`。
 */
function writeTable(table: TableNode): string {
  const tblPr = writeTblPr(table.props, table.styleId);
  const tblGrid = writeTblGrid(table.grid);
  const rows = table.rows.map(writeRow).join('');
  return `<w:tbl>${tblPr}${tblGrid}${rows}</w:tbl>`;
}

/**
 * `<w:tblPr>` — 表格層級屬性（OOXML §17.4.59）。
 *
 * 子元素順序（CT_TblPrBase schema）：tblStyle → tblpPr → tblOverlap → bidiVisual →
 * tblStyleRowBandSize → tblStyleColBandSize → tblW → jc → tblCellSpacing →
 * tblInd → tblBorders → shd → tblLayout → tblCellMar → tblLook → tblCaption →
 * tblDescription → tblPrChange
 */
function writeTblPr(props: TableNode['props'], styleId: string | undefined): string {
  const parts: string[] = [];
  if (styleId !== undefined && styleId !== '') {
    parts.push(`<w:tblStyle w:val="${escapeXml(styleId)}"/>`);
  }
  parts.push(writeTblW(props.width, props.widthType));
  if (props.alignment !== undefined) parts.push(`<w:jc w:val="${props.alignment}"/>`);
  if (props.indent !== undefined) {
    parts.push(`<w:tblInd w:w="${ptToTwips(props.indent)}" w:type="dxa"/>`);
  }
  if (props.borders) parts.push(writeBorderSet(props.borders, 'w:tblBorders'));
  if (props.cellMargins) parts.push(writeTblCellMar(props.cellMargins));
  if (props.look !== undefined) parts.push(`<w:tblLook w:val="${escapeXml(props.look)}"/>`);
  return parts.length > 0 ? `<w:tblPr>${parts.filter((p) => p !== '').join('')}</w:tblPr>` : '';
}

/** `<w:tblW>` / `<w:tcW>` 共用：width(Pt) + widthType → twips + w:type 屬性。 */
function writeTblW(
  width: number | undefined,
  widthType: TableNode['props']['widthType'],
): string {
  // 預設 type = 'dxa'；其餘 pct/auto/nil 時 w 用 0（與 parser 對稱、parser 對非 dxa 不讀 width）
  const type = widthType ?? 'dxa';
  const wVal = type === 'dxa' && width !== undefined ? ptToTwips(width) : 0;
  return `<w:tblW w:w="${wVal}" w:type="${type}"/>`;
}

/** `<w:tcW>` (same encoding as tblW but element name 不同)。 */
function writeTcW(width: number | undefined): string {
  if (width === undefined) return '';
  return `<w:tcW w:w="${ptToTwips(width)}" w:type="dxa"/>`;
}

/** `<w:tblCellMar>` 表格層級預設 cell 邊距。 */
function writeTblCellMar(m: NonNullable<TableNode['props']['cellMargins']>): string {
  const parts: string[] = [];
  if (m.top !== undefined) parts.push(`<w:top w:w="${ptToTwips(m.top)}" w:type="dxa"/>`);
  if (m.left !== undefined) parts.push(`<w:left w:w="${ptToTwips(m.left)}" w:type="dxa"/>`);
  if (m.bottom !== undefined) parts.push(`<w:bottom w:w="${ptToTwips(m.bottom)}" w:type="dxa"/>`);
  if (m.right !== undefined) parts.push(`<w:right w:w="${ptToTwips(m.right)}" w:type="dxa"/>`);
  return parts.length > 0 ? `<w:tblCellMar>${parts.join('')}</w:tblCellMar>` : '';
}

/** `<w:tcMar>` cell 層級邊距（與 tblCellMar 同結構）。 */
function writeTcMar(m: NonNullable<CellNode['props']['margins']>): string {
  const parts: string[] = [];
  if (m.top !== undefined) parts.push(`<w:top w:w="${ptToTwips(m.top)}" w:type="dxa"/>`);
  if (m.left !== undefined) parts.push(`<w:left w:w="${ptToTwips(m.left)}" w:type="dxa"/>`);
  if (m.bottom !== undefined) parts.push(`<w:bottom w:w="${ptToTwips(m.bottom)}" w:type="dxa"/>`);
  if (m.right !== undefined) parts.push(`<w:right w:w="${ptToTwips(m.right)}" w:type="dxa"/>`);
  return parts.length > 0 ? `<w:tcMar>${parts.join('')}</w:tcMar>` : '';
}

/**
 * CellBorders → `<w:tblBorders>` 或 `<w:tcBorders>`（依 wrapper 名）。
 *
 * 子元素 top / left / bottom / right / insideH / insideV，皆 BorderDef 結構：
 * w:val / w:sz (1/8 pt) / w:color / w:space。
 */
function writeBorderSet(borders: CellBorders, wrapper: string): string {
  const sides: Array<keyof CellBorders> = ['top', 'left', 'bottom', 'right', 'insideH', 'insideV'];
  const parts: string[] = [];
  for (const side of sides) {
    const b = borders[side];
    if (!b) continue;
    const attrs = [
      `w:val="${escapeXml(b.style)}"`,
      `w:sz="${Math.round(b.width * BORDER_EIGHTHS_PER_PT)}"`,
      `w:color="${escapeXml(b.color)}"`,
    ];
    if (b.space !== undefined) attrs.push(`w:space="${Math.round(b.space)}"`);
    parts.push(`<w:${side} ${attrs.join(' ')}/>`);
  }
  return parts.length > 0 ? `<${wrapper}>${parts.join('')}</${wrapper}>` : '';
}

/** `<w:tblGrid><w:gridCol w:w="N"/>...</w:tblGrid>`：欄寬定義（皆 twips）。 */
function writeTblGrid(grid: TableNode['grid']): string {
  const cols = grid.map((w) => `<w:gridCol w:w="${ptToTwips(w)}"/>`).join('');
  return `<w:tblGrid>${cols}</w:tblGrid>`;
}

/** `<w:tr>` 單一列。 */
function writeRow(row: RowNode): string {
  const trPr = writeTrPr(row.props);
  const cells = row.cells.map(writeCell).join('');
  return `<w:tr>${trPr}${cells}</w:tr>`;
}

/** `<w:trPr>` — 列屬性（OOXML §17.4.81）：trHeight / tblHeader / cantSplit。 */
function writeTrPr(props: RowNode['props']): string {
  const parts: string[] = [];
  if (props.height !== undefined) {
    const rule = props.heightRule ?? 'auto';
    parts.push(`<w:trHeight w:val="${ptToTwips(props.height)}" w:hRule="${rule}"/>`);
  }
  if (props.isHeader) parts.push('<w:tblHeader/>');
  if (props.cantSplit) parts.push('<w:cantSplit/>');
  return parts.length > 0 ? `<w:trPr>${parts.join('')}</w:trPr>` : '';
}

/**
 * `<w:tc>` 單一儲存格。
 *
 * isContinuation=true 的 cell（vMerge 延續格）仍要輸出 `<w:tc>` —— OOXML 的
 * vMerge 機制需要每個邏輯列都有對應 cell、第二列以後的延續格用 `<w:vMerge/>`
 * （無 w:val、預設 = continue）；最上格用 `<w:vMerge w:val="restart"/>` 開始合併。
 *
 * cell content 為 BlockNode[]（可含巢狀表格）→ writeBlock 遞迴。
 */
function writeCell(cell: CellNode): string {
  const tcPr = writeTcPr(cell);
  const content = cell.content.map(writeBlock).join('');
  // 即使 isContinuation = true、cell 內容仍需有至少一個 <w:p>（OOXML 規範：
  // 每個 <w:tc> 必含一個 block-level child）。若 content 空 → 補空段落。
  const body = content !== '' ? content : '<w:p/>';
  return `<w:tc>${tcPr}${body}</w:tc>`;
}

/** `<w:tcPr>` — cell 屬性（OOXML §17.4.70）：寬 / gridSpan / vMerge / borders / shd / margins / vAlign / textDirection / noWrap。 */
function writeTcPr(cell: CellNode): string {
  const parts: string[] = [];
  const p = cell.props;

  // w:tcW
  const tcW = writeTcW(p.width);
  if (tcW !== '') parts.push(tcW);

  // w:gridSpan（>1 才掛）
  if (cell.gridSpan > 1) parts.push(`<w:gridSpan w:val="${cell.gridSpan}"/>`);

  // w:vMerge：rowSpan>1 的起始 cell → restart；isContinuation=true → 預設 continue
  if (cell.isContinuation) {
    parts.push('<w:vMerge/>');
  } else if (cell.rowSpan > 1) {
    parts.push('<w:vMerge w:val="restart"/>');
  }

  // w:tcBorders
  if (p.borders) parts.push(writeBorderSet(p.borders, 'w:tcBorders'));

  // w:shd
  if (p.shading) {
    const attrs: string[] = [];
    if (p.shading.pattern !== undefined) attrs.push(`w:val="${escapeXml(p.shading.pattern)}"`);
    if (p.shading.fill !== undefined) attrs.push(`w:fill="${escapeXml(p.shading.fill)}"`);
    if (p.shading.color !== undefined) attrs.push(`w:color="${escapeXml(p.shading.color)}"`);
    if (attrs.length > 0) parts.push(`<w:shd ${attrs.join(' ')}/>`);
  }

  // w:noWrap
  if (p.noWrap === true) parts.push('<w:noWrap/>');

  // w:tcMar
  if (p.margins) {
    const tcMar = writeTcMar(p.margins);
    if (tcMar !== '') parts.push(tcMar);
  }

  // w:textDirection
  if (p.textDirection !== undefined) {
    parts.push(`<w:textDirection w:val="${p.textDirection}"/>`);
  }

  // w:vAlign
  if (p.vAlign !== undefined) parts.push(`<w:vAlign w:val="${p.vAlign}"/>`);

  // w:tcFitText（OOXML §17.4.65）
  if (p.fitText === true) parts.push('<w:tcFitText/>');

  return parts.length > 0 ? `<w:tcPr>${parts.join('')}</w:tcPr>` : '';
}

// ── 工具 ─────────────────────────────────────────────────────────────────────

/** XML 宣告（OOXML standard：UTF-8、standalone="yes"）。 */
function xmlDecl(): string {
  return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
}

/** XML 字元跳脫：& < > " '。 */
function escapeXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/** pt → twips（四捨五入到整數、OOXML 要求整數）。 */
function ptToTwips(pt: number): number {
  return Math.round(pt * TWIPS_PER_PT);
}

/** pt → half-points（`<w:sz>` 單位、12pt = 24、四捨五入到整數）。 */
function ptToHalfPoints(pt: number): number {
  return Math.round(pt * HALF_POINTS_PER_PT);
}
