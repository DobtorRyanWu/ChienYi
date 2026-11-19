# -*- coding: utf-8 -*-
"""模組安裝時帶入「自主檢查樣板庫」（全域類型、不綁工程）。

只在新裝時跑（post_init_hook），不在 -u 升級時跑：既有站台的樣板庫是當年用匯入工具建的、
沒有 xmlid，升級時若重建會整批重複。載入本身也是冪等的：同名全域類型已存在就跳過，
所以手動重跑 `load_inspection_library(env)` 也不會重複。
資料來源：data/self_inspection_library.json（由 tools/import_self_inspection/export_library_json.py 匯出）。
"""
import base64
import json
import logging
import os

from odoo import Command

_logger = logging.getLogger(__name__)

LIBRARY_JSON = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data', 'self_inspection_library.json')


def _read_library(path=LIBRARY_JSON):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_inspection_library(env, library=None, base_dir=None):
    """建立樣板庫；回傳新建的類型數。library／base_dir 給測試注入用。"""
    if library is None:
        library = _read_library()
    base_dir = base_dir or os.path.dirname(LIBRARY_JSON)
    Type = env['self.inspection.type'].with_context(active_test=False)
    existing = set(Type.search([('project_id', '=', False)]).mapped('name'))
    created = 0
    for t in library:
        if t['name'] in existing:
            continue
        stage_cmds = [Command.create({'name': s['name'], 'sequence': s['sequence'], 'legacy_code': s['legacy_code']})
                      for s in t['stages']]
        timing_cmds = [Command.create({'name': m['name'], 'sequence': m['sequence'], 'legacy_code': m['legacy_code']})
                       for m in t['timings']]
        vals = {
            'name': t['name'], 'sequence': t['sequence'], 'category': t['category'],
            'description': t['description'] or False, 'result_layout': t['result_layout'],
            'allow_close_with_defect': t['allow_close_with_defect'], 'template_filename': t['template_filename'],
            'stage_ids': stage_cmds, 'timing_ids': timing_cmds,
        }
        if t.get('docx'):
            with open(os.path.join(base_dir, t['docx']), 'rb') as f:
                vals['template_file'] = base64.b64encode(f.read())
        rec = Type.create(vals)
        stage_by_name = {s.name: s.id for s in rec.stage_ids}
        Item = env['self.inspection.type.item']
        Item.create([{
            'type_id': rec.id, 'name': i['name'], 'sequence': i['sequence'],
            'check_standard': i['check_standard'] or False, 'note': i['note'] or False,
            'reverse_question': bool(i['reverse_question']),
            'stage_id': stage_by_name.get(i['stage'], False),
        } for i in t['items']])
        created += 1
    _logger.info('自主檢查樣板庫：新建 %d 份、略過 %d 份（同名已存在）', created, len(library) - created)
    return created


def post_init_hook(env):
    load_inspection_library(env)
