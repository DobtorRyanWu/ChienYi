# -*- coding: utf-8 -*-
from . import models


def post_init_compute_geo_points(env):
    """安裝後批量計算所有現有照片的 geo_point"""
    photos = env['supervision.photo'].search([
        ('latitude', '!=', 0),
        ('longitude', '!=', 0),
    ])
    if photos:
        photos._compute_geo_point()
