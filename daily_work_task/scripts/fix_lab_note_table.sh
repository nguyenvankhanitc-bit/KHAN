#!/bin/bash
# Tạo bảng daily_work_note trên lab khi model đã load nhưng thiếu table.
set -euo pipefail

echo "===== 1) Tạo bảng + ACL ====="
docker exec -i odoo-db-1 psql -U odoo -d master <<'SQL'
CREATE TABLE IF NOT EXISTS daily_work_note (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    note_date DATE NOT NULL,
    user_id INTEGER NOT NULL REFERENCES res_users(id) ON DELETE CASCADE,
    create_uid INTEGER,
    create_date TIMESTAMP WITHOUT TIME ZONE,
    write_uid INTEGER,
    write_date TIMESTAMP WITHOUT TIME ZONE
);
CREATE INDEX IF NOT EXISTS daily_work_note__note_date_index ON daily_work_note (note_date);
CREATE INDEX IF NOT EXISTS daily_work_note__user_id_index ON daily_work_note (user_id);

INSERT INTO ir_model (model, name, state, transient, info)
SELECT 'daily.work.note', 'Ghi chú công việc', 'manual', false, NULL
WHERE NOT EXISTS (SELECT 1 FROM ir_model WHERE model = 'daily.work.note');

INSERT INTO ir_model_access (name, model_id, group_id, perm_read, perm_write, perm_create, perm_unlink, active)
SELECT 'daily.work.note all users', m.id, NULL, true, true, true, true, true
FROM ir_model m
WHERE m.model = 'daily.work.note'
  AND NOT EXISTS (
      SELECT 1 FROM ir_model_access a WHERE a.model_id = m.id AND a.name = 'daily.work.note all users'
  );
SQL

echo "===== 2) Đồng bộ model qua Odoo shell ====="
docker exec -u odoo -i odoo-odoo19-1 odoo shell -c /etc/odoo/odoo.conf -d master --no-http <<'PY'
model_name = "daily.work.note"
if model_name in env:
    env.registry.init_models(env.cr, [model_name], {"module": "daily_work_task"})
    env.cr.commit()
    print("INIT_OK", env[model_name]._table, env[model_name].search_count([]))
else:
    print("MODEL_NOT_IN_REGISTRY")
PY

echo "===== 3) Kiểm tra ====="
docker exec odoo-db-1 psql -U odoo -d master -c "\dt daily_work_note"
docker exec odoo-db-1 psql -U odoo -d master -c "SELECT count(*) AS notes FROM daily_work_note;"
docker restart odoo-odoo19-1
echo "DONE — Ctrl+F5 trang Ghi chú"
