# -*- coding: utf-8 -*-


def post_init_hook(env):
    env["hr.employee"].search([])._sync_store_working_calendar()
