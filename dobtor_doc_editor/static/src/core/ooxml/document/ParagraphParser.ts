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
import { DrawingParser } from '../drawing/DrawingParser';
import { effectiveChildren } from '../utils/dom';
import { resolveColorElement } from '../styles/colorResolver';
import type { ThemeMap } from '../styles/ThemeResolver';
import type {
  Alignment,
  BreakNode,
  FieldNode,
  HyperlinkInfo,
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

const drawingParser = new DrawingParser();

/**
 * Sprint 38：module-level「目前正在解析的 ParagraphParser 實例」reference。
 *
 * 由 ParagraphParser.parse() 在入口處 push、出口處 pop，讓 module-level 函式
 * （parseRun）可以回呼到目前實例（保留 relsLookup / themeMap 等狀態）。
 *
 * 用於 anchor text box (`<wp:anchor><wps:wsp><wps:txbx><w:txbxContent>`) 遞迴解析
 * 內部 `<w:p>`：DrawingParser.parse 接受 paragraphFactory callback。
 */
let currentParagraphParser: ParagraphParser | null = null;

/**
 * Module-scoped ThemeMap，由 setThemeMapForParser() / ParagraphParser.setThemeMap 賦值。
 * parseRunProps / parseParagraphProps 為 named export（不在 class），
 * 此中介變數允許 module-level 函式存取 ThemeMap 而不需重整 API。
 *
 * 對外 named export `setThemeMapForParser` 讓 StyleResolver、test 等其他位置也能直接設定。
 */
let themeMapForParser: ThemeMap | null = null;

export function setThemeMapForParser(theme: ThemeMap | null): void {
  themeMapForParser = theme;
}

/**
 * 把 rId 解析為 External URL 的查詢函式介面。
 *
 * 由 OoxmlParser 在 parse() 時把 mainDoc 的 rels 轉成此介面注入 ParagraphParser，
 * 解析 hyperlink 時即可從 rId 取得實際 URL。
 *
 * 不傳時 hyperlink 仍會解析（rId / anchor / tooltip 會記錄），只是 url 為空。
 */
export type RelsLookup = (rId: string) => string | undefined;

// ── 對外 ──────────────────────────────────────────────────────────────────────

export class ParagraphParser {
  /**
   * 由外部注入的 rId → URL 查詢函式（hyperlink 解析用）。
   *
   * OoxmlParser orchestrator 會在 parse() 開始時設定一次。
   * 若未設定，hyperlink 仍會解析 rId/anchor/tooltip，但 url 會留空。
   */
  private relsLookup?: RelsLookup;

  /**
   * 注入 rels 查詢函式。
   *
   * @example
   *   parser.setRelsLookup((rId) => pkg.relationships.get('word/document.xml')?.get(rId)
   *     ?.targetMode === 'External' ? rels.get(rId).target : undefined);
   */
  setRelsLookup(fn: RelsLookup | undefined): void {
    this.relsLookup = fn;
  }

  /**
   * Phase 4.1：設定 ThemeMap（給 parseRunProps / parseParagraphProps 用以解 themeColor）
   *
   * parseRunProps 是 module-level named export（Phase B+ ADR-008.4），無法直接
   * 從 class state 讀；所以用 module-scoped variable themeMapForParser 中介，
   * 由此 setter 賦值。
   */
  setThemeMap(theme: ThemeMap | null): void {
    setThemeMapForParser(theme);
  }

  /**
   * 解析單一 <w:p> Element 為 ParagraphNode。
   * @param p w:p 元素（已是 DOM Element）
   */
  parse(p: Element): ParagraphNode {
    // Sprint 38：把自己 push 到 module-level current 變數，讓 parseRun 在處理
    // `<w:drawing>` 時能回呼到本實例（保留 relsLookup / themeMap 狀態）。
    // 用 try/finally 確保 nested 呼叫 ( anchor text box 內 paragraph) 正確 push/pop。
    const prevParser = currentParagraphParser;
    currentParagraphParser = this;
    try {
      return this._parseInternal(p);
    } finally {
      currentParagraphParser = prevParser;
    }
  }

  private _parseInternal(p: Element): ParagraphNode {
    const pPrEl = directChild(p, 'w:pPr');
    const props = pPrEl ? parseParagraphProps(pPrEl) : {};
    const styleId = pPrEl
      ? attr(directChild(pPrEl, 'w:pStyle'), 'w:val')
      : undefined;

    const runs: InlineNode[] = [];
    for (const child of effectiveChildren(p)) {
      switch (child.tagName) {
        case 'w:r':
          for (const node of parseRun(child)) runs.push(node);
          break;
        case 'w:fldSimple':
          runs.push(parseFldSimple(child));
          break;
        case 'w:hyperlink': {
          const linkInfo = parseHyperlinkInfo(child, this.relsLookup);
          // hyperlink 內含 w:r，視同包裹 — 展平 runs 並標記 hyperlink 資訊
          for (const r of effectiveChildren(child)) {
            if (r.tagName !== 'w:r') continue;
            for (const node of parseRun(r)) {
              if (linkInfo && node.type === 'run') {
                node.hyperlink = linkInfo;
              }
              runs.push(node);
            }
          }
          break;
        }
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

/**
 * 解析 <w:hyperlink> 的 r:id / w:anchor / w:tooltip 為 HyperlinkInfo。
 *
 * @param el w:hyperlink 元素
 * @param lookup rId → URL 查詢函式（External 連結才回 URL）
 * @returns HyperlinkInfo；若四個欄位皆無則回 undefined
 */
function parseHyperlinkInfo(
  el: Element,
  lookup: RelsLookup | undefined,
): HyperlinkInfo | undefined {
  const rId = el.getAttribute('r:id') ?? el.getAttribute('id') ?? undefined;
  const anchor = el.getAttribute('w:anchor') ?? undefined;
  const tooltip = el.getAttribute('w:tooltip') ?? undefined;
  const url = rId && lookup ? lookup(rId) : undefined;

  const info: HyperlinkInfo = {};
  if (rId) info.rId = rId;
  if (url) info.url = url;
  if (anchor) info.anchor = anchor;
  if (tooltip) info.tooltip = tooltip;
  return Object.keys(info).length > 0 ? info : undefined;
}

// ── w:pPr ─────────────────────────────────────────────────────────────────────

/**
 * 解析 <w:pPr> 為 ParagraphProps。對外公開供 StyleResolver 共用同一份邏輯。
 *
 * @public 給 StyleResolver / SectionParser 在解析 styles.xml / sectPr 時重用
 */
export function parseParagraphProps(pPr: Element): ParagraphProps {
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

  // Sprint 29：w:snapToGrid — 預設 true（OOXML §17.3.1.32），val="0" 顯式關閉
  const snapEl = directChild(pPr, 'w:snapToGrid');
  if (snapEl) {
    const v = snapEl.getAttribute('w:val');
    if (v === '0' || v === 'false') props.snapToGrid = false;
  }

  // w:tabs — tab stop 定義
  const tabsEl = directChild(pPr, 'w:tabs');
  if (tabsEl) {
    const tabs: NonNullable<ParagraphProps['tabs']> = [];
    for (const child of directChildren(tabsEl)) {
      if (child.tagName !== 'w:tab') continue;
      // w:val 可為 left / right / center / decimal / bar / num / clear / start / end
      const valRaw = child.getAttribute('w:val');
      // 'clear' 表示移除繼承的 tab stop，跳過記錄
      if (valRaw === 'clear') continue;
      let align: NonNullable<ParagraphProps['tabs']>[number]['align'] = 'left';
      if (valRaw === 'right' || valRaw === 'end') align = 'right';
      else if (valRaw === 'center') align = 'center';
      else if (valRaw === 'decimal') align = 'decimal';
      const posRaw = child.getAttribute('w:pos');
      if (posRaw === null) continue;
      const posTwip = parseInt(posRaw, 10);
      if (!Number.isFinite(posTwip)) continue;
      const tab: NonNullable<ParagraphProps['tabs']>[number] = {
        pos: twipToPt(posTwip),
        align,
      };
      const leader = child.getAttribute('w:leader');
      if (leader) tab.leader = leader;
      tabs.push(tab);
    }
    if (tabs.length > 0) {
      // 依 pos 升序排序（OOXML 不保證寫入順序）
      tabs.sort((a, b) => a.pos - b.pos);
      props.tabs = tabs;
    }
  }

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

  // 用 effectiveChildren 展開 mc:AlternateContent（Run 內 drawing 常被它包）
  for (const child of effectiveChildren(r)) {
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
      case 'w:drawing': {
        flushText();
        // Sprint 38：透過 module-level currentParagraphParser 提供 paragraphFactory，
        // 讓 DrawingParser 解析 anchor text box (`<wps:txbx>` 內 `<w:p>`) 遞迴回到本實例
        const activeParser = currentParagraphParser;
        const factory = activeParser
          ? (el: Element) => activeParser.parse(el)
          : undefined;
        out.push(drawingParser.parse(child, factory));
        break;
      }
      case 'w:object': {
        // Sprint 122 — OLE 物件降級渲染（ECMA-376 §17.3.3.19）
        // <w:object> 包 <v:shape>（VML preview）+ <o:OLEObject ProgID="..."/>
        // 我們不嘗試渲染實際 OLE blob、emit italic 文字 placeholder 讓使用者
        // 至少知道此處原本有嵌入物件、配合 ProgID / alt 顯示類型。
        flushText();
        const placeholder = buildOleFallbackText(child);
        if (placeholder) {
          out.push({
            type: 'run',
            text: placeholder,
            props: { ...baseProps, italic: true },
          });
        }
        break;
      }
      case 'w:pict': {
        // Sprint 122 — VML 舊圖 placeholder（ECMA-376 §17.3.3.21、Word 97-2003 相容）
        // <w:pict> 內含 <v:shape>、可能有 <o:OLEObject>（圖象化的舊版 OLE）。
        // 同樣 emit italic placeholder、若內含 OLEObject 走 OLE 文案、否則 VML 文案。
        flushText();
        const placeholder = buildPictFallbackText(child);
        if (placeholder) {
          out.push({
            type: 'run',
            text: placeholder,
            props: { ...baseProps, italic: true },
          });
        }
        break;
      }
      // w:rPr 已先處理；w:fldChar 暫不處理（Sprint 123 候選）
    }
  }

  flushText();
  return out;
}

// ── w:rPr ─────────────────────────────────────────────────────────────────────

/**
 * 解析 <w:rPr> 為 RunProps。對外公開供 StyleResolver 共用同一份邏輯。
 *
 * @public 給 StyleResolver 解析 styles.xml 時重用
 */
export function parseRunProps(rPr: Element): RunProps {
  const props: RunProps = {};

  const fontsEl = directChild(rPr, 'w:rFonts');
  if (fontsEl) {
    const ascii = fontsEl.getAttribute('w:ascii');
    const east = fontsEl.getAttribute('w:eastAsia');
    const hAnsi = fontsEl.getAttribute('w:hAnsi');
    const cs = fontsEl.getAttribute('w:cs');
    if (ascii) props.fontFamily = ascii;
    if (east) props.fontFamilyEastAsia = east;
    if (hAnsi) props.fontFamilyHAnsi = hAnsi;
    if (cs) props.fontFamilyCs = cs;
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

  // 顏色：優先 w:val（顯式 hex），再嘗試 themeColor + tint/shade（透過 ThemeMap）
  const colorEl = directChild(rPr, 'w:color');
  const resolvedColor = resolveColorElement(colorEl, themeMapForParser);
  if (resolvedColor) props.color = resolvedColor;

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

// ── Sprint 122：OLE / VML pict 降級 placeholder ─────────────────────────────

/**
 * Sprint 122 — `<w:object>` placeholder 文字。
 *
 * OOXML §17.3.3.19：`<w:object>` 包 VML `<v:shape>` + `<o:OLEObject>`。
 *   - 嘗試讀 `<o:OLEObject ProgID="Equation.3"/>` → `[嵌入物件: Equation.3]`
 *   - 若有 `<v:shape alt="...">` → 加 alt 補充
 *   - 兩者都缺 → 純 `[嵌入物件]`
 *
 * 設計：getElementsByTagName 不限 namespace 前綴（OOXML 真實 docx 偶見
 *   `<OLEObject>` 無前綴、或 `<v:shape>` 改成 `<vml:shape>`）。
 */
function buildOleFallbackText(objectEl: Element): string {
  let progId = '';
  let alt = '';

  // 寬鬆 walk：對 wildcard tagName endsWith 比對
  // happy-dom / browser 對 namespace 前綴處理不一致、用 walker 統一
  const walk = (root: Element): void => {
    const children = root.childNodes;
    for (let i = 0; i < children.length; i++) {
      const c = children[i];
      if (c.nodeType !== 1) continue;
      const el = c as Element;
      const local = el.localName ?? el.tagName.split(':').pop() ?? '';
      if (!progId && local === 'OLEObject') {
        progId = el.getAttribute('ProgID') ?? '';
      }
      if (!alt && local === 'shape') {
        alt = el.getAttribute('alt') ?? '';
      }
      walk(el);
    }
  };
  walk(objectEl);

  if (progId && alt) return `[嵌入物件: ${progId} — ${alt}]`;
  if (progId) return `[嵌入物件: ${progId}]`;
  if (alt) return `[嵌入物件: ${alt}]`;
  return '[嵌入物件]';
}

/**
 * Sprint 122 — `<w:pict>` placeholder 文字（VML legacy picture）。
 *
 * OOXML §17.3.3.21：Word 97-2003 相容圖片包裝。
 *   - 內含 `<o:OLEObject>` → 走 OLE 文案
 *   - 否則純 VML → `[圖片(VML)]` 或 `[圖片(VML): <alt>]`
 */
function buildPictFallbackText(pictEl: Element): string {
  let hasOle = false;
  let progId = '';
  let alt = '';

  const walk = (root: Element): void => {
    const children = root.childNodes;
    for (let i = 0; i < children.length; i++) {
      const c = children[i];
      if (c.nodeType !== 1) continue;
      const el = c as Element;
      const local = el.localName ?? el.tagName.split(':').pop() ?? '';
      if (local === 'OLEObject') {
        hasOle = true;
        if (!progId) progId = el.getAttribute('ProgID') ?? '';
      }
      if (!alt && local === 'shape') {
        alt = el.getAttribute('alt') ?? '';
      }
      walk(el);
    }
  };
  walk(pictEl);

  if (hasOle) {
    if (progId && alt) return `[嵌入物件: ${progId} — ${alt}]`;
    if (progId) return `[嵌入物件: ${progId}]`;
    if (alt) return `[嵌入物件: ${alt}]`;
    return '[嵌入物件]';
  }

  if (alt) return `[圖片(VML): ${alt}]`;
  return '[圖片(VML)]';
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
