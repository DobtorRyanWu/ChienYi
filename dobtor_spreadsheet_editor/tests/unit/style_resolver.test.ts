// style_resolver.test.ts — xf cascade 攤平（規劃書 §2.1）
import { describe, it, expect } from 'vitest';
import { StylesParser } from '../../static/src/core/ooxmlspreadsheet/styles_parser';
import { StyleResolver } from '../../static/src/core/ooxmlspreadsheet/style_resolver';

const NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';

// fonts: 0=預設 / 1=粗體 / 2=紅色粗體
// fills: 0=none / 1=gray / 2=solid 黃
// borders: 0=空 / 1=thin
// cellStyleXfs[0]：numFmt0 font0 fill0 border0 + alignment vertical=center（named style 基底）
// cellXfs:
//   0：全 0、無 apply → 全繼承 named style（alignment vertical=center）
//   1：fontId1 + applyFont → 只覆寫 font，其餘繼承
//   2：全自訂 + 全 apply（含 numFmt176 日期、alignment horizontal=center）
//   3：fontId1 但「無」applyFont → 應繼承 named style 的 font0（驗證 apply 旗標 gating）
const STYLES = StylesParser.parse(
    `<?xml version="1.0"?><styleSheet xmlns="${NS}">` +
        `<numFmts count="1"><numFmt numFmtId="176" formatCode="[$-404]gge&quot;年&quot;m&quot;月&quot;d&quot;日&quot;;@"/></numFmts>` +
        `<fonts count="3">` +
        `<font><sz val="12"/><name val="新細明體"/></font>` +
        `<font><b/><sz val="12"/><name val="標楷體"/></font>` +
        `<font><b/><sz val="14"/><color rgb="FFFF0000"/><name val="標楷體"/></font>` +
        `</fonts>` +
        `<fills count="3">` +
        `<fill><patternFill patternType="none"/></fill>` +
        `<fill><patternFill patternType="gray125"/></fill>` +
        `<fill><patternFill patternType="solid"><fgColor rgb="FFFFFF00"/></patternFill></fill>` +
        `</fills>` +
        `<borders count="2">` +
        `<border><left/><right/><top/><bottom/></border>` +
        `<border><left style="thin"/><right style="thin"/><top style="thin"/><bottom style="thin"/></border>` +
        `</borders>` +
        `<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"><alignment vertical="center"/></xf></cellStyleXfs>` +
        `<cellXfs count="4">` +
        `<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>` +
        `<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>` +
        `<xf numFmtId="176" fontId="2" fillId="2" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>` +
        `<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/>` +
        `</cellXfs></styleSheet>`,
);
const R = new StyleResolver(STYLES);

describe('StyleResolver — cascade', () => {
    it('index 0：全繼承 named style', () => {
        const s = R.resolve(0);
        expect(s.numFmtId).toBe(0);
        expect(s.font.bold).toBeUndefined();
        expect(s.fill.patternType).toBe('none');
        expect(s.alignment?.vertical).toBe('center'); // 繼承自 cellStyleXf
    });
    it('index 1：applyFont 只覆寫 font、其餘繼承', () => {
        const s = R.resolve(1);
        expect(s.font.bold).toBe(true);
        expect(s.font.name).toBe('標楷體');
        expect(s.fill.patternType).toBe('none'); // 繼承
        expect(s.alignment?.vertical).toBe('center'); // 繼承 named style
    });
    it('index 2：全自訂（日期 numFmt + 紅粗體 + 黃底 + thin 框 + 置中）', () => {
        const s = R.resolve(2);
        expect(s.numFmtId).toBe(176);
        expect(s.isDate).toBe(true);
        expect(s.font.bold).toBe(true);
        expect(s.font.color?.rgb).toBe('FFFF0000');
        expect(s.font.size).toBe(14);
        expect(s.fill.patternType).toBe('solid');
        expect(s.fill.fgColor?.rgb).toBe('FFFFFF00');
        expect(s.border.left?.style).toBe('thin');
        expect(s.alignment?.horizontal).toBe('center');
        expect(s.alignment?.wrapText).toBe(true);
    });
    it('index 3：fontId1 但無 applyFont → 繼承 named style font0（apply gating）', () => {
        const s = R.resolve(3);
        expect(s.font.bold).toBeUndefined(); // 非粗體 → 證明沒套 cellXf 的 fontId1
        expect(s.font.name).toBe('新細明體');
    });
});

describe('StyleResolver — 預設與快取', () => {
    it('styleIndex undefined → 預設樣式', () => {
        const s = R.resolve(undefined);
        expect(s.numFmtId).toBe(0);
        expect(s.font.name).toBe('新細明體');
    });
    it('越界 index → 預設樣式不丟錯', () => {
        expect(() => R.resolve(999)).not.toThrow();
    });
    it('同 index 回快取同一物件', () => {
        expect(R.resolve(2)).toBe(R.resolve(2));
    });
});
