# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class PhotoSyncMixin(models.AbstractModel):
    """
    照片自動同步 Mixin
    
    功能：
    - 讓其他模組的照片自動建檔到 supervision.photo
    - 提供統一的同步機制
    - 支援多種照片欄位（缺失照片、改善照片、檢查照片等）
    
    使用方式：
    1. 繼承此 Mixin：_inherit = ['your.model', 'photo.sync.mixin']
    2. 實作 _get_photo_sync_config() 方法來定義同步規則
    """
    _name = 'photo.sync.mixin'
    _description = '照片自動同步混入'
    
    def _get_photo_sync_config(self):
        """
        子類別需實作：定義哪些欄位要同步到 supervision.photo
        
        回傳格式：
        {
            'photo_field_name': {
                'source_model': str,           # 必填：來源類型
                'name_prefix': str,            # 必填：照片說明的前綴
                'description_field': str,      # 選填：要複製的欄位名稱
                'description_template': str,   # 選填：自訂說明模板
                'location_field': str,         # 選填：位置欄位名稱
            }
        }
        """
        return {}
    
    def write(self, vals):
        """攔截 write 方法，自動同步照片"""
        result = super().write(vals)
        
        sync_config = self._get_photo_sync_config()
        if not sync_config:
            return result
        
        for field_name, config in sync_config.items():
            if field_name in vals:
                try:
                    self._auto_sync_photos(field_name, config)
                except Exception as e:
                    _logger.warning(
                        f'照片同步失敗 - Model: {self._name}, '
                        f'Field: {field_name}, Error: {str(e)}'
                    )
        
        return result
    
    @api.model_create_multi
    def create(self, vals_list):
        """建立記錄時也要同步照片"""
        records = super().create(vals_list)
        
        sync_config = records._get_photo_sync_config()
        if not sync_config:
            return records
        
        for record in records:
            for field_name, config in sync_config.items():
                if hasattr(record, field_name) and getattr(record, field_name):
                    try:
                        record._auto_sync_photos(field_name, config)
                    except Exception as e:
                        _logger.warning(
                            f'建立時照片同步失敗 - Model: {record._name}, '
                            f'ID: {record.id}, Field: {field_name}, Error: {str(e)}'
                        )
        
        return records
    
    def _auto_sync_photos(self, field_name, config):
        """自動同步照片到 supervision.photo"""
        SupervisionPhoto = self.env['supervision.photo']
        
        for record in self:
            if not hasattr(record, 'project_id') or not record.project_id:
                _logger.debug(
                    f'跳過同步：記錄沒有 project_id - '
                    f'Model: {record._name}, ID: {record.id}'
                )
                continue
            
            attachments = getattr(record, field_name, False)
            if not attachments:
                continue
            
            for attachment in attachments:
                existing = SupervisionPhoto.search([
                    ('attachment_id', '=', attachment.id)
                ], limit=1)
                
                if existing:
                    _logger.debug(
                        f'照片已存在，跳過同步 - Attachment ID: {attachment.id}'
                    )
                    continue
                
                photo_vals = record._prepare_photo_vals(attachment, config)
                
                if photo_vals:
                    new_photo = SupervisionPhoto.create(photo_vals)
                    _logger.info(
                        f'照片自動同步成功 - Photo ID: {new_photo.id}, '
                        f'Source: {record._name}#{record.id}, '
                        f'Attachment: {attachment.name}'
                    )
    
    def _prepare_photo_vals(self, attachment, config):
        """準備建立 supervision.photo 的資料"""
        self.ensure_one()
        
        name_prefix = config.get('name_prefix', '照片')
        record_name = getattr(self, 'name', '') or f'ID:{self.id}'
        description = f'{name_prefix} - {record_name}'
        
        notes = None
        if config.get('description_template'):
            try:
                notes = config['description_template'].format(record=self)
            except Exception as e:
                _logger.warning(f'模板格式化失敗: {str(e)}')
        elif config.get('description_field'):
            field_name = config['description_field']
            if hasattr(self, field_name):
                field_value = getattr(self, field_name)
                if field_value:
                    notes = str(field_value)
        
        vals = {
            'description': description,
            'project_id': self.project_id.id,
            'attachment_id': attachment.id,
            'source_model': config.get('source_model', 'other'),
            'source_id': self.id,
            'shot_at': fields.Datetime.now(),
        }
        
        if notes:
            vals['notes'] = notes
        
        if config.get('location_field'):
            location_field = config['location_field']
            if hasattr(self, location_field):
                location_value = getattr(self, location_field)
                if location_value:
                    vals['location_description'] = str(location_value)
        
        return vals
