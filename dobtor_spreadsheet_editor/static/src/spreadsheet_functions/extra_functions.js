/** @odoo-module **/
// MROUND / REPT / SIGN shim：o-spreadsheet 18.0.48 未內建這三個函數，
// 於此補上 functionRegistry，讓匯入的 xlsx 含這些公式可即時運算（不必 fallback cached）。

import { _t } from "@web/core/l10n/translation";
import * as spreadsheet from "@odoo/o-spreadsheet";

const { arg, toNumber, toString } = spreadsheet.helpers;
const { functionRegistry } = spreadsheet.registries;

function addIfMissing(name, definition) {
    // 已存在就不重複註冊（避免未來版本內建後衝突）
    if (!functionRegistry.content || !functionRegistry.content[name]) {
        functionRegistry.add(name, definition);
    }
}

addIfMissing("MROUND", {
    description: _t("將數值四捨五入到最接近的指定倍數。"),
    category: "math",
    compute: function (value, factor) {
        const v = toNumber(value, this.locale);
        const f = toNumber(factor, this.locale);
        if (f === 0) return 0;
        // Excel：value 與 factor 異號 → #NUM!
        if ((v > 0 && f < 0) || (v < 0 && f > 0)) {
            return { value: "#NUM!", message: _t("MROUND：數值與倍數須同號。") };
        }
        return Math.round(v / f) * f;
    },
    args: [
        arg("value (number)", _t("要四捨五入的數值。")),
        arg("factor (number)", _t("要捨入到的倍數。")),
    ],
    returns: ["NUMBER"],
});

addIfMissing("REPT", {
    description: _t("將文字重複指定次數。"),
    category: "text",
    compute: function (text, repetitions) {
        const t = toString(text);
        const n = Math.trunc(toNumber(repetitions, this.locale));
        if (n < 0) {
            return { value: "#VALUE!", message: _t("REPT：重複次數不可為負。") };
        }
        return t.repeat(n);
    },
    args: [
        arg("text (string)", _t("要重複的文字。")),
        arg("repetitions (number)", _t("重複次數。")),
    ],
    returns: ["STRING"],
});

addIfMissing("SIGN", {
    description: _t("回傳數值的正負號（正 1、零 0、負 -1）。"),
    category: "math",
    compute: function (value) {
        return Math.sign(toNumber(value, this.locale));
    },
    args: [arg("value (number)", _t("要取正負號的數值。"))],
    returns: ["NUMBER"],
});
