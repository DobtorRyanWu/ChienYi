// number_formatter.ts — Excel number format code → 顯示字串（規劃書 §2.3 完整版子集）
//
// 僅供「視覺渲染」（VR / o-spreadsheet 顯示）；cell value 提取仍用原始數字（與 calamine 對齊）。
// 涵蓋常用 token：# 0 ? , .（千分位/小數）、%（百分比）、"字面" \跳脫 [$貨幣] _寬度 *填充、
// 多段 正;負;零;文字。日期 token（y/m/d/h/s）不在此（走 number_format.ts 的日期路徑）。

const GROUP_SIZE = 3;

interface Token {
    t: 'lit' | 'num' | 'pct' | 'text';
    s?: string;
    pat?: string;
}

/** 從 [$NT$-404] 取貨幣符號 "NT$"；[$-404]（純 locale）或 [Red] 等 → ''。*/
function bracketLiteral(inner: string): string {
    if (inner.startsWith('$')) {
        const rest = inner.slice(1);
        const dash = rest.indexOf('-');
        return dash >= 0 ? rest.slice(0, dash) : rest;
    }
    return ''; // 顏色 / 條件 / locale → 不輸出
}

/** 以 ; 分段，忽略引號/方括號內的分號。*/
function splitSections(code: string): string[] {
    const sections: string[] = [];
    let cur = '';
    let i = 0;
    while (i < code.length) {
        const c = code[i];
        if (c === '"') {
            const j = code.indexOf('"', i + 1);
            const end = j < 0 ? code.length : j;
            cur += code.slice(i, end + 1);
            i = end + 1;
        } else if (c === '[') {
            const j = code.indexOf(']', i);
            const end = j < 0 ? code.length : j;
            cur += code.slice(i, end + 1);
            i = end + 1;
        } else if (c === '\\') {
            cur += code.slice(i, i + 2);
            i += 2;
        } else if (c === ';') {
            sections.push(cur);
            cur = '';
            i++;
        } else {
            cur += c;
            i++;
        }
    }
    sections.push(cur);
    return sections;
}

function tokenize(section: string): Token[] {
    const tokens: Token[] = [];
    let num = '';
    const flush = () => {
        if (num) {
            tokens.push({ t: 'num', pat: num });
            num = '';
        }
    };
    let i = 0;
    while (i < section.length) {
        const c = section[i];
        if (c === '#' || c === '0' || c === '?' || ((c === ',' || c === '.') && num !== '')) {
            num += c;
            i++;
            continue;
        }
        flush();
        if (c === '"') {
            const j = section.indexOf('"', i + 1);
            const end = j < 0 ? section.length : j;
            tokens.push({ t: 'lit', s: section.slice(i + 1, end) });
            i = end + 1;
        } else if (c === '\\') {
            tokens.push({ t: 'lit', s: section[i + 1] ?? '' });
            i += 2;
        } else if (c === '[') {
            const j = section.indexOf(']', i);
            const end = j < 0 ? section.length : j;
            tokens.push({ t: 'lit', s: bracketLiteral(section.slice(i + 1, end)) });
            i = end + 1;
        } else if (c === '_') {
            tokens.push({ t: 'lit', s: ' ' }); // 下一字元的寬度 ≈ 空白
            i += 2;
        } else if (c === '*') {
            i += 2; // 填充字元：跳過
        } else if (c === '%') {
            tokens.push({ t: 'pct' });
            i++;
        } else if (c === '@') {
            tokens.push({ t: 'text' });
            i++;
        } else {
            tokens.push({ t: 'lit', s: c });
            i++;
        }
    }
    flush();
    return tokens;
}

function groupThousands(intStr: string): string {
    let out = '';
    for (let i = 0; i < intStr.length; i++) {
        if (i > 0 && (intStr.length - i) % GROUP_SIZE === 0) out += ',';
        out += intStr[i];
    }
    return out;
}

/** 依 number pattern（如 "#,##0.00"）格式化非負數。*/
function renderNumber(n: number, pat: string): string {
    const dot = pat.indexOf('.');
    const intPat = dot >= 0 ? pat.slice(0, dot) : pat;
    const decPat = dot >= 0 ? pat.slice(dot + 1) : '';
    const decDigits = (decPat.match(/[0#?]/g) ?? []).length;
    const thousands = intPat.includes(',');
    const minInt = (intPat.match(/0/g) ?? []).length;

    const fixed = n.toFixed(decDigits);
    const [rawInt, rawDec = ''] = fixed.split('.');
    let intStr = rawInt;
    if (intStr.length < minInt) intStr = '0'.repeat(minInt - intStr.length) + intStr;
    if (thousands) intStr = groupThousands(intStr);
    return decDigits > 0 ? `${intStr}.${rawDec}` : intStr;
}

/** Excel General：整數不帶小數、浮點原樣（去尾零）。*/
function generalFormat(value: number): string {
    if (Number.isInteger(value)) return String(value);
    return String(value);
}

/**
 * 把數值依 format code 渲染成顯示字串。
 * @param value     數值（非日期；日期走 number_format.ts）
 * @param code      formatCode（如 "#,##0.00"、"0%"、'"NT$"#,##0'）
 */
export function formatNumber(value: number, code: string): string {
    if (code === '' || code === 'General' || code === '@') return generalFormat(value);

    const sections = splitSections(code);
    let section: string;
    let prependMinus = false;
    if (value > 0) {
        section = sections[0];
    } else if (value < 0) {
        if (sections[1] !== undefined) {
            section = sections[1]; // 負數段（自帶括號/負號為字面）
        } else {
            section = sections[0];
            prependMinus = true;
        }
    } else {
        section = sections[2] ?? sections[0];
    }

    const tokens = tokenize(section);
    const pctCount = tokens.filter((t) => t.t === 'pct').length;
    const numTok = tokens.find((t) => t.t === 'num');
    const minus = prependMinus ? '-' : '';

    if (!numTok || numTok.pat === undefined) {
        // 純文字/字面段
        const body = tokens.map((t) => (t.t === 'lit' ? t.s ?? '' : t.t === 'pct' ? '%' : '')).join('');
        return minus + body;
    }

    const scaled = Math.abs(value) * Math.pow(100, pctCount);
    const formatted = renderNumber(scaled, numTok.pat);
    const out = tokens
        .map((t) => (t.t === 'lit' ? t.s ?? '' : t.t === 'num' ? formatted : t.t === 'pct' ? '%' : ''))
        .join('');
    return minus + out;
}
