/** @odoo-module **/

/**
 * html_table_colwidth — 範本 HTML 進 canvas-editor 之前，把表格欄寬與底色改成它認得的寫法。
 *
 * 問題（2026-11-06 jt 實查）：範本的表格欄寬寫成 `<td style="width:25%">`、表頭底色寫在
 * `<tr style="background:#f0f0f0">`。瀏覽器照畫，所以範本預覽是完整的；但 canvas-editor 的
 * executeSetHTML（canvas-editor.umd.min.js 的 `"TABLE"===l.nodeName` 分支）：
 *   - 欄寬只讀 `<colgroup><col width="…">`，沒有就一律 ceil(版心寬 / 欄數) 平均分配；
 *   - 底色只讀 `<td>/<th>` 自己的 style.backgroundColor，`<tr>` 上的底色直接丟掉。
 * 結果：用範本建出來的文件欄寬全部平均（jt 估驗文件 4 欄各 139、6 欄各 93）、表頭沒底色，
 * 而且轉完的結果會被 AutoSave 存進 content_json，之後都讀它。
 *
 * 做法：在呼叫 executeSetHTML 之前，對每個**最外層**表格
 *   ① 從各列「colspan=1」的儲存格讀 width（% 或 px），換算成像素、補一個 `<colgroup>`；
 *   ② 把 `<tr>` 的底色抄到沒有自己底色的儲存格上。
 * 已經有 `<col width>` 的表格不動（canvas-editor 本來就讀得到）。
 * 巢狀表格不補欄寬（內外層都不補）：canvas-editor 數欄時會把內層的格子算進外層，
 * 對儲存格內容也用整頁版心寬換算，這裡給像素只會更寬。
 *
 * 只用 getAttribute / setAttribute / childNodes / createElement / insertBefore，
 * 不用 element.style 與 querySelectorAll —— 這樣 vitest 可以用 @xmldom/xmldom 測整段流程
 * （tests/unit/html_table_colwidth.test.ts），瀏覽器裡照常用原生 DOMParser。
 */

/** 沒寫寬度的欄位，至少保留這麼寬（px）；全部欄位都被其他欄位擠掉時才會用到 */
export const MIN_COL_WIDTH_PX = 24;

/** colspan 上限：瀏覽器的 td.colSpan 會夾在 1000（canvas-editor 讀的就是它），這裡跟它一致。
 *  直接讀屬性不設上限的話，colspan="2000000" 會產生兩百萬個 <col>、分頁卡死（抗辯 red-team #3）。 */
export const MAX_COLSPAN = 1000;

/**
 * 解析 CSS 寬度字串。
 * @param {string|null|undefined} value 例如 "25%"、"120px"、"120"
 * @returns {{pct:number}|{px:number}|null}
 */
export function parseWidthSpec(value) {
    if (value === null || value === undefined) return null;
    const m = String(value).trim().match(/^([0-9]*\.?[0-9]+)\s*(%|px)?$/i);
    if (!m) return null;
    const n = parseFloat(m[1]);
    // 309 位以上的數字 parseFloat 會得到 Infinity → 之後 Infinity/Infinity 算出 NaN（抗辯 skeptic r2 #3）
    if (!(n > 0) || !Number.isFinite(n)) return null;
    return m[2] === "%" ? { pct: n } : { px: n };
}

/** 從 style 屬性字串取出某個 CSS 屬性值（最後一個生效，跟瀏覽器一樣） */
export function styleValue(style, prop) {
    if (!style) return null;
    let found = null;
    for (const decl of String(style).split(";")) {
        const idx = decl.indexOf(":");
        if (idx < 0) continue;
        if (decl.slice(0, idx).trim().toLowerCase() === prop) {
            found = decl.slice(idx + 1).trim();
        }
    }
    return found || null;
}

/**
 * 依每欄的寬度規格算出整數像素寬，總和恰好等於 targetWidth。
 *
 * - `{pct}` → targetWidth × pct / 100；`{px}` → 原值；`null` → 平分剩下的寬度。
 * - 有指定的欄位加總超過 targetWidth、或全部都有指定但加總不等於 targetWidth 時，
 *   全部等比例縮放到 targetWidth（瀏覽器對 width:100% 的表格也是這樣分）。
 *
 * @param {Array<{pct:number}|{px:number}|null>} specs 每欄一個
 * @param {number} targetWidth 表格要佔的寬度（px）
 * @returns {number[]} 每欄寬度（整數 px）；specs 為空或 targetWidth 不合理時回 []
 */
export function computeColWidths(specs, targetWidth) {
    const target = Math.floor(targetWidth);
    // 欄數比像素還多：每欄連 1px 都分不到，交回 canvas-editor 自己平分
    if (!Array.isArray(specs) || specs.length === 0 || !(target >= specs.length)) return [];

    const widths = specs.map((s) => {
        if (s && s.pct > 0) return (target * s.pct) / 100;
        if (s && s.px > 0) return s.px;
        return null;
    });
    const fixed = widths.reduce((sum, w) => sum + (w || 0), 0);
    const freeCount = widths.filter((w) => w === null).length;
    if (freeCount > 0) {
        const share = Math.max((target - fixed) / freeCount, MIN_COL_WIDTH_PX);
        for (let i = 0; i < widths.length; i++) {
            if (widths[i] === null) widths[i] = share;
        }
    }
    const total = widths.reduce((sum, w) => sum + w, 0);
    const scaled = widths.map((w) => (w * target) / total);
    // 極大的寬度（例如 1e306px）在 w*target 溢位成 Infinity → NaN／無窮迴圈（抗辯 skeptic r3）。
    // 算不出有限值就交回 canvas-editor 自己平分。
    if (!Number.isFinite(total) || !scaled.every((w) => Number.isFinite(w))) return [];

    // 取整：先全部無條件捨去（每欄至少 1px），差額補給／扣自最寬的欄（視覺上最不明顯）
    const out = scaled.map((w) => Math.max(1, Math.floor(w)));
    const widestIndex = () => out.reduce((best, w, i) => (w > out[best] ? i : best), 0);
    let diff = target - out.reduce((sum, w) => sum + w, 0);
    if (diff > 0) out[widestIndex()] += diff;
    // 只有很多欄被墊成 1px 時才會發生；一次扣 1，不讓任何一欄 < 1。
    // 上面已保證都是有限值，|diff| 最多是欄數，所以這個迴圈有界
    while (diff < 0) {
        const i = widestIndex();
        if (out[i] <= 1) break;
        out[i] -= 1;
        diff += 1;
    }
    return out;
}

// ─── DOM 輔助（只用 xmldom 也有的 API） ─────────────────────────────

function tagOf(node) {
    return node && node.nodeType === 1 ? String(node.localName || node.nodeName).toLowerCase() : "";
}

function childElements(node, ...tags) {
    const out = [];
    const list = node.childNodes || [];
    for (let i = 0; i < list.length; i++) {
        const child = list[i];
        if (child.nodeType === 1 && (tags.length === 0 || tags.includes(tagOf(child)))) {
            out.push(child);
        }
    }
    return out;
}

/** 表格自己的列（含 thead/tbody/tfoot 底下的），不含巢狀表格的列 */
function tableRows(table) {
    const rows = [];
    for (const child of childElements(table)) {
        const tag = tagOf(child);
        if (tag === "tr") rows.push(child);
        else if (tag === "thead" || tag === "tbody" || tag === "tfoot") {
            rows.push(...childElements(child, "tr"));
        }
    }
    return rows;
}

function hasTableAncestor(node) {
    for (let p = node.parentNode; p; p = p.parentNode) {
        if (tagOf(p) === "table") return true;
    }
    return false;
}

function intAttr(el, name) {
    const n = parseInt(el.getAttribute(name) || "1", 10);
    return n > 0 ? Math.min(n, MAX_COLSPAN) : 1;
}

function cellWidthSpec(cell) {
    return parseWidthSpec(styleValue(cell.getAttribute("style"), "width"))
        || parseWidthSpec(cell.getAttribute("width"));
}

function hasColWidths(table) {
    const cols = [];
    for (const child of childElements(table)) {
        if (tagOf(child) === "col") cols.push(child);
        if (tagOf(child) === "colgroup") cols.push(...childElements(child, "col"));
    }
    return cols.some((c) => parseFloat(c.getAttribute("width")) > 0);
}

/** 是 CSS 關鍵字、不是顏色：抄到儲存格上會變成 canvas 的無效 fillStyle（抗辯 skeptic #5） */
const CSS_KEYWORDS = new Set(["inherit", "initial", "unset", "revert", "revert-layer", "currentcolor", "none"]);

/** 只接受單一顏色值（#hex／rgb()／hsl()／色名），`background:url(...) no-repeat` 這類不抄 */
function colorOnly(value) {
    if (!value) return null;
    const v = value.trim();
    if (CSS_KEYWORDS.has(v.toLowerCase())) return null;
    if (/^(#[0-9a-f]{3,8}|(rgb|rgba|hsl|hsla)\([^)]*\)|[a-z]+)$/i.test(v)) return v;
    return null;
}

/**
 * 每欄的寬度規格：canvas-editor 以第一列的 colspan 總和當欄數，這裡跟它一致；
 * 各欄寬度取「第一個在這一欄上 colspan=1 且有寫寬度」的儲存格。
 * 表格裡有 rowspan 時欄位位置不好推，只看第一列，其餘留給平分。
 */
function columnSpecs(rows) {
    const first = childElements(rows[0], "td", "th");
    const colCount = first.reduce((sum, c) => sum + intAttr(c, "colspan"), 0);
    if (colCount === 0) return [];
    const specs = new Array(colCount).fill(null);
    const anyRowspan = rows.some((r) => childElements(r, "td", "th").some((c) => intAttr(c, "rowspan") > 1));
    for (const row of anyRowspan ? [rows[0]] : rows) {
        const cells = childElements(row, "td", "th");
        if (cells.reduce((sum, c) => sum + intAttr(c, "colspan"), 0) !== colCount) continue;
        let col = 0;
        for (const cell of cells) {
            const span = intAttr(cell, "colspan");
            if (span === 1 && specs[col] === null) specs[col] = cellWidthSpec(cell);
            col += span;
        }
    }
    return specs;
}

/**
 * 直接修改 doc：補 `<colgroup>`、把列底色抄到儲存格。
 * @param {Document} doc DOMParser 解析出來的文件
 * @param {number} innerWidth canvas-editor 的版心寬（px）
 * @returns {number} 改動處數（補 colgroup 的表格＋補底色的儲存格）；0＝什麼都沒改
 */
export function applyCanvasTableHints(doc, innerWidth) {
    if (!doc || !(innerWidth > 0)) return 0;
    let changed = 0;
    const tables = Array.from(doc.getElementsByTagName("table"));
    for (const table of tables) {
        if (hasTableAncestor(table)) continue;
        const rows = tableRows(table);
        if (rows.length === 0) continue;

        // ② 列底色 → 儲存格
        for (const row of rows) {
            const rowStyle = row.getAttribute("style");
            const bg = colorOnly(styleValue(rowStyle, "background-color"))
                || colorOnly(styleValue(rowStyle, "background"));
            if (!bg) continue;
            for (const cell of childElements(row, "td", "th")) {
                const own = cell.getAttribute("style") || "";
                if (styleValue(own, "background-color") || styleValue(own, "background")) continue;
                const sep = own.trim() && !own.trim().endsWith(";") ? ";" : "";
                cell.setAttribute("style", `${own}${sep}background-color:${bg}`);
                changed += 1;
            }
        }

        // ① 欄寬 → colgroup
        if (hasColWidths(table)) continue;
        // 裡面還有表格：canvas-editor 用 querySelectorAll("th,td") 數欄，會把內層的格子也算成
        // 外層的欄，欄數跟這裡算的對不上；補了只會更寬（抗辯 skeptic #1）。維持它原本的平分。
        if (table.getElementsByTagName("table").length > 0) continue;
        const specs = columnSpecs(rows);
        if (!specs.some((s) => s !== null)) continue;   // 都沒寫寬度：維持 canvas-editor 的平分
        const tableSpec = parseWidthSpec(styleValue(table.getAttribute("style"), "width"))
            || parseWidthSpec(table.getAttribute("width"));
        let target = innerWidth;
        if (tableSpec && tableSpec.pct) target = (innerWidth * Math.min(tableSpec.pct, 100)) / 100;
        else if (tableSpec && tableSpec.px) target = Math.min(tableSpec.px, innerWidth);
        const widths = computeColWidths(specs, target);
        if (widths.length === 0) continue;

        for (const old of childElements(table, "colgroup", "col")) table.removeChild(old);
        const colgroup = doc.createElement("colgroup");
        for (const w of widths) {
            const col = doc.createElement("col");
            col.setAttribute("width", String(w));
            colgroup.appendChild(col);
        }
        table.insertBefore(colgroup, table.firstChild);
        changed += 1;
    }
    return changed;
}

/**
 * 瀏覽器用：HTML 字串 → 補好提示的 HTML 字串。任何一步出錯就原樣回傳（不擋開檔）。
 * @param {string} html
 * @param {number} innerWidth
 * @returns {string}
 */
export function prepareHtmlForCanvas(html, innerWidth) {
    if (!html || typeof DOMParser === "undefined") return html;
    try {
        // 明寫 <body>：開頭的 <style>／<meta>／<title> 才會留在 body 裡；不寫的話 HTML 解析器
        // 會把它們搬進 <head>，而下面只回傳 body.innerHTML → 樣式被丟掉（抗辯 red-team #4）
        const doc = new DOMParser().parseFromString(`<!DOCTYPE html><body>${html}`, "text/html");
        if (!doc || !doc.body) return html;
        // 沒改到任何東西就回原字串，避免序列化造成無關的差異
        return applyCanvasTableHints(doc, innerWidth) > 0 ? doc.body.innerHTML : html;
    } catch (e) {
        console.warn("[DocEditor] 表格欄寬前處理失敗，改用原始 HTML：", e);
        return html;
    }
}
