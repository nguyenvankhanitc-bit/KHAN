#!/usr/bin/env sh
set -eu

DB_NAME="${DB_NAME:-odoo_db}"
MODULES="${MODULES:-hr_employee_multi_responsible,hr_employee_hrm_detail,hr_leave_mien_tenure_unpaid,time_off_extra_approval,time_off_responsible_approval,hr_job_title_vn,hr_employee_cccd_scan,hr_employee_self_only,business_discuss_bots}"

echo "Updating modules on database: ${DB_NAME}"
echo "IMPORTANT: hr_employee_hrm_detail must upgrade after every pull (visibility_policy schema)."
docker compose -f deploy/docker-compose.yml exec -T odoo \
  odoo -c /etc/odoo/odoo.conf -d "${DB_NAME}" -u "${MODULES}" --stop-after-init

echo "Post-deploy update done."
echo "If res_users column errors persist, run:"
echo "  docker compose -f deploy/docker-compose.yml exec -T odoo odoo shell -c /etc/odoo/odoo.conf -d ${DB_NAME} --no-http < scripts/repair_visibility_schema.py"
