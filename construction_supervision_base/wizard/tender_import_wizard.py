# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
from markupsafe import escape
import xml.etree.ElementTree as ET
import base64
import re


class TenderImportWizard(models.TransientModel):
    """
    契約標單匯入精靈

    用於匯入政府採購標單 XML (ETenderSheet 格式)
    將 PayItem 轉換為契約工項 (project.task)
    """
    _name = 'tender.import.wizard'
    _description = '契約標單匯入精靈'

    # === 關聯工程案件 ===
    project_id = fields.Many2one(
        'project.project',
        string='工程案件',
        required=True,
        readonly=True,
        help='將標單匯入此工程案件')

    project_name = fields.Char(
        string='工程名稱',
        related='project_id.name',
        readonly=True)

    # === 上傳檔案 ===
    xml_file = fields.Binary(
        string='標單 XML 檔案',
        required=True,
        attachment=False,
        help='請上傳政府採購標單 XML 檔案 (ETenderSheet 格式)')

    xml_filename = fields.Char(string='檔案名稱')

    # === 狀態 ===
    state = fields.Selection([
        ('upload', '上傳檔案'),
        ('previewing', '確認中'),
        ('done', '匯入完成'),
    ], string='狀態', default='upload', readonly=True)

    # === 匯入結果 ===
    imported_count = fields.Integer(
        string='已匯入工項數',
        readonly=True)

    preview_count = fields.Integer(
        string='預計匯入工項數',
        readonly=True)

    # === 金額核對報告 ===
    validation_report = fields.Text(
        string='金額核對報告',
        readonly=True)
    has_validation_warning = fields.Boolean(
        string='有差異',
        default=False)

    # === 重複匯入防呆（覆蓋模式）===
    # 匯入按鈕只在 state='draft' 顯示，但同一個「未開始」的工程可以按很多次，
    # 而 _create_tasks 只有 create、沒有任何既有工項的檢查 —— 按第二次會整套重建，
    # 契約金額（Σ 頂層工項）直接變兩倍且不報錯。
    # 這裡不是把路堵死（選錯檔案要能重匯），而是「偵測到就停下來問」。
    existing_task_count = fields.Integer(
        string='此工程已有工項數',
        readonly=True)
    blocking_reference_info = fields.Text(
        string='阻擋覆蓋的引用單據',
        readonly=True)
    has_blocking_reference = fields.Boolean(
        string='有單據引用既有工項',
        default=False)
    # ⚠️ 這個 string 就是使用者在畫面上唯一看得到的說明文字 ——
    # view 裡用 <label for="confirm_overwrite"/> 把它渲染在勾選框旁邊。
    # 第一版只放了 <field/>、沒放 <label/>，結果是一個**沒有任何文字的裸勾選框**，
    # 使用者找不到它（實測回報）。改動這裡要連 view 一起看。
    confirm_overwrite = fields.Boolean(
        string='我確認：本次匯入會先刪除全部既有工項，再以本檔重建',
        help='此工程已有契約工項。勾選後本次匯入會先刪除全部既有工項再重建。\n'
             '⚠️ 刪除無法復原；若已有通報單／估驗／日誌／契約變更引用這些工項，'
             '系統會擋下來、不允許覆蓋。')

    # === 匯入過程的處理紀錄 ===
    # 自動做掉的事（刪舊工項／小計列勾不計入／比例基數回填）一定要留痕，
    # 否則使用者只看得到「匯入成功 N 筆」，不知道系統替他決定了什麼。
    import_note = fields.Text(
        string='匯入處理紀錄',
        readonly=True)

    # === 小工具 ===

    @staticmethod
    def _remark_to_html(remark):
        """備註純文字 → Html 欄位（project.task.description 是 fields.Html）。

        不 escape 的話，備註裡的「網目<4.5CM」「<免議價>」這種字串會被
        Odoo 的 html sanitizer 當成標籤處理掉，而且不會報錯。
        """
        text = (remark or '').strip()
        if not text:
            return False
        return '<p>%s</p>' % escape(text).replace('\n', '<br/>')

    # === 比例基數（rate_base_task_ids）===

    # 標單只用 <Percent> 表達「比例是多少」，**基數是哪幾個工項只寫在 <Remark>
    # 的散文裡**，例如：
    #     (一)*2%[發包]                 → 基數只有「一」
    #     [(一)~(七)]*約10.96%[發包]     → 基數是「一」到「七」
    #     （一~八*約11%）[發包]          → 基數是「一」到「八」
    # 精靈先前完全不讀這一段，基數就落在預設值「同層全部前置工項」——
    # 對第一種寫法是錯的（111-16 的「七 自主品管費」因此多算 17,344.36，
    # 連帶把「八 稅什費」墊高，契約總價差 19,245.30）。
    _BRACKETS = '()[]{}（）［］｛｝【】〔〕'
    _RANGE_SEPARATORS = '~～－—-至'

    @classmethod
    def _parse_rate_base_expression(cls, remark):
        """從備註的公式抽出基數項次。

        回傳 ('single', ['一'])／('range', ['一', '七'])／(None, [])。
        認不出來就回 (None, []) —— **寧可留空走預設值，也不要猜一個錯的基數**。
        """
        text = (remark or '')
        # 公式在第一個乘號之前；沒有乘號就不是公式（「單價訂約」「損耗率0.67」…）
        for star in ('*', '＊', '×'):
            if star in text:
                text = text.split(star, 1)[0]
                break
        else:
            return None, []
        for ch in cls._BRACKETS:
            text = text.replace(ch, '')
        text = text.strip()
        if not text:
            return None, []
        for sep in cls._RANGE_SEPARATORS:
            if sep in text:
                parts = [p.strip() for p in text.split(sep) if p.strip()]
                if len(parts) == 2:
                    return 'range', parts
                return None, []
        parts = [p.strip() for p in re.split(r'[,，、+＋]', text) if p.strip()]
        if parts:
            return 'single', parts
        return None, []

    def _apply_rate_bases(self, tasks, items_data):
        """依備註的公式回填 rate_base_task_ids，回傳處理紀錄（list of str）。

        只處理「比例項」＝ 無子工項且 tax_misc_rate 不為 0 的工項
        （彙總項的金額走子項加總，基數對它沒有意義）。

        🔴 解析出來的基數若**剛好等於「同層全部前置工項」，一律留空不寫** ——
        留空在模型裡就是這個意思（`_rate_base_records`），與 xlsx 匯入那條路的
        慣例一致；寫死反而會讓日後插進來的新工項進不了基數。
        """
        notes = []
        remark_by_item_no = {}
        for item in items_data:
            remark_by_item_no.setdefault(item.get('item_no', ''), item.get('remark', ''))

        rate_tasks = tasks.filtered(lambda t: t.tax_misc_rate and not t.child_ids)
        for task in rate_tasks:
            remark = task.construction_notes or remark_by_item_no.get(task.item_no, '')
            kind, tokens = self._parse_rate_base_expression(remark)
            if not kind:
                continue

            # 同層前置工項（限本次匯入建立的，避免抓到別批資料）
            siblings = tasks.filtered(
                lambda t: t.parent_id.id == task.parent_id.id
                and t.id != task.id
                and t.sequence < task.sequence
            ).sorted('sequence')
            if not siblings:
                continue
            by_no = {t.item_no: t for t in siblings}

            if kind == 'single':
                picked = [by_no[t] for t in tokens if t in by_no]
                if len(picked) != len(tokens):
                    notes.append(
                        '⚠ 「%s」的基數 %s 在同層前置工項裡找不到，已留空改用'
                        '「同層全部前置工項」。備註原文：%s'
                        % (task.name, '、'.join(tokens), remark))
                    continue
            else:  # range
                start, end = tokens
                if start not in by_no or end not in by_no:
                    notes.append(
                        '⚠ 「%s」的基數範圍 %s~%s 在同層前置工項裡找不到端點，已留空改用'
                        '「同層全部前置工項」。備註原文：%s'
                        % (task.name, start, end, remark))
                    continue
                ordered = list(siblings)
                i, j = ordered.index(by_no[start]), ordered.index(by_no[end])
                if i > j:
                    i, j = j, i
                picked = ordered[i:j + 1]

            if not picked:
                continue
            # 與「同層全部前置」等價 → 留空（慣例）
            if len(picked) == len(siblings):
                continue

            task.write({'rate_base_task_ids': [Command.set([t.id for t in picked])]})
            notes.append(
                '比例基數：「%s」(%g%%) ← %s　（依備註 %s）'
                % (task.name, task.tax_misc_rate,
                   '、'.join(t.name for t in picked), remark))
        return notes

    # === 既有工項的引用檢查（覆蓋前的守門）===

    def _find_task_references(self, tasks):
        """找出還在引用這批工項的單據，回傳 [(說明, 筆數), ...]。

        不寫死模型清單 —— 掃 `ir.model.fields` 找所有指向 project.task 的
        many2one，日後新增模組也涵蓋得到。
        跳過三種：project.task 自己（parent_id 之類）、暫存模型、
        以及 ondelete='cascade' 的（那些會跟著一起刪，不算阻擋）。
        """
        if not tasks:
            return []
        hits = []
        Fields = self.env['ir.model.fields'].sudo()
        refs = Fields.search([
            ('ttype', '=', 'many2one'),
            ('relation', '=', 'project.task'),
            ('store', '=', True),
            ('on_delete', '!=', 'cascade'),
        ])
        for f in refs:
            if f.model == 'project.task':
                continue
            if f.model not in self.env:
                continue
            Model = self.env[f.model]
            # 🔴 `_auto = False` 要排掉 —— 那是 SQL view 撐起來的報表模型
            # （例如 Odoo 原生的 `report.project.task.user`），它沒有自己的資料表，
            # 刪工項時會跟著消失，不是「引用」。第一版沒排，結果任何一次覆蓋
            # 都會被「Tasks Analysis：443 筆」擋死。
            if Model._transient or Model._abstract or not Model._auto:
                continue
            if f.name not in Model._fields:
                continue
            try:
                count = Model.sudo().search_count([(f.name, 'in', tasks.ids)])
            except Exception:       # noqa: BLE001 - 模型有特殊 domain/權限就跳過
                continue
            if count:
                hits.append(('%s（%s.%s）' % (
                    Model._description or f.model, f.model, f.name), count))
        return hits

    # === 金額核對（不建立 task）===

    def _compute_reconciliation_from_items(self, items_data):
        """
        從 items_data（parse 結果，尚未建立 task）計算金額核對報告。
        遞迴模擬 planned_amount，與 xml_amount 比較。
        回傳 (report_text, has_warning)。
        """
        def compute_item_amount(item):
            children = [i for i in items_data if i['parent_item_key'] == item['item_key']]
            if children:
                return round(sum(compute_item_amount(c) for c in children), 2)
            elif item.get('unit_price'):
                return round((item.get('quantity') or 0) * item['unit_price'], 2)
            else:
                # 稅什費等無單價項，以 xml_amount 為準（不需比對）
                return item.get('amount') or 0.0

        warn_rows = []
        ok_count = 0
        for item in items_data:
            xml_amt = item.get('amount') or 0.0
            if item.get('has_children'):
                if not xml_amt:
                    continue
                computed = compute_item_amount(item)
                label = f'[分類] {item["name"]}'
            elif item.get('unit_price'):
                computed = round((item.get('quantity') or 0) * item['unit_price'], 2)
                label = item.get('name', '')
            else:
                ok_count += 1
                continue

            diff = round(computed - xml_amt, 2)
            if abs(diff) > 0.01:
                warn_rows.append(
                    f'⚠ {label}：計算 {computed:,.2f} / XML {xml_amt:,.2f} / 差異 {diff:+,.2f}')
            else:
                ok_count += 1

        if warn_rows:
            report = '\n'.join(warn_rows)
            if ok_count:
                report += f'\n（其餘 {ok_count} 個工項金額吻合）'
            return report, True
        else:
            return f'全部 {ok_count} 個工項金額核對無誤。', False

    def _parse_xml_and_validate(self):
        """解析 XML 並做前置驗證，回傳 items_data。共用於 preview 與 confirm。"""
        if not self.xml_file:
            raise UserError('請先上傳 XML 檔案')
        if not self.project_id:
            raise UserError('工程案件未關聯專案，無法建立工項')
        try:
            xml_data = base64.b64decode(self.xml_file)
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            raise UserError(f'XML 解析失敗：{str(e)}')
        except Exception as e:
            raise UserError(f'處理檔案時發生錯誤：{str(e)}')
        if 'ETenderSheet' not in root.tag:
            raise UserError('檔案格式錯誤：必須是 ETenderSheet 格式的 XML 檔案')
        items_data = self._parse_pay_items(root)
        if not items_data:
            raise UserError('未解析到任何工項資料')
        leaf_items = [item for item in items_data if not item.get('has_children')]
        if leaf_items and all(item.get('unit_price', 0) == 0 for item in leaf_items):
            raise UserError(
                '此為空白標單（所有末端工項的單價皆為 0），無法匯入。\n'
                '請上傳含有單價的標單檔案。'
            )
        return items_data

    # === 解析 XML ===
    def _parse_pay_items(self, root, parent_item_key='', level=0):
        """
        遞迴解析 PayItem

        返回格式：
        [
            {
                'item_key': '1',          # XML itemKey（唯一整數，用於父子關係追蹤）
                'item_no': '壹',           # XML itemNo（完整項次編號）
                'name': '發包工程費',
                'unit': '式',
                'quantity': 1,
                'unit_price': 0,
                'amount': 0,
                'remark': '[發包]',
                'level': 0,
                'parent_item_key': '',    # 父節點的 itemKey
                'ref_item_code': '',
                'item_kind': 'mainItem',  # PCCES 的節點種類；'subtotal' = 小計列
                'has_children': True,
            },
            ...
        ]
        """
        items = []

        # 找到 DetailList
        ns = {'ns': 'http://pcstd.pcc.gov.tw/2003/eTender'}
        detail_list = root.find('.//ns:DetailList', ns)

        if detail_list is None:
            return items

        # 解析所有 PayItem
        items = self._parse_pay_item_recursive(detail_list, ns, parent_item_key, level)

        return items

    def _parse_pay_item_recursive(self, element, ns, parent_item_key='', level=0):
        """遞迴解析 PayItem，以 itemKey 作為父子關係的唯一識別"""
        items = []

        for pay_item in element.findall('ns:PayItem', ns):
            # 取得基本資訊
            item_key = pay_item.get('itemKey', '')      # 唯一識別（用於 task_map）
            item_no = pay_item.get('itemNo', '')         # 完整項次編號
            ref_item_code = pay_item.get('refItemCode', '').strip()
            # PCCES 會把詳細價目表裡「沒有項次的小計列」也匯出成 PayItem，
            # 靠 itemKind="subtotal" 區分（實測 7 份標單：出現時一律是頂層的
            # 「總價(總計)」，從沒用在真工項上；也有整份標單完全沒有這個節點的）。
            # 它的金額是「壹 發包工程費」的重複，建成一般工項會讓契約金額變兩倍。
            item_kind = pay_item.get('itemKind', '')

            # 取得中文描述
            desc_elem = pay_item.find('ns:Description[@language="zh-TW"]', ns)
            name = desc_elem.text if desc_elem is not None else ''

            # 取得單位
            unit_elem = pay_item.find('ns:Unit[@language="zh-TW"]', ns)
            unit = unit_elem.text if unit_elem is not None else ''

            # 取得數量
            qty_elem = pay_item.find('ns:Quantity', ns)
            quantity = float(qty_elem.text) if qty_elem is not None and qty_elem.text else 0

            # 取得單價
            price_elem = pay_item.find('ns:Price', ns)
            unit_price = float(price_elem.text) if price_elem is not None and price_elem.text else 0

            # 取得複價
            amount_elem = pay_item.find('ns:Amount', ns)
            amount = float(amount_elem.text) if amount_elem is not None and amount_elem.text else 0

            # 取得備註
            remark_elem = pay_item.find('ns:Remark', ns)
            remark = remark_elem.text if remark_elem is not None else ''

            # 取得稅什費比例（官方電子標單專屬欄位）
            percent_elem = pay_item.find('ns:Percent', ns)
            percent = float(percent_elem.text) if percent_elem is not None and percent_elem.text else 0.0

            # 檢查是否有子項目
            child_pay_items = pay_item.findall('ns:PayItem', ns)
            has_children = len(child_pay_items) > 0

            # 建立項目資料
            item_data = {
                'item_key': item_key,
                'item_no': item_no,
                'name': name,
                'unit': unit,
                'quantity': quantity,
                'unit_price': unit_price,
                'amount': amount,
                'remark': remark,
                'percent': percent,
                'level': level,
                'parent_item_key': parent_item_key,
                'ref_item_code': ref_item_code,
                'item_kind': item_kind,
                'has_children': has_children,
            }

            items.append(item_data)

            # 遞迴解析子項目，傳遞本節點的 itemKey 作為子節點的父參考
            if has_children:
                child_items = self._parse_pay_item_recursive(
                    pay_item, ns, item_key, level + 1
                )
                items.extend(child_items)

        return items

    def _existing_tasks(self):
        """此工程既有的契約工項（含封存的，避免看不到卻撞到）。"""
        return self.env['project.task'].with_context(active_test=False).search(
            [('project_id', '=', self.project_id.id)])

    def action_preview(self):
        """預覽金額核對報告（不建立任何工項）"""
        self.ensure_one()
        items_data = self._parse_xml_and_validate()
        report, has_warning = self._compute_reconciliation_from_items(items_data)

        # 重複匯入防呆：先看這個工程是不是已經有工項了
        existing = self._existing_tasks()
        blocking = self._find_task_references(existing) if existing else []
        blocking_text = '\n'.join(
            '・%s：%d 筆' % (label, count) for label, count in blocking) or False

        self.write({
            'state': 'previewing',
            'preview_count': len(items_data),
            'validation_report': report,
            'has_validation_warning': has_warning,
            'existing_task_count': len(existing),
            'has_blocking_reference': bool(blocking),
            'blocking_reference_info': blocking_text,
            'confirm_overwrite': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_reset_upload(self):
        """清除預覽結果，回到上傳狀態"""
        self.write({
            'state': 'upload',
            'validation_report': False,
            'has_validation_warning': False,
            'preview_count': 0,
            'existing_task_count': 0,
            'has_blocking_reference': False,
            'blocking_reference_info': False,
            'confirm_overwrite': False,
            'import_note': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm_import(self):
        """確認匯入：建立工項並顯示結果"""
        self.ensure_one()
        items_data = self._parse_xml_and_validate()
        notes = []

        # ── 重複匯入防呆：權威在這裡，不是在 view 的 invisible ──────────────
        # （view 只是 UX；程式路徑／RPC 一樣走得到這個方法）
        existing = self._existing_tasks()
        if existing:
            blocking = self._find_task_references(existing)
            if blocking:
                raise UserError(
                    '此工程已有 %d 個契約工項，而且還有單據正在引用它們，無法覆蓋：\n%s\n\n'
                    '請先處理（或刪除）這些單據，再重新匯入標單。'
                    % (len(existing),
                       '\n'.join('・%s：%d 筆' % (label, count)
                                 for label, count in blocking)))
            if not self.confirm_overwrite:
                raise UserError(
                    '此工程已有 %d 個契約工項。\n\n'
                    '若要以本次上傳的檔案重建，請回到「金額核對預覽」頁勾選\n'
                    '「我確認要刪除既有工項，並以本次上傳的檔案重建」後再按確認匯入。\n\n'
                    '（沒有這道確認的話，再按一次匯入會整套重建，契約金額會變成兩倍）'
                    % len(existing))
            removed = len(existing)
            existing.unlink()
            notes.append('已刪除既有契約工項 %d 筆（覆蓋匯入）。' % removed)

        # 建立工項
        created_tasks, create_notes = self._create_tasks(items_data)
        notes.extend(create_notes)

        # 儲存原始 XML 供後續契約變更 XLSX 匯入使用
        if self.xml_file:
            self.project_id.write({
                'tender_xml_data': self.xml_file,
                'tender_xml_filename': self.xml_filename or 'tender.xml',
            })

        # 更新統計，使用 previewing 階段已計算好的核對報告
        self.write({
            'state': 'done',
            'imported_count': len(created_tasks),
            'import_note': '\n'.join(notes) or False,
            'existing_task_count': 0,
            'confirm_overwrite': False,
        })

        # 無差異 → 導航到工項列表；有差異 → 留在 wizard done 頁顯示報告
        if not self.has_validation_warning:
            tree_view_id = self.env.ref(
                'construction_supervision_base.view_task_tree_project_specific').id
            return {
                'type': 'ir.actions.act_window',
                'name': f'{self.project_id.name} - 契約工項',
                'res_model': 'project.task',
                'view_mode': 'list,form',
                'views': [(tree_view_id, 'list'), (False, 'form')],
                'domain': [('id', 'in', created_tasks.ids)],
                'context': {'default_project_id': self.project_id.id},
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_task_list(self):
        """從 done 頁導航至剛匯入的工項列表"""
        self.ensure_one()
        tree_view_id = self.env.ref(
            'construction_supervision_base.view_task_tree_project_specific').id
        tasks = self.env['project.task'].search([
            ('project_id', '=', self.project_id.id),
            ('active', '=', True),
        ])
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.project_id.name} - 契約工項',
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'views': [(tree_view_id, 'list'), (False, 'form')],
            'domain': [('id', 'in', tasks.ids)],
            'context': {
                'default_project_id': self.project_id.id,
            },
            'target': 'current',
        }

    def _create_tasks(self, items_data):
        """建立工項記錄，回傳 (created_tasks, notes)。

        notes 是「系統自動替使用者做掉的事」的清單（小計列勾不計入、
        比例基數回填、解析不出來而留空…），由呼叫端寫進 import_note 顯示出來。
        """
        Task = self.env['project.task']
        created_tasks = Task.browse()
        notes = []

        # 以 itemKey（XML 唯一整數）作為 key，避免 itemNo 重複導致父子關係錯亂
        task_map = {}

        # 單位標準化與 uom 解析改用共用方法（project.task._normalize_unit_display /
        # _resolve_uom_id），與契約變更、成本分析共用同一份，確保全系統一致。

        # 預建立 product cache：批次查詢已存在的 product（以 default_code 為鍵）
        all_ref_codes = {
            item.get('ref_item_code', '').strip()
            for item in items_data
            if item.get('ref_item_code', '').strip()
        }
        product_cache = {}
        if all_ref_codes:
            existing_products = self.env['product.product'].search_read(
                [('default_code', 'in', list(all_ref_codes))],
                ['id', 'default_code', 'uom_id']
            )
            for p in existing_products:
                product_cache[p['default_code']] = p
            # 批次確保已存在的 product 都標記為標準工項
            if existing_products:
                existing_ids = [p['id'] for p in existing_products]
                self.env['product.product'].browse(existing_ids).mapped(
                    'product_tmpl_id').write({'is_standard_work_item': True})

        # 按順序賦予 sequence 值，從 10 開始，每次遞增 10
        for index, item in enumerate(items_data, start=1):
            item_key = item.get('item_key', '')
            parent_item_key = item.get('parent_item_key', '')
            unit_name = item.get('unit', '')
            ref_code = item.get('ref_item_code', '').strip()

            # 標準化顯示單位 + 解析 uom_id（共用方法：精確→別名→模糊→自動建立）
            display_unit = Task._normalize_unit_display(unit_name)
            uom_id = Task._resolve_uom_id(display_unit)

            # 對應或建立 product.product（僅有 ref_item_code 時處理）
            product_id = False
            if ref_code:
                if ref_code not in product_cache:
                    # 找不到則自動建立服務型 product
                    new_product = self.env['product.product'].create({
                        'name': item.get('name', ''),
                        'default_code': ref_code,
                        'type': 'service',
                        'uom_id': uom_id or False,
                        'uom_po_id': uom_id or False,
                        'is_standard_work_item': True,
                    })
                    product_cache[ref_code] = {
                        'id': new_product.id,
                        'default_code': ref_code,
                        'uom_id': (uom_id, unit_name) if uom_id else False,
                    }
                cached = product_cache[ref_code]
                product_id = cached['id']
                # ⚠️ 不再「以 product 的 uom 為準」：unit_id 一律由標單單位解析，
                #    避免 ref_item_code 不可靠時把錯 product 的單位帶進 unit_id。

            # 準備工項資料（item_level 由 compute 自動計算，無需傳入）
            task_vals = {
                'project_id': self.project_id.id,
                'name': item.get('name', ''),
                'item_no': item.get('item_no', ''),
                'sequence': index * 10,
                'unit': display_unit,
                'unit_id': uom_id,
                'product_id': product_id,
                'planned_qty': item.get('quantity', 0),
                'unit_price': item.get('unit_price', 0),
                'xml_amount': item.get('amount', 0),
                'construction_notes': item.get('remark', ''),
                'tax_misc_rate': item.get('percent', 0) or 0.0,
                'ref_item_code': ref_code or item.get('ref_item_code', ''),
                # description（「說明」）與 construction_notes（「施工說明」）是
                # 兩個不同的 Odoo 欄位，來源同樣是詳細價目表的備註欄。
                # xlsx 匯入那條路兩個都寫，這裡本來只寫後者 —— 補齊才一致。
                # description 是 Html 欄位：先 escape 再包 <p>，否則備註裡的
                # 「網目<4.5CM」這種字會被 sanitizer 當標籤吃掉。
                'description': self._remark_to_html(item.get('remark', '')),
                # 小計列（PCCES 的 itemKind="subtotal"）：金額是「壹」的重複，
                # 建起來但標「不計入契約金額」，契約金額才不會變兩倍。
                # _compute_planned_amount 與 _compute_contract_amount 兩層都看
                # 這個旗標，所以巢狀的小計列也擋得住。
                'exclude_from_contract_amount': item.get('item_kind') == 'subtotal',
            }

            # 以 itemKey 查找父節點，保留階層結構
            if parent_item_key:
                parent_task = task_map.get(parent_item_key)
                if parent_task:
                    task_vals['parent_id'] = parent_task.id

            # 建立任務
            task = Task.create(task_vals)
            created_tasks |= task

            # 以 itemKey 記錄，確保唯一性
            if item_key:
                task_map[item_key] = task

        # ── 稅什費比例計算 ────────────────────────────────────────
        # 找到名稱含「稅什費」的工項，計算其佔同層前置項目的比例 N%
        # N = 稅什費.xml_amount ÷ sum(同層 sequence 較小的項目 xml_amount) × 100
        self._compute_tax_misc_rate(created_tasks)

        # ── 比例基數回填 ────────────────────────────────────────────
        # 必須排在 _compute_tax_misc_rate 之後（要先知道誰是比例項），
        # 也必須在整批建立完成之後（要有同層前置工項可以指）。
        notes.extend(self._apply_rate_bases(created_tasks, items_data))

        # ── 整包費用項標記 ──────────────────────────────────────────
        # 必須排在 _compute_tax_misc_rate 之後：稅什費的比例要先寫進去，
        # _mark_lump_sum_items 才排除得掉它（比例項不該被標成整包項）。
        # 也必須在整批建立完成之後 —— 建立過程中子項還不存在，判不出「無子項」。
        Task._mark_lump_sum_items(created_tasks)

        # ── 小計列的留痕 ────────────────────────────────────────────
        subtotal_tasks = created_tasks.filtered('exclude_from_contract_amount')
        if subtotal_tasks:
            notes.append(
                '標單的小計列（itemKind="subtotal"）%d 筆已自動勾「不計入契約金額」：%s'
                % (len(subtotal_tasks),
                   '、'.join('%s %s' % (t.item_no or '', t.name) for t in subtotal_tasks)))

        return created_tasks, notes

    def _compute_tax_misc_rate(self, tasks):
        """
        計算並儲存稅什費比例（N%）。

        三段優先：
        1. XML <Percent> 欄位 > 0（官方電子標單）→ 建立 task 時已寫入，此處跳過
        2. 備註含 N% 格式（自行轉檔但備註完整）→ regex 解析
        3. 反推算（自行轉檔且備註遺失）→ xml_amount ÷ 同層前置加總
        """
        import re as _re
        tax_tasks = tasks.filtered(lambda t: '稅什費' in (t.name or '') or '稅雜費' in (t.name or ''))
        for tax_task in tax_tasks:
            # 優先 1：<Percent> 已在建立 task 時寫入 tax_misc_rate，直接跳過
            if tax_task.tax_misc_rate:
                continue

            # 優先 2：備註含 N% 格式（如 "(一~八*約10.95%)" 或 "(一)~(七) × 3.5%"）
            remark = tax_task.construction_notes or ''
            m = _re.search(r'([\d.]+)\s*%', remark)
            if m:
                n_pct = float(m.group(1))
                tax_task.write({'tax_misc_rate': n_pct})
                continue

            # 優先 3：反推算（備註遺失時的 fallback）
            domain = [
                ('id', 'in', tasks.ids),
                ('sequence', '<', tax_task.sequence),
            ]
            if tax_task.parent_id:
                domain.append(('parent_id', '=', tax_task.parent_id.id))
            else:
                domain.append(('parent_id', '=', False))

            preceding = self.env['project.task'].search(domain)
            base_sum = sum(t.xml_amount for t in preceding)

            if not base_sum:
                continue  # 分母為 0，無法計算

            n_pct = (tax_task.xml_amount / base_sum) * 100.0
            tax_task.write({'tax_misc_rate': n_pct})
