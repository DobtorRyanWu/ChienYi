// number_format.ts — Excel 日期序號 → 日期字串（規劃書 §2.3 最小版）
//
// 範圍：只做「日期序號 → YYYY-MM-DD」，補 §1.6 提取率的日期缺口。
// 完整 number format 渲染（千分位/貨幣/百分比/自訂 token）是 §2.3 後續工作。
//
// Excel 1900 日期系統：serial 1 = 1900-01-01，但 Excel 誤把 1900 當閏年（serial 60 = 不存在的
// 1900-02-29）。以 1899-12-30 為 day 0 的基準，可對 serial ≥ 61（即 ≥ 1900-03-01）正確還原——
// 涵蓋所有現代日期。serial ≤ 60 的邊界（1900 年初）本最小版不保證，營造資料用不到。

const EXCEL_EPOCH_TO_UNIX_DAYS = 25569; // 1899-12-30 → 1970-01-01 的天數
const DAYS_PER_ERA = 146097; // 400 年的天數
const ERA_SHIFT = 719468; // Hinnant 演算法：1970-01-01 對齊到 0000-03-01 era 起點

export interface Ymd {
    y: number;
    m: number; // 1-12
    d: number; // 1-31
}

/**
 * days since 1970-01-01 → 民曆 (y, m, d)。
 * Howard Hinnant civil_from_days 演算法（純整數、無時區、可處理負值）。
 */
export function civilFromDays(z: number): Ymd {
    const zz = z + ERA_SHIFT;
    const era = Math.floor((zz >= 0 ? zz : zz - (DAYS_PER_ERA - 1)) / DAYS_PER_ERA);
    const doe = zz - era * DAYS_PER_ERA; // [0, 146096]
    const yoe = Math.floor((doe - Math.floor(doe / 1460) + Math.floor(doe / 36524) - Math.floor(doe / 146096)) / 365); // [0,399]
    const y = yoe + era * 400;
    const doy = doe - (365 * yoe + Math.floor(yoe / 4) - Math.floor(yoe / 100)); // [0,365]
    const mp = Math.floor((5 * doy + 2) / 153); // [0,11]
    const d = doy - Math.floor((153 * mp + 2) / 5) + 1; // [1,31]
    const m = mp < 10 ? mp + 3 : mp - 9; // [1,12]
    return { y: m <= 2 ? y + 1 : y, m, d };
}

/** Excel 日期序號 → (y, m, d)（取整數部分，1899-12-30 基準）。*/
export function excelSerialToYmd(serial: number): Ymd {
    const unixDays = Math.floor(serial) - EXCEL_EPOCH_TO_UNIX_DAYS;
    return civilFromDays(unixDays);
}

function pad2(n: number): string {
    return n < 10 ? '0' + n : String(n);
}

/** Excel 日期序號 → "YYYY-MM-DD"（對齊 python-calamine 的 str(date) 輸出）。*/
export function formatExcelDate(serial: number): string {
    const { y, m, d } = excelSerialToYmd(serial);
    return `${String(y).padStart(4, '0')}-${pad2(m)}-${pad2(d)}`;
}

const MINGUO_EPOCH = 1911; // 民國元年 = 西元 1912；民國年 = 西元年 - 1911

/**
 * 依 Excel 日期格式碼渲染日期字串（§2.3）——支援台灣常見格式含**民國年**。
 * token：yyyy/yy（西元）、e/ee（民國年 = y-1911）、gg/g（→「民國」）、m/mm（月）、d/dd（日）、
 * "字面"、\跳脫、其餘字元（/ . 年 月 日 - 空白）原樣輸出。去 [$-xxx] locale、取 ';' 前第一段。
 * 非日期格式（無 y/m/d/e token）回 undefined。
 */
export function formatExcelDateByCode(serial: number, code: string): string | undefined {
    return formatYmdByCode(excelSerialToYmd(serial), code);
}

/** 同 formatExcelDateByCode，但輸入已是 (y,m,d)（給已轉 ISO 字串的 render 路徑重用）。*/
export function formatYmdByCode(ymd: Ymd, code: string): string | undefined {
    const fmt = code.split(';')[0].replace(/\[\$-[0-9A-Fa-f]+\]/g, '').replace(/\[[^\]]*\]/g, '');
    if (!fmt) return undefined;
    const { y, m, d } = ymd;
    const minguo = y - MINGUO_EPOCH;
    let out = '';
    let i = 0;
    let sawDateToken = false;
    while (i < fmt.length) {
        const ch = fmt[i];
        if (ch === '"') {
            const end = fmt.indexOf('"', i + 1);
            if (end === -1) { out += fmt.slice(i + 1); break; }
            out += fmt.slice(i + 1, end);
            i = end + 1;
            continue;
        }
        if (ch === '\\') { if (i + 1 < fmt.length) out += fmt[i + 1]; i += 2; continue; }
        const lower = ch.toLowerCase();
        if ('yemdg'.includes(lower)) {
            let j = i;
            while (j < fmt.length && fmt[j].toLowerCase() === lower) j++;
            const len = j - i;
            i = j;
            sawDateToken = true;
            switch (lower) {
                case 'y': out += len <= 2 ? String(y % 100).padStart(2, '0') : String(y); break;
                case 'e': out += len >= 2 ? String(minguo).padStart(2, '0') : String(minguo); break;
                case 'g': out += '民國'; break; // [$-404] gg = 民國
                case 'm': out += len >= 2 ? pad2(m) : String(m); break; // date-only 格式：m=月
                case 'd': out += len >= 2 ? pad2(d) : String(d); break;
            }
            continue;
        }
        out += ch;
        i++;
    }
    return sawDateToken ? out : undefined;
}
