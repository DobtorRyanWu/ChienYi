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
