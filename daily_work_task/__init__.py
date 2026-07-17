# -*- coding: utf-8 -*-

from . import models
from . import wizard


def post_init_hook(env):
    from .hooks import post_init_hook as _hook

    _hook(env)