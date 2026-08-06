# -*- coding: utf-8 -*-
"""xlsx 工作表複製（分頁列印用）。

EAGLE 原系統對會超過一頁的表一律用 `template.copySheet('第N頁','第N+1頁')`
——每頁填固定列數、不足補空白列，工作表命名「第1頁」「第2頁」…。
（來源：TKU source map 還原的 models/dailyRecord.js、inspection.js、project.js）

我們的樣板沿用同樣的命名（daily_log_c2.xlsx 的工作表就叫「第1頁」），
所以要能複製工作表才做得出一樣的版面。

複製一張工作表要動四個地方：
    xl/worksheets/sheetN.xml            新的工作表本體
    xl/worksheets/_rels/sheetN.xml.rels 沿用第一張的（指向 printerSettings）
    xl/workbook.xml                     <sheets> 加一個 <sheet name r:id>
    xl/_rels/workbook.xml.rels          加一條 worksheet Relationship
    [Content_Types].xml                 加一個 Override

新 entry 由 zip_patch.patch(..., additions=…) 附加在最後，
既有 entry 的位元組完全不受影響。
"""

import re

WORKSHEET_TYPE = ('http://schemas.openxmlformats.org/officeDocument/2006/'
                  'relationships/worksheet')
WORKSHEET_CONTENT_TYPE = ('application/vnd.openxmlformats-officedocument'
                          '.spreadsheetml.worksheet+xml')

SHEETS_RE = re.compile(r'(<sheets>)(.*?)(</sheets>)', re.DOTALL)
SHEET_RE = re.compile(r'<sheet\s[^>]*?name="([^"]*)"[^>]*?sheetId="(\d+)"[^>]*?'
                      r'r:id="(rId\d+)"[^>]*/>')
RELS_END_RE = re.compile(r'</Relationships>')
CT_END_RE = re.compile(r'</Types>')
RID_RE = re.compile(r'Id="rId(\d+)"')


def first_sheet(workbook_xml):
    """回傳第一張工作表的 (名稱, sheetId, rId)"""
    m = SHEET_RE.search(workbook_xml)
    if not m:
        raise ValueError('workbook.xml 找不到任何 <sheet>')
    return m.group(1), int(m.group(2)), m.group(3)


def sheet_target(workbook_rels_xml, rid):
    """由 rId 找出該工作表的 Target（例：worksheets/sheet1.xml）"""
    m = re.search(r'<Relationship[^>]*Id="%s"[^>]*Target="([^"]+)"' % rid,
                  workbook_rels_xml)
    if not m:
        m = re.search(r'<Relationship[^>]*Target="([^"]+)"[^>]*Id="%s"' % rid,
                      workbook_rels_xml)
    if not m:
        raise ValueError('workbook.xml.rels 找不到 %s' % rid)
    return m.group(1)


def build_pages(base_parts, page_sheets):
    """產生「多分頁」所需的 zip 更新內容。

    :param base_parts: {entry 名稱: 原始 XML str}，至少要有
                       xl/workbook.xml、xl/_rels/workbook.xml.rels、
                       [Content_Types].xml，以及第一張工作表的 rels（若有）
    :param page_sheets: 各頁的 worksheet XML（str）陣列，第 0 個會取代原本
                        那張工作表，其餘的變成新增的工作表
    :return: (updates, additions) —— 直接餵給 zip_patch.patch()
    """
    workbook = base_parts['xl/workbook.xml']
    workbook_rels = base_parts['xl/_rels/workbook.xml.rels']
    content_types = base_parts['[Content_Types].xml']

    name0, sheet_id0, rid0 = first_sheet(workbook)
    target0 = sheet_target(workbook_rels, rid0).lstrip('/')
    entry0 = 'xl/' + target0 if not target0.startswith('xl/') else target0
    base_rels_entry = entry0.replace('xl/worksheets/',
                                     'xl/worksheets/_rels/') + '.rels'
    base_rels = base_parts.get(base_rels_entry)

    updates = {entry0: page_sheets[0].encode('utf-8')}
    additions = {}
    if len(page_sheets) == 1:
        return updates, additions

    # 續用的最大編號，避免與既有 rId / sheetId / 檔名相撞
    next_rid = max(int(n) for n in RID_RE.findall(workbook_rels)) + 1
    next_sheet_id = max(int(m.group(2)) for m in SHEET_RE.finditer(workbook)) + 1
    used = {int(m.group(1)) for m in
            re.finditer(r'xl/worksheets/sheet(\d+)\.xml', ' '.join(base_parts))}
    next_file_no = max(used | {1}) + 1

    new_sheet_tags, new_rel_tags, new_overrides = [], [], []
    for index, sheet_xml in enumerate(page_sheets[1:], start=2):
        entry = 'xl/worksheets/sheet%s.xml' % next_file_no
        additions[entry] = sheet_xml.encode('utf-8')
        if base_rels:
            additions[entry.replace('xl/worksheets/', 'xl/worksheets/_rels/')
                      + '.rels'] = base_rels.encode('utf-8')

        rid = 'rId%s' % next_rid
        new_sheet_tags.append('<sheet name="第%s頁" sheetId="%s" r:id="%s"/>'
                              % (index, next_sheet_id, rid))
        new_rel_tags.append('<Relationship Id="%s" Type="%s" Target="worksheets/sheet%s.xml"/>'
                            % (rid, WORKSHEET_TYPE, next_file_no))
        new_overrides.append('<Override PartName="/%s" ContentType="%s"/>'
                             % (entry, WORKSHEET_CONTENT_TYPE))
        next_rid += 1
        next_sheet_id += 1
        next_file_no += 1

    # 第一張的名稱也要正規化成「第1頁」，否則多頁時命名不一致
    workbook = SHEETS_RE.sub(
        lambda m: m.group(1) + m.group(2) + ''.join(new_sheet_tags) + m.group(3),
        workbook, count=1)
    if name0 != '第1頁':
        workbook = workbook.replace('name="%s"' % name0, 'name="第1頁"', 1)

    workbook_rels = RELS_END_RE.sub(''.join(new_rel_tags) + '</Relationships>',
                                    workbook_rels, count=1)
    content_types = CT_END_RE.sub(''.join(new_overrides) + '</Types>',
                                  content_types, count=1)

    updates['xl/workbook.xml'] = workbook.encode('utf-8')
    updates['xl/_rels/workbook.xml.rels'] = workbook_rels.encode('utf-8')
    updates['[Content_Types].xml'] = content_types.encode('utf-8')
    return updates, additions
