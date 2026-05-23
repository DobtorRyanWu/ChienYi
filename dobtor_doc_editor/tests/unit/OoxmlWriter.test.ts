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

describe('OoxmlWriter — Sprint 186 RunProps 序列化', () => {
  function runWithProps(text: string, props: RunNode['props']): RunNode {
    return { type: 'run', text, props };
  }

  function getDocXml(runs: RunNode[]): string {
    const doc = makeDoc([makeSection([makeParagraph(runs)])]);
    return unzipToText(writer.write(doc))['word/document.xml'];
  }

  it('無 props → 不輸出 <w:rPr>（紀律 #21）', () => {
    const xml = getDocXml([runWithProps('x', {})]);
    expect(xml).not.toContain('<w:rPr>');
  });

  it('粗體 true → <w:b/>', () => {
    const xml = getDocXml([runWithProps('x', { bold: true })]);
    expect(xml).toContain('<w:rPr><w:b/></w:rPr>');
  });

  it('粗體 false → <w:b w:val="0"/>（顯式關閉、覆蓋 style）', () => {
    const xml = getDocXml([runWithProps('x', { bold: false })]);
    expect(xml).toContain('<w:b w:val="0"/>');
  });

  it('斜體 / 刪除線 / 雙刪除線', () => {
    const xml = getDocXml([runWithProps('x', { italic: true, strike: true, dstrike: true })]);
    expect(xml).toContain('<w:i/>');
    expect(xml).toContain('<w:strike/>');
    expect(xml).toContain('<w:dstrike/>');
  });

  it('字級 fontSize → <w:sz w:val=>（half-points、12pt = 24）', () => {
    const xml = getDocXml([runWithProps('x', { fontSize: 12 })]);
    expect(xml).toContain('<w:sz w:val="24"/>');
  });

  it('顏色 → <w:color w:val="RRGGBB"/>', () => {
    const xml = getDocXml([runWithProps('x', { color: 'FF0000' })]);
    expect(xml).toContain('<w:color w:val="FF0000"/>');
  });

  it('高亮 → <w:highlight w:val>', () => {
    const xml = getDocXml([runWithProps('x', { highlight: 'yellow' })]);
    expect(xml).toContain('<w:highlight w:val="yellow"/>');
  });

  it('底線 → <w:u w:val>（含複雜列舉值）', () => {
    for (const u of ['single', 'double', 'wave']) {
      const xml = getDocXml([runWithProps('x', { underline: u as 'single' })]);
      expect(xml).toContain(`<w:u w:val="${u}"/>`);
    }
  });

  it('上下標 vertAlign → <w:vertAlign w:val>', () => {
    expect(getDocXml([runWithProps('x', { vertAlign: 'superscript' })]))
      .toContain('<w:vertAlign w:val="superscript"/>');
    expect(getDocXml([runWithProps('x', { vertAlign: 'subscript' })]))
      .toContain('<w:vertAlign w:val="subscript"/>');
  });

  it('字型 rFonts → ascii / eastAsia / hAnsi / cs 屬性', () => {
    const xml = getDocXml([runWithProps('x', {
      fontFamily: 'Arial', fontFamilyEastAsia: '微軟正黑體',
      fontFamilyHAnsi: 'Arial', fontFamilyCs: 'Arial',
    })]);
    expect(xml).toContain('w:ascii="Arial"');
    expect(xml).toContain('w:eastAsia="微軟正黑體"');
    expect(xml).toContain('w:hAnsi="Arial"');
    expect(xml).toContain('w:cs="Arial"');
  });

  it('部分字型欄位 → 只輸出有值的 attribute', () => {
    const xml = getDocXml([runWithProps('x', { fontFamily: 'Arial' })]);
    expect(xml).toContain('<w:rFonts w:ascii="Arial"/>');
    expect(xml).not.toContain('w:eastAsia');
    expect(xml).not.toContain('w:hAnsi');
  });

  it('字距 spacing → <w:spacing w:val=>（twips、pt × 20）', () => {
    const xml = getDocXml([runWithProps('x', { spacing: 1 })]);
    expect(xml).toContain('<w:spacing w:val="20"/>');
  });

  it('語言 lang → <w:lang w:val>', () => {
    const xml = getDocXml([runWithProps('x', { lang: 'zh-TW' })]);
    expect(xml).toContain('<w:lang w:val="zh-TW"/>');
  });

  it('多 prop 組合 → 依 schema 大致順序輸出（rFonts → b → color → sz → u）', () => {
    const xml = getDocXml([runWithProps('x', {
      bold: true, color: 'FF0000', fontSize: 14, underline: 'single', fontFamily: 'Arial',
    })]);
    // 驗證順序
    const rFontsIdx = xml.indexOf('<w:rFonts');
    const bIdx = xml.indexOf('<w:b/>');
    const colorIdx = xml.indexOf('<w:color');
    const szIdx = xml.indexOf('<w:sz');
    const uIdx = xml.indexOf('<w:u ');
    expect(rFontsIdx).toBeLessThan(bIdx);
    expect(bIdx).toBeLessThan(colorIdx);
    expect(colorIdx).toBeLessThan(szIdx);
    expect(szIdx).toBeLessThan(uIdx);
  });
});

describe('OoxmlWriter — Sprint 187 ParagraphProps 序列化', () => {
  function paraWith(props: ParagraphNode['props'], styleId?: string): ParagraphNode {
    const para: ParagraphNode = { type: 'paragraph', runs: [makeRun('x')], props };
    if (styleId) para.styleId = styleId;
    return para;
  }
  function getDocXml(para: ParagraphNode): string {
    return unzipToText(writer.write(makeDoc([makeSection([para])])))['word/document.xml'];
  }

  it('無 props 與 styleId → 不輸出 <w:pPr>（紀律 #21）', () => {
    const xml = getDocXml(paraWith({}));
    expect(xml).not.toContain('<w:pPr>');
  });

  it('styleId → <w:pStyle w:val>（pPr 第一個子元素）', () => {
    const xml = getDocXml(paraWith({}, 'Heading1'));
    expect(xml).toContain('<w:pStyle w:val="Heading1"/>');
    expect(xml.indexOf('<w:pStyle')).toBeLessThan(xml.indexOf('<w:r>'));
  });

  it('keepNext / keepLines / pageBreakBefore toggle properties', () => {
    const xml = getDocXml(paraWith({
      keepNext: true, keepLines: true, pageBreakBefore: true,
    }));
    expect(xml).toContain('<w:keepNext/>');
    expect(xml).toContain('<w:keepLines/>');
    expect(xml).toContain('<w:pageBreakBefore/>');
  });

  it('keepNext false → 顯式 w:val="0"', () => {
    const xml = getDocXml(paraWith({ keepNext: false }));
    expect(xml).toContain('<w:keepNext w:val="0"/>');
  });

  it('numId + ilvl → <w:numPr><w:ilvl/><w:numId/></w:numPr>', () => {
    const xml = getDocXml(paraWith({ numId: 5, ilvl: 2 }));
    expect(xml).toContain('<w:numPr>');
    expect(xml).toContain('<w:ilvl w:val="2"/>');
    expect(xml).toContain('<w:numId w:val="5"/>');
    // ilvl 在 numId 之前
    expect(xml.indexOf('<w:ilvl')).toBeLessThan(xml.indexOf('<w:numId'));
  });

  it('alignment → <w:jc w:val>', () => {
    for (const a of ['left', 'center', 'right', 'justify'] as const) {
      const xml = getDocXml(paraWith({ alignment: a }));
      expect(xml).toContain(`<w:jc w:val="${a}"/>`);
    }
  });

  it('indent 四欄位 → <w:ind w:left w:right w:firstLine w:hanging>（pt→twips）', () => {
    const xml = getDocXml(paraWith({
      indent: { left: 36, right: 36, firstLine: 18, hanging: 12 },
    }));
    // 36pt × 20 = 720 twips, 18pt × 20 = 360, 12pt × 20 = 240
    expect(xml).toContain('w:left="720"');
    expect(xml).toContain('w:right="720"');
    expect(xml).toContain('w:firstLine="360"');
    expect(xml).toContain('w:hanging="240"');
  });

  it('spacing before/after/line（auto rule、240 分母）', () => {
    const xml = getDocXml(paraWith({
      spacing: { before: 6, after: 6, line: { rule: 'auto', value: 1.5 } },
    }));
    // 6pt × 20 = 120 twips
    expect(xml).toContain('w:before="120"');
    expect(xml).toContain('w:after="120"');
    // 1.5 × 240 = 360
    expect(xml).toContain('w:line="360"');
    expect(xml).toContain('w:lineRule="auto"');
  });

  it('spacing line exact rule → twips 換算', () => {
    const xml = getDocXml(paraWith({
      spacing: { line: { rule: 'exact', value: 14 } },
    }));
    // 14pt × 20 = 280 twips
    expect(xml).toContain('w:line="280"');
    expect(xml).toContain('w:lineRule="exact"');
  });

  it('tabs → <w:tabs><w:tab w:val w:pos w:leader/></w:tabs>', () => {
    const xml = getDocXml(paraWith({
      tabs: [
        { pos: 100, align: 'left' },
        { pos: 200, align: 'right', leader: 'dot' },
      ],
    }));
    expect(xml).toContain('<w:tabs>');
    expect(xml).toContain('<w:tab w:val="left" w:pos="2000"/>');
    expect(xml).toContain('<w:tab w:val="right" w:pos="4000" w:leader="dot"/>');
  });

  it('textAlignment → <w:textAlignment w:val>', () => {
    const xml = getDocXml(paraWith({ textAlignment: 'center' }));
    expect(xml).toContain('<w:textAlignment w:val="center"/>');
  });

  it('snapToGrid toggle', () => {
    expect(getDocXml(paraWith({ snapToGrid: true }))).toContain('<w:snapToGrid/>');
    expect(getDocXml(paraWith({ snapToGrid: false }))).toContain('<w:snapToGrid w:val="0"/>');
  });

  it('子元素順序：pStyle → keepNext → numPr → spacing → ind → jc → textAlignment', () => {
    const xml = getDocXml(paraWith({
      keepNext: true, numId: 1, ilvl: 0,
      spacing: { before: 6 }, indent: { left: 10 },
      alignment: 'left', textAlignment: 'auto',
    }, 'MyStyle'));
    const indices = [
      ['<w:pStyle', xml.indexOf('<w:pStyle')],
      ['<w:keepNext', xml.indexOf('<w:keepNext')],
      ['<w:numPr', xml.indexOf('<w:numPr')],
      ['<w:spacing', xml.indexOf('<w:spacing')],
      ['<w:ind ', xml.indexOf('<w:ind ')],
      ['<w:jc ', xml.indexOf('<w:jc ')],
      ['<w:textAlignment', xml.indexOf('<w:textAlignment')],
    ] as const;
    for (let i = 1; i < indices.length; i++) {
      expect(indices[i][1]).toBeGreaterThan(indices[i - 1][1]);
    }
  });
});

describe('OoxmlWriter — Sprint 188 ParagraphProps 進階（pBdr / shd / framePr）', () => {
  function paraWith(props: ParagraphNode['props']): ParagraphNode {
    return { type: 'paragraph', runs: [makeRun('x')], props };
  }
  function getDocXml(para: ParagraphNode): string {
    return unzipToText(writer.write(makeDoc([makeSection([para])])))['word/document.xml'];
  }

  // ── pBdr ────────────────────────────────────────────────────────────────────

  it('borders 全四邊 → <w:pBdr> 含 top/bottom/left/right', () => {
    const xml = getDocXml(paraWith({
      borders: {
        top:    { style: 'single', width: 0.5, color: '000000' },
        bottom: { style: 'single', width: 0.5, color: '000000' },
        left:   { style: 'double', width: 1, color: 'FF0000' },
        right:  { style: 'double', width: 1, color: 'FF0000' },
      },
    }));
    expect(xml).toContain('<w:pBdr>');
    expect(xml).toContain('<w:top ');
    expect(xml).toContain('<w:bottom ');
    expect(xml).toContain('<w:left ');
    expect(xml).toContain('<w:right ');
  });

  it('borders w:sz 單位為 1/8 pt（width 0.5pt → sz=4、width 1pt → sz=8）', () => {
    const xml = getDocXml(paraWith({
      borders: { top: { style: 'single', width: 0.5, color: '000000' } },
    }));
    expect(xml).toContain('w:sz="4"');
    const xml2 = getDocXml(paraWith({
      borders: { top: { style: 'single', width: 1, color: '000000' } },
    }));
    expect(xml2).toContain('w:sz="8"');
  });

  it('borders space → w:space 屬性（缺漏跳過）', () => {
    const xml = getDocXml(paraWith({
      borders: { top: { style: 'single', width: 0.5, color: '000000', space: 4 } },
    }));
    expect(xml).toContain('w:space="4"');
    const xml2 = getDocXml(paraWith({
      borders: { top: { style: 'single', width: 0.5, color: '000000' } },
    }));
    expect(xml2).not.toContain('w:space=');
  });

  it('borders 僅單邊 → 只輸出該邊', () => {
    const xml = getDocXml(paraWith({
      borders: { bottom: { style: 'single', width: 0.5, color: '000000' } },
    }));
    expect(xml).toContain('<w:bottom ');
    expect(xml).not.toContain('<w:top ');
    expect(xml).not.toContain('<w:left ');
    expect(xml).not.toContain('<w:right ');
  });

  // ── shd ─────────────────────────────────────────────────────────────────────

  it('shading fill/color/pattern → <w:shd>', () => {
    const xml = getDocXml(paraWith({
      shading: { fill: 'DEEAF6', color: 'auto', pattern: 'clear' },
    }));
    expect(xml).toContain('<w:shd ');
    expect(xml).toContain('w:val="clear"');
    expect(xml).toContain('w:fill="DEEAF6"');
    expect(xml).toContain('w:color="auto"');
  });

  it('shading 部分欄位 → 缺漏屬性跳過', () => {
    const xml = getDocXml(paraWith({ shading: { fill: 'FFFF00' } }));
    expect(xml).toContain('w:fill="FFFF00"');
    expect(xml).not.toContain('w:val=');
    expect(xml).not.toContain('w:color=');
  });

  // ── framePr ─────────────────────────────────────────────────────────────────

  it('framePr 完整屬性 → <w:framePr/>（w/h/hSpace/vSpace 為 twips）', () => {
    const xml = getDocXml(paraWith({
      framePr: {
        width: 100, height: 50, hRule: 'exact', hSpace: 4, vSpace: 4,
        wrap: 'around', hAnchor: 'page', vAnchor: 'margin',
        xAlign: 'center', yAlign: 'top', x: 10, y: 20,
      },
    }));
    expect(xml).toContain('w:w="2000"');         // 100pt × 20
    expect(xml).toContain('w:h="1000"');         // 50pt × 20
    expect(xml).toContain('w:hRule="exact"');
    expect(xml).toContain('w:hSpace="80"');      // 4pt × 20
    expect(xml).toContain('w:vSpace="80"');
    expect(xml).toContain('w:wrap="around"');
    expect(xml).toContain('w:hAnchor="page"');
    expect(xml).toContain('w:vAnchor="margin"');
    expect(xml).toContain('w:xAlign="center"');
    expect(xml).toContain('w:yAlign="top"');
    expect(xml).toContain('w:x="200"');
    expect(xml).toContain('w:y="400"');
  });

  it('framePr 部分欄位 → 缺漏屬性跳過', () => {
    const xml = getDocXml(paraWith({ framePr: { wrap: 'around', hAnchor: 'page' } }));
    // 取出 <w:framePr ... /> 區段（避開 sectPr 的 pgSz w:w）
    const m = xml.match(/<w:framePr[^/]*\/>/);
    expect(m).not.toBeNull();
    const frameXml = m![0];
    expect(frameXml).toContain('w:wrap="around"');
    expect(frameXml).toContain('w:hAnchor="page"');
    // framePr 自身不應含 width/height 屬性
    expect(frameXml).not.toMatch(/\bw:w="/);
    expect(frameXml).not.toMatch(/\bw:h="/);
  });

  // ── schema 順序 ─────────────────────────────────────────────────────────────

  it('schema 順序：framePr → numPr → pBdr → shd → tabs', () => {
    const xml = getDocXml(paraWith({
      framePr: { wrap: 'around' },
      numId: 1, ilvl: 0,
      borders: { top: { style: 'single', width: 0.5, color: '000000' } },
      shading: { fill: 'FFFF00' },
      tabs: [{ pos: 100, align: 'left' }],
    }));
    const indices = [
      ['framePr', xml.indexOf('<w:framePr')],
      ['numPr', xml.indexOf('<w:numPr')],
      ['pBdr', xml.indexOf('<w:pBdr')],
      ['shd', xml.indexOf('<w:shd ')],
      ['tabs', xml.indexOf('<w:tabs')],
    ] as const;
    for (let i = 1; i < indices.length; i++) {
      expect(indices[i][1]).toBeGreaterThan(indices[i - 1][1]);
    }
  });
});

describe('OoxmlWriter — Sprint 189 Styles.xml 輸出', () => {
  function getStylesXml(styles: DocumentNode['styles']): string {
    const doc = makeDoc([makeSection([])]);
    doc.styles = styles;
    return unzipToText(writer.write(doc))['word/styles.xml'];
  }

  it('空 styles map → 空 <w:styles/> 骨架（與 MVS 相容）', () => {
    const xml = getStylesXml(new Map());
    expect(xml).toContain('<w:styles xmlns:w=');
    expect(xml).toMatch(/<w:styles[^>]*\/>/);
    expect(xml).not.toContain('<w:style ');
  });

  it('單一空 entry → <w:style w:type="paragraph" w:styleId="X"/>（self-closing）', () => {
    const xml = getStylesXml(new Map([['Heading1', {}]]));
    expect(xml).toContain('<w:style w:type="paragraph" w:styleId="Heading1"/>');
  });

  it('entry 含 pProps → <w:style ...><w:pPr>...</w:pPr></w:style>', () => {
    const xml = getStylesXml(new Map([
      ['Heading1', { pProps: { alignment: 'center', keepNext: true } }],
    ]));
    expect(xml).toContain('<w:style w:type="paragraph" w:styleId="Heading1">');
    expect(xml).toContain('<w:pPr>');
    expect(xml).toContain('<w:jc w:val="center"/>');
    expect(xml).toContain('<w:keepNext/>');
    expect(xml).toContain('</w:style>');
  });

  it('entry 含 rProps → <w:style ...><w:rPr>...</w:rPr></w:style>', () => {
    const xml = getStylesXml(new Map([
      ['Strong', { rProps: { bold: true, fontSize: 14 } }],
    ]));
    expect(xml).toContain('<w:rPr>');
    expect(xml).toContain('<w:b/>');
    expect(xml).toContain('<w:sz w:val="28"/>');  // 14pt × 2 half-points
  });

  it('entry 同時含 pProps 與 rProps → 兩者皆輸出', () => {
    const xml = getStylesXml(new Map([
      ['Title', { pProps: { alignment: 'center' }, rProps: { bold: true } }],
    ]));
    expect(xml).toContain('<w:pPr>');
    expect(xml).toContain('<w:rPr>');
    expect(xml.indexOf('<w:pPr>')).toBeLessThan(xml.indexOf('<w:rPr>'));
  });

  it('多 entry → 依 Map 順序輸出', () => {
    const xml = getStylesXml(new Map([
      ['A', { rProps: { bold: true } }],
      ['B', { rProps: { italic: true } }],
      ['C', { pProps: { alignment: 'right' } }],
    ]));
    const aIdx = xml.indexOf('w:styleId="A"');
    const bIdx = xml.indexOf('w:styleId="B"');
    const cIdx = xml.indexOf('w:styleId="C"');
    expect(aIdx).toBeLessThan(bIdx);
    expect(bIdx).toBeLessThan(cIdx);
  });

  it('styleId 內含 XML 特殊字元 → 跳脫', () => {
    const xml = getStylesXml(new Map([['A&B<C', {}]]));
    expect(xml).toContain('w:styleId="A&amp;B&lt;C"');
  });

  it('不輸出 docDefaults / basedOn（parser 已 flatten）', () => {
    const xml = getStylesXml(new Map([
      ['X', { pProps: { alignment: 'left' }, rProps: { bold: true } }],
    ]));
    expect(xml).not.toContain('<w:docDefaults');
    expect(xml).not.toContain('<w:basedOn');
  });
});
