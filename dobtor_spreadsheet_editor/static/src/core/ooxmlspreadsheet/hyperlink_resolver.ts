// hyperlink_resolver.ts — worksheet hyperlinks 的 rId → URL 解析（§1.6）

import type { PackageReader } from './package_reader';
import type { Hyperlink } from './worksheet_parser';

export interface ResolvedHyperlink {
    ref: string;
    url: string;
    display?: string;
}

/** 把 worksheet 的 hyperlinks（rId/location）解析成 ref→url。*/
export function resolveHyperlinks(
    pkg: PackageReader,
    sheetPart: string,
    hyperlinks: Hyperlink[],
): ResolvedHyperlink[] {
    if (hyperlinks.length === 0) return [];
    const relMap = new Map(pkg.getRels(sheetPart).map((r) => [r.id, r]));
    const out: ResolvedHyperlink[] = [];
    for (const h of hyperlinks) {
        let url: string | undefined;
        if (h.rId) {
            const rel = relMap.get(h.rId);
            if (rel) url = rel.targetMode === 'External' ? rel.target : rel.resolvedTarget;
        } else if (h.location) {
            url = `#${h.location}`; // 內部參照（同檔 sheet!cell）
        }
        if (url) out.push({ ref: h.ref, url, display: h.display });
    }
    return out;
}
