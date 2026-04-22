# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class SupervisionPhotoGeo(models.Model):
    """擴展工程照片 - 新增 GeoPoint 欄位供 GeoEngine 地圖視圖使用"""
    _inherit = 'supervision.photo'

    # GeoPoint 欄位（PostGIS geometry, SRID 3857 Web Mercator）
    geo_point = fields.GeoPoint(
        string='地理位置',
        srid=3857,
        compute='_compute_geo_point',
        inverse='_inverse_geo_point',
        store=True,
    )

    @api.depends('latitude', 'longitude')
    def _compute_geo_point(self):
        """從 latitude/longitude (EPSG:4326) 轉換為 geo_point (EPSG:3857)"""
        for photo in self:
            if photo.latitude and photo.longitude:
                try:
                    photo.geo_point = fields.GeoPoint.from_latlon(
                        self.env.cr, photo.latitude, photo.longitude
                    )
                except Exception as e:
                    _logger.warning(
                        "照片 ID:%s GPS 座標轉換失敗: %s", photo.id, e
                    )
                    photo.geo_point = False
            else:
                photo.geo_point = False

    def _inverse_geo_point(self):
        """從 geo_point (EPSG:3857) 反算 latitude/longitude (EPSG:4326)"""
        for photo in self:
            if photo.geo_point:
                try:
                    # to_latlon 回傳 (longitude, latitude)
                    lng, lat = fields.GeoPoint.to_latlon(
                        self.env.cr, photo.geo_point
                    )
                    photo.latitude = lat
                    photo.longitude = lng
                    photo.gps_location = f"{lat},{lng}"
                except Exception as e:
                    _logger.warning(
                        "照片 ID:%s GeoPoint 反算失敗: %s", photo.id, e
                    )
