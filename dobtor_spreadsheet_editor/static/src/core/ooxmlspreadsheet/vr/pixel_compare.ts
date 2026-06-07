// pixel_compare.ts — VR 像素比對原語（規劃書 §6 Phase 4 VR pipeline）
//
// 用 pngjs 解碼 + pixelmatch 比對兩張 PNG，回傳差異率。
// 尺寸不一致時：取交集區比對，非重疊區計入差異（避免假性 0%）。

import { PNG } from 'pngjs';
import pixelmatch from 'pixelmatch';

export interface PixelDiff {
    /** 比對交集寬/高。*/
    width: number;
    height: number;
    /** 差異像素數（含尺寸不匹配區）。*/
    diffPixels: number;
    /** 分母（兩圖較大面積）。*/
    totalPixels: number;
    /** 差異率 0..1。*/
    ratio: number;
    /** 差異視覺化 PNG（交集區），未要求時為 undefined。*/
    diffPng?: Buffer;
}

export interface CompareOptions {
    /** pixelmatch 色差門檻 0..1（預設 0.1）。*/
    threshold?: number;
    /** 是否產出 diff 視覺化 PNG。*/
    emitDiff?: boolean;
    /**
     * 尺寸不匹配時縮放對齊後再比對（消除尺寸不同造成的假性差異，只量內容差異）。
     * 預設 false（交集 + 非重疊計入差異）。
     */
    scaleToMatch?: boolean;
}

/** 把 PNG data 裁切成 w×h 的 RGBA buffer（左上對齊）。*/
function cropRGBA(png: PNG, w: number, h: number): Uint8Array {
    if (png.width === w && png.height === h) return png.data;
    const out = new Uint8Array(w * h * 4);
    for (let y = 0; y < h; y++) {
        const srcStart = y * png.width * 4;
        const dstStart = y * w * 4;
        out.set(png.data.subarray(srcStart, srcStart + w * 4), dstStart);
    }
    return out;
}

/** 最近鄰縮放 PNG data 到 w×h 的 RGBA buffer。*/
function resizeNearestRGBA(png: PNG, w: number, h: number): Uint8Array {
    if (png.width === w && png.height === h) return png.data;
    const out = new Uint8Array(w * h * 4);
    for (let y = 0; y < h; y++) {
        const sy = Math.min(png.height - 1, Math.floor((y * png.height) / h));
        for (let x = 0; x < w; x++) {
            const sx = Math.min(png.width - 1, Math.floor((x * png.width) / w));
            const si = (sy * png.width + sx) * 4;
            const di = (y * w + x) * 4;
            out[di] = png.data[si];
            out[di + 1] = png.data[si + 1];
            out[di + 2] = png.data[si + 2];
            out[di + 3] = png.data[si + 3];
        }
    }
    return out;
}

/** 比對兩張 PNG buffer，回傳差異率。*/
export function comparePng(aBuf: Buffer, bBuf: Buffer, opts: CompareOptions = {}): PixelDiff {
    const threshold = opts.threshold ?? 0.1;
    const a = PNG.sync.read(aBuf);
    const b = PNG.sync.read(bBuf);
    const w = Math.min(a.width, b.width);
    const h = Math.min(a.height, b.height);

    const ca = opts.scaleToMatch ? resizeNearestRGBA(a, w, h) : cropRGBA(a, w, h);
    const cb = opts.scaleToMatch ? resizeNearestRGBA(b, w, h) : cropRGBA(b, w, h);
    const out = opts.emitDiff ? new PNG({ width: w, height: h }) : undefined;
    const diff = pixelmatch(ca, cb, out ? out.data : undefined, w, h, { threshold });

    // scaleToMatch：兩圖皆縮放到 w×h、無非重疊區；否則非重疊面積計入差異
    const totalPixels = opts.scaleToMatch ? w * h : Math.max(a.width * a.height, b.width * b.height);
    const diffPixels = opts.scaleToMatch ? diff : diff + (totalPixels - w * h);

    return {
        width: w,
        height: h,
        diffPixels,
        totalPixels,
        ratio: totalPixels > 0 ? diffPixels / totalPixels : 0,
        diffPng: out ? PNG.sync.write(out) : undefined,
    };
}
