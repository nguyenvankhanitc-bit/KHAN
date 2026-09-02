# -*- coding: utf-8 -*-

from datetime import datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class LinkqStoreNotification(models.AbstractModel):
    _name = "linkq.store.notification"
    _description = "Thông báo cửa hàng (popup)"

    def _user_store_ids(self):
        user = self.env.user
        ids = []
        if "store_id" in user._fields and getattr(user, "store_id", False):
            ids.append(user.store_id.id)
        if hasattr(user, "_linkq_allowed_hr_store_ids"):
            ids.extend(user._linkq_allowed_hr_store_ids() or [])
        return list({i for i in ids if i})

    def _roster_domain(self):
        store_ids = self._user_store_ids()
        if store_ids:
            return [("store_id", "in", store_ids)]
        if self.env.user.has_group("base.group_system") or self.env.user.has_group(
            "lug_phan_he.group_phan_he_admin"
        ):
            return []
        return [("id", "=", 0)]

    def _vn_now(self):
        now = fields.Datetime.now()
        return fields.Datetime.context_timestamp(self, now)

    def _month_deadline_utc(self, year, month):
        """Hạn xếp lịch: ngày cuối tháng lúc 08:00 Asia/Ho_Chi_Minh."""
        tzname = self.env.user.tz or "Asia/Ho_Chi_Minh"
        last = (datetime(year, month, 1) + relativedelta(months=1, days=-1)).date()
        local = datetime.combine(last, time(8, 0))
        try:
            from pytz import timezone, UTC

            aware = timezone(tzname).localize(local)
            return aware.astimezone(UTC).replace(tzinfo=None)
        except Exception:
            return local - timedelta(hours=7)

    def _fmt_vn(self, utc_dt, with_luc=False):
        if not utc_dt:
            return ""
        local = fields.Datetime.context_timestamp(self, utc_dt)
        if with_luc:
            return local.strftime("%d/%m/%Y lúc %H:%M")
        return local.strftime("%d/%m/%Y %H:%M")

    def _next_lock_dt(self, rec, now):
        lock_dt = rec.lock_datetime
        if lock_dt and lock_dt > now:
            return lock_dt
        y = rec.year or fields.Date.context_today(rec).year
        m = int(rec.month or 1)
        utc_dt = rec._period_lock_utc(y, m)
        if utc_dt and utc_dt > now:
            return utc_dt
        today = fields.Date.context_today(self)
        utc_dt = rec._period_lock_utc(today.year, today.month)
        if utc_dt and utc_dt > now:
            return utc_dt
        nm = today.month + 1
        ny = today.year
        if nm > 12:
            nm, ny = 1, ny + 1
        return rec._period_lock_utc(ny, nm)

    def _card_from_roster(self, rec, ntype, now, lock_dt=None):
        slots, first_day = rec._lack_summary()
        staff = rec.line_count or len(rec.line_ids)
        month_n = int(rec.month or 1)
        days = rec.days_in_month or 31
        lock_dt = lock_dt or rec.lock_datetime
        first_date = ""
        shift_span = "14:00 – 18:00"
        morning = rec.lack_morning or []
        evening = rec.lack_evening or []
        if first_day:
            first_date = f"{first_day:02d}/{month_n:02d}/{rec.year or ''}"
            idx = first_day - 1
            miss_m = idx < len(morning) and morning[idx]
            miss_e = idx < len(evening) and evening[idx]
            if miss_m and not miss_e:
                shift_span = "08:00 – 14:00"
            elif miss_e and not miss_m:
                shift_span = "14:00 – 22:00"
        store = rec.store_id.name or ""
        period = f"{month_n:02d}/{rec.year}"
        missing_people = slots
        return {
            "key": f"{rec.id}-{ntype}",
            "id": rec.id,
            "type": ntype,
            "store_name": store,
            "store_line": f"Cửa hàng {store} • Lịch tháng {period}",
            "period": f"Tháng {period}",
            "period_long": f"Tháng {month_n} năm {rec.year} (ngày 01–{days:02d})",
            "lock_txt": self._fmt_vn(lock_dt),
            "lock_full": self._fmt_vn(lock_dt, with_luc=True),
            "lock_at": fields.Datetime.to_string(lock_dt) if lock_dt else "",
            "staff": staff,
            "shift_count": rec._shift_filled_count(),
            "missing_slots": slots,
            "missing_count": missing_people,
            "need_n": staff + missing_people,
            "first_date": first_date,
            "shift_span": shift_span,
        }

    def _reminder_card(self, store, year, month, deadline_utc):
        period = f"{month:02d}/{year}"
        store_name = store.name if store else ""
        return {
            "key": f"reminder-{store.id if store else 0}-{year}-{month}",
            "id": 0,
            "type": "reminder",
            "store_name": store_name,
            "store_line": f"Cửa hàng {store_name} • Lịch tháng {period}" if store_name else f"Lịch tháng {period}",
            "period": f"Tháng {period}",
            "period_long": f"Tháng {period}",
            "lock_txt": self._fmt_vn(deadline_utc),
            "lock_full": self._fmt_vn(deadline_utc, with_luc=True),
            "lock_at": fields.Datetime.to_string(deadline_utc) if deadline_utc else "",
            "staff": 0,
            "shift_count": 0,
            "missing_slots": 0,
            "missing_count": 0,
            "need_n": 0,
            "first_date": "",
            "shift_span": "",
        }

    @api.model
    def get_store_notification_cards(self, kind="all"):
        kind = kind or "all"
        kind_map = {
            "sap_khoa": "expiring",
            "nhac_nho": "reminder",
            "da_khoa": "locked",
            "can_xu_ly": "need",
            "thong_tin": "info",
        }
        kind = kind_map.get(kind, kind)
        now = fields.Datetime.now()
        Roster = self.env["linkq.monthly.roster"]
        recs = Roster.search(self._roster_domain(), order="id desc", limit=120)
        today = fields.Date.context_today(self)
        year, month = today.year, today.month
        deadline = self._month_deadline_utc(year, month)

        cards = []
        counts = {"all": 0, "expiring": 0, "reminder": 0, "locked": 0, "need": 0, "info": 0}

        def push(card):
            ntype = card["type"]
            counts[ntype] = counts.get(ntype, 0) + 1
            counts["all"] += 1
            if kind in ("all", ntype):
                cards.append(card)

        stores_with_month = set()
        for rec in recs:
            if rec.year == year and int(rec.month or 0) == month and rec.store_id:
                stores_with_month.add(rec.store_id.id)
            locked = bool(rec.is_locked or rec.lock_status == "locked")
            slots, _first = rec._lack_summary()
            staff = rec.line_count or len(rec.line_ids)
            lock_dt = rec.lock_datetime
            types = []
            upcoming = False if locked else self._next_lock_dt(rec, now)
            if not locked and upcoming:
                types.append("expiring")
            if locked:
                types.append("locked")
            if not types and not locked and staff:
                types.append("info")
            for ntype in types:
                push(self._card_from_roster(rec, ntype, now, lock_dt=upcoming if ntype == "expiring" else lock_dt))

        store_ids = self._user_store_ids()
        Store = self.env["hr.store"].sudo()
        if store_ids:
            stores = Store.browse(store_ids)
        elif recs:
            stores = recs.mapped("store_id")
        else:
            stores = Store.browse()
        if not stores and (
            self.env.user.has_group("base.group_system")
            or self.env.user.has_group("lug_phan_he.group_phan_he_admin")
        ):
            stores = Store.search([], limit=40)
        seen_names = set()
        missing_stores = []
        for store in stores:
            if not store:
                continue
            name_key = (store.name or "").strip().upper()
            if store.id in stores_with_month or name_key in seen_names:
                continue
            if name_key:
                seen_names.add(name_key)
            missing_stores.append(store)
        if missing_stores:
            card = self._reminder_card(missing_stores[0], year, month, deadline)
            if len(missing_stores) > 1:
                names = ", ".join(s.name for s in missing_stores if s.name)
                card["store_line"] = names
                card["store_name"] = names
            push(card)
        return {"cards": cards[:80], "counts": counts}
