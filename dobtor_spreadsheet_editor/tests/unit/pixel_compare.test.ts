// pixel_compare.test.ts — VR 像素比對原語（規劃書 §6）
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { PNG } from 'pngjs';
import { comparePng } from '../../static/src/core/ooxmlspreadsheet/vr/pixel_compare';

const FIXTURES = join(__dirname, '..', 'fixtures');

/** 建純色 PNG buffer。*/
function solidPng(w: number, h: number, rgb: [number, number, number]): Buffer {
    const png = new PNG({ width: w, height: h });
    for (let i = 0; i < w * h; i++) {
        png.data[i * 4] = rgb[0];
        png.data[i * 4 + 1] = rgb[1];
        png.data[i * 4 + 2] = rgb[2];
        png.data[i * 4 + 3] = 255;
    }
    return PNG.sync.write(png);
}

function pngWithBlackCorner(w: number, h: number): Buffer {
    const png = new PNG({ width: w, height: h });
    for (let i = 0; i < w * h; i++) {
        png.data[i * 4] = png.data[i * 4 + 1] = png.data[i * 4 + 2] = 255;
        png.data[i * 4 + 3] = 255;
    }
    png.data[0] = png.data[1] = png.data[2] = 0; // 左上一像素塗黑
    return PNG.sync.write(png);
}

describe('comparePng — 自洽', () => {
    it('相同圖 → ratio 0', () => {
        const a = solidPng(20, 20, [255, 255, 255]);
        const d = comparePng(a, a);
        expect(d.diffPixels).toBe(0);
        expect(d.ratio).toBe(0);
        expect(d.totalPixels).toBe(400);
    });
    it('一像素不同 → diffPixels >= 1、ratio > 0', () => {
        const white = solidPng(20, 20, [255, 255, 255]);
        const corner = pngWithBlackCorner(20, 20);
        const d = comparePng(white, corner);
        expect(d.diffPixels).toBeGreaterThanOrEqual(1);
        expect(d.ratio).toBeGreaterThan(0);
    });
    it('全黑 vs 全白 → ratio ~1', () => {
        const d = comparePng(solidPng(10, 10, [0, 0, 0]), solidPng(10, 10, [255, 255, 255]));
        expect(d.ratio).toBeGreaterThan(0.9);
    });
    it('尺寸不匹配 → 非重疊區計入差異', () => {
        const small = solidPng(10, 10, [255, 255, 255]);
        const big = solidPng(12, 12, [255, 255, 255]);
        const d = comparePng(small, big);
        expect(d.width).toBe(10);
        expect(d.height).toBe(10);
        expect(d.totalPixels).toBe(144); // max(100,144)
        expect(d.diffPixels).toBe(44); // 144-100 非重疊
    });
    it('scaleToMatch：同色不同尺寸 → 無尺寸假性差異（ratio 0）', () => {
        const small = solidPng(10, 10, [255, 255, 255]);
        const big = solidPng(16, 16, [255, 255, 255]);
        const d = comparePng(small, big, { scaleToMatch: true });
        expect(d.totalPixels).toBe(100); // 縮放到交集 10×10、無非重疊
        expect(d.diffPixels).toBe(0);
        expect(d.ratio).toBe(0);
    });
    it('scaleToMatch：異色不同尺寸 → 純內容差異 ~1', () => {
        const d = comparePng(solidPng(10, 10, [0, 0, 0]), solidPng(16, 16, [255, 255, 255]), {
            scaleToMatch: true,
        });
        expect(d.ratio).toBeGreaterThan(0.9);
    });
    it('emitDiff → 產出 diff PNG buffer', () => {
        const d = comparePng(solidPng(8, 8, [0, 0, 0]), solidPng(8, 8, [255, 255, 255]), {
            emitDiff: true,
        });
        expect(d.diffPng).toBeInstanceOf(Buffer);
        expect(PNG.sync.read(d.diffPng!).width).toBe(8);
    });
});

describe('comparePng — 真實 golden PNG 自比對', () => {
    it('golden 自比對 → ratio 0', () => {
        const dir = join(FIXTURES, '08_chienyii_business', 'golden');
        const png = readdirSync(dir).find((f) => f.endsWith('.png'));
        const buf = readFileSync(join(dir, png!));
        const d = comparePng(buf, buf);
        expect(d.ratio).toBe(0);
        expect(d.totalPixels).toBeGreaterThan(1000);
    });
});
