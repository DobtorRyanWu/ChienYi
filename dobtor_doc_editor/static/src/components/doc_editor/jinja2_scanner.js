/** @odoo-module **/

/**
 * jinja2_scanner — Phase 8 Sprint G
 *
 * 純函式 util：掃描 canvas-editor 的 IElement[] 結構，找出所有 jinja2 風格的
 * `{{ var }}` / `{{ object.partner_id.name }}` 變數，回傳去重後的清單。
 *
 * 設計考量：
 *   - 不依賴 canvas-editor runtime，純 JS、可被 vitest 單測（見 tests/unit/jinja2_scanner.test.ts）
 *   - 遞迴走進 table.trList[].tdList[].value、list/title/block.valueList
 *   - 跳過 control 元素內部的 placeholder/value（已是註冊欄位、不應重複建）
 *   - 允許 `object.partner_id.name` 等帶點路徑的變數名（與 Sprint E 對齊）
 *   - 不消耗變數內的空白，允許 `{{name}}` / `{{ name }}` / `{{  name  }}`
 *
 * 為什麼選 regex 而非 AST：
 *   docxtpl/jinja2 變數實務上都是單行 `{{ ident }}` 形式，文件中不會跨多行（除非
 *   user 手動換行——這種已是 broken template）。Regex 對 5 個變數的場景過殺，
 *   但維護性最好、邊界條件最少。
 */

/**
 * jinja2 變數正則：
 *   - `{{`  起頭，允許前後任意空白
 *   - 識別字：英文字母或底線開頭，後跟 `\w` 或 `.`（支援 `object.partner_id.name`）
 *   - `}}`  結尾
 *
 * 注意：故意不允許變數內含其他符號（如 `|filter`、`(arg)`），那種已偏離單純
 * 「Odoo 欄位路徑」語意，Sprint E 的 odoo_field_name 也不收這種格式。
 */
const JINJA2_VAR_RE = /\{\{\s*([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)\s*\}\}/g;

/**
 * 把 IElement[] 的所有 text 連接成單一字串。
 *
 * 進入 canvas-editor 的 element 通常為單字元的 TEXT 元素（type === 'text' 或
 * type undefined），但也可能是 TABLE/LIST/TITLE/BLOCK 等複合元素，內含
 * `trList[].tdList[].value`、`valueList` 等子陣列。
 *
 * 我們**只**收 text 字元（含複合元素內遞迴的 text）。CONTROL 元素直接跳過——
 * 那已是註冊過的欄位，placeholder 雖然顯示為 `{{ ... }}` 但不應再重複建。
 *
 * @param {Array} elements - IElement[]
 * @returns {string}
 */
export function flattenElementsToText(elements) {
    if (!Array.isArray(elements)) return "";
    const buf = [];
    for (const el of elements) {
        if (!el || typeof el !== "object") continue;
        const type = el.type;

        // Sprint E 已註冊欄位用 CONTROL 元素表示 → 跳過內部 placeholder 文字
        if (type === "control") continue;

        // TABLE：遞迴所有 td.value
        if (type === "table" && Array.isArray(el.trList)) {
            for (const tr of el.trList) {
                if (!tr || !Array.isArray(tr.tdList)) continue;
                for (const td of tr.tdList) {
                    if (td && Array.isArray(td.value)) {
                        buf.push(flattenElementsToText(td.value));
                    }
                }
            }
            continue;
        }

        // LIST / TITLE / BLOCK / HYPERLINK / SUPERSCRIPT / SUBSCRIPT：遞迴 valueList
        if (Array.isArray(el.valueList)) {
            buf.push(flattenElementsToText(el.valueList));
            continue;
        }

        // 純 text 元素（type === 'text' 或 undefined）
        if (typeof el.value === "string") {
            buf.push(el.value);
        }
    }
    return buf.join("");
}

/**
 * 掃描 canvas-editor 的 IEditorData 主流文字，回傳所有 `{{ var }}` 變數。
 *
 * @param {object} editorData - `editor.command.getValue().data`，含 main/header/footer
 * @returns {Array<{varName: string, occurrences: number}>}
 *   去重後的變數清單，按出現次數降冪、同次數按字母升冪排序（穩定輸出便於測試 / UI）。
 */
export function scanJinja2Variables(editorData) {
    if (!editorData || typeof editorData !== "object") return [];

    // canvas-editor 的 data 物件結構：{ main: IElement[], header?: IElement[], footer?: IElement[] }
    // 三個區塊都要掃，這樣頁首/頁尾的變數也能被批次建檔。
    const buckets = [];
    if (Array.isArray(editorData.main)) buckets.push(editorData.main);
    if (Array.isArray(editorData.header)) buckets.push(editorData.header);
    if (Array.isArray(editorData.footer)) buckets.push(editorData.footer);

    const counts = new Map();
    for (const bucket of buckets) {
        const text = flattenElementsToText(bucket);
        // 注意：JS regex 帶 /g 時要 reset lastIndex 才能在新字串上重用
        JINJA2_VAR_RE.lastIndex = 0;
        let m;
        while ((m = JINJA2_VAR_RE.exec(text)) !== null) {
            // m[1] = 去掉 `{{ }}` 與空白後的純變數名（如 `partner_id.name`）
            const varName = m[1];
            // Sprint E 的 odoo_field_name 不收 `object.` 前綴，這裡也對齊
            const cleaned = varName.replace(/^object\./, "");
            if (!cleaned) continue;
            counts.set(cleaned, (counts.get(cleaned) || 0) + 1);
        }
    }

    // 排序：出現次數降冪 → 字母升冪
    const items = Array.from(counts.entries()).map(([varName, occurrences]) => ({
        varName,
        occurrences,
    }));
    items.sort((a, b) => {
        if (b.occurrences !== a.occurrences) return b.occurrences - a.occurrences;
        return a.varName.localeCompare(b.varName);
    });
    return items;
}
