# Shared technical keys for handover workflow on hr.leave.

HANDOVER_ACTIVITY_XMLID = "time_off_work_handover.mail_act_leave_work_handover"
HANDOVER_ACTIVE_STATES = ("confirm", "validate1")
SKIP_SUBMIT_BOT_NOTIFY_CTX = "skip_handover_submit_bot_notify"
# Same key as time_off_responsible_approval (handover cancel must not double-notify outcome).
SKIP_OUTCOME_BOT_NOTIFY_CTX = "skip_outcome_bot_notify"
# Public-holiday create/write re-evaluates overlapping hr.leave rows — skip side effects.
SKIP_HANDOVER_CONSTRAINTS_ON_LEAVE_SYNC_CTX = "skip_handover_constraints_on_leave_sync"
PUBLIC_HOLIDAY_LEAVE_SYNC_CONTEXT = {
    SKIP_HANDOVER_CONSTRAINTS_ON_LEAVE_SYNC_CTX: True,
    "skip_outcome_bot_notify": True,
    "skip_responsible_submit_notify": True,
    "skip_handover_submit_bot_notify": True,
}

HANDOVER_ESCALATION_MINUTES = 5
HANDOVER_ESCALATION_TO_MANAGER_HOURS = 2
DEPARTMENT_HEAD_JOB_TITLE_KEY = "trưởng bộ phận"
DEPARTMENT_MANAGER_JOB_TITLE_KEY = "trưởng phòng"

# Miền Bắc / Nam / ĐTT: chỉ Nhóm trưởng và Cửa hàng trưởng bắt buộc bàn giao công việc.
STORE_REGION_HANDOVER_MIEN_CODES = frozenset({"Bắc", "Nam", "ĐTT"})
STORE_LEADER_HANDOVER_REQUIRED_JOB_TITLE_KEYS = frozenset(
    {"nhom truong", "cua hang truong"}
)
