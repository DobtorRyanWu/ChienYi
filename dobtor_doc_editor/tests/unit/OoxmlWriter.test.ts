/**
 * OoxmlWriter 單元測試（Sprint 185、Phase 6 docx export MVS）
 *
 * 驗證 DocumentNode → .docx package 的最小可行切片：純文字段落、單 section
 * pgSz/pgMar、5 個必要 part。其他 RunProps/表格/圖片/Phase 5 子功能等留後續 sprint。
 */

import { describe, expect, it } from 'vitest';
import { unzipSync, strFromU8 } from 'fflate';
import { OoxmlWriter } from '../../static/src/core/ooxml/export/OoxmlWriter';
import type {
  DocumentNode,
  ParagraphNode,
  RunNode,
  SectionNode,
} from '../../static/src/core/ooxml/ast/types';

const writer = new OoxmlWriter();

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

/** 把 OoxmlWriter 輸出解 zip 為 path → 字串 map（測試方便）。 */
function unzipToText(bytes: Uint8Array): Record<string, string> {
  const entries = unzipSync(bytes);
  const out: Record<string, string> = {};
  for (const [path, u8] of Object.entries(entries)) {
    out[path] = strFromU8(u8);
  }
  return out;
}

describe('OoxmlWriter — 5 必要 part', () => {
  it('空文件 → zip 含 [Content_Types].xml / _rels/.rels / document.xml / styles.xml / document.xml.rels', () => {
    const bytes = writer.write(makeDoc([makeSection([])]));
    const files = unzipToText(bytes);
    expect(Object.keys(files).sort()).toEqual([
      '[Content_Types].xml',
      '_rels/.rels',
      'word/_rels/document.xml.rels',
      'word/document.xml',
      'word/styles.xml',
    ]);
  });

  it('Content Types 宣告 document.xml 與 styles.xml 兩個 override', () => {
    const files = unzipToText(writer.write(makeDoc([makeSection([])])));
    expect(files['[Content_Types].xml']).toContain('PartName="/word/document.xml"');
    expect(files['[Content_Types].xml']).toContain('PartName="/word/styles.xml"');
    expect(files['[Content_Types].xml']).toContain('wordprocessingml.document.main+xml');
  });

  it('root rels 指向 word/document.xml（officeDocument 關係型別）', () => {
    const files = unzipToText(writer.write(makeDoc([makeSection([])])));
    expect(files['_rels/.rels']).toContain('Target="word/document.xml"');
    expect(files['_rels/.rels']).toContain('officeDocument');
  });

  it('document rels 指向 styles.xml', () => {
    const files = unzipToText(writer.write(makeDoc([makeSection([])])));
    expect(files['word/_rels/document.xml.rels']).toContain('Target="styles.xml"');
    expect(files['word/_rels/document.xml.rels']).toContain('relationships/styles');
  });
});

describe('OoxmlWriter — 段落與 Run 輸出', () => {
  it('單一段落單一 run → <w:p><w:r><w:t>text</w:t></w:r></w:p>', () => {
    const doc = makeDoc([makeSection([makeParagraph([makeRun('Hello')])])]);
    const xml = unzipToText(writer.write(doc))['word/document.xml'];
    expect(xml).toContain('<w:p>');
    expect(xml).toContain('<w:r>');
    expect(xml).toContain('<w:t xml:space="preserve">Hello</w:t>');
  });

  it('多 run → 同段落內依序輸出', () => {
    const doc = makeDoc([makeSection([
      makeParagraph([makeRun('A'), makeRun('B'), makeRun('C')]),
    ])]);
    const xml = unzipToText(writer.write(doc))['word/document.xml'];
    const aIdx = xml.indexOf('>A<');
    const bIdx = xml.indexOf('>B<');
    const cIdx = xml.indexOf('>C<');
    expect(aIdx).toBeGreaterThan(-1);
    expect(aIdx).toBeLessThan(bIdx);
    expect(bIdx).toBeLessThan(cIdx);
  });

  it('多段落 → 依序輸出 <w:p>', () => {
    const doc = makeDoc([makeSection([
      makeParagraph([makeRun('一')]),
      makeParagraph([makeRun('二')]),
    ])]);
    const xml = unzipToText(writer.write(doc))['word/document.xml'];
    expect((xml.match(/<w:p>/g) ?? []).length).toBe(2);
  });

  it('XML 特殊字元跳脫：& < > " \'', () => {
    const doc = makeDoc([makeSection([
      makeParagraph([makeRun('a&b<c>d"e\'f')]),
    ])]);
    const xml = unzipToText(writer.write(doc))['word/document.xml'];
    expect(xml).toContain('a&amp;b&lt;c&gt;d&quot;e&apos;f');
  });

  it('xml:space="preserve" 保留前後空白', () => {
    const doc = makeDoc([makeSection([makeParagraph([makeRun('  leading')])])]);
    const xml = unzipToText(writer.write(doc))['word/document.xml'];
    expect(xml).toContain('xml:space="preserve"');
  });

  it('非 run 的 InlineNode（image / break / field）→ MVS 跳過', () => {
    const doc = makeDoc([makeSection([
      makeParagraph([
        makeRun('前'),
        { type: 'inlineImage', rId: 'rId1', width: 100, height: 50 },
        { type: 'break', breakType: 'line' },
        makeRun('後'),
      ]),
    ])]);
    const xml = unzipToText(writer.write(doc))['word/document.xml'];
    expect(xml).toContain('>前<');
    expect(xml).toContain('>後<');
    // MVS 不輸出 image / break
    expect(xml).not.toContain('<w:drawing');
    expect(xml).not.toContain('<w:br');
  });

  it('表格 BlockNode → MVS 跳過（後續 sprint 補）', () => {
    const doc = makeDoc([makeSection([
      makeParagraph([makeRun('段落')]),
      { type: 'table', grid: [], rows: [] } as Parameters<typeof writer.write>[0]['sections'][number]['body'][number],
    ])]);
    const xml = unzipToText(writer.write(doc))['word/document.xml'];
    expect(xml).toContain('>段落<');
    expect(xml).not.toContain('<w:tbl');
  });
});

describe('OoxmlWriter — sectPr', () => {
  it('pgSz / pgMar 由 section page/margins 換算為 twips（×20）', () => {
    const doc = makeDoc([makeSection([])]);
    const xml = unzipToText(writer.write(doc))['word/document.xml'];
    // A4 = 595.3 × 20 = 11906；841.9 × 20 = 16838
    expect(xml).toContain('w:w="11906"');
    expect(xml).toContain('w:h="16838"');
    // 邊距 72pt × 20 = 1440 twips
    expect(xml).toContain('w:top="1440"');
    expect(xml).toContain('w:left="1440"');
  });

  it('多 section → 使用最後一個 section 的 sectPr（MVS 退化為單 section）', () => {
    const secA = makeSection([makeParagraph([makeRun('A')])]);
    const secB = {
      ...makeSection([makeParagraph([makeRun('B')])]),
      page: { width: 841.9, height: 595.3, orientation: 'landscape' as const },
    };
    const doc = makeDoc([secA, secB]);
    const xml = unzipToText(writer.write(doc))['word/document.xml'];
    // 末 sectPr = 橫式（841.9 × 20 = 16838）
    expect(xml).toContain('w:w="16838"');
    // 兩 section 的段落都有
    expect(xml).toContain('>A<');
    expect(xml).toContain('>B<');
  });

  it('無 section 時用 A4 + Word 預設邊距 fallback', () => {
    const doc = makeDoc([]);
    const xml = unzipToText(writer.write(doc))['word/document.xml'];
    expect(xml).toContain('w:w="11906"');  // A4 width
    expect(xml).toContain('w:top="1440"'); // 72pt 邊距
  });
});

describe('OoxmlWriter — 輸出格式', () => {
  it('所有 part 開頭含 XML 宣告（UTF-8 / standalone="yes"）', () => {
    const files = unzipToText(writer.write(makeDoc([makeSection([])])));
    for (const path of Object.keys(files)) {
      expect(files[path]).toMatch(/^<\?xml version="1\.0" encoding="UTF-8" standalone="yes"\?>/);
    }
  });

  it('輸出為 Uint8Array、可直接 unzipSync 解析（fflate 對稱）', () => {
    const bytes = writer.write(makeDoc([makeSection([])]));
    expect(bytes).toBeInstanceOf(Uint8Array);
    expect(() => unzipSync(bytes)).not.toThrow();
  });
});
