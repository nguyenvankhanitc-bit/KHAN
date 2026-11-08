from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Audit = env['store.audit'].with_context(active_test=False)
    audits = Audit.search([], order='id')
    taken = {}
    for audit in audits:
        prefix = '%s/%s' % (audit.store_id.code or audit.store_id.display_name or 'PHIEU',
                            fields_ts(env, audit.audit_date).strftime('%d%m%Y'))
        taken[prefix] = taken.get(prefix, 0) + 1
        cr.execute("UPDATE store_audit SET name = %s WHERE id = %s", ('%s_%d' % (prefix, taken[prefix]), audit.id))
    audits.invalidate_recordset(['name'])


def fields_ts(env, value):
    from odoo import fields
    return fields.Datetime.context_timestamp(env['store.audit'], value)
