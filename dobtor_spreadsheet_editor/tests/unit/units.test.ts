// units.test.ts — 單位系統測試（規劃書 §1.2）
import { describe, it, expect } from 'vitest';
import {
    EMU_PER_INCH,
    EMU_PER_POINT,
    DEFAULT_DPI,
    DEFAULT_MDW,
    pointsToPixels,
    pixelsToPoints,
    emuToPixels,
    pixelsToEmu,
    emuToPoints,
    pointsToEmu,
    rowHeightToPixels,
    columnWidthToPixels,
    pixelsToColumnWidth,
} from '../../static/src/core/ooxmlspreadsheet/units';

describe('units — 常數', () => {
    it('EMU 基準正確', () => {
        expect(EMU_PER_INCH).toBe(914400);
        expect(EMU_PER_POINT).toBe(12700);
        expect(DEFAULT_DPI).toBe(96);
        expect(DEFAULT_MDW).toBe(7);
    });
});

describe('units — point ↔ pixel', () => {
    it('72pt = 96px @96DPI', () => {
        expect(pointsToPixels(72)).toBe(96);
        expect(pixelsToPoints(96)).toBe(72);
    });
    it('11pt 字級 ≈ 14.667px', () => {
        expect(pointsToPixels(11)).toBeCloseTo(14.6667, 3);
    });
    it('72DPI 時 1pt = 1px', () => {
        expect(pointsToPixels(10, 72)).toBe(10);
    });
});

describe('units — EMU ↔ pixel / point', () => {
    it('1 inch = 914400 EMU = 96px @96DPI', () => {
        expect(emuToPixels(EMU_PER_INCH)).toBe(96);
        expect(pixelsToEmu(96)).toBe(EMU_PER_INCH);
    });
    it('1px @96DPI = 9525 EMU', () => {
        expect(pixelsToEmu(1)).toBe(9525);
    });
    it('EMU ↔ point round-trip', () => {
        expect(emuToPoints(EMU_PER_POINT)).toBe(1);
        expect(pointsToEmu(1)).toBe(12700);
    });
});

describe('units — 列高', () => {
    it('15pt 預設列高 = 20px @96DPI', () => {
        expect(rowHeightToPixels(15)).toBe(20);
    });
});

describe('units — 欄寬（字元數 ↔ pixel）', () => {
    // 依 ECMA-376 §18.3.1.13 反算式驗證
    it('width 10 @MDW7 = 70px', () => {
        // Trunc(((256*10 + Trunc(128/7)) / 256) * 7) = Trunc((2578/256)*7) = Trunc(70.49) = 70
        expect(columnWidthToPixels(10)).toBe(70);
    });
    it('width 8.43（Excel 預設）@MDW7 = 59px', () => {
        expect(columnWidthToPixels(8.43)).toBe(59);
    });
    it('回傳整數 pixel', () => {
        expect(Number.isInteger(columnWidthToPixels(12.5))).toBe(true);
    });
    it('pixelsToColumnWidth 為近似反函式', () => {
        const px = columnWidthToPixels(10);
        const back = pixelsToColumnWidth(px);
        expect(back).toBeGreaterThan(8);
        expect(back).toBeLessThan(11);
    });
});
