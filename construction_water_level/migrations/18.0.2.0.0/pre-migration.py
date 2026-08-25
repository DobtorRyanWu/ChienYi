# -*- coding: utf-8 -*-
"""v2 新增「監測場域」層：升級前先把表建好、資料補齊。

為什麼要在 pre-migration 做，而不是讓 Odoo 建完表再用 post-migration 回填：
  device.site_id 是 required 欄位。Odoo 建欄位時若表內已有資料列，會發現無法
  設 NOT NULL，只印一行 warning 就放過，欄位留成可空——升級「成功」但約束沒生效，
  而且要再跑一次 -u 才會補上。與其依賴「跑兩次」，不如在 Odoo 讀 model 之前
  就把欄位填好，NOT NULL 一次到位。

做三件事，全部冪等：
  1. 建 water_level_site 表（欄位與 model 對齊，缺的 Odoo 之後會自己補）
  2. 現有設備的每個 distinct 工程案件建一個「工程」型場域
  3. device 加 site_id 欄位並回填

不刪任何東西。project_project.name 是 jsonb（可翻譯欄位），取值要用 ->> 不能直接塞。
"""

import logging

_logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 730


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        CREATE TABLE IF NOT EXISTS water_level_site (
            id serial PRIMARY KEY,
            name varchar NOT NULL,
            code varchar,
            active boolean DEFAULT true,
            site_type varchar NOT NULL DEFAULT 'project',
            project_id integer,
            owner_partner_id integer,
            retention_days integer DEFAULT %s,
            latitude numeric,
            longitude numeric,
            address varchar,
            create_uid integer,
            create_date timestamp without time zone,
            write_uid integer,
            write_date timestamp without time zone
        )
    """, (DEFAULT_RETENTION_DAYS,))

    # 每個有設備的工程案件建一個場域。名稱取工程名（jsonb 可翻譯欄位），沒有就退回工程編號。
    cr.execute("""
        INSERT INTO water_level_site
            (name, code, site_type, project_id, retention_days,
             active, create_uid, create_date, write_uid, write_date)
        SELECT COALESCE(p.name->>'en_US', p.name->>'zh_TW', p.code, '未命名場域'),
               p.code, 'project', p.id, %s,
               true, 1, now(), 1, now()
          FROM project_project p
         WHERE p.id IN (SELECT DISTINCT project_id
                          FROM water_level_device
                         WHERE project_id IS NOT NULL)
           AND NOT EXISTS (SELECT 1 FROM water_level_site s
                            WHERE s.project_id = p.id AND s.site_type = 'project')
    """, (DEFAULT_RETENTION_DAYS,))
    created = cr.rowcount

    cr.execute("ALTER TABLE water_level_device ADD COLUMN IF NOT EXISTS site_id integer")
    cr.execute("""
        UPDATE water_level_device d
           SET site_id = s.id
          FROM water_level_site s
         WHERE s.project_id = d.project_id
           AND s.site_type = 'project'
           AND d.site_id IS NULL
    """)
    linked = cr.rowcount

    cr.execute("SELECT count(*) FROM water_level_device WHERE site_id IS NULL")
    orphans = cr.fetchone()[0]
    if orphans:
        # 沒有 project_id 又沒有場域的設備：升級會在設 NOT NULL 時失敗，先講清楚。
        raise RuntimeError(
            '有 %s 台設備無法歸到任何場域（project_id 為空）。'
            '請先人工處理再升級。' % orphans)

    _logger.info('水位監測 v2 前置遷移：新建場域 %s 個、回填設備 %s 台', created, linked)
