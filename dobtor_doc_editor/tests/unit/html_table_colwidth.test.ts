/**
 * html_table_colwidth.test.ts — 2026-11-06
 *
 * 範本 HTML 進 canvas-editor 前的表格前處理（static/src/components/doc_editor/html_table_colwidth.js）。
 * 背景：canvas-editor 的 executeSetHTML 不認 `<td style="width:%">`、不認 `<tr>` 底色，
 * jt 上用「估驗計價單樣板」建的文件欄寬全部平均（4 欄各 139、6 欄各 93）。
 *
 * DOM 測試用 setup.ts 注入的 @xmldom/xmldom（XML 解析），所以 fixture 必須是合法 XHTML。
 */

import { describe, expect, it } from "vitest";
import {
    applyCanvasTableHints,
    computeColWidths,
    MAX_COLSPAN,
    MIN_COL_WIDTH_PX,
    parseWidthSpec,
    styleValue,
} from "../../static/src/components/doc_editor/html_table_colwidth.js";

// canvas-editor 預設 A4 直向：794 − 左右邊界 120×2
const A4_INNER = 554;

const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

function parse(xhtml: string): Document {
    return new DOMParser().parseFromString(`<div>${xhtml}</div>`, "text/xml") as unknown as Document;
}

function colWidths(table: Element): number[] {
    const cols = Array.from(table.getElementsByTagName("col")) as Element[];
    return cols.map((c) => Number(c.getAttribute("width")));
}

// 與 data/doc_template_data.xml 的 template_payment_estimate 同結構（改成合法 XHTML）
const ESTIMATE_TEMPLATE = `
<table style="width:100%;border-collapse:collapse">
  <tr>
    <td style="border:1px solid #000;padding:6px;width:25%"><b>工程名稱</b></td>
    <td style="border:1px solid #000;padding:6px;width:25%">{{ project_name }}</td>
    <td style="border:1px solid #000;padding:6px;width:25%"><b>估驗日期</b></td>
    <td style="border:1px solid #000;padding:6px;width:25%">{{ estimate_date }}</td>
  </tr>
  <tr>
    <td style="border:1px solid #000;padding:6px"><b>承包商</b></td>
    <td style="border:1px solid #000;padding:6px">{{ contractor }}</td>
    <td style="border:1px solid #000;padding:6px"><b>估驗期</b></td>
    <td style="border:1px solid #000;padding:6px">第 {{ estimate_no }} 期</td>
  </tr>
</table>
<h3>本期完成工項</h3>
<table style="width:100%;border-collapse:collapse">
  <thead>
    <tr style="background:#f0f0f0">
      <th style="border:1px solid #000;padding:6px;width:6%">項次</th>
      <th style="border:1px solid #000;padding:6px">工項名稱</th>
      <th style="border:1px solid #000;padding:6px;width:10%">單位</th>
      <th style="border:1px solid #000;padding:6px;width:14%">本期數量</th>
      <th style="border:1px solid #000;padding:6px;width:14%">單價</th>
      <th style="border:1px solid #000;padding:6px;width:14%">小計</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>a</td><td>b</td><td>c</td><td>d</td><td>e</td><td>f</td></tr>
  </tbody>
</table>`;

describe("parseWidthSpec / styleValue", () => {
    it("認得 %、px、純數字，其他回 null", () => {
        expect(parseWidthSpec("25%")).toEqual({ pct: 25 });
        expect(parseWidthSpec(" 120px ")).toEqual({ px: 120 });
        expect(parseWidthSpec("80")).toEqual({ px: 80 });
        expect(parseWidthSpec("auto")).toBeNull();
        expect(parseWidthSpec("0%")).toBeNull();
        expect(parseWidthSpec(null)).toBeNull();
        // 超過 309 位的數字：parseFloat 得 Infinity，不可以當成寬度（否則算出 NaN）
        expect(parseWidthSpec("1" + "0".repeat(400) + "px")).toBeNull();
    });

    it("styleValue 取最後一個宣告、不分大小寫", () => {
        expect(styleValue("border:1px solid #000;padding:6px;width:25%", "width")).toBe("25%");
        expect(styleValue("WIDTH:10%;width:20%", "width")).toBe("20%");
        expect(styleValue("padding:6px", "width")).toBeNull();
        expect(styleValue(null, "width")).toBeNull();
    });
});

describe("computeColWidths", () => {
    it("4 欄各 25%：總和恰好等於版心寬", () => {
        const w = computeColWidths(Array(4).fill({ pct: 25 }), A4_INNER);
        expect(sum(w)).toBe(A4_INNER);
        expect(Math.max(...w) - Math.min(...w)).toBeLessThanOrEqual(2);
    });

    it("估驗工項表 6%／（空）／10%／14%×3：項次窄、工項名稱拿剩下的", () => {
        const w = computeColWidths(
            [{ pct: 6 }, null, { pct: 10 }, { pct: 14 }, { pct: 14 }, { pct: 14 }], A4_INNER);
        expect(sum(w)).toBe(A4_INNER);
        expect(w[0]).toBeLessThan(40);                          // 6% × 554 ≈ 33
        expect(w[1]).toBe(Math.max(...w));                     // 工項名稱最寬
        expect(w[1]).toBeGreaterThan(200);
        // 修正前 canvas-editor 的結果是 6 欄各 93 —— 不可以再是平均值
        expect(new Set(w).size).toBeGreaterThan(1);
    });

    it("px 混空欄：空欄平分剩下的", () => {
        expect(computeColWidths([{ px: 100 }, null], A4_INNER)).toEqual([100, A4_INNER - 100]);
    });

    it("指定寬度加總超過版心：等比例縮到版心寬", () => {
        expect(computeColWidths([{ px: 400 }, { px: 400 }], A4_INNER)).toEqual([277, 277]);
    });

    it("指定寬度加總不足且沒有空欄：等比例撐滿", () => {
        const w = computeColWidths([{ pct: 50 }, { pct: 25 }], A4_INNER);
        expect(sum(w)).toBe(A4_INNER);
        expect(w[0]).toBeGreaterThan(w[1] * 1.9);
    });

    it("空欄被擠到沒空間時至少保留 MIN_COL_WIDTH_PX（縮放前）", () => {
        const w = computeColWidths([{ pct: 100 }, null], A4_INNER);
        expect(sum(w)).toBe(A4_INNER);
        expect(w[1]).toBeGreaterThan(0);
        expect(w[1]).toBeLessThanOrEqual(MIN_COL_WIDTH_PX);
    });

    it("極大的寬度：乘法溢位成 Infinity 時交回 canvas-editor（不可以無窮迴圈、不可以出現 NaN）", () => {
        // skeptic r3 實測：1e306px → w*target 溢位 → diff=-Infinity → while 永遠不結束
        for (const specs of [[{ px: 1e306 }], [{ px: 1e306 }, null], [{ px: 1e308 }, { pct: 50 }], [{ pct: 1e306 }], [{ pct: 1e306 }, null]]) {
            const w = computeColWidths(specs, A4_INNER);
            expect(w.every((x) => Number.isFinite(x))).toBe(true);
            if (w.length) expect(sum(w)).toBe(A4_INNER);
        }
    });

    it("不合理的輸入回 []", () => {
        expect(computeColWidths([], A4_INNER)).toEqual([]);
        expect(computeColWidths([{ pct: 50 }], 0)).toEqual([]);
    });
});

describe("applyCanvasTableHints", () => {
    it("估驗計價單樣板：兩個表格都補 colgroup、表頭底色抄到每個 th", () => {
        const doc = parse(ESTIMATE_TEMPLATE);
        const changed = applyCanvasTableHints(doc, A4_INNER);
        expect(changed).toBeGreaterThan(0);

        const [t1, t2] = Array.from(doc.getElementsByTagName("table")) as Element[];
        const w1 = colWidths(t1);
        const w2 = colWidths(t2);
        expect(w1).toHaveLength(4);
        expect(sum(w1)).toBe(A4_INNER);
        expect(w2).toHaveLength(6);
        expect(sum(w2)).toBe(A4_INNER);
        expect(w2[0]).toBeLessThan(w2[1]);

        // colgroup 要在表格最前面（canvas-editor 用 querySelectorAll("colgroup col") 讀）
        expect((t2.firstChild as Element).nodeName.toLowerCase()).toBe("colgroup");

        const ths = Array.from(t2.getElementsByTagName("th")) as Element[];
        expect(ths).toHaveLength(6);
        for (const th of ths) {
            expect(styleValue(th.getAttribute("style"), "background-color")).toBe("#f0f0f0");
        }
        // 沒有列底色的 td 不可以被加上底色
        const tds = Array.from(t2.getElementsByTagName("td")) as Element[];
        for (const td of tds) expect(td.getAttribute("style")).toBeNull();
    });

    it("已經有 <col width> 的表格不動", () => {
        const doc = parse(`<table><colgroup><col width="300"/><col width="254"/></colgroup>
            <tr><td style="width:10%">a</td><td>b</td></tr></table>`);
        applyCanvasTableHints(doc, A4_INNER);
        const t = doc.getElementsByTagName("table")[0] as Element;
        expect(colWidths(t)).toEqual([300, 254]);
    });

    it("完全沒寫寬度的表格不補 colgroup（維持 canvas-editor 原本的平分）", () => {
        const doc = parse(`<table><tr><td>a</td><td>b</td></tr></table>`);
        expect(applyCanvasTableHints(doc, A4_INNER)).toBe(0);
        expect(doc.getElementsByTagName("colgroup").length).toBe(0);
    });

    it("含巢狀表格：內外層都不補 colgroup（canvas-editor 會把內層格子算成外層的欄）", () => {
        // skeptic 實跑：補了 2 欄的 colgroup，canvas-editor 卻認定 4 欄 → [166,388,139,139] 總和 832 > 554
        const doc = parse(`<table style="width:100%"><tr><td style="width:30%">A</td><td>
              <table><tr><td style="width:50%">x</td><td>y</td></tr></table>
            </td></tr></table>`);
        applyCanvasTableHints(doc, A4_INNER);
        expect(doc.getElementsByTagName("colgroup").length).toBe(0);
    });

    it("欄數比像素還多：不補（交回 canvas-editor），不會出現 0 或負的欄寬", () => {
        // skeptic 實跑：width:1% 配 8 個 10% 的格子 → 以前會算出 [-2,1,1,1,1,1,1,1]
        const cells = Array(8).fill(`<td style="width:10%">x</td>`).join("");
        const doc = parse(`<table style="width:1%"><tr>${cells}</tr></table>`);
        applyCanvasTableHints(doc, A4_INNER);
        expect(doc.getElementsByTagName("colgroup").length).toBe(0);
        for (const n of [9, 50, 553, 554]) {
            const w = computeColWidths(Array(n).fill({ pct: 1 }), A4_INNER);
            expect(sum(w)).toBe(A4_INNER);
            expect(Math.min(...w)).toBeGreaterThanOrEqual(1);
        }
        expect(computeColWidths(Array(555).fill(null), A4_INNER)).toEqual([]);
    });

    it("colspan 夾在 1000（與瀏覽器 td.colSpan 一致），不會長出幾百萬個 col", () => {
        // red-team 實跑：colspan=2000000 → 卡 5.8 秒、200 萬個 <col>
        const doc = parse(`<table><tr><td style="width:10%">a</td><td colspan="2000000">b</td></tr></table>`);
        applyCanvasTableHints(doc, 2000);
        const cols = doc.getElementsByTagName("col").length;
        expect(cols).toBeLessThanOrEqual(1 + MAX_COLSPAN);
    });

    it("列底色是 inherit 之類的 CSS 關鍵字時不抄", () => {
        const doc = parse(`<table><tr style="background:inherit"><td style="width:50%">a</td><td>b</td></tr></table>`);
        applyCanvasTableHints(doc, A4_INNER);
        expect(styleValue(doc.getElementsByTagName("td")[0].getAttribute("style"), "background-color")).toBeNull();
    });

    it("第一列有 colspan：欄寬從其他 colspan=1 的列取", () => {
        const doc = parse(`<table>
            <tr><td colspan="2">標題</td></tr>
            <tr><td style="width:20%">a</td><td style="width:80%">b</td></tr></table>`);
        applyCanvasTableHints(doc, A4_INNER);
        const w = colWidths(doc.getElementsByTagName("table")[0] as Element);
        expect(w).toHaveLength(2);
        expect(sum(w)).toBe(A4_INNER);
        expect(w[1]).toBeGreaterThan(w[0] * 3.5);
    });

    it("表格本身寫 width:50%：欄寬總和是版心的一半", () => {
        const doc = parse(`<table style="width:50%"><tr><td style="width:50%">a</td><td>b</td></tr></table>`);
        applyCanvasTableHints(doc, A4_INNER);
        expect(sum(colWidths(doc.getElementsByTagName("table")[0] as Element))).toBe(Math.floor(A4_INNER / 2));
    });

    it("列底色是圖片之類的非顏色值時不抄", () => {
        const doc = parse(`<table><tr style="background:url(x.png) no-repeat"><td style="width:50%">a</td><td>b</td></tr></table>`);
        applyCanvasTableHints(doc, A4_INNER);
        const td = doc.getElementsByTagName("td")[0] as Element;
        expect(styleValue(td.getAttribute("style"), "background-color")).toBeNull();
    });
});
