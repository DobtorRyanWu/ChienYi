/**
 * Sprint 185 整合驗證（Phase 6 docx export MVS round-trip）
 *
 * 規畫書 §6 黃金測試：`import(export(doc))` ≅ `doc`。本 MVS 切片只驗證**段落
 * 文字內容**對稱（RunProps / 樣式 / 表格 / Phase 5 子功能等留後續 sprint）。
 *
 * 完整對稱性將隨後續 export sprint 逐步擴充覆蓋。
 */

import { describe, expect, it } from 'vitest';
import { OoxmlWriter } from '../../static/src/core/ooxml/export/OoxmlWriter';
import { OoxmlParser } from '../../static/src/core/ooxml/OoxmlParser';
import type {
  DocumentNode,
  ParagraphNode,
  RunNode,
  SectionNode,
} from '../../static/src/core/ooxml/ast/types';

const writer = new OoxmlWriter();
const parser = new OoxmlParser();

function makeRun(text: string): RunNode {
  return { type: 'run', text, props: {} };
}

function makeParagraph(runs: ParagraphNode['runs']): ParagraphNode {
  return { type: 'paragraph', runs, props: {} };
}

function makeSection(body: SectionNode['body']): SectionNode {
  return {
    type: 'section',
    page: { width: 595.3, height: 841.9, orientation: 'portrait' },
    margins: { top: 72, bottom: 72, left: 72, right: 72, header: 36, footer: 36 },
    headerRefs: {},
    footerRefs: {},
    titlePage: false,
    evenAndOddHeaders: false,
    body,
  };
}

function makeDoc(sections: SectionNode[]): DocumentNode {
  return {
    type: 'document',
    sections,
    headers: new Map(),
    footers: new Map(),
    footnotes: new Map(),
    endnotes: new Map(),
    comments: new Map(),
    settings: {},
    fontTable: new Map(),
    webSettings: {},
    styles: new Map(),
    numbering: new Map(),
    media: new Map(),
    docProps: {},
    appProps: {},
    customProps: new Map(),
    contentTypes: { defaults: new Map(), overrides: new Map() },
    latentStyles: {},
  };
}

/** 從 DocumentNode 抽出純文字（按段落、run 順序、段落以 \n 分隔）。 */
function extractText(doc: DocumentNode): string {
  const lines: string[] = [];
  for (const sec of doc.sections) {
    for (const block of sec.body) {
      if (block.type !== 'paragraph') continue;
      const t = block.runs
        .filter((r): r is RunNode => r.type === 'run')
        .map((r) => r.text)
        .join('');
      lines.push(t);
    }
  }
  return lines.join('\n');
}

/** 寫出 → 再讀回 → 回傳 round-trip 後的 DocumentNode。 */
function roundTrip(doc: DocumentNode): DocumentNode {
  const bytes = writer.write(doc);
  const arr = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
  return parser.parse(arr);
}

describe('Sprint 185 — Phase 6 export round-trip（純文字段落）', () => {
  it('空文件 → round-trip 不 crash、產出有效 docx', () => {
    const doc = makeDoc([makeSection([])]);
    expect(() => roundTrip(doc)).not.toThrow();
  });

  it('單段落單 run → round-trip 文字保留', () => {
    const doc = makeDoc([makeSection([makeParagraph([makeRun('Hello World')])])]);
    const back = roundTrip(doc);
    expect(extractText(back)).toBe('Hello World');
  });

  it('多段落 → round-trip 順序保留', () => {
    const doc = makeDoc([makeSection([
      makeParagraph([makeRun('第一段')]),
      makeParagraph([makeRun('第二段')]),
      makeParagraph([makeRun('第三段')]),
    ])]);
    expect(extractText(roundTrip(doc))).toBe('第一段\n第二段\n第三段');
  });

  it('多 run 同段落 → round-trip 拼接保留', () => {
    const doc = makeDoc([makeSection([
      makeParagraph([makeRun('Hello, '), makeRun('世界'), makeRun('!')]),
    ])]);
    expect(extractText(roundTrip(doc))).toBe('Hello, 世界!');
  });

  it('XML 特殊字元 → round-trip 文字 byte-identical', () => {
    const txt = 'a&b<c>d"e\'f';
    const doc = makeDoc([makeSection([makeParagraph([makeRun(txt)])])]);
    expect(extractText(roundTrip(doc))).toBe(txt);
  });

  it('前後空白 → round-trip 保留（xml:space="preserve"）', () => {
    const doc = makeDoc([makeSection([
      makeParagraph([makeRun('  前後皆有空白  ')]),
    ])]);
    expect(extractText(roundTrip(doc))).toBe('  前後皆有空白  ');
  });

  it('中文 / CJK / 表情符號 → round-trip 文字保留', () => {
    const txt = '繁體中文・日本語・한국어・🎯';
    const doc = makeDoc([makeSection([makeParagraph([makeRun(txt)])])]);
    expect(extractText(roundTrip(doc))).toBe(txt);
  });

  it('round-trip 後仍只有 1 個 section（MVS 多 section 退化為單）', () => {
    const doc = makeDoc([
      makeSection([makeParagraph([makeRun('A')])]),
      makeSection([makeParagraph([makeRun('B')])]),
    ]);
    const back = roundTrip(doc);
    expect(back.sections).toHaveLength(1);
    // 兩 section 的段落都在
    expect(extractText(back)).toBe('A\nB');
  });

  it('section page / margins round-trip（pt → twips → pt 量化、A4 + 72pt）', () => {
    const doc = makeDoc([makeSection([makeParagraph([makeRun('x')])])]);
    const back = roundTrip(doc);
    // 595.3pt → 11906 twips → 595.3pt（× 20 / 20 整數運算可能差 0.05、容忍度）
    expect(back.sections[0].page.width).toBeCloseTo(595.3, 0);
    expect(back.sections[0].page.height).toBeCloseTo(841.9, 0);
    expect(back.sections[0].margins.top).toBeCloseTo(72, 1);
    expect(back.sections[0].margins.left).toBeCloseTo(72, 1);
  });
});

describe('Sprint 186 — Phase 6 export round-trip（RunProps）', () => {
  /** 從 round-trip 後的 doc 取第一段第一個 run 的 props。 */
  function firstRunProps(doc: DocumentNode): RunNode['props'] {
    const sec = doc.sections[0];
    const para = sec.body[0];
    if (para.type !== 'paragraph') throw new Error('expected paragraph');
    const run = para.runs[0];
    if (run.type !== 'run') throw new Error('expected run');
    return run.props;
  }

  function makeRunWithProps(text: string, props: RunNode['props']): RunNode {
    return { type: 'run', text, props };
  }

  it('粗體 / 斜體 / 刪除線 round-trip', () => {
    const doc = makeDoc([makeSection([makeParagraph([
      makeRunWithProps('x', { bold: true, italic: true, strike: true }),
    ])])]);
    const back = firstRunProps(roundTrip(doc));
    expect(back.bold).toBe(true);
    expect(back.italic).toBe(true);
    expect(back.strike).toBe(true);
  });

  it('字級 fontSize round-trip（half-points 精度）', () => {
    const doc = makeDoc([makeSection([makeParagraph([
      makeRunWithProps('x', { fontSize: 14 }),
    ])])]);
    expect(firstRunProps(roundTrip(doc)).fontSize).toBe(14);
  });

  it('顏色 hex round-trip（大寫正規化由 parser 處理）', () => {
    const doc = makeDoc([makeSection([makeParagraph([
      makeRunWithProps('x', { color: 'FF0000' }),
    ])])]);
    const back = firstRunProps(roundTrip(doc));
    expect(back.color?.toUpperCase()).toBe('FF0000');
  });

  it('底線 underline round-trip', () => {
    for (const u of ['single', 'double', 'wave'] as const) {
      const doc = makeDoc([makeSection([makeParagraph([
        makeRunWithProps('x', { underline: u }),
      ])])]);
      expect(firstRunProps(roundTrip(doc)).underline).toBe(u);
    }
  });

  it('上下標 vertAlign round-trip', () => {
    for (const v of ['superscript', 'subscript'] as const) {
      const doc = makeDoc([makeSection([makeParagraph([
        makeRunWithProps('x', { vertAlign: v }),
      ])])]);
      expect(firstRunProps(roundTrip(doc)).vertAlign).toBe(v);
    }
  });

  it('字型 rFonts 四欄位 round-trip', () => {
    const doc = makeDoc([makeSection([makeParagraph([
      makeRunWithProps('x', {
        fontFamily: 'Arial',
        fontFamilyEastAsia: '微軟正黑體',
        fontFamilyHAnsi: 'Calibri',
        fontFamilyCs: 'Arial',
      }),
    ])])]);
    const back = firstRunProps(roundTrip(doc));
    expect(back.fontFamily).toBe('Arial');
    expect(back.fontFamilyEastAsia).toBe('微軟正黑體');
    expect(back.fontFamilyHAnsi).toBe('Calibri');
    expect(back.fontFamilyCs).toBe('Arial');
  });

  it('高亮 highlight round-trip（具名色）', () => {
    const doc = makeDoc([makeSection([makeParagraph([
      makeRunWithProps('x', { highlight: 'yellow' }),
    ])])]);
    expect(firstRunProps(roundTrip(doc)).highlight).toBe('yellow');
  });

  it('語言 lang round-trip', () => {
    const doc = makeDoc([makeSection([makeParagraph([
      makeRunWithProps('x', { lang: 'zh-TW' }),
    ])])]);
    expect(firstRunProps(roundTrip(doc)).lang).toBe('zh-TW');
  });

  it('多 props 組合 round-trip', () => {
    const props = {
      bold: true, italic: true, fontSize: 16, color: 'FF0000',
      underline: 'single' as const, fontFamily: 'Arial', vertAlign: 'superscript' as const,
    };
    const doc = makeDoc([makeSection([makeParagraph([makeRunWithProps('x', props)])])]);
    const back = firstRunProps(roundTrip(doc));
    expect(back.bold).toBe(true);
    expect(back.italic).toBe(true);
    expect(back.fontSize).toBe(16);
    expect(back.color?.toUpperCase()).toBe('FF0000');
    expect(back.underline).toBe('single');
    expect(back.fontFamily).toBe('Arial');
    expect(back.vertAlign).toBe('superscript');
  });
});

describe('Sprint 187 — Phase 6 export round-trip（ParagraphProps）', () => {
  function firstParaProps(doc: DocumentNode): ParagraphNode['props'] {
    const block = doc.sections[0].body[0];
    if (block.type !== 'paragraph') throw new Error('expected paragraph');
    return block.props;
  }
  function firstParaStyleId(doc: DocumentNode): string | undefined {
    const block = doc.sections[0].body[0];
    if (block.type !== 'paragraph') throw new Error('expected paragraph');
    return block.styleId;
  }
  function paraWith(props: ParagraphNode['props'], styleId?: string): ParagraphNode {
    const p: ParagraphNode = { type: 'paragraph', runs: [makeRun('x')], props };
    if (styleId) p.styleId = styleId;
    return p;
  }

  it('alignment round-trip（left / center / right / justify）', () => {
    for (const a of ['left', 'center', 'right', 'justify'] as const) {
      const doc = makeDoc([makeSection([paraWith({ alignment: a })])]);
      expect(firstParaProps(roundTrip(doc)).alignment).toBe(a);
    }
  });

  it('styleId round-trip', () => {
    const doc = makeDoc([makeSection([paraWith({}, 'Heading1')])]);
    expect(firstParaStyleId(roundTrip(doc))).toBe('Heading1');
  });

  it('numId + ilvl round-trip', () => {
    const doc = makeDoc([makeSection([paraWith({ numId: 5, ilvl: 2 })])]);
    const back = firstParaProps(roundTrip(doc));
    expect(back.numId).toBe(5);
    expect(back.ilvl).toBe(2);
  });

  it('indent 四欄位 round-trip', () => {
    const doc = makeDoc([makeSection([paraWith({
      indent: { left: 36, right: 24, firstLine: 18, hanging: 12 },
    })])]);
    const back = firstParaProps(roundTrip(doc)).indent;
    expect(back?.left).toBeCloseTo(36, 1);
    expect(back?.right).toBeCloseTo(24, 1);
    expect(back?.firstLine).toBeCloseTo(18, 1);
    expect(back?.hanging).toBeCloseTo(12, 1);
  });

  it('spacing before/after/line auto round-trip', () => {
    const doc = makeDoc([makeSection([paraWith({
      spacing: { before: 6, after: 12, line: { rule: 'auto', value: 1.5 } },
    })])]);
    const back = firstParaProps(roundTrip(doc)).spacing;
    expect(back?.before).toBeCloseTo(6, 1);
    expect(back?.after).toBeCloseTo(12, 1);
    expect(back?.line?.rule).toBe('auto');
    expect(back?.line?.value).toBeCloseTo(1.5, 2);
  });

  it('spacing line exact round-trip', () => {
    const doc = makeDoc([makeSection([paraWith({
      spacing: { line: { rule: 'exact', value: 14 } },
    })])]);
    const back = firstParaProps(roundTrip(doc)).spacing;
    expect(back?.line?.rule).toBe('exact');
    expect(back?.line?.value).toBeCloseTo(14, 1);
  });

  it('keepNext / keepLines / pageBreakBefore toggle round-trip', () => {
    const doc = makeDoc([makeSection([paraWith({
      keepNext: true, keepLines: true, pageBreakBefore: true,
    })])]);
    const back = firstParaProps(roundTrip(doc));
    expect(back.keepNext).toBe(true);
    expect(back.keepLines).toBe(true);
    expect(back.pageBreakBefore).toBe(true);
  });

  it('tabs round-trip（多 tab + leader）', () => {
    const doc = makeDoc([makeSection([paraWith({
      tabs: [
        { pos: 100, align: 'left' },
        { pos: 200, align: 'right', leader: 'dot' },
      ],
    })])]);
    const back = firstParaProps(roundTrip(doc)).tabs;
    expect(back).toHaveLength(2);
    expect(back?.[0].pos).toBeCloseTo(100, 1);
    expect(back?.[0].align).toBe('left');
    expect(back?.[1].pos).toBeCloseTo(200, 1);
    expect(back?.[1].align).toBe('right');
    expect(back?.[1].leader).toBe('dot');
  });

  it('textAlignment round-trip', () => {
    for (const v of ['auto', 'top', 'center', 'baseline', 'bottom'] as const) {
      const doc = makeDoc([makeSection([paraWith({ textAlignment: v })])]);
      expect(firstParaProps(roundTrip(doc)).textAlignment).toBe(v);
    }
  });

  it('多 ParagraphProps 組合 round-trip', () => {
    const props = {
      alignment: 'center' as const,
      indent: { left: 24, firstLine: 12 },
      spacing: { before: 6, after: 6, line: { rule: 'auto' as const, value: 1.0 } },
      keepNext: true,
      numId: 1, ilvl: 0,
    };
    const doc = makeDoc([makeSection([paraWith(props, 'Body')])]);
    const back = roundTrip(doc);
    const props2 = firstParaProps(back);
    expect(firstParaStyleId(back)).toBe('Body');
    expect(props2.alignment).toBe('center');
    expect(props2.indent?.left).toBeCloseTo(24, 1);
    expect(props2.spacing?.before).toBeCloseTo(6, 1);
    expect(props2.keepNext).toBe(true);
    expect(props2.numId).toBe(1);
    expect(props2.ilvl).toBe(0);
  });
});

describe('Sprint 188 — Phase 6 export round-trip（ParagraphProps 進階）', () => {
  function firstParaProps(doc: DocumentNode): ParagraphNode['props'] {
    const block = doc.sections[0].body[0];
    if (block.type !== 'paragraph') throw new Error('expected paragraph');
    return block.props;
  }
  function paraWith(props: ParagraphNode['props']): ParagraphNode {
    return { type: 'paragraph', runs: [makeRun('x')], props };
  }

  // ── pBdr ──────────────────────────────────────────────────────────────────

  it('borders 全四邊 round-trip', () => {
    const doc = makeDoc([makeSection([paraWith({
      borders: {
        top:    { style: 'single', width: 0.5, color: '000000' },
        bottom: { style: 'single', width: 0.5, color: '000000' },
        left:   { style: 'double', width: 1, color: 'FF0000' },
        right:  { style: 'double', width: 1, color: 'FF0000' },
      },
    })])]);
    const back = firstParaProps(roundTrip(doc)).borders;
    expect(back?.top?.style).toBe('single');
    expect(back?.top?.width).toBeCloseTo(0.5, 2);
    expect(back?.top?.color?.toUpperCase()).toBe('000000');
    expect(back?.left?.style).toBe('double');
    expect(back?.left?.width).toBeCloseTo(1, 2);
    expect(back?.left?.color?.toUpperCase()).toBe('FF0000');
  });

  it('borders space round-trip', () => {
    const doc = makeDoc([makeSection([paraWith({
      borders: { bottom: { style: 'single', width: 0.5, color: '000000', space: 4 } },
    })])]);
    expect(firstParaProps(roundTrip(doc)).borders?.bottom?.space).toBeCloseTo(4, 0);
  });

  // ── shd ──────────────────────────────────────────────────────────────────

  it('shading fill/pattern round-trip', () => {
    const doc = makeDoc([makeSection([paraWith({
      shading: { fill: 'DEEAF6', pattern: 'clear', color: 'auto' },
    })])]);
    const back = firstParaProps(roundTrip(doc)).shading;
    expect(back?.fill?.toUpperCase()).toBe('DEEAF6');
    expect(back?.pattern).toBe('clear');
    expect(back?.color).toBe('auto');
  });

  // ── framePr ──────────────────────────────────────────────────────────────

  it('framePr 完整 round-trip', () => {
    const fp = {
      width: 100, height: 50, hRule: 'exact' as const,
      hSpace: 4, vSpace: 4,
      wrap: 'around' as const,
      hAnchor: 'page' as const, vAnchor: 'margin' as const,
      xAlign: 'center' as const, yAlign: 'top' as const,
      x: 10, y: 20,
    };
    const doc = makeDoc([makeSection([paraWith({ framePr: fp })])]);
    const back = firstParaProps(roundTrip(doc)).framePr;
    expect(back?.width).toBeCloseTo(100, 1);
    expect(back?.height).toBeCloseTo(50, 1);
    expect(back?.hRule).toBe('exact');
    expect(back?.hSpace).toBeCloseTo(4, 1);
    expect(back?.vSpace).toBeCloseTo(4, 1);
    expect(back?.wrap).toBe('around');
    expect(back?.hAnchor).toBe('page');
    expect(back?.vAnchor).toBe('margin');
    expect(back?.xAlign).toBe('center');
    expect(back?.yAlign).toBe('top');
    expect(back?.x).toBeCloseTo(10, 1);
    expect(back?.y).toBeCloseTo(20, 1);
  });

  it('framePr 部分欄位 round-trip（無值欄位不掛 key）', () => {
    const doc = makeDoc([makeSection([paraWith({
      framePr: { wrap: 'around', hAnchor: 'page' },
    })])]);
    const back = firstParaProps(roundTrip(doc)).framePr;
    expect(back?.wrap).toBe('around');
    expect(back?.hAnchor).toBe('page');
    expect(back?.width).toBeUndefined();
    expect(back?.height).toBeUndefined();
  });

  // ── 複合 round-trip ───────────────────────────────────────────────────────

  it('pBdr + shd + framePr 同段落 round-trip', () => {
    const doc = makeDoc([makeSection([paraWith({
      framePr: { wrap: 'around', hAnchor: 'page' },
      borders: { top: { style: 'single', width: 0.5, color: '000000' } },
      shading: { fill: 'FFFF00' },
    })])]);
    const back = firstParaProps(roundTrip(doc));
    expect(back.framePr?.wrap).toBe('around');
    expect(back.borders?.top?.style).toBe('single');
    expect(back.shading?.fill?.toUpperCase()).toBe('FFFF00');
  });
});
