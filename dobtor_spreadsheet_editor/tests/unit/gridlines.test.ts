import { describe, it, expect } from 'vitest';
import { WorksheetParser } from '../../static/src/core/ooxmlspreadsheet/worksheet_parser';
import { StylesParser } from '../../static/src/core/ooxmlspreadsheet/styles_parser';
import { ThemeParser } from '../../static/src/core/ooxmlspreadsheet/theme_parser';
import { buildOSpreadsheetData } from '../../static/src/core/ooxmlspreadsheet/to_ospreadsheet';
const NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
const THEME = ThemeParser.default();
const STYLES = StylesParser.parse('<styleSheet/>');
function grid(showAttr: string): boolean {
    const ws = WorksheetParser.parse(
        `<?xml version="1.0"?><worksheet xmlns="${NS}"><sheetViews><sheetView ${showAttr} workbookViewId="0"/></sheetViews>` +
            `<sheetData/></worksheet>`,
    );
    return buildOSpreadsheetData([{ name: 'S', ws }], [], STYLES, THEME).sheets[0].areGridLinesVisible;
}
describe('areGridLinesVisible（§1.6 sheetViews）', () => {
    it('showGridLines="0" → false', () => { expect(grid('showGridLines="0"')).toBe(false); });
    it('預設（無屬性）→ true', () => { expect(grid('')).toBe(true); });
});
