// concrete_style.test.ts — StyleResolver + ThemeResolver → 全具體 RGB（Sprint 10 對接層）
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { WorkbookParser } from '../../static/src/core/ooxmlspreadsheet/workbook_parser';
import { StylesParser } from '../../static/src/core/ooxmlspreadsheet/styles_parser';
import { ThemeParser } from '../../static/src/core/ooxmlspreadsheet/theme_parser';
import {
    ConcreteStyleResolver,
    fillBackgroundColor,
} from '../../static/src/core/ooxmlspreadsheet/concrete_style';

const FIXTURES = join(__dirname, '..', 'fixtures');
const NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';

// cellXf[0]：日期 numFmt176 + 紅字粗體(font1) + accent4@tint0.8 黃底(fill1) + thin框(border1)
const STYLES = StylesParser.parse(
    `<?xml version="1.0"?><styleSheet xmlns="${NS}">` +
        `<numFmts count="1"><numFmt numFmtId="176" formatCode="[$-404]gge&quot;年&quot;m&quot;月&quot;d&quot;日&quot;;@"/></numFmts>` +
        `<fonts count="2">` +
        `<font><sz val="12"/><name val="新細明體"/></font>` +
        `<font><b/><sz val="14"/><color rgb="FFFF0000"/><name val="標楷體"/></font>` +
        `</fonts>` +
        `<fills count="2">` +
        `<fill><patternFill patternType="none"/></fill>` +
        `<fill><patternFill patternType="solid"><fgColor theme="7" tint="0.79998168889431442"/><bgColor indexed="64"/></patternFill></fill>` +
        `</fills>` +
        `<borders count="2">` +
        `<border><left/><right/><top/><bottom/></border>` +
        `<border><left style="thin"><color auto="1"/></left><top style="thin"><color rgb="FF000000"/></top><right/><bottom/></border>` +
        `</borders>` +
        `<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>` +
        `<cellXfs count="1">` +
        `<xf numFmtId="176" fontId="1" fillId="1" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1"/>` +
        `</cellXfs></styleSheet>`,
);
const THEME = ThemeParser.default();
const R = new ConcreteStyleResolver(STYLES, THEME);

describe('ConcreteStyleResolver — 全具體化', () => {
    const s = R.resolve(0);

    it('日期 numFmt', () => {
        expect(s.numFmtId).toBe(176);
        expect(s.isDate).toBe(true);
    });
    it('font：粗體 + ARGB 去 alpha 紅字', () => {
        expect(s.font.bold).toBe(true);
        expect(s.font.color).toBe('FF0000');
        expect(s.font.name).toBe('標楷體');
    });
    it('fill：theme accent4 + tint0.8 = FFF2CC（具體 RGB）', () => {
        expect(s.fill.patternType).toBe('solid');
        expect(s.fill.fgColor).toBe('FFF2CC');
    });
    it('border：thin 框、auto 色 → undefined、rgb 色 → 具體', () => {
        expect(s.border.left?.style).toBe('thin');
        expect(s.border.left?.color).toBeUndefined(); // auto → 系統色
        expect(s.border.top?.color).toBe('000000'); // FF000000 去 alpha
    });
    it('fillBackgroundColor：solid → fgColor 為可見底色', () => {
        expect(fillBackgroundColor(s.fill)).toBe('FFF2CC');
    });
    it('快取：同 index 回同一物件', () => {
        expect(R.resolve(0)).toBe(R.resolve(0));
    });
});

describe('ConcreteStyleResolver — 真實契約詳細表端到端', () => {
    const f = join(
        FIXTURES,
        '08_chienyii_business',
        '延壽橋至三合橋-契約詳細表-勇-五變議價後-計算11412-3.xlsx',
    );
    const pkg = PackageReader.fromBuffer(readFileSync(f));
    const wbp = new WorkbookParser(pkg);
    const styles = StylesParser.parse(pkg.getPartText(wbp.stylesPart()!));
    const themePart = wbp.themePart();
    const theme = themePart ? ThemeParser.parse(pkg.getPartText(themePart)) : ThemeParser.default();
    const resolver = new ConcreteStyleResolver(styles, theme);

    it('每個 cellXf 解出的色彩皆為合法 6-hex 或 undefined', () => {
        const HEX6 = /^[0-9A-F]{6}$/;
        for (let i = 0; i < styles.cellXfs.length; i++) {
            const s = resolver.resolve(i);
            for (const c of [s.font.color, s.fill.fgColor, s.fill.bgColor, s.border.top?.color]) {
                if (c !== undefined) expect(c).toMatch(HEX6);
            }
        }
    });
});
