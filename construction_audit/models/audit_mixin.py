# -*- coding: utf-8 -*-

from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class AuditTrailMixin(models.AbstractModel):
    """
    稽核軌跡 Mixin

    設計特點：
    - 供其他模型繼承，自動記錄操作軌跡
    - 自動追蹤建立、修改、狀態變更、刪除
    - 可配置追蹤的欄位
    - 不影響原有業務邏輯

    使用方式：
    class MyModel(models.Model):
        _name = 'my.model'
        _inherit = ['audit.trail.mixin']

        # 可選：指定要追蹤的欄位
        _audit_track_fields = ['name', 'state', 'amount']

        # 可選：指定狀態欄位名稱
        _audit_state_field = 'state'
    """
    _name = 'audit.trail.mixin'
    _description = '稽核軌跡 Mixin'

    # 預設追蹤的欄位（子類可覆寫）
    _audit_track_fields = []

    # 狀態欄位名稱（子類可覆寫）
    _audit_state_field = 'state'

    # 是否啟用稽核追蹤
    _audit_enabled = True

    def _get_audit_track_fields(self):
        """取得要追蹤的欄位列表"""
        if self._audit_track_fields:
            return self._audit_track_fields

        # 預設追蹤有 tracking=True 的欄位
        tracked_fields = []
        for field_name, field in self._fields.items():
            if getattr(field, 'tracking', False):
                tracked_fields.append(field_name)

        return tracked_fields

    def _get_field_value_for_audit(self, field_name):
        """取得欄位值用於稽核記錄"""
        self.ensure_one()
        field = self._fields.get(field_name)
        if not field:
            return None

        value = getattr(self, field_name, None)

        if field.type == 'many2one':
            if value:
                return {'id': value.id, 'display_name': value.display_name}
            return None
        elif field.type in ('many2many', 'one2many'):
            if value:
                return value.ids
            return []
        elif field.type == 'binary':
            # 不記錄二進位資料
            return '[Binary Data]' if value else None
        elif field.type == 'html':
            # 簡化 HTML 內容
            if value and len(str(value)) > 500:
                return str(value)[:500] + '...'
            return value
        else:
            return value

    def _get_record_name_for_audit(self):
        """取得記錄名稱用於稽核記錄"""
        self.ensure_one()
        try:
            return self.display_name or self.name_get()[0][1]
        except Exception:
            return f'{self._name},{self.id}'

    def _should_audit(self):
        """檢查是否應該記錄稽核軌跡"""
        # 檢查是否啟用
        if not self._audit_enabled:
            return False

        # 檢查是否在批次匯入等情境中
        if self.env.context.get('skip_audit'):
            return False

        # 檢查稽核模組是否安裝
        if 'audit.trail' not in self.env:
            return False

        return True

    def _log_audit_create(self):
        """記錄建立操作"""
        if not self._should_audit():
            return

        AuditTrail = self.env['audit.trail']
        track_fields = self._get_audit_track_fields()

        for record in self:
            try:
                new_values = {}
                for field_name in track_fields:
                    if field_name in record._fields:
                        new_values[field_name] = record._get_field_value_for_audit(field_name)

                AuditTrail.log_operation(
                    model_name=record._name,
                    res_id=record.id,
                    operation_type='create',
                    new_values=new_values,
                    res_name=record._get_record_name_for_audit(),
                    changed_fields=list(new_values.keys()),
                )
            except Exception as e:
                _logger.warning(f'Failed to log audit trail for create: {e}')

    def _log_audit_write(self, old_values_dict, changed_fields_dict):
        """記錄修改操作"""
        if not self._should_audit():
            return

        AuditTrail = self.env['audit.trail']
        state_field = self._audit_state_field

        for record in self:
            try:
                old_values = old_values_dict.get(record.id, {})
                changed_fields = changed_fields_dict.get(record.id, [])

                if not changed_fields:
                    continue

                # 取得新值
                new_values = {}
                for field_name in changed_fields:
                    if field_name in record._fields:
                        new_values[field_name] = record._get_field_value_for_audit(field_name)

                # 判斷是否為狀態變更
                old_state = None
                new_state = None
                operation_type = 'write'

                if state_field in changed_fields:
                    old_state = old_values.get(state_field)
                    new_state = new_values.get(state_field)
                    operation_type = 'state_change'

                AuditTrail.log_operation(
                    model_name=record._name,
                    res_id=record.id,
                    operation_type=operation_type,
                    old_values=old_values,
                    new_values=new_values,
                    old_state=old_state,
                    new_state=new_state,
                    res_name=record._get_record_name_for_audit(),
                    changed_fields=changed_fields,
                )
            except Exception as e:
                _logger.warning(f'Failed to log audit trail for write: {e}')

    def _log_audit_unlink(self):
        """記錄刪除操作"""
        if not self._should_audit():
            return

        AuditTrail = self.env['audit.trail']
        track_fields = self._get_audit_track_fields()

        for record in self:
            try:
                old_values = {}
                for field_name in track_fields:
                    if field_name in record._fields:
                        old_values[field_name] = record._get_field_value_for_audit(field_name)

                AuditTrail.log_operation(
                    model_name=record._name,
                    res_id=record.id,
                    operation_type='unlink',
                    old_values=old_values,
                    res_name=record._get_record_name_for_audit(),
                )
            except Exception as e:
                _logger.warning(f'Failed to log audit trail for unlink: {e}')

    @api.model_create_multi
    def create(self, vals_list):
        """覆寫建立方法，記錄稽核軌跡"""
        records = super().create(vals_list)
        records._log_audit_create()
        return records

    def write(self, vals):
        """覆寫修改方法，記錄稽核軌跡"""
        if not self._should_audit():
            return super().write(vals)

        # 記錄修改前的值
        track_fields = self._get_audit_track_fields()
        old_values_dict = {}
        changed_fields_dict = {}

        for record in self:
            old_values = {}
            changed_fields = []

            for field_name in track_fields:
                if field_name in vals and field_name in record._fields:
                    old_values[field_name] = record._get_field_value_for_audit(field_name)
                    changed_fields.append(field_name)

            if changed_fields:
                old_values_dict[record.id] = old_values
                changed_fields_dict[record.id] = changed_fields

        # 執行實際修改
        result = super().write(vals)

        # 記錄稽核軌跡
        if old_values_dict:
            self._log_audit_write(old_values_dict, changed_fields_dict)

        return result

    def unlink(self):
        """覆寫刪除方法，記錄稽核軌跡"""
        self._log_audit_unlink()
        return super().unlink()
