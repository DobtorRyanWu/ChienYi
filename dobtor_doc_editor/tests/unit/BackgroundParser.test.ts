/**
 * BackgroundParser.test.ts — Sprint 171（Phase 5.6 浮水印 + 背景）
 *
 * 涵蓋：
 *   - `<w:background w:color>` → color（6-hex、大寫正規化）
 *   - `w:color="auto"` / 非法 hex → 不掛 color
 *   - `w:themeColor` → themeColor（capture raw）
 *   - 無 `<w:background>` / 空 / 解析失敗 → undefined
 */

import { describe, expect, it } from 'vitest';
import { BackgroundParser } from '../../static/src/core/ooxml/background/BackgroundParser';

const NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"';

/** 把 `<w:background>` 片段包進最小 document.xml。 */
function wrapDoc(backgroundEl: string): string {
  return `<?xml version="1.0" encoding="UTF-8"?>\n<w:document ${NS}>${backgroundEl}<w:body/></w:document>`;
}

describe('BackgroundParser — w:color', () => {
  it('w:color 6-hex → color', () => {
    const r = new BackgroundParser().parse(wrapDoc('<w:background w:color="FFFF00"/>'));
    expect(r).toEqual({ color: 'FFFF00' });
  });

  it('小寫 hex → 正規化為大寫', () => {
    const r = new BackgroundParser().parse(wrapDoc('<w:background w:color="abcdef"/>'));
    expect(r?.color).toBe('ABCDEF');
  });

  it('w:color="auto" → 不掛 color、回 undefined', () => {
    const r = new BackgroundParser().parse(wrapDoc('<w:background w:color="auto"/>'));
    expect(r).toBeUndefined();
  });

  it('非法 hex（長度不符）→ 不掛 color', () => {
    const r = new BackgroundParser().parse(wrapDoc('<w:background w:color="FFF"/>'));
    expect(r).toBeUndefined();
  });

  it('非法 hex（非 16 進位字元）→ 不掛 color', () => {
    const r = new BackgroundParser().parse(wrapDoc('<w:background w:color="GGGGGG"/>'));
    expect(r).toBeUndefined();
  });
});

describe('BackgroundParser — w:themeColor', () => {
  it('w:themeColor → themeColor（capture raw）', () => {
    const r = new BackgroundParser().parse(wrapDoc('<w:background w:themeColor="accent1"/>'));
    expect(r).toEqual({ themeColor: 'accent1' });
  });

  it('color + themeColor 同時存在 → 兩者皆掛', () => {
    const r = new BackgroundParser().parse(
      wrapDoc('<w:background w:color="00B0F0" w:themeColor="accent5"/>'),
    );
    expect(r).toEqual({ color: '00B0F0', themeColor: 'accent5' });
  });
});

describe('BackgroundParser — 防禦邊界', () => {
  it('無 <w:background> 元素 → undefined', () => {
    const r = new BackgroundParser().parse(`<w:document ${NS}><w:body/></w:document>`);
    expect(r).toBeUndefined();
  });

  it('undefined 輸入 → undefined', () => {
    expect(new BackgroundParser().parse(undefined)).toBeUndefined();
  });

  it('空字串 → undefined', () => {
    expect(new BackgroundParser().parse('')).toBeUndefined();
  });

  it('XML 解析失敗 → undefined（不 throw）', () => {
    expect(new BackgroundParser().parse('<w:document <<<broken')).toBeUndefined();
  });

  it('<w:background> 無任何有效屬性 → undefined（紀律 #21 不掛空 key）', () => {
    const r = new BackgroundParser().parse(wrapDoc('<w:background/>'));
    expect(r).toBeUndefined();
  });
});
