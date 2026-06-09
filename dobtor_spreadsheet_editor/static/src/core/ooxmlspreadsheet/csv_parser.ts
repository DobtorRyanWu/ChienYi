// csv_parser.ts — CSV → o-spreadsheet WorkbookData / HTML 預覽
//
// RFC 4180：欄以逗號分隔、雙引號包覆可含逗號/換行、"" 跳脫引號。去 UTF-8 BOM。
// 編碼（UTF-8 / Big5）由上層 OWL 元件解碼後傳純文字進來。

import { columnIndexToLetter } from './cell_ref';
import type { OSpreadsheetData } from './to_ospreadsheet';

/** 解析 CSV 文字 → 列陣列。*/
export function parseCsv(text: string): string[][] {
    if (text.charCodeAt(0) === 0xfeff) text = text.slice(1); // 去 BOM
    const rows: string[][] = [];
    let row: string[] = [];
    let field = '';
    let inQuotes = false;
    let i = 0;
    let cellStarted = false;
    while (i < text.length) {
        const ch = text[i];
        if (inQuotes) {
            if (ch === '"') {
                if (text[i + 1] === '"') {
                    field += '"';
                    i += 2;
                    continue;
                }
                inQuotes = false;
                i++;
                continue;
            }
            field += ch;
            i++;
            continue;
        }
        if (ch === '"') {
            inQuotes = true;
            cellStarted = true;
            i++;
            continue;
        }
        if (ch === ',') {
            row.push(field);
            field = '';
            cellStarted = true;
            i++;
            continue;
        }
        if (ch === '\r') {
            i++;
            continue; // 吃掉 CR；由 \n 斷行
        }
        if (ch === '\n') {
            row.push(field);
            rows.push(row);
            row = [];
            field = '';
            cellStarted = false;
            i++;
            continue;
        }
        field += ch;
        cellStarted = true;
        i++;
    }
    // 收尾最後一欄/列（避免漏掉無結尾換行的最後一行）
    if (cellStarted || field !== '' || row.length > 0) {
        row.push(field);
        rows.push(row);
    }
    return rows;
}

const MAX_CSV_ROWS = 50000;
const MAX_CSV_COLS = 256;

/** CSV → o-spreadsheet WorkbookData（單一工作表、純值無樣式）。*/
export function csvToOSpreadsheetData(text: string): OSpreadsheetData {
    const rows = parseCsv(text);
    const cells: Record<string, { content: string }> = {};
    let maxCol = 1;
    const nRows = Math.min(rows.length, MAX_CSV_ROWS);
    for (let r = 0; r < nRows; r++) {
        const row = rows[r];
        const nCols = Math.min(row.length, MAX_CSV_COLS);
        for (let c = 0; c < nCols; c++) {
            const val = row[c];
            if (val !== '') cells[`${columnIndexToLetter(c + 1)}${r + 1}`] = { content: val };
            if (c + 1 > maxCol) maxCol = c + 1;
        }
    }
    return {
        version: 1,
        sheets: [
            {
                id: 'sheet1',
                name: 'CSV',
                colNumber: Math.max(maxCol, 1),
                rowNumber: Math.max(nRows, 1),
                cells,
                merges: [],
                cols: {},
                rows: {},
                conditionalFormats: [],
                dataValidationRules: [],
                tables: [],
                figures: [],
            },
        ],
        styles: {},
        formats: {},
        borders: {},
    };
}

function esc(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** CSV → HTML 預覽（與 XlsxPreview 同形）。*/
export function csvToHtmlPreview(text: string): { sheets: string[]; activeSheet: number; html: string } {
    const rows = parseCsv(text);
    const nRows = Math.min(rows.length, 500); // 預覽僅前 500 列
    const body = rows
        .slice(0, nRows)
        .map(
            (row) =>
                `<tr>${row
                    .slice(0, MAX_CSV_COLS)
                    .map((v) => `<td style="border:1px solid #ddd;padding:2px 6px;white-space:nowrap">${esc(v)}</td>`)
                    .join('')}</tr>`,
        )
        .join('');
    const html =
        `<table style="border-collapse:collapse;font:13px sans-serif">${body}</table>` +
        (rows.length > nRows ? `<div style="color:#888;padding:4px">（預覽前 ${nRows} 列，共 ${rows.length} 列）</div>` : '');
    return { sheets: ['CSV'], activeSheet: 0, html };
}
