/**
 * ToCanvasEditor 單元測試 (Phase D.1)
 *
 * 驗證 DocumentNode → IElement[] 轉換正確：
 *   - Run 文字逐字拆 + 樣式套用
 *   - 段落結束符 \n + rowFlex / rowMargin
 *   - Break / Field / Image / Hyperlink
 *   - Table colgroup + trList + colspan + rowspan + isContinuation 跳過
 *   - 多 section 之間的 pageBreak
 */

import { describe, expect, it } from 'vitest';
import { ToCanvasEditor } from '../../static/src/core/ooxml/mapper/ToCanvasEditor';
import type {
  DocumentNode,
  ParagraphNode,
  RunNode,
  SectionNode,
  TableNode,
} from '../../static/src/core/ooxml/ast/types';

const mapper = new ToCanvasEditor();

function makeRun(text: string, props: RunNode['props'] = {}): RunNode {
  return { type: 'run', text, props };
}

function makeParagraph(
  runs: ParagraphNode['runs'],
  props: ParagraphNode['props'] = {},
): ParagraphNode {
  return { type: 'paragraph', runs, props };
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

function makeDoc(
  sections: SectionNode[],
  media = new Map<string, string>(),
  numbering: DocumentNode['numbering'] = new Map(),
): DocumentNode {
  return {
    type: 'document',
    sections,
    headers: new Map(),
    footers: new Map(),
    footnotes: new Map(),
    endnotes: new Map(),
    settings: {},
    fontTable: new Map(),
    webSettings: {},
    styles: new Map(),
    numbering,
    media,
    docProps: {},
    appProps: {},
    customProps: new Map(),
    contentTypes: { defaults: new Map(), overrides: new Map() },
  };
}

describe('ToCanvasEditor — 基本 Run 轉換', () => {
  it('段落內文字逐字拆，每字一個 IElement', () => {
    const doc = makeDoc([makeSection([makeParagraph([makeRun('abc')])])]);
    const elements = mapper.convert(doc);
    // a, b, c, \n（段落終止）
    expect(elements).toHaveLength(4);
    expect(elements[0]).toMatchObject({ value: 'a' });
    expect(elements[1]).toMatchObject({ value: 'b' });
    expect(elements[2]).toMatchObject({ value: 'c' });
    expect(elements[3]).toMatchObject({ value: '\n' });
  });

  it('CJK 字元每字一個 IElement', () => {
    const doc = makeDoc([makeSection([makeParagraph([makeRun('監造會議')])])]);
    const elements = mapper.convert(doc);
    expect(elements.slice(0, 4).map((e) => e.value)).toEqual([
      '監', '造', '會', '議',
    ]);
  });

  it('RunProps 樣式套用到每個字元', () => {
    const doc = makeDoc([
      makeSection([
        makeParagraph([
          makeRun('AB', {
            fontFamily: 'Arial',
            fontSize: 12,
            bold: true,
            italic: true,
            color: '0000FF',
          }),
        ]),
      ]),
    ]);
    const elements = mapper.convert(doc);
    expect(elements[0]).toMatchObject({
      value: 'A',
      font: 'Arial',
      size: 12,
      bold: true,
      italic: true,
      color: '#0000FF',
    });
    expect(elements[1]).toMatchObject({ value: 'B', bold: true, italic: true });
  });

  it('CJK 字型優先：fontFamilyEastAsia 優於 fontFamily', () => {
    const doc = makeDoc([
      makeSection([
        makeParagraph([
          makeRun('中', {
            fontFamily: 'Times New Roman',
            fontFamilyEastAsia: '細明體',
          }),
        ]),
      ]),
    ]);
    const elements = mapper.convert(doc);
    expect(elements[0].font).toBe('細明體');
  });
});

describe('ToCanvasEditor — 段落樣式', () => {
  it('alignment center → rowFlex=center 套用所有元素', () => {
    const doc = makeDoc([
      makeSection([makeParagraph([makeRun('xy')], { alignment: 'center' })]),
    ]);
    const elements = mapper.convert(doc);
    for (const el of elements) {
      expect(el.rowFlex).toBe('center');
    }
  });

  it('alignment justify → rowFlex=justify', () => {
    const doc = makeDoc([
      makeSection([makeParagraph([makeRun('a')], { alignment: 'justify' })]),
    ]);
    const elements = mapper.convert(doc);
    expect(elements[0].rowFlex).toBe('justify');
  });

  it('段落間距 spacing.before → rowMargin', () => {
    const doc = makeDoc([
      makeSection([
        makeParagraph([makeRun('x')], { spacing: { before: 12 } }),
      ]),
    ]);
    const elements = mapper.convert(doc);
    expect(elements[0].rowMargin).toBe(12);
  });
});

describe('ToCanvasEditor — Break / Field', () => {
  it('line break → \\n IElement', () => {
    const doc = makeDoc([
      makeSection([
        makeParagraph([
          makeRun('a'),
          { type: 'break', breakType: 'line' },
          makeRun('b'),
        ]),
      ]),
    ]);
    const elements = mapper.convert(doc);
    // a, \n（line break）, b, \n（段落終止）
    expect(elements.map((e) => e.value)).toEqual(['a', '\n', 'b', '\n']);
  });

  it('page break → type=pageBreak', () => {
    const doc = makeDoc([
      makeSection([
        makeParagraph([{ type: 'break', breakType: 'page' }]),
      ]),
    ]);
    const elements = mapper.convert(doc);
    expect(elements[0]).toMatchObject({ type: 'pageBreak', value: '\n' });
  });

  it('field 用 cachedValue', () => {
    const doc = makeDoc([
      makeSection([
        makeParagraph([
          {
            type: 'field',
            instruction: ' PAGE ',
            fieldType: 'PAGE',
            cachedValue: '12',
          },
        ]),
      ]),
    ]);
    const elements = mapper.convert(doc);
    expect(elements.slice(0, 2).map((e) => e.value)).toEqual(['1', '2']);
  });
});

describe('ToCanvasEditor — Image', () => {
  it('inline image → type=image，從 media map 取 dataURL', () => {
    const media = new Map([['rId5', 'data:image/png;base64,XYZ']]);
    const doc = makeDoc(
      [
        makeSection([
          makeParagraph([
            { type: 'inlineImage', rId: 'rId5', width: 100, height: 50 },
          ]),
        ]),
      ],
      media,
    );
    const elements = mapper.convert(doc);
    expect(elements[0]).toMatchObject({
      type: 'image',
      value: 'data:image/png;base64,XYZ',
      width: 100,
      height: 50,
    });
  });

  it('找不到 rId 對應 media 顯示「[圖片缺失]」', () => {
    const doc = makeDoc([
      makeSection([
        makeParagraph([
          { type: 'inlineImage', rId: 'rId99', width: 100, height: 50 },
        ]),
      ]),
    ]);
    const elements = mapper.convert(doc);
    expect(elements[0].value).toBe('[圖片缺失]');
  });

  it('float image 暫降級為 inline image', () => {
    const media = new Map([['rId7', 'data:image/jpeg;base64,ZZZ']]);
    const doc = makeDoc(
      [
        makeSection([
          makeParagraph([
            {
              type: 'floatImage',
              rId: 'rId7',
              width: 200,
              height: 100,
              posH: { relativeFrom: 'margin' },
              posV: { relativeFrom: 'paragraph' },
              wrapType: 'square',
            },
          ]),
        ]),
      ],
      media,
    );
    const elements = mapper.convert(doc);
    expect(elements[0].type).toBe('image');
    expect(elements[0].value).toBe('data:image/jpeg;base64,ZZZ');
  });
});

describe('ToCanvasEditor — Hyperlink', () => {
  it('帶 url 的 hyperlink → type=hyperlink + valueList', () => {
    const doc = makeDoc([
      makeSection([
        makeParagraph([
          {
            type: 'run',
            text: 'Click',
            props: {},
            hyperlink: { rId: 'rId1', url: 'https://example.com' },
          },
        ]),
      ]),
    ]);
    const elements = mapper.convert(doc);
    expect(elements[0]).toMatchObject({
      type: 'hyperlink',
      url: 'https://example.com',
    });
    expect(elements[0].valueList).toHaveLength(5); // C, l, i, c, k
  });

  it('沒 url 也沒 anchor 的 hyperlink 降級為純 run', () => {
    const doc = makeDoc([
      makeSection([
        makeParagraph([
          {
            type: 'run',
            text: 'X',
            props: {},
            hyperlink: { rId: 'rId99' }, // url 沒解析到
          },
        ]),
      ]),
    ]);
    const elements = mapper.convert(doc);
    expect(elements[0].type).toBeUndefined();
    expect(elements[0].value).toBe('X');
  });
});

describe('ToCanvasEditor — Table', () => {
  function makeTable(): TableNode {
    return {
      type: 'table',
      grid: [100, 100],
      rows: [
        {
          type: 'row',
          cells: [
            {
              type: 'cell',
              gridCol: 0,
              gridSpan: 1,
              rowSpan: 2, // anchor 跨 2 列
              isContinuation: false,
              content: [makeParagraph([makeRun('A')])],
              props: {},
            },
            {
              type: 'cell',
              gridCol: 1,
              gridSpan: 1,
              rowSpan: 1,
              isContinuation: false,
              content: [makeParagraph([makeRun('B')])],
              props: {},
            },
          ],
          props: { isHeader: false, cantSplit: false },
        },
        {
          type: 'row',
          cells: [
            {
              // vMerge continue（跳過）
              type: 'cell',
              gridCol: 0,
              gridSpan: 1,
              rowSpan: 1,
              isContinuation: true,
              content: [],
              props: {},
            },
            {
              type: 'cell',
              gridCol: 1,
              gridSpan: 1,
              rowSpan: 1,
              isContinuation: false,
              content: [makeParagraph([makeRun('C')])],
              props: {},
            },
          ],
          props: { isHeader: false, cantSplit: false },
        },
      ],
      props: {},
    };
  }

  it('colgroup widths + trList + 跳過 isContinuation cells', () => {
    const doc = makeDoc([makeSection([makeTable()])]);
    const elements = mapper.convert(doc);
    const table = elements[0];
    expect(table.type).toBe('table');
    expect(table.colgroup).toHaveLength(2);
    expect(table.colgroup?.[0].width).toBe(100);
    expect(table.trList).toHaveLength(2);
    // 第一列：anchor (rowspan=2) + B
    expect(table.trList?.[0].tdList).toHaveLength(2);
    expect(table.trList?.[0].tdList[0].rowspan).toBe(2);
    // 第二列：只有 C（continuation 被跳過）
    expect(table.trList?.[1].tdList).toHaveLength(1);
  });

  it('cell vAlign center → verticalAlign=middle', () => {
    const tbl: TableNode = {
      type: 'table',
      grid: [100],
      rows: [
        {
          type: 'row',
          cells: [
            {
              type: 'cell',
              gridCol: 0,
              gridSpan: 1,
              rowSpan: 1,
              isContinuation: false,
              content: [],
              props: { vAlign: 'center' },
            },
          ],
          props: { isHeader: false, cantSplit: false },
        },
      ],
      props: {},
    };
    const doc = makeDoc([makeSection([tbl])]);
    const elements = mapper.convert(doc);
    const td = elements[0].trList?.[0].tdList[0];
    expect(td?.verticalAlign).toBe('middle');
  });

  it('cell shading.fill → backgroundColor 加 # 前綴', () => {
    const tbl: TableNode = {
      type: 'table',
      grid: [100],
      rows: [
        {
          type: 'row',
          cells: [
            {
              type: 'cell',
              gridCol: 0,
              gridSpan: 1,
              rowSpan: 1,
              isContinuation: false,
              content: [],
              props: { shading: { fill: 'FFFF00' } },
            },
          ],
          props: { isHeader: false, cantSplit: false },
        },
      ],
      props: {},
    };
    const doc = makeDoc([makeSection([tbl])]);
    const elements = mapper.convert(doc);
    expect(elements[0].trList?.[0].tdList[0].backgroundColor).toBe('#FFFF00');
  });
});

describe('ToCanvasEditor — 多 section', () => {
  it('section 之間插 pageBreak', () => {
    const doc = makeDoc([
      makeSection([makeParagraph([makeRun('A')])]),
      makeSection([makeParagraph([makeRun('B')])]),
    ]);
    const elements = mapper.convert(doc);
    // A, \n, pageBreak, B, \n
    expect(elements.map((e) => e.value)).toEqual(['A', '\n', '\n', 'B', '\n']);
    expect(elements[2].type).toBe('pageBreak');
  });

  it('單一 section 開頭不插 pageBreak', () => {
    const doc = makeDoc([makeSection([makeParagraph([makeRun('A')])])]);
    const elements = mapper.convert(doc);
    expect(elements[0].type).toBeUndefined();
    expect(elements[0].value).toBe('A');
  });
});

// ── Sprint 138：numbering wire-up ───────────────────────────────────────────

import type { AbstractNumbering, NumberingLevel } from '../../static/src/core/ooxml/ast/types';

function level(ilvl: number, opts: Partial<NumberingLevel> = {}): NumberingLevel {
  return { ilvl, numFmt: 'decimal', text: `%${ilvl + 1}.`, start: 1, ...opts };
}

function numMap(numId: number, ...levels: NumberingLevel[]): Map<number, AbstractNumbering> {
  return new Map([[numId, { abstractNumId: 0, levels }]]);
}

describe('ToCanvasEditor — Sprint 138 numbering wire-up', () => {
  it('段落無 numId：不 emit prefix（回歸 Sprint 137 之前行為）', () => {
    const doc = makeDoc([makeSection([makeParagraph([makeRun('abc')])])]);
    const elements = mapper.convert(doc);
    // a, b, c, \n（無編號 prefix、無 tab）
    expect(elements.map((e) => e.value)).toEqual(['a', 'b', 'c', '\n']);
  });

  it('段落有 numId：emit 編號 prefix + tab + 文字', () => {
    const para = makeParagraph([makeRun('hello')], { numId: 1, ilvl: 0 });
    const doc = makeDoc([makeSection([para])], new Map(), numMap(1, level(0)));
    const elements = mapper.convert(doc);
    // "1", ".", \t, h, e, l, l, o, \n
    expect(elements.map((e) => e.value)).toEqual(['1', '.', '\t', 'h', 'e', 'l', 'l', 'o', '\n']);
    expect(elements[2].type).toBe('tab');
  });

  it('連續同 numId 段落：counter +1', () => {
    const numbering = numMap(1, level(0));
    const doc = makeDoc(
      [
        makeSection([
          makeParagraph([makeRun('A')], { numId: 1, ilvl: 0 }),
          makeParagraph([makeRun('B')], { numId: 1, ilvl: 0 }),
          makeParagraph([makeRun('C')], { numId: 1, ilvl: 0 }),
        ]),
      ],
      new Map(),
      numbering,
    );
    const elements = mapper.convert(doc);
    const values = elements.map((e) => e.value);
    // P1: "1", ".", \t, A, \n
    // P2: "2", ".", \t, B, \n
    // P3: "3", ".", \t, C, \n
    expect(values).toEqual([
      '1', '.', '\t', 'A', '\n',
      '2', '.', '\t', 'B', '\n',
      '3', '.', '\t', 'C', '\n',
    ]);
  });

  it('多 ilvl 巢狀：深層 reset、淺層保留', () => {
    const numbering = numMap(1, level(0), level(1, { text: '%1.%2.' }));
    const doc = makeDoc(
      [
        makeSection([
          makeParagraph([makeRun('A')], { numId: 1, ilvl: 0 }),
          makeParagraph([makeRun('B')], { numId: 1, ilvl: 1 }),
          makeParagraph([makeRun('C')], { numId: 1, ilvl: 1 }),
          makeParagraph([makeRun('D')], { numId: 1, ilvl: 0 }),
          makeParagraph([makeRun('E')], { numId: 1, ilvl: 1 }),
        ]),
      ],
      new Map(),
      numbering,
    );
    const elements = mapper.convert(doc);
    const values = elements.map((e) => e.value).join('');
    // P1: 1.\tA\n  P2: 1.1.\tB\n  P3: 1.2.\tC\n  P4: 2.\tD\n  P5: 2.1.\tE\n
    expect(values).toBe('1.\tA\n1.1.\tB\n1.2.\tC\n2.\tD\n2.1.\tE\n');
  });

  it('多 numId 互相獨立', () => {
    const numbering: Map<number, AbstractNumbering> = new Map([
      [1, { abstractNumId: 0, levels: [level(0)] }],
      [2, { abstractNumId: 1, levels: [level(0)] }],
    ]);
    const doc = makeDoc(
      [
        makeSection([
          makeParagraph([makeRun('X')], { numId: 1, ilvl: 0 }),
          makeParagraph([makeRun('Y')], { numId: 2, ilvl: 0 }),
          makeParagraph([makeRun('Z')], { numId: 1, ilvl: 0 }),
        ]),
      ],
      new Map(),
      numbering,
    );
    const elements = mapper.convert(doc);
    const values = elements.map((e) => e.value).join('');
    // P1: 1.\tX\n（numId=1）  P2: 1.\tY\n（numId=2 從 start）  P3: 2.\tZ\n（numId=1 接 2）
    expect(values).toBe('1.\tX\n1.\tY\n2.\tZ\n');
  });

  it('缺失 numbering map：placeholder fallback decimal', () => {
    const para = makeParagraph([makeRun('x')], { numId: 99, ilvl: 0 });
    // numbering 為空 map、numId=99 找不到
    const doc = makeDoc([makeSection([para])], new Map(), new Map());
    const elements = mapper.convert(doc);
    // placeholder: "1", ".", \t, x, \n
    expect(elements.map((e) => e.value)).toEqual(['1', '.', '\t', 'x', '\n']);
  });

  it('中文章節「第%1章」+ chineseCounting', () => {
    const numbering = numMap(1, level(0, { text: '第%1章', numFmt: 'chineseCounting' }));
    const doc = makeDoc(
      [
        makeSection([
          makeParagraph([makeRun('緒論')], { numId: 1, ilvl: 0 }),
          makeParagraph([makeRun('結論')], { numId: 1, ilvl: 0 }),
        ]),
      ],
      new Map(),
      numbering,
    );
    const elements = mapper.convert(doc);
    const values = elements.map((e) => e.value).join('');
    expect(values).toBe('第一章\t緒論\n第二章\t結論\n');
  });

  it('Bullet：lvlText 是字元（如「•」）、不依賴 expandLvlText 計算', () => {
    const numbering = numMap(1, level(0, { numFmt: 'bullet', text: '•' }));
    const para = makeParagraph([makeRun('item')], { numId: 1, ilvl: 0 });
    const doc = makeDoc([makeSection([para])], new Map(), numbering);
    const elements = mapper.convert(doc);
    expect(elements.map((e) => e.value)).toEqual(['•', '\t', 'i', 't', 'e', 'm', '\n']);
  });

  it('空 lvlText：跳過 prefix emit（避免空字串污染）', () => {
    const numbering = numMap(1, level(0, { text: '' }));
    const para = makeParagraph([makeRun('x')], { numId: 1, ilvl: 0 });
    const doc = makeDoc([makeSection([para])], new Map(), numbering);
    const elements = mapper.convert(doc);
    // 完全沒 prefix、沒 tab
    expect(elements.map((e) => e.value)).toEqual(['x', '\n']);
  });

  it('cell 內 numbered paragraph：counter 與 body 共享 state', () => {
    const numbering = numMap(1, level(0));
    const tbl: TableNode = {
      type: 'table',
      grid: [100],
      rows: [
        {
          type: 'row',
          props: { isHeader: false, cantSplit: false },
          cells: [
            {
              type: 'cell',
              gridSpan: 1,
              rowSpan: 1,
              isContinuation: false,
              props: {},
              content: [makeParagraph([makeRun('cell')], { numId: 1, ilvl: 0 })],
            },
          ],
        },
      ],
      props: {},
    };
    const doc = makeDoc(
      [makeSection([makeParagraph([makeRun('body')], { numId: 1, ilvl: 0 }), tbl])],
      new Map(),
      numbering,
    );
    const elements = mapper.convert(doc);
    const tableIdx = elements.findIndex((e) => e.type === 'table');
    expect(tableIdx).toBeGreaterThanOrEqual(0);
    const bodyPart = elements.slice(0, tableIdx).map((e) => e.value).join('');
    expect(bodyPart).toBe('1.\tbody\n');
    // cell 內 paragraph：counter advance 到 2（共用 state）
    const tableEl = elements[tableIdx];
    const cellValue = tableEl.trList?.[0].tdList[0].value ?? [];
    expect(cellValue.map((e) => e.value).join('')).toBe('2.\tcell\n');
  });
});

