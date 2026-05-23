/**
 * jinja2_scanner.test.ts — Phase 8 Sprint G
 *
 * 對 scanJinja2Variables / flattenElementsToText 的純函式單測。
 * 涵蓋：
 *   - 主流 + 表格 + 多層巢狀
 *   - 去重 + 出現次數計算
 *   - 變數內空白容錯（`{{name}}` / `{{ name }}` / `{{  name  }}`）
 *   - 帶點路徑（`partner_id.name`）與 `object.` 前綴剝除
 *   - 跳過 control 元素（Sprint E 已註冊欄位不應重複偵測）
 *   - 排序穩定性（次數降冪 → 字母升冪）
 *   - 防禦邊界（null / undefined / 非陣列 main）
 */

import { describe, expect, it } from "vitest";
// 從 OWL 元件資料夾匯入 .js scanner（vitest bundler resolver 支援 .js）
// @ts-expect-error -- 沒附型別宣告，純函式 OK
import { scanJinja2Variables, flattenElementsToText } from "../../static/src/components/doc_editor/jinja2_scanner.js";

/** 把字串展開為 canvas-editor 的單字元 IElement[]（測試 fixture helper） */
function textToElements(text: string) {
    return Array.from(text).map((ch) => ({ value: ch }));
}

describe("scanJinja2Variables", () => {
    it("找到主流的單一變數", () => {
        const data = { main: textToElements("Hello {{ name }} world") };
        expect(scanJinja2Variables(data)).toEqual([
            { varName: "name", occurrences: 1 },
        ]);
    });

    it("user 截圖那 5 個變數場景（去重 + 計次）", () => {
        const text =
            "工程名稱：{{ project_name }}\n" +
            "承包商：{{ contractor }}\n" +
            "估驗日期：{{ estimate_date }}\n" +
            "工程名稱（重複）：{{ project_name }}\n" +
            "金額：{{ amount }}\n" +
            "備註：{{ remark }}";
        const data = { main: textToElements(text) };
        const result = scanJinja2Variables(data);
        // 5 個 unique（project_name 出現 2 次）
        expect(result).toHaveLength(5);
        // project_name 排第一（次數最多）
        expect(result[0]).toEqual({ varName: "project_name", occurrences: 2 });
        // 其餘 4 個各 1 次，按字母排序
        expect(result.slice(1).map((r: any) => r.varName)).toEqual([
            "amount",
            "contractor",
            "estimate_date",
            "remark",
        ]);
    });

    it("變數內空白容錯", () => {
        const data = {
            main: textToElements("{{name}} {{ name }} {{  name  }}"),
        };
        const result = scanJinja2Variables(data);
        expect(result).toEqual([{ varName: "name", occurrences: 3 }]);
    });

    it("帶點路徑變數（partner_id.name）", () => {
        const data = { main: textToElements("{{ partner_id.name }}") };
        const result = scanJinja2Variables(data);
        expect(result).toEqual([
            { varName: "partner_id.name", occurrences: 1 },
        ]);
    });

    it("剝除 `object.` 前綴（與 Sprint E odoo_field_name 對齊）", () => {
        const data = {
            main: textToElements("{{ object.partner_id.name }} 和 {{ partner_id.name }}"),
        };
        const result = scanJinja2Variables(data);
        // 兩個應合併為同一個 `partner_id.name`
        expect(result).toEqual([
            { varName: "partner_id.name", occurrences: 2 },
        ]);
    });

    it("跳過 control 元素（已註冊欄位不重複偵測）", () => {
        const data = {
            main: [
                ...textToElements("Hello "),
                { type: "control", value: "", placeholder: "{{ already_registered }}" },
                ...textToElements(" {{ new_var }}"),
            ],
        };
        const result = scanJinja2Variables(data);
        expect(result).toEqual([{ varName: "new_var", occurrences: 1 }]);
    });

    it("遞迴 table 內 td.value", () => {
        const data = {
            main: [
                {
                    type: "table",
                    trList: [
                        {
                            tdList: [
                                { value: textToElements("欄位 1：{{ field_a }}") },
                                { value: textToElements("欄位 2：{{ field_b }}") },
                            ],
                        },
                        {
                            tdList: [
                                { value: textToElements("欄位 1 重複：{{ field_a }}") },
                            ],
                        },
                    ],
                },
            ],
        };
        const result = scanJinja2Variables(data);
        expect(result).toEqual([
            { varName: "field_a", occurrences: 2 },
            { varName: "field_b", occurrences: 1 },
        ]);
    });

    it("遞迴 list/title 等 valueList", () => {
        const data = {
            main: [
                {
                    type: "title",
                    valueList: textToElements("標題：{{ title_var }}"),
                },
                {
                    type: "list",
                    valueList: textToElements("項目：{{ item_var }}"),
                },
            ],
        };
        const result = scanJinja2Variables(data);
        expect(result.map((r: any) => r.varName).sort()).toEqual([
            "item_var",
            "title_var",
        ]);
    });

    it("同時掃 main / header / footer", () => {
        const data = {
            main: textToElements("{{ main_var }}"),
            header: textToElements("{{ header_var }}"),
            footer: textToElements("{{ footer_var }} {{ header_var }}"),
        };
        const result = scanJinja2Variables(data);
        expect(result).toHaveLength(3);
        // header_var 出現 2 次（header + footer）
        expect(result[0]).toEqual({ varName: "header_var", occurrences: 2 });
    });

    it("沒找到變數時回空陣列", () => {
        const data = { main: textToElements("一段沒有任何變數的純文字") };
        expect(scanJinja2Variables(data)).toEqual([]);
    });

    it("變數內含非法字元（如 |filter）不收", () => {
        const data = {
            main: textToElements("{{ name | upper }} {{ valid_var }}"),
        };
        const result = scanJinja2Variables(data);
        // `name | upper` 不符合純識別字 regex，應不收
        expect(result).toEqual([{ varName: "valid_var", occurrences: 1 }]);
    });

    it("防禦：editorData 為 null / undefined / 空物件", () => {
        expect(scanJinja2Variables(null as any)).toEqual([]);
        expect(scanJinja2Variables(undefined as any)).toEqual([]);
        expect(scanJinja2Variables({})).toEqual([]);
    });

    it("防禦：main 不是陣列", () => {
        expect(scanJinja2Variables({ main: "not an array" } as any)).toEqual([]);
        expect(scanJinja2Variables({ main: null } as any)).toEqual([]);
    });
});

describe("flattenElementsToText", () => {
    it("純 text 字元串接", () => {
        expect(flattenElementsToText(textToElements("Hello"))).toBe("Hello");
    });

    it("跳過 control 元素", () => {
        const elements = [
            ...textToElements("A"),
            { type: "control", value: "B" },
            ...textToElements("C"),
        ];
        expect(flattenElementsToText(elements)).toBe("AC");
    });

    it("非陣列 → 空字串", () => {
        expect(flattenElementsToText(null as any)).toBe("");
        expect(flattenElementsToText(undefined as any)).toBe("");
        expect(flattenElementsToText("string" as any)).toBe("");
    });

    it("table 巢狀遞迴", () => {
        const elements = [
            {
                type: "table",
                trList: [
                    {
                        tdList: [
                            { value: textToElements("X") },
                            { value: textToElements("Y") },
                        ],
                    },
                ],
            },
        ];
        expect(flattenElementsToText(elements)).toBe("XY");
    });
});
