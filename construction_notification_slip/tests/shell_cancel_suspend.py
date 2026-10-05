# -*- coding: utf-8 -*-
"""通報單「停工」「退單」驗收（18.0.3.0.0；odoo shell 執行，全程 rollback，不留資料）。

docker exec pg18-odoo bash -lc 'odoo shell -d system_development --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" --no-http --log-level=warn -c /etc/odoo/odoo.conf <<< "exec(open(\"/mnt/extra-addons/construction_notification_slip/tests/shell_cancel_suspend.py\").read())"'

逐一測每一個允許的轉換與每一個該被擋的轉換；逾期天數用北搶 111-19 第 12、36 通
的真實日期驗（管理表：第 12 通預定竣工 7/7→8/3、第 36 通 8/29→9/21、逾期 6 天）。
"""
import datetime
from lxml import etree
from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError

results = []
D = datetime.date


def check(name, cond, detail=''):
    results.append((bool(cond), name, detail))


def raises(name, fn, contains=None, exc=(UserError, ValidationError)):
    try:
        with env.cr.savepoint():
            fn()
    except exc as e:
        msg = str(e.args[0] if e.args else e)
        ok = (contains is None) or (contains in msg)
        results.append((ok, name, msg[:90] if ok else 'wrong message: ' + msg[:200]))
        return
    except Exception as e:  # noqa: BLE001 型別不對也算失敗
        results.append((False, name, 'raised %s: %s' % (type(e).__name__, str(e)[:200])))
        return
    results.append((False, name, 'did not raise'))


Slip = env['reservation.notification.slip']
Susp = env['reservation.notification.slip.suspension']
env.cr.execute('SAVEPOINT slip_cancel_suspend')
try:
    project = env['project.project'].search([('code', '=', 'DEMO-2026-003')], limit=1)
    other_project = env['project.project'].search(
        [('project_type', '=', 'reservation'), ('id', '!=', project.id)], limit=1)
    task = env['project.task'].search([
        ('supervision_project_id', '=', project.id), ('is_summary_item', '=', False),
        ('unit_price', '>', 0)], limit=1)
    base_no = 900

    def new_slip(no, **kw):
        vals = {
            'project_id': project.id, 'slip_no': no, 'location': f'測試地點{no}',
            'detail_line_ids': [Command.create({
                'task_id': task.id, 'item_no': task.display_item_no or 'T1',
                'unit': task.unit or '式', 'unit_price': task.unit_price, 'planned_qty': 1})],
        }
        vals.update(kw)
        return Slip.create(vals)

    # ---------- 欄位與狀態值 ----------
    sel = dict(Slip._fields['state'].selection)
    check('state 含 停工／退單', sel.get('suspended') == '停工' and sel.get('cancelled') == '退單')
    check('related 欄位 slip_state 自動跟上新值',
          'cancelled' in dict(env['reservation.self.inspection']._fields['slip_state']._description_selection(env)))

    # ---------- 草稿退單 → 解除 ----------
    s1 = new_slip(base_no + 1)
    raises('退單原因不合法', lambda: s1.action_cancel_slip('xxx'), '退單原因')
    raises('合併但沒選目標', lambda: s1.action_cancel_slip('merge'), '併入的通報單')
    raises('其他但沒填說明', lambda: s1.action_cancel_slip('other'), '說明')
    s1.action_cancel_slip('return', '2026-05-24', '工項價格有問題')
    check('草稿→退單', s1.state == 'cancelled' and s1.state_before_cancel == 'draft',
          s1.state)
    check('退單日期寫入', s1.cancel_date == D(2026, 5, 24))
    check('顯示名稱加「（已退單）」', s1.display_name.endswith('（已退單）'), s1.display_name)
    raises('退單後改地點被擋', lambda: s1.write({'location': 'X'}), '已退單')
    raises('退單後改明細被擋', lambda: s1.detail_line_ids.write({'planned_qty': 9}), '已退單')
    raises('退單後新增明細被擋', lambda: env['reservation.notification.slip.line'].create({
        'slip_id': s1.id, 'task_id': task.id, 'item_no': 'Z9', 'unit': '式'}), '已退單')
    raises('退單後刪明細被擋', lambda: s1.detail_line_ids.unlink(), '已退單')
    raises('退單後不可刪除通報單', lambda: s1.unlink(), '不可刪除')
    raises('退單後不可新增停工紀錄', lambda: Susp.create({
        'slip_id': s1.id, 'suspend_date': '2026-05-01', 'resume_date': '2026-05-02',
        'reason': 'x'}), '已退單')
    raises('退單後不可掛新照片', lambda: env['supervision.photo'].create({
        'slip_id': s1.id, 'project_id': project.id}), '已退單')
    raises('已退單不能再退單', lambda: s1.action_cancel_slip('return'), '已是退單')
    raises('已退單不能確認', lambda: s1.action_confirm(), None)
    s1.message_post(body='chatter 不受唯讀影響')
    check('退單後 chatter 可留言', True)
    s1.action_uncancel()
    check('解除退單→回草稿', s1.state == 'draft' and not s1.cancel_reason
          and not s1.cancel_date and not s1.state_before_cancel)
    raises('非退單不能解除退單', lambda: s1.action_uncancel(), '只有退單')

    # ---------- 未開始退單 → 解除回未開始 ----------
    s1.action_confirm()
    s1.action_cancel_slip('other', cancel_note='機關取消')
    check('未開始→退單', s1.state == 'cancelled' and s1.state_before_cancel == 'not_started')
    s1.action_uncancel()
    check('解除退單→回未開始（不是草稿）', s1.state == 'not_started')

    # ---------- 停工／復工 ----------
    raises('未開始不能停工', lambda: s1.action_suspend('2026-06-21', 'x'), '只有施工中')
    s1.write({'planned_start_date': '2026-06-17', 'planned_duration': 21,
              'actual_start_date': '2026-06-17'})
    s1.action_start()
    check('預定完工日 6/17+21-1＝7/7', s1.planned_end_date == D(2026, 7, 7), str(s1.planned_end_date))
    raises('停工沒填原因', lambda: s1.action_suspend('2026-06-21', ' '), '停工原因')
    raises('停工日早於實際開工', lambda: s1.action_suspend('2026-06-01', '測試'), '實際開工日')
    s1.action_suspend('2026-06-21', '機關通知暫停')
    open_line = s1.suspension_ids.filtered(lambda s: not s.resume_date)
    check('施工中→停工，新增一筆未復工紀錄', s1.state == 'suspended' and len(open_line) == 1)
    raises('停工中不能再停工', lambda: s1.action_suspend('2026-06-25', 'x'), '只有施工中')
    raises('停工中不能退回草稿', lambda: s1.action_return_to_draft(), None)
    raises('停工中不能「開始施工」', lambda: s1.action_start(), None)
    raises('停工中不能刪掉未復工那筆', lambda: open_line.unlink(), '復工')
    raises('停工狀態不能有兩筆未復工', lambda: Susp.create({
        'slip_id': s1.id, 'suspend_date': '2026-06-30', 'reason': 'x'}), None)

    # 停工中退單 → 解除回停工（未復工那筆保持未復工）
    s1.action_cancel_slip('return')
    check('停工→退單，未復工紀錄保留', s1.state == 'cancelled'
          and s1.state_before_cancel == 'suspended'
          and len(s1.suspension_ids.filtered(lambda s: not s.resume_date)) == 1)
    s1.action_uncancel()
    check('解除退單→回停工', s1.state == 'suspended')

    raises('復工日早於停工日', lambda: s1.action_resume('2026-06-20'), '不可早於')
    s1.action_resume('2026-07-18')
    check('停工→復工回施工中', s1.state == 'in_progress')
    check('停工天數＝復工日−停工日＝27', s1.suspended_days == 27, str(s1.suspended_days))
    check('調整後預定完工＝8/3（北搶第 12 通）', s1.adjusted_planned_end_date == D(2026, 8, 3),
          str(s1.adjusted_planned_end_date))
    raises('施工中不能復工', lambda: s1.action_resume('2026-07-20'), '只有停工')
    raises('施工中不能有未復工紀錄（手動清掉復工日）',
           lambda: s1.suspension_ids.write({'resume_date': False}), '不是停工狀態')
    raises('停工期間重疊', lambda: Susp.create({
        'slip_id': s1.id, 'suspend_date': '2026-07-01', 'resume_date': '2026-07-05',
        'reason': '補登'}), '重疊')
    # 第二次停工（可多次）
    s1.action_suspend('2026-07-20', '颱風')
    s1.action_resume('2026-07-22')
    check('可多次停工，天數加總 27+2', s1.suspended_days == 29, str(s1.suspended_days))
    # 補登一筆已結束的歷史停工（兩個日期都有）不必經過狀態
    Susp.create({'slip_id': s1.id, 'suspend_date': '2026-07-25', 'resume_date': '2026-07-26',
                 'reason': '補登'})
    check('補登已結束的停工紀錄', s1.suspended_days == 30, str(s1.suspended_days))

    # ---------- 有實作數量就不能退單 ----------
    s1.detail_line_ids.write({'actual_qty': 1})
    raises('施工中有實作量不能退單', lambda: s1.action_cancel_slip('return'), '改走「結案」')
    s1.action_suspend('2026-07-28', '測試')
    raises('停工中有實作量不能退單', lambda: s1.action_cancel_slip('return'), '改走「結案」')

    # ---------- 停工直接結案 ----------
    s1.write({'actual_end_date': '2026-08-10'})
    s1.action_close()
    last = s1.suspension_ids.sorted('suspend_date')[-1]
    check('停工→結案，未復工那筆以實際竣工日收尾',
          s1.state == 'closed' and last.resume_date == D(2026, 8, 10), str(last.resume_date))
    raises('已結案不能退單', lambda: s1.action_cancel_slip('return'), '已結案')
    raises('已結案不能停工', lambda: s1.action_suspend('2026-08-11', 'x'), '只有施工中')

    # ---------- 逾期天數（北搶第 36 通）----------
    s2 = new_slip(base_no + 2, planned_start_date='2026-08-09', planned_duration=21,
                  actual_start_date='2026-08-09')
    s2.action_confirm()
    s2.action_start()
    s2.action_suspend('2026-08-19', '停工')
    s2.action_resume('2026-09-11')
    s2.detail_line_ids.write({'actual_qty': 1})
    s2.write({'actual_end_date': '2026-09-27'})
    s2.action_close()
    check('第 36 通：預定 8/29、停工 23 天 → 調整後 9/21',
          s2.planned_end_date == D(2026, 8, 29) and s2.suspended_days == 23
          and s2.adjusted_planned_end_date == D(2026, 9, 21), str(s2.adjusted_planned_end_date))
    check('第 36 通：逾期 6 天（與管理表相同）', s2.overdue_days == 6, str(s2.overdue_days))
    s2.write({'schedule_review_days': 6})
    check('工期檢討增加 6 天 → 逾期 0', s2.adjusted_planned_end_date == D(2026, 9, 27)
          and s2.overdue_days == 0, str(s2.overdue_days))
    check('沒停工、沒工期檢討的舊單：調整後＝預定完工',
          all(r.adjusted_planned_end_date == r.planned_end_date
              for r in Slip.search([('id', 'not in', (s1 + s2).ids), ('planned_end_date', '!=', False)])))

    # ---------- 同一個通報單次：退單後可重開 ----------
    s3 = new_slip(base_no + 3)
    raises('同一工程同次（兩張都未退單）被擋', lambda: new_slip(base_no + 3), None,
           exc=(UserError, ValidationError, Exception))
    s3.action_cancel_slip('return')
    s3b = new_slip(base_no + 3)
    check('退單後可用同一個次數重開', s3b.slip_no == s3.slip_no and s3b.state == 'draft')
    raises('重開後不能解除舊單的退單', lambda: s3.action_uncancel(), '重新開立')
    raises('重開後不能再開第三張未退單同次', lambda: new_slip(base_no + 3), None,
           exc=(UserError, ValidationError, Exception))

    # ---------- 合併 ----------
    s4 = new_slip(base_no + 4)
    s5 = new_slip(base_no + 5)
    raises('不能併入自己', lambda: s4.action_cancel_slip('merge', merged_into_slip_id=s4.id), '自己')
    raises('不能併入已退單', lambda: s4.action_cancel_slip('merge', merged_into_slip_id=s3.id), '已退單')
    if other_project:
        s_other = Slip.search([('project_id', '=', other_project.id), ('state', '!=', 'cancelled')], limit=1)
        if s_other:
            raises('不能併入別的工程', lambda: s4.action_cancel_slip(
                'merge', merged_into_slip_id=s_other.id), '同一工程')
    s4.action_confirm()
    s4.action_start()
    s4.action_cancel_slip('merge', merged_into_slip_id=s5.id)
    check('施工中（無實作量）可合併退單', s4.state == 'cancelled' and s4.merged_into_slip_id == s5)
    check('目標單看得到併入的通報單', s4 in s5.merged_slip_ids)
    s4.action_uncancel()
    check('解除退單清掉併入單', not s4.merged_into_slip_id and s4.state == 'in_progress')

    # ---------- 其他模組 ----------
    Insp = env['reservation.self.inspection']
    itype = env['self.inspection.type'].search([], limit=1)
    s4.action_suspend(fields.Date.today(), '測試')
    insp = Insp.create({'slip_id': s4.id, 'inspection_type_id': itype.id,
                        'sub_project_name': '停工中檢查', 'inspection_date': fields.Date.today()})
    check('停工的通報單可掛自主檢查', insp.slip_id == s4)
    act = s4.action_create_self_inspection()
    check('停工的通報單可按「新增自主檢查」', act.get('res_model') == 'reservation.self.inspection')
    raises('退單的通報單不能掛自主檢查', lambda: Insp.create({
        'slip_id': s3.id, 'inspection_type_id': itype.id, 'sub_project_name': 'x',
        'inspection_date': fields.Date.today()}), '已退單')
    raises('退單的通報單不能掛缺失改善', lambda: env['reservation.defect.improvement'].create({
        'slip_id': s3.id, 'defect_description': 'x'}), '已退單')
    raises('退單的通報單不能按「新增自主檢查」', lambda: s3.action_create_self_inspection(), None)
    check('已掛檢查的通報單仍可退單（不擋，只列在精靈）',
          not s4.detail_line_ids.filtered('actual_qty'))
    wiz = env['reservation.notification.slip.state.wizard'].create(
        {'slip_id': s4.id, 'mode': 'cancel'})
    check('退單精靈列出仍掛在本單的資料', '自主檢查 1 筆' in (wiz.linked_summary or ''),
          wiz.linked_summary)
    wiz.write({'cancel_reason': 'return'})
    wiz.action_confirm()
    check('精靈退單', s4.state == 'cancelled' and insp.slip_id == s4)
    check('既有檢查仍掛在退單上（關聯欄位顯示已退單）',
          insp.slip_id.display_name.endswith('（已退單）'))
    s4.action_uncancel()
    wz = env['reservation.notification.slip.state.wizard'].create(
        {'slip_id': s4.id, 'mode': 'resume', 'resume_date': fields.Date.today()})
    check('復工精靈帶出本次停工日', wz.open_suspend_date == fields.Date.today())
    wz.action_confirm()
    check('精靈復工', s4.state == 'in_progress')
    wz = env['reservation.notification.slip.state.wizard'].create(
        {'slip_id': s4.id, 'mode': 'suspend', 'suspend_reason': '精靈停工',
         'suspend_date': fields.Date.today()})
    wz.action_confirm()
    check('精靈停工', s4.state == 'suspended')

    # 下拉 domain
    check('自主檢查／缺失／日誌／照片的通報單下拉排除退單', all(
        "'state', '!=', 'cancelled'" in str(env[m]._fields[f].domain) for m, f in [
            ('reservation.self.inspection', 'slip_id'),
            ('reservation.defect.improvement', 'slip_id'),
            ('daily.log.sheet', 'notification_slip_id'),
            ('supervision.photo', 'slip_id')]))
    from odoo.addons.construction_batch.wizard import batch_download_wizard as bdw
    st = bdw.RECORD_SOURCES['notification_slip']['states']
    check('批次下載自動選取排除退單（含停工）', st and 'cancelled' not in st and 'suspended' in st, str(st))

    # copy
    s3c = s3.copy()
    check('複製退單的通報單 → 新草稿、不帶退單欄位',
          s3c.state == 'draft' and not s3c.cancel_reason and not s3c.suspension_ids)

    # ---------- 視圖渲染 ----------
    for model, vtypes in [
        ('reservation.notification.slip', ['form', 'list', 'kanban', 'search']),
        ('reservation.notification.slip.state.wizard', ['form']),
        ('reservation.self.inspection', ['form', 'list']),
        ('reservation.defect.improvement', ['form', 'list']),
        ('daily.log.sheet', ['form']),
    ]:
        try:
            env[model].get_views([(False, v) for v in vtypes])
            check(f'get_views {model} {vtypes}', True)
        except Exception as e:  # noqa: BLE001
            check(f'get_views {model} {vtypes}', False, str(e)[:200])
    try:
        g = Slip.web_read_group([('project_id', '=', project.id)], ['state'], ['state'])
        check('看板依狀態分組（web_read_group）', any(x['state'] == 'cancelled' for x in g['groups']))
    except Exception as e:  # noqa: BLE001
        check('看板依狀態分組（web_read_group）', False, str(e)[:200])
    # 用 lxml 找元素（arch 會保留 XML 註解，字串搜尋會被註解騙）
    doc = etree.fromstring(Slip.get_views([(False, 'form')])['views']['form']['arch'])
    for btn in ('action_open_suspend_wizard', 'action_open_resume_wizard',
                'action_open_cancel_wizard', 'action_uncancel'):
        check(f'表單有按鈕 {btn}', bool(doc.xpath(f"//button[@name='{btn}']")))
    raw = env.ref('construction_notification_slip.view_reservation_notification_slip_form').arch_db
    raw_doc = etree.fromstring(raw.encode() if isinstance(raw, str) else raw)
    check('四個新按鈕都沒有 groups 限制', all(
        not raw_doc.xpath(f"//button[@name='{b}' and @groups]") for b in (
            'action_open_suspend_wizard', 'action_open_resume_wizard',
            'action_open_cancel_wizard', 'action_uncancel')))
finally:
    env.cr.execute('ROLLBACK TO SAVEPOINT slip_cancel_suspend')
    # 通報單編號是 standard 序號（PG sequence），rollback 不會退號 —— 退回「現存最大號」，
    # 否則每跑一次測試，正式編號就跳號一次。setval 不受交易影響，所以放在 rollback 之後。
    seq = env.ref('construction_notification_slip.seq_reservation_notification_slip', raise_if_not_found=False)         or env['ir.sequence'].search([('code', '=', 'reservation.notification.slip')], limit=1)
    env.cr.execute("""SELECT COALESCE(MAX(NULLIF(regexp_replace(slip_number, '^.*-', ''), '')::int), 0)
                        FROM reservation_notification_slip WHERE slip_number ~ '-[0-9]+$'""")
    max_no = env.cr.fetchone()[0]
    if seq.implementation == 'standard' and max_no:
        env.cr.execute("SELECT setval('ir_sequence_%03d', %%s, true)" % seq.id, (max_no,))

ok = sum(1 for r in results if r[0])
for passed, name, detail in results:
    print(('PASS ' if passed else 'FAIL ') + name + (('  — ' + detail) if detail else ''))
print(f'\n{ok}/{len(results)} passed')
