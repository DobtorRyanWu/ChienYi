// preview_images.ts — drawing 圖片 → data URL（§5.3 HTML 預覽用）
//
// 僅供 HTML 預覽（<img src=data-url>，瀏覽器原生支援）。
// 可編輯 o-spreadsheet 的圖片需 ir.attachment + imageProvider，另案處理。

import type { PackageReader } from './package_reader';
import { parseDrawingPics } from './drawing_parser';

export interface PreviewImage {
    dataUrl: string;
    /** 錨點左上格（1-based row/col），供預覽標示位置。*/
    row: number;
    col: number;
}

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

/** 解析某 worksheet part 連結的圖片 → data URL（預覽用）。*/
export function resolvePreviewImages(pkg: PackageReader, sheetPart: string): PreviewImage[] {
    const out: PreviewImage[] = [];
    const drawingRels = pkg.getRels(sheetPart).filter((r) => r.type.endsWith('/drawing'));
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
                dataUrl: `data:${mimetype};base64,${toBase64(bytes)}`,
                row: pic.fromRow + 1,
                col: pic.fromCol + 1,
            });
        }
    }
    return out;
}

/** 圖片清單 → 預覽 gallery HTML 片段。*/
export function previewImagesHtml(images: PreviewImage[]): string {
    if (images.length === 0) return '';
    const items = images
        .map(
            (im) =>
                `<figure style="margin:4px;display:inline-block;text-align:center;vertical-align:top">` +
                `<img src="${im.dataUrl}" style="max-width:300px;max-height:240px;border:1px solid #ccc"/>` +
                `<figcaption style="color:#888;font-size:12px">錨點 R${im.row}C${im.col}</figcaption></figure>`,
        )
        .join('');
    return `<div style="margin-top:12px;padding-top:8px;border-top:1px solid #ddd"><div style="color:#666;margin-bottom:4px">內嵌圖片（${images.length}）：</div>${items}</div>`;
}
