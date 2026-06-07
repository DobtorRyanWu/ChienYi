// Vitest 環境初始化
// 沿用 dobtor_doc_editor 模式：注入 @xmldom/xmldom 的 DOMParser（OOXML prefix 命名空間需要）

import { DOMParser, XMLSerializer } from '@xmldom/xmldom';

// @ts-expect-error — Node 環境補 DOMParser
globalThis.DOMParser = DOMParser as unknown as typeof globalThis.DOMParser;
// @ts-expect-error — Node 環境補 XMLSerializer
globalThis.XMLSerializer = XMLSerializer as unknown as typeof globalThis.XMLSerializer;
