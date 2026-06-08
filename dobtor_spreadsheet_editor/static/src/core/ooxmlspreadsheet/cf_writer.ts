// cf_writer.ts — ConditionalFormatting + dxfs → OOXML（Phase 6 §6.2 CF 匯出回 xlsx）
//
// exportXlsxFromBuffer 的反向：把解析的 CF AST 與 dxfs 序列化回 worksheet 的 <conditionalFormatting>
// 與 styles.xml 的 <dxfs>，達成 CF 雙向 round-trip。

import type { ConditionalFormatting, CfRule, CfValueObject } from './cf_parser';
import type { Dxf, Font, Fill, Border, BorderEdge } from './styles_parser';
import type { Color } from './color';

function escAttr(s: string): string {
    return s
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function escText(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** Color → `<tag .../>`（rgb / theme+tint / indexed / auto）。回空字串表示無色。*/
function colorXml(tag: string, c: Color | undefined): string {
    if (!c) return '';
    const a: string[] = [];
    if (c.rgb) a.push(`rgb="${c.rgb}"`);
    else if (c.theme !== undefined) {
        a.push(`theme="${c.theme}"`);
        if (c.tint !== undefined && c.tint !== 0) a.push(`tint="${c.tint}"`);
    } else if (c.indexed !== undefined) a.push(`indexed="${c.indexed}"`);
    else if (c.auto) a.push(`auto="1"`);
    else return '';
    return `<${tag} ${a.join(' ')}/>`;
}

function fontXml(f: Font): string {
    let s = '';
    if (f.bold) s += '<b/>';
    if (f.italic) s += '<i/>';
    if (f.strike) s += '<strike/>';
    if (f.underline && f.underline !== 'none') {
        s += f.underline === 'single' ? '<u/>' : `<u val="${escAttr(f.underline)}"/>`;
    }
    s += colorXml('color', f.color);
    if (f.size !== undefined) s += `<sz val="${f.size}"/>`;
    if (f.name) s += `<name val="${escAttr(f.name)}"/>`;
    return `<font>${s}</font>`;
}

function fillXml(fill: Fill): string {
    const pattern = fill.patternType ?? 'solid';
    return (
        `<fill><patternFill patternType="${escAttr(pattern)}">` +
        colorXml('fgColor', fill.fgColor) +
        colorXml('bgColor', fill.bgColor) +
        `</patternFill></fill>`
    );
}

function edgeXml(tag: string, e: BorderEdge | undefined): string {
    if (!e || !e.style) return `<${tag}/>`;
    return `<${tag} style="${escAttr(e.style)}">${colorXml('color', e.color)}</${tag}>`;
}

function borderXml(b: Border): string {
    return (
        `<border>` +
        edgeXml('left', b.left) +
        edgeXml('right', b.right) +
        edgeXml('top', b.top) +
        edgeXml('bottom', b.bottom) +
        (b.diagonal ? edgeXml('diagonal', b.diagonal) : '') +
        `</border>`
    );
}

function dxfXml(dxf: Dxf): string {
    let s = '';
    if (dxf.font) s += fontXml(dxf.font);
    // dxf numFmt（罕見，CF 多用 font/fill）
    if (dxf.numFmtId !== undefined && dxf.numFmtCode)
        s += `<numFmt numFmtId="${dxf.numFmtId}" formatCode="${escAttr(dxf.numFmtCode)}"/>`;
    if (dxf.fill) s += fillXml(dxf.fill);
    if (dxf.border) s += borderXml(dxf.border);
    return `<dxf>${s}</dxf>`;
}

/** dxfs → `<dxfs>`（保留原索引順序，cfRule 的 dxfId 仍有效）。回空字串表示無 dxf。*/
export function writeDxfs(dxfs: Dxf[]): string {
    if (!dxfs || dxfs.length === 0) return '';
    return `<dxfs count="${dxfs.length}">${dxfs.map(dxfXml).join('')}</dxfs>`;
}

function cfvoXml(v: CfValueObject): string {
    return `<cfvo type="${escAttr(v.type)}"${v.val !== undefined ? ` val="${escAttr(v.val)}"` : ''}/>`;
}

function ruleXml(rule: CfRule): string {
    const a: string[] = [`type="${escAttr(rule.type)}"`];
    if (rule.dxfId !== undefined) a.push(`dxfId="${rule.dxfId}"`);
    a.push(`priority="${rule.priority}"`);
    if (rule.operator) a.push(`operator="${escAttr(rule.operator)}"`);
    if (rule.text !== undefined) a.push(`text="${escAttr(rule.text)}"`);
    if (rule.percent) a.push('percent="1"');
    if (rule.rank !== undefined) a.push(`rank="${rule.rank}"`);
    if (rule.stopIfTrue) a.push('stopIfTrue="1"');

    let inner = '';
    if (rule.colorScale) {
        inner +=
            `<colorScale>` +
            rule.colorScale.cfvo.map(cfvoXml).join('') +
            rule.colorScale.colors.map((c) => colorXml('color', c)).join('') +
            `</colorScale>`;
    } else if (rule.dataBar) {
        inner +=
            `<dataBar>` + rule.dataBar.cfvo.map(cfvoXml).join('') + colorXml('color', rule.dataBar.color) + `</dataBar>`;
    } else if (rule.iconSet) {
        inner += `<iconSet iconSet="${escAttr(rule.iconSet.iconSet)}">` + rule.iconSet.cfvo.map(cfvoXml).join('') + `</iconSet>`;
    }
    inner += rule.formulas.map((f) => `<formula>${escText(f)}</formula>`).join('');
    return `<cfRule ${a.join(' ')}>${inner}</cfRule>`;
}

/** ConditionalFormatting[] → 串接的 `<conditionalFormatting>` XML（放在 mergeCells 之後）。*/
export function writeConditionalFormattings(blocks: ConditionalFormatting[] | undefined): string {
    if (!blocks || blocks.length === 0) return '';
    return blocks
        .filter((b) => b.ranges.length > 0 && b.rules.length > 0)
        .map((b) => `<conditionalFormatting sqref="${escAttr(b.ranges.join(' '))}">${b.rules.map(ruleXml).join('')}</conditionalFormatting>`)
        .join('');
}
