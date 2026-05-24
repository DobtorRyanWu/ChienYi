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
import { scanJinja2Variables, flattenElementsToText, scanJinja2VariablesWithPositions, scanJinja2VariablesInTables } from "../../static/src/components/doc_editor/jinja2_scanner.js";

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

describe("scanJinja2VariablesWithPositions (Sprint H)", () => {
    it("回傳 main 流的逐筆匹配 + 元素索引", () => {
        // "Hi {{ a }} bye" 共 14 字元，每個元素 1 字元
        const main = textToElements("Hi {{ a }} bye");
        const result = scanJinja2VariablesWithPositions(main);
        expect(result).toHaveLength(1);
        expect(result[0].varName).toBe("a");
        expect(result[0].fullMatch).toBe("{{ a }}");
        // "Hi " 佔 0-2，"{{ a }}" 佔 3-9
        expect(result[0].startIdx).toBe(3);
        expect(result[0].endIdx).toBe(9);
    });

    it("多個變數按文件順序回傳（不去重）", () => {
        const main = textToElements("{{ a }} 和 {{ b }} 還有 {{ a }}");
        const result = scanJinja2VariablesWithPositions(main);
        expect(result).toHaveLength(3);
        expect(result.map((r: any) => r.varName)).toEqual(["a", "b", "a"]);
        // 確認位置嚴格遞增
        expect(result[0].endIdx).toBeLessThan(result[1].startIdx);
        expect(result[1].endIdx).toBeLessThan(result[2].startIdx);
    });

    it("跨 control 元素的 match 作廢（不會跨越 unsafe sentinel）", () => {
        const main = [
            ...textToElements("{{ "),
            { type: "control", value: "X", placeholder: "" },
            ...textToElements("name }}"),
        ];
        const result = scanJinja2VariablesWithPositions(main);
        // `{{ ` + control + `name }}` 不應產生 match
        expect(result).toEqual([]);
    });

    it("跨 table 元素的 match 作廢", () => {
        const main = [
            ...textToElements("{{ "),
            { type: "table", trList: [{ tdList: [{ value: textToElements("X") }] }] },
            ...textToElements("a }}"),
        ];
        const result = scanJinja2VariablesWithPositions(main);
        expect(result).toEqual([]);
    });

    it("跨 multi-char value 元素的 match 作廢（無法精確設 range）", () => {
        const main = [
            ...textToElements("{{ "),
            { value: "abc" }, // multi-char value
            ...textToElements(" }}"),
        ];
        const result = scanJinja2VariablesWithPositions(main);
        expect(result).toEqual([]);
    });

    it("complex element 不會打斷其外圍的 match", () => {
        // "ok {{ a }} sep {{ b }} done"
        // 中間夾一個 control 元素在 sep 之後，b 的 match 應該仍然有效
        const main = [
            ...textToElements("ok {{ a }} sep "),
            { type: "control", value: "X" },
            ...textToElements(" {{ b }} done"),
        ];
        const result = scanJinja2VariablesWithPositions(main);
        expect(result).toHaveLength(2);
        expect(result[0].varName).toBe("a");
        expect(result[1].varName).toBe("b");
    });

    it("剝 `object.` 前綴與 Sprint G 對齊", () => {
        const main = textToElements("{{ object.partner_id.name }}");
        const result = scanJinja2VariablesWithPositions(main);
        expect(result).toHaveLength(1);
        expect(result[0].varName).toBe("partner_id.name");
        // fullMatch 不剝（保留原文用於 search）
        expect(result[0].fullMatch).toBe("{{ object.partner_id.name }}");
    });

    it("變數內空白容錯", () => {
        const main = textToElements("{{name}} and {{  spacey  }}");
        const result = scanJinja2VariablesWithPositions(main);
        expect(result.map((r: any) => r.varName)).toEqual(["name", "spacey"]);
    });

    it("帶點路徑變數", () => {
        const main = textToElements("{{ partner_id.name }}");
        const result = scanJinja2VariablesWithPositions(main);
        expect(result).toHaveLength(1);
        expect(result[0].varName).toBe("partner_id.name");
        expect(result[0].startIdx).toBe(0);
        // "{{ partner_id.name }}" 共 21 字元，endIdx = 20
        expect(result[0].endIdx).toBe(20);
    });

    it("變數內含非法字元（如 |filter）不收", () => {
        const main = textToElements("{{ a|upper }} {{ b }}");
        const result = scanJinja2VariablesWithPositions(main);
        expect(result).toHaveLength(1);
        expect(result[0].varName).toBe("b");
    });

    it("沒找到變數時回空陣列", () => {
        const main = textToElements("just plain text no variables");
        expect(scanJinja2VariablesWithPositions(main)).toEqual([]);
    });

    it("防禦：非陣列回空", () => {
        expect(scanJinja2VariablesWithPositions(null as any)).toEqual([]);
        expect(scanJinja2VariablesWithPositions(undefined as any)).toEqual([]);
        expect(scanJinja2VariablesWithPositions({} as any)).toEqual([]);
    });

    it("位置精度可用於 setRange：startIdx..endIdx 的元素串接 = fullMatch", () => {
        const main = textToElements("prefix {{ project_name }} suffix");
        const result = scanJinja2VariablesWithPositions(main);
        expect(result).toHaveLength(1);
        const { startIdx, endIdx, fullMatch } = result[0];
        // 對 mainElements[startIdx..endIdx] 取 value 串起來、應該 = fullMatch
        const reconstructed = main.slice(startIdx, endIdx + 1)
            .map((el: any) => el.value).join("");
        expect(reconstructed).toBe(fullMatch);
    });
});

describe("scanJinja2VariablesInTables (Sprint J)", () => {
    it("找到 table cell 內的變數，含 table/tr/td 座標", () => {
        const main = [
            ...textToElements("前文 "),
            {
                type: "table",
                id: "tbl_1",
                trList: [
                    {
                        tdList: [
                            { value: textToElements("姓名：{{ name }}") },
                            { value: textToElements("公司：{{ company }}") },
                        ],
                    },
                ],
            },
        ];
        const result = scanJinja2VariablesInTables(main);
        expect(result).toHaveLength(2);
        expect(result[0]).toMatchObject({
            varName: "name",
            tableElementIdx: 3,  // "前文 " 佔 3 個 element
            trIdx: 0,
            tdIdx: 0,
            tableId: "tbl_1",
        });
        expect(result[1]).toMatchObject({
            varName: "company",
            tableElementIdx: 3,
            trIdx: 0,
            tdIdx: 1,
            tableId: "tbl_1",
        });
    });

    it("多列多欄 table，座標正確", () => {
        const main = [
            {
                type: "table",
                id: "tbl_x",
                trList: [
                    {
                        tdList: [
                            { value: textToElements("{{ a }}") },
                            { value: textToElements("{{ b }}") },
                        ],
                    },
                    {
                        tdList: [
                            { value: textToElements("{{ c }}") },
                        ],
                    },
                ],
            },
        ];
        const result = scanJinja2VariablesInTables(main);
        expect(result).toHaveLength(3);
        expect(result.map((r: any) => [r.trIdx, r.tdIdx, r.varName])).toEqual([
            [0, 0, "a"],
            [0, 1, "b"],
            [1, 0, "c"],
        ]);
    });

    it("table 無 id 時仍回傳（tableId=null，呼叫者要 fallback）", () => {
        const main = [
            {
                type: "table",
                trList: [{ tdList: [{ value: textToElements("{{ x }}") }] }],
            },
        ];
        const result = scanJinja2VariablesInTables(main);
        expect(result).toHaveLength(1);
        expect(result[0].tableId).toBeNull();
    });

    it("td.value 內含 control 的 match 作廢（複用 main flow 的 sentinel 邏輯）", () => {
        const main = [
            {
                type: "table",
                id: "t1",
                trList: [{
                    tdList: [{
                        value: [
                            ...textToElements("{{ "),
                            { type: "control", value: "X" },
                            ...textToElements("a }}"),
                        ],
                    }],
                }],
            },
        ];
        expect(scanJinja2VariablesInTables(main)).toEqual([]);
    });

    it("非 table 元素跳過、不影響其他 table 處理", () => {
        const main = [
            ...textToElements("nope"),
            { type: "image", value: "" },
            {
                type: "table",
                id: "tt",
                trList: [{ tdList: [{ value: textToElements("{{ ok }}") }] }],
            },
        ];
        const result = scanJinja2VariablesInTables(main);
        expect(result).toHaveLength(1);
        expect(result[0].varName).toBe("ok");
    });

    it("空 / 缺失 trList / tdList 防禦", () => {
        expect(scanJinja2VariablesInTables([])).toEqual([]);
        expect(scanJinja2VariablesInTables([{ type: "table" }])).toEqual([]);
        expect(scanJinja2VariablesInTables([{ type: "table", trList: [] }])).toEqual([]);
        expect(scanJinja2VariablesInTables([{ type: "table", trList: [{}] }])).toEqual([]);
        expect(scanJinja2VariablesInTables([{ type: "table", trList: [{ tdList: [] }] }])).toEqual([]);
        expect(scanJinja2VariablesInTables([{ type: "table", trList: [{ tdList: [{}] }] }])).toEqual([]);
    });

    it("防禦：非陣列回空", () => {
        expect(scanJinja2VariablesInTables(null as any)).toEqual([]);
        expect(scanJinja2VariablesInTables(undefined as any)).toEqual([]);
        expect(scanJinja2VariablesInTables({} as any)).toEqual([]);
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
