import json
sa=env.ref('construction_supervision_base.group_supervisor_admin'); op=env.ref('construction_supervision_base.group_operator')
out={}
for tag,g in (('sa',sa),('op',op)):
    out[tag+'_acl']=sorted(f"{a.model_id.model}|{a.perm_read}{a.perm_write}{a.perm_create}{a.perm_unlink}|{a.active}" for a in env['ir.model.access'].with_context(active_test=False).search([('group_id','=',g.id)]))
    out[tag+'_rule']=sorted(f"{r.model_id.model}|{r.domain_force}|{r.perm_read}{r.perm_write}{r.perm_create}{r.perm_unlink}|{r.active}" for r in env['ir.rule'].with_context(active_test=False).search([('groups','in',g.id)]))
    out[tag+'_trans']=sorted(x.get_external_id()[x.id] for x in g.trans_implied_ids)
u6=env['res.users'].browse(6); u2=env['res.users'].browse(2)
out['u6_groups']=sorted(x.get_external_id()[x.id] or str(x.id) for x in u6.groups_id)
out['u2_groups']=sorted(x.get_external_id()[x.id] or str(x.id) for x in u2.groups_id)
out['u2_action']=u2.action_id.id; out['u6_action']=u6.action_id.id
open('/tmp/'+SNAPNAME,'w').write(json.dumps(out,ensure_ascii=False,indent=1))
print('SNAP', {k:len(v) if isinstance(v,list) else v for k,v in out.items()})
