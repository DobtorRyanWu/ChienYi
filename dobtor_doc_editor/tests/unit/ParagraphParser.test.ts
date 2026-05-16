/**
 * ParagraphParser 單元測試 (Sprint 1 issues #4 #5 #6)
 *
 * 用手寫 <w:p> XML 驗證解析輸出對應到 ast/types.ts 的型別。
 * 不依賴 fixture .docx — 純 OOXML 行為單元測試。
 */

import { describe, expect, it } from 'vitest';
import { ParagraphParser } from '../../static/src/core/ooxml/document/ParagraphParser';

const W_NS_DECL = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"';

function parsePXml(innerPXml: string): Element {
  const xml = `<?xml version="1.0"?><w:p ${W_NS_DECL}>${innerPXml}</w:p>`;
  const doc = new DOMParser().parseFromString(xml, 'application/xml');
  return doc.documentElement;
}

const parser = new ParagraphParser();

describe('ParagraphParser — w:r / w:t', () => {
  it('純文字段落，單一 run', () => {
    const p = parsePXml('<w:r><w:t>Hello, 世界</w:t></w:r>');
    const node = parser.parse(p);

    expect(node.type).toBe('paragraph');
    expect(node.runs).toHaveLength(1);
    expect(node.runs[0]).toMatchObject({ type: 'run', text: 'Hello, 世界' });
    expect(node.props).toEqual({});
  });

  it('多個 run 順序保留', () => {
    const p = parsePXml(
      '<w:r><w:t>A</w:t></w:r><w:r><w:t>B</w:t></w:r><w:r><w:t>C</w:t></w:r>',
    );
    const node = parser.parse(p);
    expect(node.runs.map((r) => (r.type === 'run' ? r.text : null))).toEqual([
      'A',
      'B',
      'C',
    ]);
  });

  it('w:t xml:space="preserve" 保留前後空白', () => {
    const p = parsePXml('<w:r><w:t xml:space="preserve">  spaced  </w:t></w:r>');
    const node = parser.parse(p);
    expect(node.runs[0]).toMatchObject({ type: 'run', text: '  spaced  ' });
  });
});

describe('ParagraphParser — w:rPr', () => {
  it('粗體 / 斜體 / 顏色 / 字級', () => {
    const p = parsePXml(`
      <w:r>
        <w:rPr>
          <w:b/>
          <w:i/>
          <w:color w:val="FF0000"/>
          <w:sz w:val="28"/>
        </w:rPr>
        <w:t>X</w:t>
      </w:r>
    `);
    const node = parser.parse(p);
    expect(node.runs[0]).toMatchObject({
      type: 'run',
      text: 'X',
      props: { bold: true, italic: true, color: 'FF0000', fontSize: 14 },
    });
  });

  it('w:b val="0" 為 false（停用粗體）', () => {
    const p = parsePXml('<w:r><w:rPr><w:b w:val="0"/></w:rPr><w:t>A</w:t></w:r>');
    const node = parser.parse(p);
    if (node.runs[0].type !== 'run') throw new Error('expected run');
    expect(node.runs[0].props.bold).toBeUndefined();
  });

  it('CJK 字型 (eastAsia)', () => {
    const p = parsePXml(`
      <w:r>
        <w:rPr><w:rFonts w:ascii="Calibri" w:eastAsia="新細明體"/></w:rPr>
        <w:t>中文</w:t>
      </w:r>
    `);
    const node = parser.parse(p);
    if (node.runs[0].type !== 'run') throw new Error('expected run');
    expect(node.runs[0].props).toMatchObject({
      fontFamily: 'Calibri',
      fontFamilyEastAsia: '新細明體',
    });
  });

  it('底線、刪除線、上下標', () => {
    const p = parsePXml(`
      <w:r>
        <w:rPr>
          <w:u w:val="single"/>
          <w:strike/>
          <w:vertAlign w:val="superscript"/>
        </w:rPr>
        <w:t>x</w:t>
      </w:r>
    `);
    const node = parser.parse(p);
    if (node.runs[0].type !== 'run') throw new Error('expected run');
    expect(node.runs[0].props).toMatchObject({
      underline: 'single',
      strike: true,
      vertAlign: 'superscript',
    });
  });
});

describe('ParagraphParser — w:pPr', () => {
  it('置中對齊 + style ID', () => {
    const p = parsePXml(`
      <w:pPr>
        <w:pStyle w:val="Title"/>
        <w:jc w:val="center"/>
      </w:pPr>
      <w:r><w:t>Title</w:t></w:r>
    `);
    const node = parser.parse(p);
    expect(node.props.alignment).toBe('center');
    expect(node.styleId).toBe('Title');
  });

  it('jc both → justify', () => {
    const p = parsePXml('<w:pPr><w:jc w:val="both"/></w:pPr>');
    const node = parser.parse(p);
    expect(node.props.alignment).toBe('justify');
  });

  it('縮排（twip → pt）', () => {
    // 720 twip = 36 pt = 0.5 inch
    const p = parsePXml(
      '<w:pPr><w:ind w:left="720" w:firstLine="240"/></w:pPr>',
    );
    const node = parser.parse(p);
    expect(node.props.indent).toEqual({ left: 36, firstLine: 12 });
  });

  it('段落間距 + 行距 (atLeast 規則)', () => {
    const p = parsePXml(`
      <w:pPr>
        <w:spacing w:before="120" w:after="60" w:line="480" w:lineRule="atLeast"/>
      </w:pPr>
    `);
    const node = parser.parse(p);
    expect(node.props.spacing).toEqual({
      before: 6, // 120 twip = 6 pt
      after: 3,
      line: { rule: 'atLeast', value: 24 }, // 480 twip = 24 pt
    });
  });

  it('行距 auto 用 240 分母', () => {
    // line=360 + auto → 1.5 倍行距
    const p = parsePXml(
      '<w:pPr><w:spacing w:line="360" w:lineRule="auto"/></w:pPr>',
    );
    const node = parser.parse(p);
    expect(node.props.spacing?.line).toEqual({ rule: 'auto', value: 1.5 });
  });

  it('numbering numId + ilvl', () => {
    const p = parsePXml(`
      <w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="3"/></w:numPr></w:pPr>
    `);
    const node = parser.parse(p);
    expect(node.props.numId).toBe(3);
    expect(node.props.ilvl).toBe(1);
  });

  it('keepNext + pageBreakBefore 旗標', () => {
    const p = parsePXml('<w:pPr><w:keepNext/><w:pageBreakBefore/></w:pPr>');
    const node = parser.parse(p);
    expect(node.props.keepNext).toBe(true);
    expect(node.props.pageBreakBefore).toBe(true);
  });
});

describe('ParagraphParser — inline elements', () => {
  it('w:br type="line" → BreakNode (line)', () => {
    const p = parsePXml(
      '<w:r><w:t>A</w:t><w:br/><w:t>B</w:t></w:r>',
    );
    const node = parser.parse(p);
    expect(node.runs).toHaveLength(3);
    expect(node.runs[1]).toMatchObject({ type: 'break', breakType: 'line' });
  });

  it('w:br type="page" → BreakNode (page)', () => {
    const p = parsePXml('<w:r><w:br w:type="page"/></w:r>');
    const node = parser.parse(p);
    expect(node.runs[0]).toMatchObject({ type: 'break', breakType: 'page' });
  });

  it('w:tab 轉為 \\t', () => {
    const p = parsePXml('<w:r><w:t>A</w:t><w:tab/><w:t>B</w:t></w:r>');
    const node = parser.parse(p);
    expect(node.runs).toHaveLength(1);
    expect(node.runs[0]).toMatchObject({ type: 'run', text: 'A\tB' });
  });

  it('w:fldSimple PAGE 含快取值', () => {
    const p = parsePXml(`
      <w:fldSimple w:instr=" PAGE ">
        <w:r><w:t>3</w:t></w:r>
      </w:fldSimple>
    `);
    const node = parser.parse(p);
    expect(node.runs[0]).toMatchObject({
      type: 'field',
      fieldType: 'PAGE',
      cachedValue: '3',
    });
  });

  it('w:fldSimple unknown instruction 標為 unknown', () => {
    const p = parsePXml('<w:fldSimple w:instr=" SEQ Figure \\* ARABIC "/>');
    const node = parser.parse(p);
    expect(node.runs[0]).toMatchObject({ type: 'field', fieldType: 'unknown' });
  });

  it('w:hyperlink 內 run 展平到段落層', () => {
    const p = parsePXml(`
      <w:hyperlink>
        <w:r><w:t>click</w:t></w:r>
        <w:r><w:t> here</w:t></w:r>
      </w:hyperlink>
    `);
    const node = parser.parse(p);
    expect(node.runs).toHaveLength(2);
    expect(node.runs[0]).toMatchObject({ type: 'run', text: 'click' });
    expect(node.runs[1]).toMatchObject({ type: 'run', text: ' here' });
  });
});

describe('ParagraphParser — 邊界情況', () => {
  it('空 <w:p/> 段落 → runs=[], props={}', () => {
    const p = parsePXml('');
    const node = parser.parse(p);
    expect(node.type).toBe('paragraph');
    expect(node.runs).toEqual([]);
    expect(node.props).toEqual({});
    expect(node.styleId).toBeUndefined();
  });

  it('w:r 只有 w:rPr 沒有文字內容 → 不產生 RunNode', () => {
    const p = parsePXml('<w:r><w:rPr><w:b/></w:rPr></w:r>');
    const node = parser.parse(p);
    expect(node.runs).toEqual([]);
  });

  it('未知子節點靜默忽略，不丟例外', () => {
    const p = parsePXml(`
      <w:bookmarkStart w:id="0" w:name="x"/>
      <w:proofErr w:type="spellStart"/>
      <w:r><w:t>OK</w:t></w:r>
    `);
    const node = parser.parse(p);
    expect(node.runs).toHaveLength(1);
    expect(node.runs[0]).toMatchObject({ type: 'run', text: 'OK' });
  });
});

// ─── Sprint 122：OLE / VML pict 降級 placeholder ─────────────────────────────
describe('ParagraphParser — Sprint 122 OLE / pict fallback', () => {
  const O_NS_DECL = 'xmlns:o="urn:schemas-microsoft-com:office:office"';
  const V_NS_DECL = 'xmlns:v="urn:schemas-microsoft-com:vml"';
  const R_NS_DECL = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"';

  function parsePXmlNs(innerPXml: string): Element {
    const xml = `<?xml version="1.0"?><w:p ${W_NS_DECL} ${O_NS_DECL} ${V_NS_DECL} ${R_NS_DECL}>${innerPXml}</w:p>`;
    const doc = new DOMParser().parseFromString(xml, 'application/xml');
    return doc.documentElement;
  }

  it('w:object 帶 ProgID → italic 文字 placeholder「[嵌入物件: <ProgID>]」', () => {
    const p = parsePXmlNs(`
      <w:r>
        <w:object>
          <v:shape id="_x0000_i1025" type="#_x0000_t75"/>
          <o:OLEObject Type="Embed" ProgID="Equation.3" ShapeID="_x0000_i1025" DrawAspect="Content" ObjectID="_1234567" r:id="rId4"/>
        </w:object>
      </w:r>
    `);
    const node = parser.parse(p);
    expect(node.runs).toHaveLength(1);
    expect(node.runs[0]).toMatchObject({
      type: 'run',
      text: '[嵌入物件: Equation.3]',
      props: { italic: true },
    });
  });

  it('w:object 帶 ProgID + v:shape alt → 兩者組合', () => {
    const p = parsePXmlNs(`
      <w:r>
        <w:object>
          <v:shape id="s1" alt="二元二次方程式"/>
          <o:OLEObject ProgID="Equation.3" r:id="rId5"/>
        </w:object>
      </w:r>
    `);
    const node = parser.parse(p);
    expect(node.runs).toHaveLength(1);
    expect(node.runs[0]).toMatchObject({
      type: 'run',
      text: '[嵌入物件: Equation.3 — 二元二次方程式]',
      props: { italic: true },
    });
  });

  it('w:object 完全沒 ProgID / alt → 純「[嵌入物件]」placeholder', () => {
    const p = parsePXmlNs(`
      <w:r>
        <w:object>
          <v:shape id="s2"/>
        </w:object>
      </w:r>
    `);
    const node = parser.parse(p);
    expect(node.runs).toHaveLength(1);
    expect(node.runs[0]).toMatchObject({ type: 'run', text: '[嵌入物件]' });
  });

  it('w:pict 純 VML 圖（無 OLEObject）→「[圖片(VML)]」', () => {
    const p = parsePXmlNs(`
      <w:r>
        <w:pict>
          <v:shape id="img1"/>
        </w:pict>
      </w:r>
    `);
    const node = parser.parse(p);
    expect(node.runs).toHaveLength(1);
    expect(node.runs[0]).toMatchObject({ type: 'run', text: '[圖片(VML)]' });
  });

  it('w:pict 純 VML 帶 alt → 加 alt 補充', () => {
    const p = parsePXmlNs(`
      <w:r>
        <w:pict>
          <v:shape id="img2" alt="logo"/>
        </w:pict>
      </w:r>
    `);
    const node = parser.parse(p);
    expect(node.runs).toHaveLength(1);
    expect(node.runs[0]).toMatchObject({ type: 'run', text: '[圖片(VML): logo]' });
  });

  it('w:pict 內含 OLEObject → 走 OLE 文案（不是 VML 文案）', () => {
    const p = parsePXmlNs(`
      <w:r>
        <w:pict>
          <v:shape id="ole-pict" alt="圖象 OLE"/>
          <o:OLEObject ProgID="Excel.Sheet.12" r:id="rId6"/>
        </w:pict>
      </w:r>
    `);
    const node = parser.parse(p);
    expect(node.runs).toHaveLength(1);
    expect(node.runs[0]).toMatchObject({
      type: 'run',
      text: '[嵌入物件: Excel.Sheet.12 — 圖象 OLE]',
    });
  });

  it('w:object 與 w:t 文字並存 → text run + placeholder run 分離輸出', () => {
    const p = parsePXmlNs(`
      <w:r>
        <w:t>公式：</w:t>
        <w:object>
          <o:OLEObject ProgID="Equation.3" r:id="rId7"/>
        </w:object>
        <w:t>，結束</w:t>
      </w:r>
    `);
    const node = parser.parse(p);
    // text run 1 / OLE placeholder / text run 2
    expect(node.runs).toHaveLength(3);
    expect(node.runs[0]).toMatchObject({ type: 'run', text: '公式：' });
    expect(node.runs[1]).toMatchObject({ type: 'run', text: '[嵌入物件: Equation.3]' });
    expect(node.runs[2]).toMatchObject({ type: 'run', text: '，結束' });
  });

  it('w:object placeholder 繼承 baseProps（rPr bold）+ italic overlay', () => {
    // baseProps 的 italic 會被 placeholder overlay 為 true（不管原本如何）
    const p = parsePXmlNs(`
      <w:r>
        <w:rPr><w:b/></w:rPr>
        <w:object>
          <o:OLEObject ProgID="Equation.3" r:id="rId8"/>
        </w:object>
      </w:r>
    `);
    const node = parser.parse(p);
    expect(node.runs).toHaveLength(1);
    expect(node.runs[0].type).toBe('run');
    const run = node.runs[0] as { type: 'run'; props: { bold?: boolean; italic?: boolean } };
    expect(run.props.bold).toBe(true);
    expect(run.props.italic).toBe(true);
  });
});
