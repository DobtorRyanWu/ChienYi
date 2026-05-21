/**
 * CommentsParser — 解析 word/comments.xml（OOXML §17.13.4、Phase 5.5 註解）
 *
 * Sprint 176（capture-only）：
 *   Word 註解（「校閱 → 新增註解」）儲存於 comments.xml；document.xml 以
 *   `<w:commentRangeStart/End w:id>` 標記範圍、`<w:commentReference w:id>` 為錨點。
 *
 * comments.xml 結構：
 *   <w:comments>
 *     <w:comment w:id="0" w:author="Alice" w:date="2024-..." w:initials="A">
 *       <w:p>...註解內容...</w:p>
 *     </w:comment>
 *   </w:comments>
 *
 * 重用 DocumentParser.parseBodyContent 解析註解內部段落 + 表格（同 FootnotesParser /
 * HeaderFooterParser 模式）。
 *
 * Scope-down（紀律 #18）：capture comments.xml 內容；document.xml 的
 * commentRangeStart/End/Reference 錨點 wire-up + 右側 panel render 留後續 sprint。
 *
 * 防禦：undefined / 空 / XML 解析失敗 → 回空 Map（不阻塞 OoxmlParser）。
 */

import type { BlockNode, CommentContent } from '../ast/types';
import { DocumentParser } from '../document/DocumentParser';

export class CommentsParser {
  private documentParser: DocumentParser;

  /**
   * @param documentParser 可選；OoxmlParser orchestrator 注入共用 instance 以重用
   *                       TableParser 等狀態。不傳則自建一個。
   */
  constructor(documentParser?: DocumentParser) {
    this.documentParser = documentParser ?? new DocumentParser();
  }

  /**
   * 解析 word/comments.xml 為 Map<id, CommentContent>。
   *
   * @param xml comments.xml 完整字串；undefined / 空 → 回空 Map
   * @returns Map<id, CommentContent>；XML 無法解析時回空 Map（不 throw）
   */
  parse(xml: string | undefined): Map<number, CommentContent> {
    const out = new Map<number, CommentContent>();
    if (!xml) return out;

    let doc: Document;
    try {
      doc = parseXml(xml);
    } catch {
      return out;
    }
    const root = doc.documentElement;
    if (!root) return out;

    const cs = root.childNodes;
    for (let i = 0; i < cs.length; i++) {
      const n = cs[i];
      if (n.nodeType !== 1) continue;
      const el = n as Element;
      if (el.tagName !== 'w:comment') continue;

      const idRaw = el.getAttribute('w:id');
      if (idRaw === null) continue;
      const id = parseInt(idRaw, 10);
      if (!Number.isFinite(id)) continue;

      // 內部結構等同 <w:body> — 重用 DocumentParser
      let content: BlockNode[] = [];
      try {
        content = this.documentParser.parseBodyContent(el);
      } catch {
        content = [];
      }

      const entry: CommentContent = { id, content };
      const author = el.getAttribute('w:author');
      if (author) entry.author = author;
      const date = el.getAttribute('w:date');
      if (date) entry.date = date;
      const initials = el.getAttribute('w:initials');
      if (initials) entry.initials = initials;
      out.set(id, entry);
    }

    return out;
  }
}

function parseXml(xml: string): Document {
  if (typeof DOMParser === 'undefined') {
    throw new Error(
      'CommentsParser: DOMParser not available — Node tests must use vitest setup with @xmldom/xmldom',
    );
  }
  const doc = new DOMParser().parseFromString(xml, 'application/xml');
  const errors = doc.getElementsByTagName('parsererror');
  if (errors.length > 0) {
    throw new Error(`CommentsParser: XML parse error — ${errors[0].textContent}`);
  }
  return doc;
}
