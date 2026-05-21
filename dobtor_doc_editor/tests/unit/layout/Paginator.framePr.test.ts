/**
 * Sprint 169 — Paginator `<w:framePr>` 浮動段落框 wire-up（opt-in）
 *
 * 驗證 layoutDocument 端到端：
 *   - 未傳 enableFramePr → framePr 段落走一般 layParagraph、與無 framePr byte-identical
 *   - 傳 enableFramePr → 框段落抽出正常流、依 vAnchor + y 偏移定位、保留垂直空間
 *   - 連續同 framePr 段落合併為一 frame
 */

import { describe, expect, it } from 'vitest';
import { layoutDocument } from '../../../static/src/core/layout/Paginator';
import type {
  SectionNode,
  ParagraphNode,
  ParagraphProps,
  RunNode,
} from '../../../static/src/core/ooxml/ast/types';
import type { LinePageEntry } from '../../../static/src/core/layout/types';

const A4 = { width: 595, height: 842, orientation: 'portrait' as const };
const MARGINS = { top: 72, bottom: 72, left: 72, right: 72, header: 36, footer: 36 };
type FramePr = NonNullable<ParagraphProps['framePr']>;

function makeSection(body: SectionNode['body']): SectionNode {
  return {
    type: 'section', page: A4, margins: MARGINS,
    headerRefs: {}, footerRefs: {}, titlePage: false, evenAndOddHeaders: false, body,
  };
}

function para(text: string, framePr?: FramePr): ParagraphNode {
  const run: RunNode = { type: 'run', text, props: { fontSize: 12 } };
  const props: ParagraphProps = {};
  if (framePr) props.framePr = framePr;
  return { type: 'paragraph', props, runs: [run] };
}

function lineEntries(section: SectionNode, enableFramePr: boolean): LinePageEntry[] {
  const doc = layoutDocument([section], enableFramePr ? { enableFramePr: true } : {});
  const out: LinePageEntry[] = [];
  for (const page of doc.pages) {
    for (const e of page.entries) {
      if (e.kind === 'line') out.push(e);
    }
  }
  return out;
}

// vAnchor=text、y 偏移 10pt（= 200 twip）
const FP: FramePr = { wrap: 'around', vAnchor: 'text', hAnchor: 'margin', y: 10 };

describe('Paginator framePr — enableFramePr 關（預設、Strategy C）', () => {
  it('framePr 段落與無 framePr 段落 byte-identical（off → framePr 被忽略）', () => {
    const framed = lineEntries(makeSection([para('標題', FP), para('內文')]), false);
    const plain = lineEntries(makeSection([para('標題'), para('內文')]), false);
    expect(framed.length).toBe(plain.length);
    for (let i = 0; i < framed.length; i++) {
      expect(framed[i].x).toBe(plain[i].x);
      expect(framed[i].y).toBe(plain[i].y);
      expect(framed[i].line.items).toStrictEqual(plain[i].line.items);
    }
  });
});

describe('Paginator framePr — enableFramePr 開', () => {
  it('框段落依 vAnchor=text + y 偏移下移', () => {
    const off = lineEntries(makeSection([para('標題', FP)]), false);
    const on = lineEntries(makeSection([para('標題', FP)]), true);
    expect(on.length).toBe(1);
    // off：框段落走一般流、y = marginTop + 0
    expect(off[0].y).toBe(MARGINS.top);
    // on：框頂 y = marginTop + yOffset(10)
    expect(on[0].y).toBeCloseTo(MARGINS.top + 10, 6);
  });

  it('框後內文落在框下方（保留垂直空間、不重疊）', () => {
    const on = lineEntries(makeSection([para('標題', FP), para('內文')]), true);
    expect(on.length).toBe(2);
    const title = on.find((e) => e.line.items.length > 0 && e.height > 0 && e === on[0])!;
    const body = on[1];
    // 內文 y 必須在框標題行的下緣之下
    expect(body.y).toBeGreaterThanOrEqual(title.y + title.height);
  });

  it('連續同 framePr 段落合併為一 frame、皆被排版', () => {
    const on = lineEntries(makeSection([para('標題一', FP), para('標題二', { ...FP }), para('內文')]), true);
    // 3 段各 1 行
    expect(on.length).toBe(3);
    const t1 = on[0];
    const t2 = on[1];
    // 框內第二段緊接第一段下方
    expect(t2.y).toBeGreaterThan(t1.y);
    expect(t2.y).toBeCloseTo(t1.y + t1.height, 6);
  });

  it('不同 framePr 不合併（各自成框）', () => {
    const FP2: FramePr = { wrap: 'around', vAnchor: 'text', hAnchor: 'margin', y: 30 };
    const on = lineEntries(makeSection([para('框A', FP), para('框B', FP2)]), true);
    expect(on.length).toBe(2);
    // 框B 的 y 偏移更大、且在框A 之後（框A 保留空間後 currentY 再加 FP2.y）
    expect(on[1].y).toBeGreaterThan(on[0].y);
  });

  it('框寬 auto 時 jc=center 在欄寬內置中', () => {
    const centered = para('置中標題', FP);
    centered.props.alignment = 'center';
    const on = lineEntries(makeSection([centered]), true);
    expect(on.length).toBe(1);
    // 置中 → x 起點 > marginLeft（行寬 < 欄寬時 alignShift > 0）
    expect(on[0].x).toBeGreaterThan(MARGINS.left);
  });
});
