// Sprint 0 smoke test — 確認 build pipeline 與 vitest 跑得起來

import { describe, it, expect } from 'vitest';
import { SPRINT, TARGET_FIDELITY, importXlsxToHtmlPreview } from '../../static/src/core/ooxmlspreadsheet/index';

describe('Sprint 0 smoke', () => {
    it('exports baseline constants', () => {
        expect(SPRINT).toBeGreaterThanOrEqual(0);
        expect(TARGET_FIDELITY).toContain('95%');
    });

    it('importXlsxToHtmlPreview 對外入口存在', () => {
        expect(typeof importXlsxToHtmlPreview).toBe('function');
    });
});
