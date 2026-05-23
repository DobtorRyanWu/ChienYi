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
  DocumentNode,
  ParagraphNode,
  RunNode,
  SectionNode,
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
      'word/styles.xml': strToU8(writeStyles()),
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

/** `word/styles.xml`：MVS 為空骨架（rels 指向但內容空、Parser 接受）。 */
function writeStyles(): string {
  return xmlDecl() + `<w:styles xmlns:w="${W_NS}"/>`;
}

/**
 * `word/document.xml`：把 DocumentNode 序列化為 `<w:document>`。
 *
 * MVS 策略：把所有 section 的段落串成單一 body、用**最後一個** section 的
 * page/margins 作為 trailing `<w:sectPr>`。多 section 場景退化為單 section
 * （多 section 區隔資訊有損；後續 sprint 補）。
 */
function writeDocument(doc: DocumentNode): string {
  const paragraphs: string[] = [];
  for (const sec of doc.sections) {
    for (const block of sec.body) {
      // MVS：只處理段落、其他 BlockNode 型別（表格）跳過、後續 sprint 補
      if (block.type === 'paragraph') {
        paragraphs.push(writeParagraph(block));
      }
    }
  }
  const sectPr = writeSectPr(doc.sections[doc.sections.length - 1]);

  return xmlDecl() +
    `<w:document xmlns:w="${W_NS}">` +
    '<w:body>' +
    paragraphs.join('') +
    sectPr +
    '</w:body>' +
    '</w:document>';
}

/** 單一段落 `<w:p>`：MVS 僅輸出 RunNode（其他 InlineNode 型別跳過）。 */
function writeParagraph(para: ParagraphNode): string {
  const runs: string[] = [];
  for (const node of para.runs) {
    if (node.type === 'run') runs.push(writeRun(node));
  }
  return `<w:p>${runs.join('')}</w:p>`;
}

/** 單一文字 run `<w:r><w:t>`：MVS 不輸出 `<w:rPr>`（樣式留後續）。 */
function writeRun(run: RunNode): string {
  // `xml:space="preserve"` 保留前後空白（OOXML §17.3.3.31）；MVS 一律帶上
  return `<w:r><w:t xml:space="preserve">${escapeXml(run.text)}</w:t></w:r>`;
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
