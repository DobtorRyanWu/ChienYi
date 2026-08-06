# -*- coding: utf-8 -*-
"""估驗照片 —— docx 對照表（一頁兩張，跟著估驗單走）。

樣板 = EAGLE 的全域 `invoiceImageTemplate.docx`。原檔用「偶數索引」技巧在
單一迴圈裡塞兩張照片：

    +++FOR evenIndex IN evenImagesIndex+++        evenImagesIndex = [0,2,4,…]
      +++IMAGE imageGenerator(images[$evenIndex].src, …)+++      左
      +++IMAGE imageGenerator(images[$evenIndex+1].src, …)+++    右
      +++INS ($evenIndex/2) +1 +++ / +++INS evenImagesIndex.length+++

那需要「以迴圈變數當索引」與算術運算式，dobtor 的 `_convert_ins_to_jinja`
與本模組的 `docx_render` 都只認 literal 索引。2026-08-06 把樣板標記改寫成
與 `defect_improvement` 相同的「一頁一物件」形式（版面完全沒動）：

    +++FOR page IN pages+++
      +++IMAGE imageGenerator($page.images[0].src, …)+++
      +++IMAGE imageGenerator($page.images[1].src, …)+++
      +++INS $page.currentPage+++ / +++INS $page.totalPage+++

分頁改由這裡算好，語意與原系統等價。

## 照片怎麼選

EAGLE 由前端把使用者挑好的 `data.images` 傳進來。Odoo 沒有這個挑選 UI，
改以估驗單的期間自動取——`supervision.photo` 沒有指向估驗單的欄位
（實查 fields_get：只有 project_id / slip_id / shot_date），
所以用「同專案 ＋ 拍攝日落在本期區間內」。

區間 = (上一張估驗的估驗日, 本張估驗日]。找不到上一張就不設下界。
"""

import base64

from ..utils import photo_stamp

MODEL = 'payment.estimate'
MODE = 'docx'

PHOTOS_PER_PAGE = 2

# 沿用原樣板 imageGenerator 的 {height:9,width:12}（公分）
MAX_WIDTH_CM = 12
MAX_HEIGHT_CM = 9


def _period(estimate):
    """(起, 迄)——起為 None 表示不設下界（第一張估驗）"""
    end = estimate.estimate_date
    if not end:
        return None, None
    previous = estimate.search([
        ('project_id', '=', estimate.project_id.id),
        ('estimate_date', '<', end),
    ], order='estimate_date desc, id desc', limit=1)
    return (previous.estimate_date if previous else None), end


def _photos(estimate):
    project = estimate.project_id
    if not project:
        return estimate.env['supervision.photo'].browse()
    start, end = _period(estimate)
    domain = [('project_id', '=', project.id)]
    if end:
        domain.append(('shot_date', '<=', end))
    if start:
        domain.append(('shot_date', '>', start))
    return estimate.env['supervision.photo'].search(domain, order='shot_date, id')


def _image(photo):
    """一格照片；photo 為 None 時回傳空格（樣板該格印空白）。

    浮水印同 EAGLE：拍攝日期紅字印在右下角（`photo_stamp.stamp_date`）。
    """
    if not photo:
        return {'image': {'__image__': None}, 'description': ''}
    raw = base64.b64decode(photo.image) if photo.image else None
    if raw:
        taken = photo.shot_date or (photo.shot_at.date() if photo.shot_at else None)
        raw = photo_stamp.stamp_date(raw, taken)
    return {
        'image': {'__image__': raw,
                  'max_width_cm': MAX_WIDTH_CM,
                  'max_height_cm': MAX_HEIGHT_CM},
        'description': photo.description or photo.name or '',
    }


def build_context(estimate):
    photos = list(_photos(estimate))
    # 補到偶數，讓最後一頁的右格有東西可放（空的）
    if len(photos) % PHOTOS_PER_PAGE:
        photos += [None] * (PHOTOS_PER_PAGE - len(photos) % PHOTOS_PER_PAGE)
    chunks = [photos[i:i + PHOTOS_PER_PAGE]
              for i in range(0, len(photos), PHOTOS_PER_PAGE)] or [[None, None]]
    total = len(chunks)
    return {
        'projectName': estimate.project_id.name or '',
        'pages': [{
            'currentPage': index + 1,
            'totalPage': total,
            'images': [_image(p) for p in chunk],
        } for index, chunk in enumerate(chunks)],
    }


def FILENAME(estimate):
    return '估驗照片_%s_第%s次.docx' % (
        estimate.project_id.name or '', estimate.estimate_no or 0)
