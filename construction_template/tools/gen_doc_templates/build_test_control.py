# -*- coding: utf-8 -*-
"""由工程會「材料設備檢（試）驗管制總表（修正版）」空白表產生系統用的 test_control.docx。

背景（2026-08-12）
------------------
實際測試人員回報「目前系統的檢試驗管制表與工程會新版格式要求不符」，並提供工程會
現行要求的空白表。那份檔案是**純空白表格、沒有任何佔位符**，直接放進
data/templates_blank/ 只會印出一張空表，所以要用這支腳本把它加工成樣板：

1. 表格最上方補 2 列工程資訊（工程名稱／契約編號／監造單位／施工廠商）
   —— 工程會原始表單沒有這兩列，是系統自己要的，否則印出來分不出是哪個案子。
2. 資料列只留 1 組（工程會原檔預填了 4 組空列），前後包 +++FOR item IN $page+++ /
   +++END-FOR item+++，由 docxtpl 的 {%tr%} 依筆數展開。
3. 表格最下方補簽核列（編製／工地主任／工地負責人）。
4. 文件層級包 +++FOR page IN pages+++ … 分頁符 … +++END-FOR page+++。

佔位符語法是 EAGLE 的 +++INS+++／+++FOR+++，套印時由
construction_template/utils/docx_render.py → dobtor_doc_editor 的
_convert_ins_to_jinja() 轉成 docxtpl 的 Jinja2。context 由
construction_template/mappings/test_control.py 的 build_context() 組。

新舊格式差異（對照 mappings/test_control.py）
--------------------------------------------
* 「進場日期」拆成「預定進場日期／實際進場日期」→ 新增 token expectedInSiteDate
* 「契約數量」欄被工程會拿掉 → payItem.quantity 不再印（模型欄位 contract_qty 仍在）
* 「項次」改印流水序號（舊版印的是記錄編號 TR-YYYYMM-NNNN，與欄位標題不符）
* 「規定抽樣頻率」改印 standard.frequency（舊版誤印 standard.norm＝規範之要求）
* 「檢(試)驗及會同人員」改印三方合併（舊版漏了業主方 owner_member）

用法
----
    python build_test_control.py                    # 用預設來源與目的
    python build_test_control.py --src X.docx --dst Y.docx
    python build_test_control.py --no-backup

需要 python-docx。重跑會先把舊的 test_control.docx 備份成
test_control.docx.bak_<YYYYMMDD_HHMMSS>（--no-backup 可關）。
"""

import argparse
import os
import shutil
from copy import deepcopy
from datetime import datetime

from docx import Document
from docx.oxml.ns import qn

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.abspath(os.path.join(HERE, '..', '..'))

DEFAULT_SRC = r'E:\for工作\任泰\舊系統預設樣板檔案\材料設備檢（試）驗管制總表（修正版）.docx'
DEFAULT_DST = os.path.join(MODULE_DIR, 'data', 'templates_blank', 'test_control.docx')

# 工程資訊列：(左半內容, 左半跨欄數, 右半內容, 右半跨欄數)
INFO_ROWS = [
    ('工程名稱：+++INS projectName+++', 6, '契約編號：+++INS projectConstructionNo+++', 4),
    ('監造單位：+++INS supervision+++', 6, '施工廠商：+++INS contractor+++', 4),
]

# 簽核列：(內容, 跨欄數)
SIGN_ROW = [('編製：', 3), ('工地主任：', 3), ('工地負責人：', 4)]

# 資料列佔位符。索引＝欄序（0-based），值為 (上列文字, 下列文字)；
# 下列文字為 None 代表該欄是上下合併的單一儲存格（文字全放上列）。
ITEM_TOKENS = [
    ('+++INS $item.no+++', None),                                     # 1 項次（流水序號）
    ('+++INS $item.payItem.fullItemNo+++',                            # 2 契約詳細表項次
     '+++INS $item.payItem.description+++'),                          #   材料/設備名稱
    ('+++INS $item.expectedInSiteDate+++',                            # 3 預定進場日期
     '+++INS $item.inSiteDate+++'),                                   #   實際進場日期
    ('+++INS $item.inSiteQuantity+++', None),                         # 4 進場數量
    ('+++INS $item.sampleDate+++', '+++INS $item.sampleQuantity+++'),  # 5 抽樣日期/數量
    ('+++INS $item.standard.frequency+++', None),                     # 6 規定抽樣頻率
    ('+++INS $item.inSiteSumQuantity+++',                             # 7 累積進場數量
     '+++INS $item.sampleSumQuantity+++'),                            #   累積抽樣數量
    ('+++INS $item.result+++', None),                                 # 8 檢(試)驗結果
    ('+++INS $item.member+++', None),                                 # 9 檢(試)驗及會同人員
    ('+++INS $item.note+++\n+++INS $item.archiveNumber+++', None),    # 10 備註/(歸檔編號)
]

# 欄寬（tblW 是 5000 pct 制，10 欄相加必須等於 5000）。
# 工程會空白表的原始配法是 [307,706,632,331,564,483,489,526,528,434]——
# 「規定抽樣頻率」只有 483（約 2.5cm）。舊樣板那一欄印的是 standard.norm，
# 而全庫 13 筆檢試驗項目的 norm 都是空的，所以從來沒人發現欄位太窄；
# 2026-08-12 改印真正的頻率文字後（中位數 55 字、最長 209 字），
# 一列就會被撐成一整頁（實測 94 筆會印出 106 頁）。故重新配寬並縮小字級。
COL_WIDTHS = [
    180,   # 1 項次
    620,   # 2 契約詳細表項次／材料設備名稱
    420,   # 3 預定進場日期／實際進場日期
    280,   # 4 進場數量
    420,   # 5 抽樣日期／抽樣數量
    1800,  # 6 規定抽樣頻率（最長的一欄，整份文件的頁數由它決定）
    380,   # 7 累積進場數量／累積抽樣數量
    300,   # 8 檢(試)驗結果
    320,   # 9 檢(試)驗及會同人員
    280,   # 10 備註／(歸檔編號)
]
HEADER_FONT_HALFPT = 20   # 10pt
DATA_FONT_HALFPT = 18     # 9pt
NOTE_FONT_HALFPT = 18     # 9pt——表格下方那 3 條註記，原檔 12pt 會多吃掉半頁
TITLE_FONT_HALFPT = 28    # 14pt
PAGE_MARGIN_TB = 480      # 上下邊界 0.85cm（原 720＝1.27cm）

# 一頁放幾筆不是固定的——mappings/test_control.py 依內容高度估算切頁
# （LINES_PER_PAGE）。這裡只保留「工程會空白表自己是一頁 4 組資料列」這個事實，
# 給改版面時當參考；動了欄寬／字級／邊界就要重新校準那邊的 LINES_PER_PAGE。
BLANK_FORM_ROWS = 4
# 資料列的最小列高（twips）。原檔是 525（0.93cm）＝空白表要留手寫空間用的，
# 但套印是機器填字，10 筆就佔滿 18.5cm 的版面高度、必定跨頁。改成剛好容納
# 一行 9pt 文字，實際列高由內容決定。
DATA_ROW_MIN_HEIGHT = 260

LOOP_START = '+++FOR item IN $page +++'
LOOP_END = '+++END-FOR item+++'
PAGE_START = '+++FOR page IN pages+++'
PAGE_END = '+++END-FOR page+++'


# --------------------------------------------------------------------------- #
# XML 小工具
# --------------------------------------------------------------------------- #
def tcs(tr):
    """該列的 <w:tc> 清單（含 gridSpan／vMerge 的實體儲存格）"""
    return tr.findall(qn('w:tc'))


def tc_width(tc):
    pr = tc.find(qn('w:tcPr'))
    w = pr.find(qn('w:tcW')) if pr is not None else None
    return int(w.get(qn('w:w'))) if w is not None else 0


def set_tc_width(tc, value):
    pr = tc.find(qn('w:tcPr'))
    w = pr.find(qn('w:tcW'))
    if w is None:
        w = pr.makeelement(qn('w:tcW'), {})
        pr.insert(0, w)
    w.set(qn('w:w'), str(value))
    w.set(qn('w:type'), 'pct')


def set_grid_span(tc, span):
    """設定 gridSpan；tcPr 內元素有順序要求，gridSpan 緊接在 tcW 之後。"""
    pr = tc.find(qn('w:tcPr'))
    old = pr.find(qn('w:gridSpan'))
    if old is not None:
        pr.remove(old)
    if span <= 1:
        return
    gs = pr.makeelement(qn('w:gridSpan'), {})
    gs.set(qn('w:val'), str(span))
    w = pr.find(qn('w:tcW'))
    if w is not None:
        w.addnext(gs)
    else:
        pr.insert(0, gs)


def drop_vmerge(tc):
    pr = tc.find(qn('w:tcPr'))
    if pr is None:
        return
    for vm in pr.findall(qn('w:vMerge')):
        pr.remove(vm)


def sample_rpr(tc):
    """取儲存格內第一個 run 的 rPr（字型），沒有就回 None。"""
    for p in tc.findall(qn('w:p')):
        for r in p.findall(qn('w:r')):
            rpr = r.find(qn('w:rPr'))
            if rpr is not None:
                return deepcopy(rpr)
    return None


def set_text(tc, text, rpr=None, align=None):
    """把儲存格內容換成 text（\n 分段），沿用原段落格式。

    空字串代表清空（保留一個空段落，Word 規定 tc 至少要有一個 w:p）。
    """
    ps = tc.findall(qn('w:p'))
    base = ps[0]
    for p in ps[1:]:
        tc.remove(p)
    if rpr is None:
        rpr = sample_rpr(tc)
    for r in base.findall(qn('w:r')):
        base.remove(r)
    if align is not None:
        ppr = base.find(qn('w:pPr'))
        if ppr is None:
            ppr = base.makeelement(qn('w:pPr'), {})
            base.insert(0, ppr)
        jc = ppr.find(qn('w:jc'))
        if jc is None:
            jc = ppr.makeelement(qn('w:jc'), {})
            ppr.append(jc)
        jc.set(qn('w:val'), align)

    def fill(par, line):
        if not line:
            return
        r = par.makeelement(qn('w:r'), {})
        if rpr is not None:
            r.append(deepcopy(rpr))
        t = par.makeelement(qn('w:t'), {})
        t.set(qn('xml:space'), 'preserve')
        t.text = line
        r.append(t)
        par.append(r)

    lines = text.split('\n')
    fill(base, lines[0])
    prev = base
    for line in lines[1:]:
        newp = deepcopy(base)
        for r in newp.findall(qn('w:r')):
            newp.remove(r)
        fill(newp, line)
        prev.addnext(newp)
        prev = newp


def build_row(template_tr, specs, rpr, align='left', height=None):
    """依 specs=[(文字, 跨欄數), ...] 由 template_tr 複製出一列。"""
    tr = deepcopy(template_tr)
    cells = tcs(tr)
    widths = [tc_width(tc) for tc in cells]
    cursor = 0
    for text, span in specs:
        tc = cells[cursor]
        drop_vmerge(tc)
        set_tc_width(tc, sum(widths[cursor:cursor + span]))
        set_grid_span(tc, span)
        set_text(tc, text, rpr=rpr, align=align)
        for extra in cells[cursor + 1:cursor + span]:
            tr.remove(extra)
        cursor += span
    for extra in cells[cursor:]:
        tr.remove(extra)
    if height is not None:
        trpr = tr.find(qn('w:trPr'))
        if trpr is not None:
            h = trpr.find(qn('w:trHeight'))
            if h is not None:
                h.set(qn('w:val'), str(height))
    return tr


def force_fixed_layout(tbl, widths, text_width_dxa):
    """把表格改成固定版面並重寫 tblGrid。

    工程會原檔的 tblPr 只有 tblW(5000 pct) 沒有 tblLayout ＝ 自動調整版面，
    Word／LibreOffice 會**忽略 tcW**、改依內容決定欄寬；於是「規定抽樣頻率」那
    一大段文字會把該欄硬撐開、其他欄被壓扁，重配 tcW 完全不生效。
    """
    pr = tbl.find(qn('w:tblPr'))
    old = pr.find(qn('w:tblLayout'))
    if old is not None:
        pr.remove(old)
    layout = pr.makeelement(qn('w:tblLayout'), {})
    layout.set(qn('w:type'), 'fixed')
    anchor = pr.find(qn('w:tblCellMar'))
    if anchor is not None:
        anchor.addprevious(layout)
    else:
        pr.append(layout)

    grid = tbl.find(qn('w:tblGrid'))
    for col in grid.findall(qn('w:gridCol')):
        grid.remove(col)
    for w in widths:
        col = grid.makeelement(qn('w:gridCol'), {})
        col.set(qn('w:w'), str(int(round(text_width_dxa * w / 5000.0))))
        grid.append(col)


def page_text_width_dxa(doc):
    """版面可用寬度（twips）＝ 紙寬 − 左右邊界"""
    sect = doc.element.body.find(qn('w:sectPr'))
    sz = sect.find(qn('w:pgSz'))
    mar = sect.find(qn('w:pgMar'))
    return (int(sz.get(qn('w:w')))
            - int(mar.get(qn('w:left'))) - int(mar.get(qn('w:right'))))


def apply_widths(tbl, widths):
    """依 COL_WIDTHS 重設每一列的 tcW（跨欄的取區間加總）。"""
    for tr in tbl.findall(qn('w:tr')):
        cursor = 0
        for tc in tcs(tr):
            pr = tc.find(qn('w:tcPr'))
            gs = pr.find(qn('w:gridSpan')) if pr is not None else None
            span = int(gs.get(qn('w:val'))) if gs is not None else 1
            set_tc_width(tc, sum(widths[cursor:cursor + span]))
            cursor += span


def set_font_size(node, half_points):
    """把 node 底下所有 run／段落標記的字級設成 half_points（半點，9pt = 18）。"""
    for r in node.iter(qn('w:r')):
        if r.find(qn('w:rPr')) is None:
            r.insert(0, r.makeelement(qn('w:rPr'), {}))
    for rpr in node.iter(qn('w:rPr')):
        for tag in ('w:sz', 'w:szCs'):
            el = rpr.find(qn(tag))
            if el is None:
                el = rpr.makeelement(qn(tag), {})
                rpr.append(el)
            el.set(qn('w:val'), str(half_points))


def new_paragraph(like, text='', page_break=False):
    """依 like 段落複製出一個新段落（清掉內容），填入 text 或分頁符。"""
    p = deepcopy(like)
    for r in p.findall(qn('w:r')):
        p.remove(r)
    for br in p.findall(qn('w:bookmarkStart')) + p.findall(qn('w:bookmarkEnd')):
        p.remove(br)
    r = p.makeelement(qn('w:r'), {})
    if page_break:
        br = p.makeelement(qn('w:br'), {})
        br.set(qn('w:type'), 'page')
        r.append(br)
    else:
        t = p.makeelement(qn('w:t'), {})
        t.set(qn('xml:space'), 'preserve')
        t.text = text
        r.append(t)
    p.append(r)
    return p


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def build(src, dst, backup=True):
    doc = Document(src)
    table = doc.tables[0]
    tbl = table._tbl
    rows = tbl.findall(qn('w:tr'))
    if len(rows) != 10 or len(tcs(rows[0])) != 10:
        raise SystemExit(
            '來源檔結構與預期不符（預期 10 列 × 10 欄，實得 %d 列 × %d 欄）——'
            '工程會可能又改版了，請重新確認欄位對應後再改這支腳本。'
            % (len(rows), len(tcs(rows[0]))))

    header_top, header_bottom = rows[0], rows[1]
    item_top, item_bottom = rows[2], rows[3]
    # 表頭字型當作全表基準（標楷體）
    base_rpr = sample_rpr(tcs(header_top)[0])

    # --- 1. 資料列：只留第 1 組，其餘 3 組（rows[4:10]）刪掉 ---------------
    for tr in rows[4:]:
        tbl.remove(tr)

    # --- 2. 資料列填入佔位符 ------------------------------------------------
    top_cells, bottom_cells = tcs(item_top), tcs(item_bottom)
    for idx, (top_text, bottom_text) in enumerate(ITEM_TOKENS):
        set_text(top_cells[idx], top_text, rpr=base_rpr, align='center')
        if bottom_text is not None:
            set_text(bottom_cells[idx], bottom_text, rpr=base_rpr, align='center')

    # --- 3. 迴圈標記列（全寬），套印時整列會被 {%tr%} 吃掉 -------------------
    item_top.addprevious(build_row(header_top, [(LOOP_START, 10)], base_rpr, height=20))
    item_bottom.addnext(build_row(header_top, [(LOOP_END, 10)], base_rpr, height=20))

    # --- 4. 表頭工程資訊 2 列（插在原表頭之前）------------------------------
    # 每次都 addprevious(header_top)，所以照 INFO_ROWS 的順序插入即為最終順序
    for left, lspan, right, rspan in INFO_ROWS:
        header_top.addprevious(
            build_row(header_top, [(left, lspan), (right, rspan)], base_rpr))

    # --- 5. 簽核列（表格最後）-----------------------------------------------
    tbl.append(build_row(header_top, SIGN_ROW, base_rpr))

    # --- 5b. 欄寬重配與字級（頻率欄放大、整表縮字，否則一列會撐成一整頁）----
    if sum(COL_WIDTHS) != 5000:
        raise SystemExit('COL_WIDTHS 相加必須等於 5000（tblW 是 pct 制），實得 %d'
                         % sum(COL_WIDTHS))
    force_fixed_layout(tbl, COL_WIDTHS, page_text_width_dxa(doc))
    apply_widths(tbl, COL_WIDTHS)
    for tr in tbl.findall(qn('w:tr')):
        set_font_size(tr, HEADER_FONT_HALFPT)
    for tr in (item_top, item_bottom):
        set_font_size(tr, DATA_FONT_HALFPT)
        trpr = tr.find(qn('w:trPr'))
        h = trpr.find(qn('w:trHeight')) if trpr is not None else None
        if h is not None:
            h.set(qn('w:val'), str(DATA_ROW_MIN_HEIGHT))

    # --- 6. 文件層級分頁迴圈 -------------------------------------------------
    body = doc.element.body
    # 表格之後的註記段落縮成 9pt（原 12pt 佔掉半頁，會把資料列擠到次頁）
    tbl_pos = list(body).index(tbl)
    for el in list(body)[tbl_pos + 1:]:
        if el.tag != qn('w:p'):
            continue
        set_font_size(el, NOTE_FONT_HALFPT)
        # 段落間距歸零：原檔每段之間有 5pt 空隙，4 段就吃掉 20pt，
        # 剛好讓最後一條註記掉到次頁。
        ppr = el.find(qn('w:pPr'))
        if ppr is None:
            ppr = el.makeelement(qn('w:pPr'), {})
            el.insert(0, ppr)
        sp = ppr.find(qn('w:spacing'))
        if sp is None:
            sp = ppr.makeelement(qn('w:spacing'), {})
            ppr.append(sp)
        sp.set(qn('w:before'), '0')
        sp.set(qn('w:after'), '0')
        sp.set(qn('w:line'), '240')
        sp.set(qn('w:lineRule'), 'auto')
    first_p = body.findall(qn('w:p'))[0]          # 標題段落
    last_p = body.findall(qn('w:p'))[-1]          # 註記最後一段
    set_font_size(first_p, TITLE_FONT_HALFPT)
    # 上下邊界收窄，讓「4 筆＋簽核列＋註記」擠得進同一張 A4
    mar = body.find(qn('w:sectPr')).find(qn('w:pgMar'))
    mar.set(qn('w:top'), str(PAGE_MARGIN_TB))
    mar.set(qn('w:bottom'), str(PAGE_MARGIN_TB))
    first_p.addprevious(new_paragraph(first_p, PAGE_START))
    last_p.addnext(new_paragraph(last_p, PAGE_END))
    last_p.addnext(new_paragraph(last_p, page_break=True))

    if backup and os.path.exists(dst):
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        shutil.copy2(dst, '%s.bak_%s' % (dst, stamp))
        print('已備份舊樣板 → %s.bak_%s' % (os.path.basename(dst), stamp))

    doc.save(dst)
    print('已產生 %s（%d bytes）' % (dst, os.path.getsize(dst)))


def main():
    ap = argparse.ArgumentParser(description='產生 test_control.docx 樣板')
    ap.add_argument('--src', default=DEFAULT_SRC, help='工程會空白表 docx')
    ap.add_argument('--dst', default=DEFAULT_DST, help='輸出的樣板路徑')
    ap.add_argument('--no-backup', action='store_true', help='不要備份既有樣板')
    args = ap.parse_args()
    build(args.src, args.dst, backup=not args.no_backup)


if __name__ == '__main__':
    main()
