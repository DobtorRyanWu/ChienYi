/** @odoo-module **/
// CHOOSE shim：o-spreadsheet 18.0.48 未內建 CHOOSE，於此補上 functionRegistry，
// 讓匯入的 xlsx 含 CHOOSE 公式可即時運算（不必 fallback cached）。

import { _t } from "@web/core/l10n/translation";
import * as spreadsheet from "@odoo/o-spreadsheet";

const { arg, toNumber } = spreadsheet.helpers;
const { functionRegistry } = spreadsheet.registries;

// 已存在就不重複註冊（避免未來版本內建後衝突）
if (!functionRegistry.content || !functionRegistry.content["CHOOSE"]) {
    functionRegistry.add("CHOOSE", {
        description: _t("依索引值回傳對應的選項（1-based）。"),
        category: "lookup",
        compute: function (index, ...values) {
            const i = Math.trunc(toNumber(index, this.locale));
            if (i < 1 || i > values.length) {
                return { value: "#VALUE!", message: _t("CHOOSE 索引超出範圍。") };
            }
            return values[i - 1];
        },
        args: [
            arg("index (number)", _t("選項索引（1-based）。")),
            arg("value1 (any, repeating)", _t("可選的值。")),
        ],
        returns: ["ANY"],
    });
}
