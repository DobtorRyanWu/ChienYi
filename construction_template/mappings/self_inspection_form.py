# -*- coding: utf-8 -*-
"""自主檢查表（單張）—— docx 對照表，一張檢查紀錄一份檔案。

與 mappings/self_inspection.py（自主檢查**總表**，專案層級的 xlsx 彙總清單）
是兩件事，不要混淆：這一份是把**某一張檢查紀錄**的資料，套進使用者為該檢查
類型上傳的 Word 樣板。

樣板來源有兩層（見 construction_quality 的 action_export_inspection_form）：
    1. 檢查類型上傳的樣板（self.inspection.type.template_file）
    2. 沒上傳 → 系統預設樣板（document.template 的 self_inspection_form）

## 同一份 context 要同時餵得動兩種樣板

使用者上傳的樣板有兩種寫法，而 docx_render.render() 是「先跑 +++INS+++
轉換器 → 再交 docxtpl」，所以兩種都吃得下：

    舊（硬編索引）  +++INS inspection.stages[0].items[1].standard+++
    新（動態表格）  {%tr for stage in inspection.stages %}…{{ item.standard }}

兩者取的是**同一個 stages 結構**，差別只在「用索引取」還是「用迴圈跑」。
所以這裡只要把資料組好，不必為兩種樣板各做一份。

## 🔴 context 必須用物件，不能用 dict

Jinja2 的 `.` 存取是**先找 attribute 再找 key**，而 dict 的 `items` 是內建
方法——`stage.items` 會拿到 `dict.items` 這個 method，直接爆
`TypeError: 'builtin_function_or_method' object is not iterable`（2026-09-11 實測）。
用 dict 子類覆寫 `items` 也不行：docx_render._swap_images() 會對 dict 呼叫
`.items()` 來遞迴，覆寫過的版本會讓它拿到 list 而炸掉。

所以一律用 SimpleNamespace。`_swap_images` 已同步支援（認得 __dict__）。

## 🔴 檢查結果的符號不要給預設值

樣板上印的符號是 ○ / ╳ / ／，對應 pass / defect / na。`check_result` 在模型
上有 `default='pass'`，那是另一個議題；這裡只負責「有什麼印什麼」，沒有值就
印空字串，不要自作主張補一個 ○——「沒填」與「合格」在紙上必須看得出差別。
"""

import base64
from types import SimpleNamespace

from odoo import fields

from ..utils import photo_stamp
from ..utils.formatters import roc_date_cn

MODEL = ('general.self.inspection', 'reservation.self.inspection')
MODE = 'docx'

# 檢查結果 → 紙本符號。刻意沒有 .get() 的預設值，見模組說明。
RESULT_MARKS = {
    'pass': '○',
    'defect': '╳',
    'na': '／',
}

# 樣板表頭「檢查時機」那一列是四個固定的勾記位置，對應 timing 的 legacy_code。
# 系統的 DEFAULT_TIMINGS 有五個（多一個 random 隨機抽查），但 79 份實體樣板
# 沒有任何一份印了「隨機抽查」那一格——勾了也印不出來，這是樣板的限制不是 bug。
TIMING_SLOTS = {
    'arbitrary': 'hold_point',
    'beforeConstruction': 'before',
    'constructing': 'during',
    'afterConstruction': 'after',
}
TIMING_MARK = 'V'          # 與 EAGLE 原系統一致（不是 ✓）

PHOTOS_PER_PAGE = 2        # 照片頁每頁兩張，同 EAGLE 的 evenImagesIndex

# 這份對照表提供給樣板的所有欄位。
#
# 用途是**檢查使用者上傳的樣板寫對了沒有**：樣板裡寫了 {{ projectTitle }}
# （正確是 projectName）或 {{ item.detail }}（正確是 item.situation）時，
# docxtpl 不會報錯——Jinja2 的 Undefined 直接印成空字串，於是產出一份
# 「每一格都空白、但看起來很正常」的檔案（2026-09-13 實測確認）。
# 使用者只會以為是自己沒填資料。
#
# 鍵是「路徑」，清單裡的元素用 [] 表示：
#   ''                              頂層
#   'inspection.stages[]'           stages 這個清單的元素
#   'inspection.stages[].items[]'   元素底下的 items 的元素
# 改 build_context() 時**這裡要一起改**，否則新欄位會被誤判成寫錯。
TOKEN_SCHEMA = {
    '': {'contractor', 'projectName', 'inspection'},
    'inspection': {
        'no', 'name', 'subContractor', 'position', 'inspectedAt',
        'inspectionTiming', 'stages', 'measures', 'images', 'imagePages',
        'evenImagesIndex',
    },
    'inspection.inspectionTiming': set(TIMING_SLOTS),
    'inspection.stages[]': {'name', 'items'},
    'inspection.stages[].items[]': {
        'name', 'standard', 'situation', 'result', 'remark'},
    'inspection.measures[]': {'title', 'lines'},
    'inspection.measures[].lines[]': {
        'no', 'text', 'result', 'passMark', 'failMark'},
    'inspection.images[]': {'image', 'date', 'description', 'isEmpty'},
    'inspection.imagePages[]': {'first', 'second'},
    'inspection.imagePages[].first': {
        'image', 'date', 'description', 'isEmpty'},
    'inspection.imagePages[].second': {
        'image', 'date', 'description', 'isEmpty'},
}


def _inspection_no(record):
    """一般式的編號欄是 name，預約式是 inspection_no"""
    return (record.inspection_no if 'inspection_no' in record._fields
            else record.name) or ''


def _timing_codes(record):
    return set(record.inspection_timing_ids.mapped('legacy_code')) - {False, ''}


def _stages(record):
    """依段落分群的檢查項目。

    分群基準是項目自己的 stage_id，不是檢查類型的 stage_ids——項目可能沒分段
    （stage_id 為空），那些要有地方去，不能整批消失。沒分段的收在最後一組，
    段落名稱留白（樣板那一欄本來就是印段落名，留白即可）。

    排序沿用模型的 _order（stage_sequence, sequence, id），也就是畫面上看到的
    順序——樣板是逐列對應的，順序一旦與畫面不同，使用者無從察覺。
    """
    groups = []
    index = {}
    for line in record.checklist_ids:
        key = line.stage_id.id or 0
        if key not in index:
            index[key] = SimpleNamespace(
                name=line.stage_id.name or '', items=[])
            groups.append(index[key])
        index[key].items.append(SimpleNamespace(
            name=line.check_item or '',
            standard=line.design_standard or '',
            situation=line.actual_result or '',
            result=RESULT_MARKS.get(line.check_result, ''),
            remark=line.note or '',
        ))
    return groups


def _measures(record):
    """量測區塊（表尾「丈量___位置…□合格□不合格」那一段）。

    依區塊分組，一個區塊一組標題 + 若干列。空列不存在（09-09 的裁示：
    紙本預印 4 列、實填 2 列就只建 2 列），所以這裡看到幾列就印幾列。

    合格／不合格是兩個獨立的勾記位置（樣板印「□合格 □不合格」的字，
    我們只負責印勾記），與檢查時機同一種做法。
    """
    blocks = []
    index = {}
    for line in record.measure_line_ids:
        block = line.block_id
        if block.id not in index:
            index[block.id] = SimpleNamespace(
                title=block.name or '', lines=[])
            blocks.append(index[block.id])
        group = index[block.id]
        group.lines.append(SimpleNamespace(
            no=len(group.lines) + 1,
            text=line.rendered or '',
            result=line.result or '',
            passMark=TIMING_MARK if line.result == 'pass' else '',
            failMark=TIMING_MARK if line.result == 'fail' else '',
        ))
    return blocks


def _photo(photo):
    """一張照片 → 樣板要的結構。

    `image` 放的是 docx_render 認得的圖片標記，由它換成 docxtpl 的 InlineImage
    （對照表拿不到 tpl 物件，自己建不了）。尺寸與日期浮水印沿用
    defect_improvement.py 的做法。
    """
    raw = None
    if photo.image:
        raw = base64.b64decode(photo.image)
        taken = photo.shot_date or (photo.shot_at.date() if photo.shot_at else None)
        raw = photo_stamp.stamp_date(raw, taken)
    return SimpleNamespace(
        image={'__image__': raw},
        date=roc_date_cn(photo.shot_date
                         or (photo.shot_at.date() if photo.shot_at else None)),
        description=photo.description or photo.name or '',
        isEmpty=not raw,
    )


def _images(record):
    """照片，依**拍攝順序**（舊到新）。

    🔴 supervision.photo 的 _order 是 'shot_at desc, id desc'——照片管理的清單
    要「最新的在最前面」，那是對的。但列印到檢查表上時順序必須反過來：
    紙本的第 1 張應該是現場先拍的那張。直接用 record.photo_ids 的話，
    三張照片會印成 3→2→1（2026-09-14 使用者實際驗證時發現，
    我的自動測試只數了「有幾張圖」，沒有檢查順序）。

    拍攝日期可能沒填（前台補傳的照片常常沒有），所以用 id 當最後的排序依據——
    id 遞增就是建立順序，與「先拍先傳」一致。
    """
    photos = record.photo_ids.sorted(
        key=lambda p: (p.shot_date or fields.Date.today(),
                       p.shot_at or fields.Datetime.now(),
                       p.id))
    return [_photo(p) for p in photos]


def _blank_photo():
    """空白照片格：舊樣板用索引取圖，張數是奇數時最後一頁的第二格會越界。"""
    return SimpleNamespace(image={'__image__': None}, date='',
                           description='', isEmpty=True)


def _image_pages(images):
    """切成一頁兩張。第二張可能沒有（奇數張時的最後一頁），樣板用 if 判斷。"""
    pages = []
    for start in range(0, len(images), PHOTOS_PER_PAGE):
        chunk = images[start:start + PHOTOS_PER_PAGE]
        pages.append(SimpleNamespace(
            first=chunk[0],
            second=chunk[1] if len(chunk) > 1 else None,
        ))
    return pages


def _merge_measures_into_stages(stages, measures, probe_result):
    """硬編樣板專用：把量測列併回 stages。

    🔴 同一份量測資料，兩種樣板走**兩條不同的路**：

        動態樣板  走 inspection.measures 的迴圈（表格外面自己一段）
        硬編樣板  量測列就印在檢查項目表格裡，佔掉某一段的 items
                  （鋼筋樣板：stages[2] 的 8 列，每列只有 standard 一欄）

    不併的後果實測：反推出來的檢查類型第 3 段只有量測區塊、沒有檢查項目，
    套印時樣板要 stages[2] 而 stages 只有 2 個 → UndefinedError 當場崩潰。

    段落位置由 probe 的 measure_blocks() 指出（那是從樣板讀出來的結構），
    不是猜的。
    """
    blocks = probe_result.measure_blocks() if probe_result else []
    if not blocks:
        return stages
    names = probe_result.stage_names()
    merged = list(stages)
    for offset, (title, row_count, stage_index) in enumerate(blocks):
        block = measures[offset] if offset < len(measures) else None
        items = [SimpleNamespace(
            name=title,
            standard=line.text,
            situation='',
            result='',
            remark='',
        ) for line in (block.lines if block else [])]
        # 🔴 量測列要**補空白**補到樣板的列數。
        # 紙本預印 8 列、實際只量了 2 處是常態（09-09 的裁示：空列＝沒有記錄，
        # 只存實填的），但硬編樣板的 stages[2] 寫死要 items[0..7]——不補的話
        # 守門會把「只量了 2 處」判成「資料比樣板少」而擋下，那是錯的：
        # 紙本上那 6 列本來就是留白。
        # 反過來，實填**超過**樣板列數時不補也不截斷，交給守門擋（那才是真的
        # 裝不下——多出來的量測記錄會靜靜消失）。
        while len(items) < row_count:
            items.append(SimpleNamespace(
                name='', standard='', situation='', result='', remark=''))
        while len(merged) <= stage_index:
            merged.append(SimpleNamespace(name='', items=[]))
        merged[stage_index] = SimpleNamespace(
            name=names.get(stage_index) or (block.title if block else title),
            items=items)
    return merged


def build_stages(record, probe_result=None):
    """本張紀錄要餵給樣板的 stages（硬編樣板會把量測列併進來）。

    守門與實際套印**必須共用這一支**——分群或合併只要有一邊不同，就會出現
    「守門過了但套印錯位」，而那種錯誤在產出的檔案上完全看不出來。
    """
    stages = _stages(record)
    if probe_result is not None and probe_result.is_indexed:
        stages = _merge_measures_into_stages(
            stages, _measures(record), probe_result)
    return stages


def stage_groups(stages):
    """stages → check_fit() 要的 [(段落名, [項目名, ...])]"""
    return [(s.name, [i.name for i in s.items]) for s in stages]


def build_context(record, probe_result=None):
    project = record.project_id
    codes = _timing_codes(record)
    images = _images(record)

    inspection = SimpleNamespace(
        no=_inspection_no(record),
        name=record.sub_project_name or '',
        subContractor=record.subcontractor_name or '',
        position=record.inspection_location or '',
        inspectedAt=roc_date_cn(record.inspection_date),
        inspectionTiming=SimpleNamespace(**{
            slot: (TIMING_MARK if code in codes else '')
            for slot, code in TIMING_SLOTS.items()
        }),
        stages=build_stages(record, probe_result),
        measures=_measures(record),
        # 🔴 舊樣板的照片頁是用**索引**取圖（images[$evenIndex] 與
        # images[$evenIndex + 1]），張數是奇數時最後一頁的第二格會越界，
        # Jinja2 的 Undefined 一被存取屬性就拋 UndefinedError，整份套印失敗
        # （2026-09-11 實測：3 張照片 → list object has no element 3）。
        # EAGLE 原樣板是靠 +++IF+++ 擋的，但那個標記在 docx_render 裡會被
        # 移除（「移除標記、保留內容」），所以這裡要補一格空白。
        # imagePages 走的是另一條路（新樣板用 {% if page.second %} 自己判斷），
        # 所以用**沒補過**的清單切，不要讓它多印一頁空白。
        images=(images + [_blank_photo()]) if len(images) % 2 else images,
        imagePages=_image_pages(images),
        # 舊樣板的照片頁是 `+++FOR evenIndex IN inspection.evenImagesIndex+++`，
        # 一次跨兩張（$evenIndex 與 $evenIndex+1），所以是 0,2,4,…
        evenImagesIndex=list(range(0, len(images), PHOTOS_PER_PAGE)),
    )
    return {
        'contractor': record.contractor_name or '',
        'projectName': project.name or '',
        'inspection': inspection,
    }


def FILENAME(record):
    return '%s_%s.docx' % (
        (record.sub_project_name or '自主檢查').replace('/', '_'),
        _inspection_no(record) or record.id)
