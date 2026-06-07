// theme_parser.test.ts — 解析 theme1.xml clrScheme/fontScheme（規劃書 §1.9）
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { PackageReader } from '../../static/src/core/ooxmlspreadsheet/package_reader';
import { WorkbookParser } from '../../static/src/core/ooxmlspreadsheet/workbook_parser';
import { ThemeParser } from '../../static/src/core/ooxmlspreadsheet/theme_parser';

const FIXTURES = join(__dirname, '..', 'fixtures');
const NS_A = 'http://schemas.openxmlformats.org/drawingml/2006/main';

const THEME_XML =
    `<?xml version="1.0"?><a:theme xmlns:a="${NS_A}" name="Office"><a:themeElements>` +
    `<a:clrScheme name="Office">` +
    `<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>` +
    `<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>` +
    `<a:dk2><a:srgbClr val="44546A"/></a:dk2>` +
    `<a:lt2><a:srgbClr val="E7E6E6"/></a:lt2>` +
    `<a:accent1><a:srgbClr val="4472C4"/></a:accent1>` +
    `<a:accent2><a:srgbClr val="ED7D31"/></a:accent2>` +
    `<a:accent3><a:srgbClr val="A5A5A5"/></a:accent3>` +
    `<a:accent4><a:srgbClr val="FFC000"/></a:accent4>` +
    `<a:accent5><a:srgbClr val="5B9BD5"/></a:accent5>` +
    `<a:accent6><a:srgbClr val="70AD47"/></a:accent6>` +
    `<a:hlink><a:srgbClr val="0563C1"/></a:hlink>` +
    `<a:folHlink><a:srgbClr val="954F72"/></a:folHlink>` +
    `</a:clrScheme>` +
    `<a:fontScheme name="Office">` +
    `<a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface="新細明體"/></a:majorFont>` +
    `<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface="新細明體"/></a:minorFont>` +
    `</a:fontScheme>` +
    `</a:themeElements></a:theme>`;

describe('ThemeParser — 合成 theme', () => {
    const t = ThemeParser.parse(THEME_XML);
    it('sysClr 取 lastClr', () => {
        expect(t.colorScheme.dk1).toBe('000000');
        expect(t.colorScheme.lt1).toBe('FFFFFF');
    });
    it('srgbClr 取 val', () => {
        expect(t.colorScheme.dk2).toBe('44546A');
        expect(t.colorScheme.accent1).toBe('4472C4');
        expect(t.colorScheme.accent4).toBe('FFC000');
        expect(t.colorScheme.folHlink).toBe('954F72');
    });
    it('fontScheme major/minor', () => {
        expect(t.majorFont.latin).toBe('Calibri Light');
        expect(t.majorFont.ea).toBe('新細明體');
        expect(t.minorFont.latin).toBe('Calibri');
    });
});

describe('ThemeParser — default fallback', () => {
    it('Office 預設 scheme', () => {
        const t = ThemeParser.default();
        expect(t.colorScheme.accent1).toBe('4472C4');
        expect(t.colorScheme.lt1).toBe('FFFFFF');
    });
});

describe('ThemeParser — 真實 fixture', () => {
    const f = join(FIXTURES, '04_conditional_format', '磺港溪C-A土單20250221-1.xlsx');
    const pkg = PackageReader.fromBuffer(readFileSync(f));
    const themePart = new WorkbookParser(pkg).themePart();
    const t = ThemeParser.parse(pkg.getPartText(themePart!));

    it('解析標準 Office 主題色', () => {
        expect(t.colorScheme.dk1).toBe('000000');
        expect(t.colorScheme.lt1).toBe('FFFFFF');
        expect(t.colorScheme.accent1).toBe('4472C4');
        expect(t.colorScheme.accent4).toBe('FFC000');
    });
});
