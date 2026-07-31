# -*- coding: utf-8 -*-

# photo_sync_mixin 已隨照片資料表收斂刪除：照片就是 supervision.photo 本身，
# 不再需要把來源模型的附件「同步」成一份副本。
from . import supervision_photo_tag
from . import supervision_photo_category
from . import supervision_photo
from . import supervision_project
