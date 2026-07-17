# -*- coding: utf-8 -*-
from pathlib import Path
import re

p = Path(r"d:\Lap_odoo\odoo_time_off_custom\custom_addons\daily_work_task\data\sample_data.xml")
text = p.read_text(encoding="utf-8")
text2 = re.sub(r'\n\s*<field name="department">[^<]*</field>', "", text)
p.write_text(text2, encoding="utf-8")
print("done", text.count('name="department"'), "->", text2.count('name="department"'))
