/** @odoo-module **/
// 兩份試算表內容（o-spreadsheet Model.exportData() 的結果）逐工作表、逐儲存格比對。
// 純函式，不碰 DOM 與網路。

const CELL_REFERENCE_PATTERN = /^([A-Z]+)([0-9]+)$/;
const LETTERS_IN_ALPHABET = 26;
const CHAR_CODE_BEFORE_A = 64;

export const CHANGE_ADDED = "added";
export const CHANGE_REMOVED = "removed";
export const CHANGE_MODIFIED = "modified";

/**
 * 取出一格的內容（公式或輸入值）。
 * 匯出格式有兩種：物件 {content: "…"}（Odoo 18.0）或直接是字串（較新的 o-spreadsheet），兩種都吃。
 * @param {Object|String|undefined} cell
 * @returns {String}
 */
export function cellContent(cell) {
    if (cell === undefined || cell === null) {
        return "";
    }
    if (typeof cell === "string") {
        return cell;
    }
    return cell.content === undefined || cell.content === null ? "" : String(cell.content);
}

/**
 * 把 "AB12" 轉成 [列, 欄] 數字，排序用；認不得的參照排最後。
 * @param {String} reference
 * @returns {Number[]}
 */
function cellSortKey(reference) {
    const match = CELL_REFERENCE_PATTERN.exec(reference);
    if (!match) {
        return [Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER];
    }
    let column = 0;
    for (const letter of match[1]) {
        column = column * LETTERS_IN_ALPHABET + (letter.charCodeAt(0) - CHAR_CODE_BEFORE_A);
    }
    return [parseInt(match[2], 10), column];
}

function compareCellReferences(left, right) {
    const [leftRow, leftColumn] = cellSortKey(left);
    const [rightRow, rightColumn] = cellSortKey(right);
    return leftRow - rightRow || leftColumn - rightColumn;
}

/**
 * 比一張工作表的儲存格。
 * @param {Object} beforeCells
 * @param {Object} afterCells
 * @returns {Object[]} [{cell, before, after, change}]
 */
function diffCells(beforeCells, afterCells) {
    const references = new Set([...Object.keys(beforeCells), ...Object.keys(afterCells)]);
    const rows = [];
    for (const reference of references) {
        const before = cellContent(beforeCells[reference]);
        const after = cellContent(afterCells[reference]);
        if (before === after) {
            continue;
        }
        let change = CHANGE_MODIFIED;
        if (before === "") {
            change = CHANGE_ADDED;
        } else if (after === "") {
            change = CHANGE_REMOVED;
        }
        rows.push({cell: reference, before, after, change});
    }
    rows.sort((left, right) => compareCellReferences(left.cell, right.cell));
    return rows;
}

/**
 * 比兩份活頁簿。工作表以 id 對應（改名不算新增／刪除）。
 * @param {Object} beforeData 原版本的 exportData()
 * @param {Object} afterData 新版本的 exportData()
 * @returns {{sheets: Object[], total: Number}}
 *   sheets: [{id, name, previousName, change, rows}]，只列有差異的工作表；
 *   change 為 added／removed／modified；total 是差異儲存格總數。
 */
export function diffWorkbooks(beforeData, afterData) {
    const beforeSheets = (beforeData && beforeData.sheets) || [];
    const afterSheets = (afterData && afterData.sheets) || [];
    const beforeById = new Map(beforeSheets.map((sheet) => [sheet.id, sheet]));
    const afterById = new Map(afterSheets.map((sheet) => [sheet.id, sheet]));
    const sheets = [];
    let total = 0;

    for (const after of afterSheets) {
        const before = beforeById.get(after.id);
        const rows = diffCells((before && before.cells) || {}, after.cells || {});
        const renamed = Boolean(before) && before.name !== after.name;
        if (before && !rows.length && !renamed) {
            continue;
        }
        total += rows.length;
        sheets.push({
            id: after.id,
            name: after.name,
            previousName: renamed ? before.name : false,
            change: before ? CHANGE_MODIFIED : CHANGE_ADDED,
            rows,
        });
    }
    for (const before of beforeSheets) {
        if (afterById.has(before.id)) {
            continue;
        }
        const rows = diffCells(before.cells || {}, {});
        total += rows.length;
        sheets.push({
            id: before.id,
            name: before.name,
            previousName: false,
            change: CHANGE_REMOVED,
            rows,
        });
    }
    return {sheets, total};
}
