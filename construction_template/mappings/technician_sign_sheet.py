# -*- coding: utf-8 -*-
"""施工日誌之技術士簽章表（新北市政府工程契約 附表9-1 附件，沒有表頭欄位、全部手填）——只帶表頭，見 project_header.py。"""

from .project_header import MODEL, MODE, build_context, filename_for  # noqa: F401

FILENAME = filename_for('施工日誌之技術士簽章表')
