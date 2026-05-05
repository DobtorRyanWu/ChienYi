/**
 * ParagraphParser — 解析 <w:p>（段落）與內部 <w:r>（Run）
 *
 * 處理範圍（Sprint 1）：
 *   - w:pPr 段落屬性：jc, ind, spacing, pStyle, numPr, keepNext, pageBreakBefore
 *   - w:rPr Run 屬性：rFonts, sz, b, i, u, strike, color, highlight, vertAlign
 *   - w:t 文字（含 xml:space="preserve" 保留空白）
 *   - w:br type="line|page|column" → BreakNode
 *   - w:tab → 暫時當文字 "\t"
 *   - w:fldSimple instr="..." → FieldNode
 *
 * 設計原則：
 *   - 用 getElementsByTagName(qualifiedName) 而非 getElementsByTagNameNS
 *     （happy-dom 對預設命名空間 NS 查詢有缺陷；此 walker 全環境一致）
 *   - 只處理「直接子節點」，不遞迴尋找（OOXML 結構非 free-form HTML）
 *   - 樣式繼承鏈交給 StyleResolver 在 Sprint 2 處理；本 Parser 只解 in-line 屬性
 *
 * Sprint 1 issue #4 + #5 + #6
 */

import { twipToPt, halfPointToPt } from '../units/units';
import type {
  Alignment,
  BreakNode,
  FieldNode,
  InlineNode,
  LineSpacingRule,
  ParagraphNode,
  ParagraphProps,
  Pt,
  RunNode,
  RunProps,
  Underline,
  VertAlign,
} from '../ast/types';

// ── 對外 ──────────────────────────────────────────────────────────────────────

export class ParagraphParser {
  /**
   * 解析單一 <w:p> Element 為 ParagraphNode。
   * @param p w:p 元素（已是 DOM Element）
   */
  parse(p: Element): ParagraphNode {
    const pPrEl = directChild(p, 'w:pPr');
    const props = pPrEl ? parseParagraphProps(pPrEl) : {};
    const styleId = pPrEl
      ? attr(directChild(pPrEl, 'w:pStyle'), 'w:val')
      : undefined;

    const runs: InlineNode[] = [];
    for (const child of directChildren(p)) {
      switch (child.tagName) {
        case 'w:r':
          for (const node of parseRun(child)) runs.push(node);
          break;
        case 'w:fldSimple':
          runs.push(parseFldSimple(child));
          break;
        case 'w:hyperlink':
          // hyperlink 內含 w:r，視同包裹 — 直接展平 runs
          for (const r of directChildren(child)) {
            if (r.tagName === 'w:r') {
              for (const node of parseRun(r)) runs.push(node);
            }
          }
          break;
        // w:pPr 已先處理；其他子節點 (w:bookmarkStart, w:proofErr) 暫時忽略
      }
    }

    const node: ParagraphNode = {
      type: 'paragraph',
      props,
      runs,
    };
    if (styleId) node.styleId = styleId;
    return node;
  }
}

// ── w:pPr ─────────────────────────────────────────────────────────────────────

function parseParagraphProps(pPr: Element): ParagraphProps {
  const props: ParagraphProps = {};

  const jc = attr(directChild(pPr, 'w:jc'), 'w:val');
  if (jc) {
    const a = mapAlignment(jc);
    if (a) props.alignment = a;
  }

  const indEl = directChild(pPr, 'w:ind');
  if (indEl) {
    const indent: ParagraphProps['indent'] = {};
    const left = attrTwip(indEl, 'w:left') ?? attrTwip(indEl, 'w:start');
    const right = attrTwip(indEl, 'w:right') ?? attrTwip(indEl, 'w:end');
    const firstLine = attrTwip(indEl, 'w:firstLine');
    const hanging = attrTwip(indEl, 'w:hanging');
    if (left !== undefined) indent.left = left;
    if (right !== undefined) indent.right = right;
    if (firstLine !== undefined) indent.firstLine = firstLine;
    if (hanging !== undefined) indent.hanging = hanging;
    if (Object.keys(indent).length > 0) props.indent = indent;
  }

  const spEl = directChild(pPr, 'w:spacing');
  if (spEl) {
    const spacing: ParagraphProps['spacing'] = {};
    const before = attrTwip(spEl, 'w:before');
    const after = attrTwip(spEl, 'w:after');
    if (before !== undefined) spacing.before = before;
    if (after !== undefined) spacing.after = after;

    const lineRaw = spEl.getAttribute('w:line');
    const ruleRaw = spEl.getAttribute('w:lineRule');
    if (lineRaw) {
      const line = parseInt(lineRaw, 10);
      if (Number.isFinite(line)) {
        const rule = mapLineSpacingRule(ruleRaw);
        // auto 規則用 240 分母（Word 慣例）；其餘 rule 與 exact/atLeast 用 twip
        const value: Pt =
          rule === 'auto' ? line / 240 : twipToPt(line);
        spacing.line = { rule, value };
      }
    }
    if (Object.keys(spacing).length > 0) props.spacing = spacing;
  }

  const numPrEl = directChild(pPr, 'w:numPr');
  if (numPrEl) {
    const ilvlVal = attr(directChild(numPrEl, 'w:ilvl'), 'w:val');
    const numIdVal = attr(directChild(numPrEl, 'w:numId'), 'w:val');
    if (ilvlVal !== undefined) {
      const n = parseInt(ilvlVal, 10);
      if (Number.isFinite(n)) props.ilvl = n;
    }
    if (numIdVal !== undefined) {
      const n = parseInt(numIdVal, 10);
      if (Number.isFinite(n)) props.numId = n;
    }
  }

  if (boolFlag(directChild(pPr, 'w:keepNext'))) props.keepNext = true;
  if (boolFlag(directChild(pPr, 'w:keepLines'))) props.keepLines = true;
  if (boolFlag(directChild(pPr, 'w:pageBreakBefore'))) props.pageBreakBefore = true;

  return props;
}

// ── w:r → RunNode[]（單一 run 可能因 w:br 等切多筆） ─────────────────────────

function parseRun(r: Element): InlineNode[] {
  const rPrEl = directChild(r, 'w:rPr');
  const baseProps = rPrEl ? parseRunProps(rPrEl) : {};
  const out: InlineNode[] = [];
  let textBuf = '';

  const flushText = (): void => {
    if (textBuf.length === 0) return;
    out.push({ type: 'run', text: textBuf, props: { ...baseProps } });
    textBuf = '';
  };

  for (const child of directChildren(r)) {
    switch (child.tagName) {
      case 'w:t': {
        // xml:space="preserve" → 保留前後空白
        // 注意：DOM 對缺省屬性取出可能是 null，不影響 textContent 讀取
        textBuf += child.textContent ?? '';
        break;
      }
      case 'w:br': {
        flushText();
        const t = child.getAttribute('w:type');
        const breakType: BreakNode['breakType'] =
          t === 'page' ? 'page' : t === 'column' ? 'column' : 'line';
        out.push({ type: 'break', breakType });
        break;
      }
      case 'w:tab':
        textBuf += '\t';
        break;
      case 'w:noBreakHyphen':
        textBuf += '‑'; // non-breaking hyphen
        break;
      case 'w:softHyphen':
        textBuf += '­'; // soft hyphen
        break;
      case 'w:cr':
        textBuf += '\n';
        break;
      // w:rPr 已先處理；w:drawing / w:pict / w:fldChar 暫不處理（Sprint 3 Drawing）
    }
  }

  flushText();
  return out;
}

// ── w:rPr ─────────────────────────────────────────────────────────────────────

function parseRunProps(rPr: Element): RunProps {
  const props: RunProps = {};

  const fontsEl = directChild(rPr, 'w:rFonts');
  if (fontsEl) {
    const ascii = fontsEl.getAttribute('w:ascii');
    const east = fontsEl.getAttribute('w:eastAsia');
    if (ascii) props.fontFamily = ascii;
    if (east) props.fontFamilyEastAsia = east;
  }

  // w:sz 與 w:szCs 都是 half-point；CS 給 complex script。先用 w:sz。
  const szVal = attr(directChild(rPr, 'w:sz'), 'w:val');
  if (szVal !== undefined) {
    const n = parseInt(szVal, 10);
    if (Number.isFinite(n)) props.fontSize = halfPointToPt(n);
  }

  if (boolFlag(directChild(rPr, 'w:b'))) props.bold = true;
  if (boolFlag(directChild(rPr, 'w:i'))) props.italic = true;
  if (boolFlag(directChild(rPr, 'w:strike'))) props.strike = true;
  if (boolFlag(directChild(rPr, 'w:dstrike'))) props.dstrike = true;

  const uVal = attr(directChild(rPr, 'w:u'), 'w:val');
  if (uVal) props.underline = uVal as Underline;

  const colorVal = attr(directChild(rPr, 'w:color'), 'w:val');
  if (colorVal) props.color = colorVal;

  // w:highlight 用具名色（yellow/cyan/...）；w:shd val + w:fill 才是 hex shading
  const highlight = attr(directChild(rPr, 'w:highlight'), 'w:val');
  if (highlight) props.highlight = highlight;

  const vert = attr(directChild(rPr, 'w:vertAlign'), 'w:val');
  if (vert === 'superscript' || vert === 'subscript' || vert === 'baseline') {
    props.vertAlign = vert as VertAlign;
  }

  const spacing = attr(directChild(rPr, 'w:spacing'), 'w:val');
  if (spacing !== undefined) {
    const n = parseInt(spacing, 10);
    if (Number.isFinite(n)) props.spacing = twipToPt(n);
  }

  const lang = attr(directChild(rPr, 'w:lang'), 'w:val');
  if (lang) props.lang = lang;

  return props;
}

// ── w:fldSimple → FieldNode ──────────────────────────────────────────────────

function parseFldSimple(el: Element): FieldNode {
  const instruction = (el.getAttribute('w:instr') ?? '').trim();
  // 第一個非空字 token 視為 fieldType，並轉大寫
  const firstToken = instruction.split(/\s+/)[0]?.toUpperCase() ?? '';
  const knownTypes = ['PAGE', 'NUMPAGES', 'DATE', 'TIME', 'AUTHOR', 'FILENAME'] as const;
  type Known = (typeof knownTypes)[number];
  const fieldType: FieldNode['fieldType'] = (knownTypes as readonly string[]).includes(
    firstToken,
  )
    ? (firstToken as Known)
    : 'unknown';

  // 快取值：fldSimple 內部的 w:r → w:t 串接
  let cached = '';
  for (const r of directChildren(el)) {
    if (r.tagName !== 'w:r') continue;
    for (const t of directChildren(r)) {
      if (t.tagName === 'w:t') cached += t.textContent ?? '';
    }
  }

  const node: FieldNode = { type: 'field', instruction, fieldType };
  if (cached) node.cachedValue = cached;
  return node;
}

// ── 共用工具 ──────────────────────────────────────────────────────────────────

function directChildren(el: Element): Element[] {
  const out: Element[] = [];
  const children = el.childNodes;
  for (let i = 0; i < children.length; i++) {
    const n = children[i];
    if (n.nodeType === 1) out.push(n as Element);
  }
  return out;
}

function directChild(el: Element | undefined | null, tagName: string): Element | undefined {
  if (!el) return undefined;
  for (const child of directChildren(el)) {
    if (child.tagName === tagName) return child;
  }
  return undefined;
}

function attr(el: Element | undefined, name: string): string | undefined {
  if (!el) return undefined;
  const v = el.getAttribute(name);
  return v === null ? undefined : v;
}

function attrTwip(el: Element | undefined, name: string): Pt | undefined {
  const v = attr(el, name);
  if (v === undefined) return undefined;
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? twipToPt(n) : undefined;
}

/**
 * OOXML 布林屬性慣例：
 *   - 元素存在且無 w:val 屬性 → true
 *   - w:val="0" / "false" → false
 *   - w:val="1" / "true"  → true
 */
function boolFlag(el: Element | undefined): boolean {
  if (!el) return false;
  const v = el.getAttribute('w:val');
  if (v === null) return true;
  return v !== '0' && v.toLowerCase() !== 'false';
}

function mapAlignment(jc: string): Alignment | undefined {
  switch (jc) {
    case 'left':
    case 'start':
      return 'left';
    case 'right':
    case 'end':
      return 'right';
    case 'center':
      return 'center';
    case 'both':
    case 'justify':
      return 'justify';
    case 'distribute':
      return 'distribute';
    default:
      return undefined;
  }
}

function mapLineSpacingRule(rule: string | null): LineSpacingRule {
  if (rule === 'exact') return 'exact';
  if (rule === 'atLeast') return 'atLeast';
  return 'auto';
}

// 對外便捷 export，供 RunNode 型別使用者
export type { RunNode };
