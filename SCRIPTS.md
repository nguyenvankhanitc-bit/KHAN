docker exec -it odoo-odoo19-1 odoo -c /etc/odoo/odoo.conf -d odoo_db -u hr_employee_gate_ticket --stop-after-init

cat /var/log/odoo/

docker exec -it odoo-odoo19-1 odoo -c /etc/odoo/odoo.conf -d master -u hr_employee_gate_ticket --i18n-overwrite --stop-after-init --no-http

docker exec -it odoo-db-1 psql -U odoo -d master -c "SELECT model, name, field_description->>'en_US' AS en_us, field_description->>'vi' AS vi, field_description->>'vi_VN' AS vi_vn FROM ir_model_fields WHERE (model='hr.employee.gate.ticket' AND name IN ('approver_id','second_approver_id','check_in','checkout_time')) OR (model='gateway.ticket' AND name IN ('approver_id','second_approver_id','check_in','checkout_time')) OR (model='hr.attendance' AND name IN ('approver_id','second_approver_id','checkout_time')) ORDER BY model, name;"

docker exec -it odoo-db-1 psql -U odoo -d master -c "SELECT code, name, active FROM res_lang WHERE code IN ('vi','vi_VN','en_US');"

docker exec -it odoo-db-1 psql -U odoo -d master -c "SELECT u.login, p.lang, u.active FROM res_users u JOIN res_partner p ON p.id=u.partner_id ORDER BY u.id LIMIT 30;"

docker exec -it odoo-db-1 psql -U odoo -d master -c "SELECT u.login, p.lang FROM res_users u JOIN res_partner p ON p.id=u.partner_id WHERE u.active IS TRUE ORDER BY u.id;"

docker exec -it odoo-db-1 psql -U odoo -d master -c "SELECT latest_version FROM ir_module_module WHERE name='time_off_work_handover';"
