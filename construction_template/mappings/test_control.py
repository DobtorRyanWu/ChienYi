# -*- coding: utf-8 -*-
"""材料設備檢（試）驗管制總表 —— docx 對照表（專案層級，分頁彙總）。

樣板語法同送審管制（`FOR item IN $page`，page 本身是清單）。
樣板由 tools/gen_doc_templates/build_test_control.py 從工程會空白表產生，
改欄位對應時兩邊要一起改。

2026-08-12 換成工程會新版格式（材料設備檢（試）驗管制總表（修正版））：
  * 「進場日期」拆成預定／實際 → 新增 token expectedInSiteDate
  * 「契約數量」欄被工程會拿掉 → payItem.quantity 保留在 context 但樣板不再引用
    （模型欄位 supervision.test.record.contract_qty 仍在，後台照常顯示）
  * 「項次」改印階層編號 A-B-C（舊版印記錄編號 TR-YYYYMM-NNNN，與欄位標題不符）
  * 「規定抽樣頻率」同一檢試驗項目跨列合併成一格（見 POSTPROCESS）
  * 「規定抽樣頻率」改印 standard.frequency（舊版誤印 standard.norm＝規範之要求）
  * 「檢(試)驗及會同人員」補上業主方 owner_member（舊版只印監造＋營造）
  * 舊版用的 `+++IF $item.standard+++ … +++END-IF+++` 不再使用（standard 一律給字串）

token → supervision.test.record：
    no（階層編號）/ payItem.fullItemNo / payItem.description /
    expectedInSiteDate / inSiteDate / inSiteQuantity / inSiteSumQuantity /
    sampleDate / sampleQuantity / sampleSumQuantity /
    standard.frequency / result / member / note / archiveNumber
"""

import io
from datetime import date

from ..utils import docx_render, record_filter
from ..utils.formatters import roc_date, selection_label

MODEL = 'project.project'
MODE = 'docx'

# --- 樣板的表格結構（build_test_control.py 產生，改樣板時這三個常數要跟著改）---
HEADER_ROWS = 4        # 工程資訊 2 列 + 兩層表頭 2 列
ROWS_PER_ITEM = 2      # 一筆資料佔 2 個實體列
FREQ_COL = 5           # 0-based 欄序：規定抽樣頻率

# 批次下載中心可用 context 限定期間；本表以「實際進場日期」為準（與既有 order 一致）
DATE_FIELD = 'in_site_date'
DATE_LABEL = '實際進場日期'


def WARNINGS(project):
    """日期空白的檢試驗記錄一律列入，但要讓人知道有哪幾筆"""
    return record_filter.project_warning(
        project, source_model(project), DATE_FIELD, DATE_LABEL)

# 切頁改成「依內容高度估算」，不是固定筆數。
#
# 為什麼不能固定筆數：「規定抽樣頻率」欄的文字長度差很多（本庫實測中位數 55 字、
# 最長 209 字），而且同一檢試驗項目會跨列合併只印一次。固定 10 筆/頁時實測 94 筆
# 會印成 106 頁（每個邏輯頁要 3 張實體紙）；固定 3 筆/頁雖然 1:1，但遇到「一個項目
# 底下十幾筆進場記錄」的真實案件又太浪費紙。
#
# 估法：把版面高度換算成「9pt 文字的行數」，每頁塞到 LINES_PER_PAGE 為止。
# 一組（同一檢試驗項目）的高度 = max(組內各筆列高總和, 該組頻率文字的行數)，
# 因為頻率是合併儲存格、高度由整組分攤。
# 校準值：示範工程 94 筆實測 25 邏輯頁 / 27 實體頁（每頁 3～4 筆，與工程會空白表
# 一頁 4 組資料列一致）。動了樣板欄寬／字級／邊界就要重新校準。
LINES_PER_PAGE = 13
MIN_LINES_PER_ITEM = 2     # 一筆資料佔上下兩列，至少 2 行
CHARS_PER_LINE_FREQ = 30   # 規定抽樣頻率欄 ≈9.8cm，9pt 中文一行約 30 字
CHARS_PER_LINE_NAME = 10   # 材料/設備名稱欄 ≈3.4cm

MAX_ROWS_PER_PAGE = 12     # 保險上限：估算失準時也不會把一頁塞爆


def source_model(project):
    """資料來源模型——批次下載中心用它算「符合條件的記錄數」"""
    return 'supervision.test.record'


def _qty(value):
    if not value:
        return ''
    return ('%g' % value) if isinstance(value, float) else str(value)


def _std_key(rec):
    """檢試驗項目的排序鍵。A 段編號依此排（不是依日期）。"""
    std = rec.standard_id
    return (std.sequence if std else 9999, std.id if std else 0)


def _date_key(rec):
    """同一材料內的排序鍵：實際進場日期；沒填的排最後。"""
    return (rec.in_site_date or date.max, rec.id)


def _ordered_items(records):
    """回傳 [(記錄, 項次字串, 檢試驗項目鍵), ...]，順序即報表列出順序。

    項次是 A-B-C 階層編號（對照既有案件的既有管制表，例如 1-1-1、2-2-8）：
        A＝檢試驗項目序（依項目自己的 sequence，不是日期——舊表也是這樣排）
        B＝該項目底下第幾種材料/設備（依該材料最早的實際進場日期）
        C＝該材料的第幾筆進場記錄（依實際進場日期）
    列出順序也跟著 A→B→C，否則「規定抽樣頻率」跨列合併會被打散。
    """
    std_groups = {}
    for rec in records:
        std_groups.setdefault(_std_key(rec), []).append(rec)

    out = []
    for a, (skey, recs) in enumerate(sorted(std_groups.items()), 1):
        task_groups = {}
        for rec in recs:
            task_groups.setdefault(rec.task_id.id or 0, []).append(rec)
        ordered_tasks = sorted(task_groups.items(),
                               key=lambda kv: min(_date_key(r) for r in kv[1]))
        for b, (_tid, trecs) in enumerate(ordered_tasks, 1):
            for c, rec in enumerate(sorted(trecs, key=_date_key), 1):
                out.append((rec, '%d-%d-%d' % (a, b, c), skey))
    return out


def _item_no(rec):
    """契約詳細表項次。

    以 supervision.test.record.task_item_no 為準——那是後台表單「基本資訊」區
    顯示的同一個欄位，兩邊共用同一份取值邏輯（item_no_path → full_item_no →
    item_no），才不會表單顯示一種、套印出來另一種。
    construction_template 不 depends construction_test，所以欄位不在時退回自己算。
    """
    if 'task_item_no' in rec._fields:
        return rec.task_item_no or ''
    task = rec.task_id
    if not task:
        return ''
    for fname in ('item_no_path', 'full_item_no', 'item_no'):
        if fname in task._fields and task[fname]:
            return task[fname]
    return ''


def _lines(text, chars_per_line):
    if not text:
        return 0
    return max(1, -(-len(text) // chars_per_line))   # 無條件進位


def _item_lines(rec):
    """一筆記錄佔幾行。

    撐高的是第 2 欄：上列印契約詳細表項次、下列印材料/設備名稱，兩列各自換行，
    所以要分開算再相加（實測這一欄就是列高的主因）。
    """
    task = rec.task_id
    name = (task.name if task else '') or (task.display_name if task else '') or ''
    return max(MIN_LINES_PER_ITEM,
               _lines(_item_no(rec), CHARS_PER_LINE_NAME)
               + _lines(name, CHARS_PER_LINE_NAME))


def _freq_lines(rec):
    std = rec.standard_id
    text = (std.standard if std and 'standard' in std._fields else '') or ''
    return _lines(text, CHARS_PER_LINE_FREQ)


def _page_height(page):
    """一頁的估算高度（行）。同一檢試驗項目是合併儲存格，高度由整組分攤：
    該組高度 = max(組內各筆列高總和, 頻率文字行數)。"""
    total, group_items, group_freq, cur_key = 0, 0, 0, None
    for rec, _no, skey in page:
        if skey != cur_key:
            total += max(group_items, group_freq)
            cur_key, group_items, group_freq = skey, 0, _freq_lines(rec)
        group_items += _item_lines(rec)
    return total + max(group_items, group_freq)


def _paginate(ordered):
    """依估算高度切頁；回傳 [[(rec, no, skey), ...], ...]。"""
    pages, cur = [], []
    for entry in ordered:
        candidate = cur + [entry]
        if cur and (len(candidate) > MAX_ROWS_PER_PAGE
                    or _page_height(candidate) > LINES_PER_PAGE):
            pages.append(cur)
            cur = [entry]
        else:
            cur = candidate
    if cur:
        pages.append(cur)
    return pages or [[]]


def _item(rec, seq):
    """seq：表格「項次」欄的階層編號字串，由 _ordered_items() 產生。"""
    task = rec.task_id
    standard = rec.standard_id
    # 檢(試)驗及會同人員＝業主方（Char 手填）＋監造方＋營造方，空值不參與 join
    members = [rec.owner_member or ''] + (
        rec.supervision_member_ids | rec.contractor_member_ids).mapped('display_name')
    return {
        # 工程會表格的「項次」是階層編號；記錄編號 rec.name 不印（2026-08-12 起）
        'no': seq,
        # payItem 對應契約工項；欄位一律給字串不給 None。
        # ⚠️ 樣板實際用的是 ${item.payItem.description}（2026-08-06 逐一比對 token
        # 清單發現），先前只給 fullItemNo，那一欄一直印空白。
        'payItem': {
            'description': task.name or task.display_name or '',
            # 契約詳細表項次＝契約工項的項次路徑（如「壹.一.1.8」，對照既有案件的
            # 「壹、一、1.8」）。
            # ⚠️ 舊寫法是 `task.code if 'code' in task._fields else ''`——但
            # project.task **根本沒有 code 這個欄位**，所以永遠 fallback 成
            # task.display_name，這一欄一直印成材料名稱、與上下兩列重複
            # （2026-08-12 使用者比對實物發現）。
            'fullItemNo': _item_no(rec),
            # 工程會新版把「契約數量」欄拿掉了，樣板不再引用；保留供其他樣板／日後復原用
            'quantity': _qty(getattr(task, 'planned_qty', False) or False),
        },
        'member': '、'.join(m for m in members if m),
        'standard': {
            # frequency＝supervision.test.standard.standard（標籤「頻率及下限」，
            # 在檢試驗記錄表單上顯示為「規定抽樣頻率」）。舊樣板誤把 norm（規範之
            # 要求）印在「規定抽樣頻率」欄，2026-08-12 修正。
            'frequency': (standard.standard if standard and 'standard' in standard._fields else '') or '',
            'norm': (standard.norm if standard and 'norm' in standard._fields else '') or '',
            'name': standard.display_name if standard else '',
        },
        'expectedInSiteDate': roc_date(rec.expected_in_site_date),
        'inSiteDate': roc_date(rec.in_site_date),
        'sampleDate': roc_date(rec.sample_date),
        'inSiteQuantity': _qty(rec.in_site_quantity),
        'inSiteSumQuantity': _qty(rec.in_site_sum_quantity),
        'sampleQuantity': _qty(rec.sample_quantity),
        'sampleSumQuantity': _qty(rec.sample_sum_quantity),
        # 印中文標籤而不是 Selection 的值（pass/fail/pending）
        'result': selection_label(rec.result, rec, 'result'),
        'resultDate': roc_date(rec.result_date),
        'archiveNumber': rec.archive_number or '',
        'note': rec.note or '',
    }


def build_context(project):
    records = project.env['supervision.test.record'].search(
        [('project_id', '=', project.id)]
        + record_filter.date_domain(project.env, DATE_FIELD))
    # 排序與項次編號都由 _ordered_items 決定（檢試驗項目 → 材料 → 進場日期）
    ordered = _ordered_items(records)
    raw_pages = _paginate(ordered)
    pages = [[_item(rec, no) for rec, no, _ in page] for page in raw_pages]

    # 每頁每一筆「與同頁前一筆是否同一檢試驗項目」——POSTPROCESS 據此合併頻率欄。
    # 每頁的第一筆一律 False：合併不能跨表格（每頁一張表）。
    merge = [[j > 0 and page[j][2] == page[j - 1][2] for j in range(len(page))]
             for page in raw_pages]

    return {
        '_merge': merge,          # 樣板不會用到，是給 POSTPROCESS 的旁通資料
        'projectName': project.name or '',
        'projectConstructionNo': project.contract_no or '',
        'supervision': project.management_company_name or '',
        'contractor': '、'.join(project.contractor_partner_ids.mapped('name')),
        'totalPage': len(pages),
        'pages': pages,
    }


def _merge_freq_cell_up(tc):
    """把這格的「規定抽樣頻率」併入上一列：vMerge 改成延續，內容清空。"""
    from docx.oxml.ns import qn
    pr = tc.find(qn('w:tcPr'))
    if pr is None:
        return
    vm = pr.find(qn('w:vMerge'))
    if vm is None:
        vm = pr.makeelement(qn('w:vMerge'), {})
        pr.append(vm)
    # 沒有 w:val 就是「延續上一列」；w:val="restart" 才是開新的合併區塊
    if qn('w:val') in vm.attrib:
        del vm.attrib[qn('w:val')]
    paras = tc.findall(qn('w:p'))
    for p in paras[1:]:
        tc.remove(p)
    if paras:
        for r in paras[0].findall(qn('w:r')):
            paras[0].remove(r)


def POSTPROCESS(content, context):
    """同一檢試驗項目的「規定抽樣頻率」欄跨列合併成一格。

    既有案件的管制表就是這樣印的（同一種材料的頻率規定只寫一次，跨越它底下
    所有進場記錄）；docxtpl 的 {%tr%} 只會原樣複製列，做不出這件事，所以改在
    產出的 docx 上動 vMerge。

    每頁一張表，表格結構固定為：工程資訊 2 列 + 表頭 2 列 + 每筆 2 列 + 簽核 1 列，
    所以第 j 筆的上列 = rows[HEADER_ROWS + j * ROWS_PER_ITEM]。
    """
    merge = context.get('_merge') or []
    if not any(any(page) for page in merge):
        return content
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(io.BytesIO(content))
    for table, flags in zip(doc.tables, merge):
        rows = table._tbl.findall(qn('w:tr'))
        for j, is_continuation in enumerate(flags):
            if not is_continuation:
                continue
            idx = HEADER_ROWS + j * ROWS_PER_ITEM
            if idx >= len(rows):
                break
            cells = rows[idx].findall(qn('w:tc'))
            if len(cells) > FREQ_COL:
                _merge_freq_cell_up(cells[FREQ_COL])
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def FILENAME(project):
    return '材料設備檢試驗管制總表_%s.docx' % (project.name or project.id)
