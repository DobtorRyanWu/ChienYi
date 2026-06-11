// image_extractor.ts — xlsx 內嵌圖片 → base64 + 位置（§5.3 可編輯版）
//
// 供 OWL 端建 ir.attachment、組 o-spreadsheet image figure（data.path = /web/image/...）。
// 與 preview_images（HTML 預覽用 data URL）分離：此處不產 data URL，只給 base64 讓 OWL 上傳。

import { PackageReader } from './package_reader';
import { WorkbookParser } from './workbook_parser';
import { parseDrawingPics } from './drawing_parser';

export interface ExtractedImage {
    /** 0-based 工作表索引（對應 OSpreadsheetData.sheets）。*/
    sheetIndex: number;
    /** 圖片 base64（無 data: 前綴）。*/
    base64: string;
    mimetype: string;
    /** figure 位置/尺寸（px，由錨點估算）。*/
    x: number;
    y: number;
    width: number;
    height: number;
}

const COL_PX = 64;
const ROW_PX = 20;
const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

function toBase64(bytes: Uint8Array): string {
    let out = '';
    let i = 0;
    for (; i + 2 < bytes.length; i += 3) {
        const n = (bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2];
        out += B64[(n >> 18) & 63] + B64[(n >> 12) & 63] + B64[(n >> 6) & 63] + B64[n & 63];
    }
    const rem = bytes.length - i;
    if (rem === 1) {
        const n = bytes[i] << 16;
        out += B64[(n >> 18) & 63] + B64[(n >> 12) & 63] + '==';
    } else if (rem === 2) {
        const n = (bytes[i] << 16) | (bytes[i + 1] << 8);
        out += B64[(n >> 18) & 63] + B64[(n >> 12) & 63] + B64[(n >> 6) & 63] + '=';
    }
    return out;
}

const MIME: Readonly<Record<string, string>> = {
    jpeg: 'image/jpeg',
    jpg: 'image/jpeg',
    png: 'image/png',
    gif: 'image/gif',
    bmp: 'image/bmp',
};

/** 解析 xlsx 全部內嵌圖片 → base64 + 位置（sheetIndex 對應 importXlsxToOSpreadsheetData 的 sheets 順序）。*/
export function extractXlsxImages(buffer: ArrayBuffer): ExtractedImage[] {
    const pkg = PackageReader.fromBuffer(buffer);
    const wbp = new WorkbookParser(pkg);
    const wb = wbp.parse();
    const out: ExtractedImage[] = [];
    // 與 importXlsxToOSpreadsheetData 相同的 sheet 過濾順序，確保 sheetIndex 對齊
    const sheets = wb.sheets.filter((s) => s.target && pkg.hasPart(s.target));
    sheets.forEach((s, sheetIndex) => {
        const drawingRels = pkg.getRels(s.target!).filter((r) => r.type.endsWith('/drawing'));
        for (const dr of drawingRels) {
            const drawingPart = dr.resolvedTarget;
            if (!drawingPart || !pkg.hasPart(drawingPart)) continue;
            const pics = parseDrawingPics(pkg.getPartText(drawingPart));
            if (pics.length === 0) continue;
            const relMap = new Map(pkg.getRels(drawingPart).map((r) => [r.id, r.resolvedTarget]));
            for (const pic of pics) {
                const mediaPart = relMap.get(pic.blipRId);
                if (!mediaPart || !pkg.hasPart(mediaPart)) continue;
                const ext = (mediaPart.split('.').pop() ?? '').toLowerCase();
                const mimetype = MIME[ext];
                if (!mimetype) continue;
                const bytes = pkg.getPart(mediaPart);
                if (!bytes || bytes.byteLength > MAX_IMAGE_BYTES) continue;
                out.push({
                    sheetIndex,
                    base64: toBase64(bytes),
                    mimetype,
                    x: pic.fromCol * COL_PX,
                    y: pic.fromRow * ROW_PX,
                    width: Math.max((pic.toCol - pic.fromCol) * COL_PX, 32),
                    height: Math.max((pic.toRow - pic.fromRow) * ROW_PX, 32),
                });
            }
        }
    });
    return out;
}
