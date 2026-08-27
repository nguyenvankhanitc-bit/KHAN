# -*- coding: utf-8 -*-
"""Generate data/shift_schedule_dtt_data.xml — run from this folder."""
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent / "shift_schedule_dtt_data.xml"

TIMES = {
    "F1": ("08:00", "20:00"),
    "F2": ("08:00", "22:00"),
    "F3": ("08:30", "21:30"),
    "F4": ("08:30", "22:00"),
    "F5": ("09:00", "21:00"),
    "F7": ("09:00", "22:00"),
    "F8": ("09:30", "22:00"),
    "F9": ("09:30", "21:00"),
    "GC1": ("12:00", "22:00"),
    "GC2": ("12:00", "21:30"),
    "GC3": ("12:00", "21:00"),
    "GS1": ("08:30", "18:30"),
    "GS3": ("09:00", "18:00"),
    "GS4": ("09:00", "19:00"),
    "GS5": ("09:30", "18:30"),
    "S1": ("09:00", "15:00"),
    "S2": ("09:00", "15:30"),
    "S3": ("09:30", "15:00"),
    "S4": ("09:30", "15:30"),
    "S5": ("08:00", "15:00"),
    "S6": ("08:00", "15:30"),
    "S8": ("08:30", "15:30"),
    "S9": ("09:00", "17:00"),
    "S10": ("08:00", "16:00"),
    "S11": ("08:00", "17:00"),
    "S12": ("08:30", "16:30"),
    "S14": ("09:30", "17:00"),
    "C1": ("15:00", "22:00"),
    "C2": ("15:00", "21:30"),
    "C3": ("14:30", "21:30"),
    "C4": ("14:00", "22:00"),
    "C5": ("14:00", "21:00"),
    "C6": ("12:00", "20:00"),
    "C9": ("15:00", "21:00"),
}


def label(code):
    if not code:
        return ""
    if code == "C2/C3":
        return "C2 / C3 (15:00 - 21:30 / 14:30 - 21:30)"
    tin, tout = TIMES[code]
    return f"{code} ({tin} - {tout})"


# xml_id, store_name, optional store note, lines
# line: apply_days, full, gs, gc, sang, chieu, note
STORES = [
    ("aebd", "AEBD", "", [
        ("T2 - T6", "F7", "", "GC1", "S9", "C4", ""),
        ("T7, CN, LỄ", "F4", "", "GC1", "S12", "C4", ""),
    ]),
    ("lug_aebd_glea", "LUG_AEBD & GLEA_AEBD", "", [
        ("T2 - T6", "F7", "", "GC1", "S9", "C4", ""),
        ("T7, CN, LỄ", "F4", "", "GC1", "S12", "C4", ""),
    ]),
    ("lug_bcm_new", "LUG_BCM_NEW", "", [
        ("T2 - T6", "F9", "", "GC3", "S3", "C5", ""),
        ("T7, CN, LỄ", "F5", "", "GC3", "S9", "C5", ""),
    ]),
    ("lug_bmt_nvc", "LUG_BMT_NVC", "", [
        ("FULL", "F1", "", "", "S10", "C6",
         "Trước 01/08/2025 là S11, từ 01/08/2025 là S10"),
    ]),
    ("lug_nt", "LUG_NT", "", [
        ("FULL", "F7", "", "GC1", "S1", "C1", ""),
    ]),
    ("lug_nt_ab", "LUG_NT_AB", "", [
        ("FULL", "F7", "GS4", "GC1", "S1", "C1", ""),
    ]),
    ("nt_ddl_dna", "NT_DDL_DNA", "", [
        ("FULL", "F7", "", "GC1", "S1", "C1", ""),
    ]),
    ("lug_vc304", "LUG_VC304", "", [
        ("T2 - T6", "F8", "GS5", "GC1", "S3", "C1", "GS5 áp dụng từ 01/05/2026"),
        ("T7, CN, LỄ", "F7", "GS3", "GC1", "S1", "C1", "GS3 áp dụng từ 01/05/2026"),
    ]),
    ("vcbh_all", "VCBH_ALL", "", [
        ("T2 - T6", "F8", "", "GC1", "S4", "C4", ""),
        ("T7, CN, LỄ", "F7", "", "GC1", "S2", "C4", ""),
    ]),
    ("go_dian", "GO_DIAN", "", [
        ("FULL", "F2", "", "GC1", "S10", "C4", ""),
    ]),
    ("go_baria", "GO_BARIA", "", [
        ("FULL", "F2", "", "GC1", "S5", "C1",
         "Gia Hân đi ca S10, C4 từ 01/08-01/11"),
    ]),
    ("go_danang", "GO_DANANG", "", [
        ("FULL", "F2", "", "GC1", "S5", "C1", ""),
    ]),
    ("go_cantho", "GO_CANTHO", "", [
        ("FULL", "F2", "", "GC1", "S5", "C4", ""),
    ]),
    ("go_hue", "GO_HUE", "", [
        ("FULL", "F2", "", "GC1", "S6", "C1", ""),
    ]),
    ("rvs_tret", "RVS_TRET", "", [
        ("T2 - T6", "F3", "GS1", "GC2", "S8", "C2/C3", ""),
        ("T7, CN, LỄ", "F4", "GS1", "GC1", "S8", "C1", ""),
    ]),
    ("lug_vcdn", "LUG_VCDN", "", [
        ("T2 - T6", "F8", "", "GC1", "S4", "C1", ""),
        ("T7, CN, LỄ", "F7", "", "GC1", "S2", "C1", ""),
    ]),
    ("lug_leduan", "LUG_LEDUAN", "", [
        ("FULL", "F5", "", "GC3", "S1", "C9", ""),
    ]),
    ("vinpearl_lug", "VINPEARL_LUG", "", [
        ("FULL", "F7", "GS4", "", "S1", "", ""),
    ]),
    ("aehue_ddl", "AEHUE_DDL", "", [
        ("T2 - T6", "F7", "", "GC1", "S2", "C1",
         "29/08-01/09/2026 mở tới 22:30"),
        ("T7, CN, LỄ", "F4", "", "GC1", "S8", "C1",
         "29/08-01/09/2026 mở tới 22:30"),
    ]),
    ("countryhide_aehue", "COUNTRYHIDE_AEHUE", "", [
        ("T2 - T6", "F7", "", "GC1", "S2", "C1",
         "29/08-01/09/2026 mở tới 22:30"),
        ("T7, CN, LỄ", "F4", "", "GC1", "S8", "C1",
         "29/08-01/09/2026 mở tới 22:30"),
    ]),
    ("kg_koh_sora", "KG_KOH_SORA", "", [
        ("T2 - T6", "F8", "", "GC1", "S14", "C4", ""),
        ("T7 - CN", "F7", "", "GC1", "S9", "C4", ""),
    ]),
    ("aeta", "AETA", "", [
        ("T2 - T6", "F7", "", "GC1", "S9", "C4", ""),
        ("T7, CN, LỄ", "F4", "", "GC1", "S12", "C4", ""),
    ]),
    ("lug_mmdn", "LUG_MMDN", "", [
        ("FULL", "F2", "", "GC1", "S5", "C1", ""),
    ]),
    ("tbl_aebd", "TBL_AEBD", "", [
        ("T2 - T6", "F7", "", "GC1", "S9", "C4", ""),
        ("T7, CN, LỄ", "F4", "", "GC1", "S12", "C4", ""),
    ]),
    ("lug_ag", "LUG_AG", "", [
        ("FULL", "F5", "", "GC3", "S1", "C9", ""),
    ]),
    ("lug_vt", "LUG_VT", "", [
        ("FULL", "F7", "", "GC1", "S9", "C4",
         "Đổi từ S1/C1 sang S9/C4 từ 01/07/2025"),
    ]),
]


def field(name, value):
    if not value:
        return ""
    return f'        <field name="{name}">{escape(value)}</field>\n'


def main():
    parts = ['<?xml version="1.0" encoding="utf-8"?>\n<odoo noupdate="1">\n']
    for idx, (xid, name, store_note, lines) in enumerate(STORES):
        seq = (idx + 1) * 10
        parts.append(f'    <record id="dtt_{xid}" model="linkq.shift.schedule.dtt">\n')
        parts.append(f'        <field name="sequence">{seq}</field>\n')
        parts.append(f'        <field name="store_name">{escape(name)}</field>\n')
        if store_note:
            parts.append(field("note", store_note))
        parts.append("    </record>\n")
        for li, (days, full, gs, gc, sang, chieu, note) in enumerate(lines):
            parts.append(
                f'    <record id="dtt_{xid}_l{li + 1}" model="linkq.shift.schedule.dtt.line">\n'
            )
            parts.append(f'        <field name="sequence">{10 + li}</field>\n')
            parts.append(f'        <field name="schedule_id" ref="dtt_{xid}"/>\n')
            parts.append(field("apply_days", days))
            parts.append(field("shift_full", label(full)))
            parts.append(field("shift_split_morning", label(gs)))
            parts.append(field("shift_split_afternoon", label(gc)))
            parts.append(field("shift_morning", label(sang)))
            parts.append(field("shift_afternoon", label(chieu)))
            parts.append(field("note", note))
            parts.append("    </record>\n")
        parts.append("\n")
    parts.append("</odoo>\n")
    OUT.write_text("".join(parts), encoding="utf-8")
    print(f"Wrote {OUT} ({len(STORES)} stores)")


if __name__ == "__main__":
    main()
