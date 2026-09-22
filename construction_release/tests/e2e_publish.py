# -*- coding: utf-8 -*-
"""端到端第二步：檢查部署並發布（會 commit）。"""
import json

cfg = json.load(open('/tmp/e2e_release.json'))
admin = env.ref('base.user_admin')
rel = env['construction.release'].with_user(admin).browse(cfg['release_id'])
dep = env['construction.deployment'].browse(rel.action_check_deployment()['res_id'])
print('DEPLOY', dep.result, dep.mismatch_count, dep.half_count)
rel.action_publish()
env.cr.commit()
print('PUBLISH OK', rel.name, rel.state, rel.publish_datetime)
