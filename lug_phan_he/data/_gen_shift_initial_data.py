# -*- coding: utf-8 -*-
"""Generate data/shift_initial_data.xml — run once from repo root."""
from pathlib import Path

OUT = Path(__file__).resolve().parent / "shift_initial_data.xml"


def hhmm(val):
    h = int(val)
    m = int(round((val - h) * 60))
    if m >= 60:
        h += 1
        m = 0
    return f"{h:02d}:{m:02d}"


def xml_id(code):
    return "shift_code_" + code.lower().replace("-", "_")


CODES = [
    # code, group, tin, tout
    ("F1", "FULL", 8.0, 20.0),
    ("F2", "FULL", 8.0, 22.0),
    ("F3", "FULL", 8.5, 21.5),
    ("F4", "FULL", 8.5, 22.0),
    ("F5", "FULL", 9.0, 21.0),
    ("F6", "FULL", 9.0, 21.5),
    ("F7", "FULL", 9.0, 22.0),
    ("F8", "FULL", 9.5, 22.0),
    ("F9", "FULL", 9.5, 21.0),
    ("F10", "FULL", 7.5, 22.5),
    ("F11", "FULL", 7.5, 22.0),
    ("F12", "FULL", 9.5, 22.5),
    ("F13", "FULL", 8.0, 21.0),
    ("GC1", "GAY_CHIEU", 12.0, 22.0),
    ("GC2", "GAY_CHIEU", 12.0, 21.5),
    ("GC3", "GAY_CHIEU", 12.0, 21.0),
    ("GC4", "GAY_CHIEU", 12.0, 22.5),
    ("GC5", "GAY_CHIEU", 10.0, 21.0),
    ("GC6", "GAY_CHIEU", 11.0, 21.0),
    ("GC7", "GAY_CHIEU", 10.0, 20.0),
    ("GS1", "GAY_SANG", 8.5, 18.5),
    ("GS2", "GAY_SANG", 9.0, 17.0),
    ("GS3", "GAY_SANG", 9.0, 18.0),
    ("GS4", "GAY_SANG", 9.0, 19.0),
    ("GS5", "GAY_SANG", 9.5, 18.5),
    ("S1", "SANG", 9.0, 15.0),
    ("S2", "SANG", 9.0, 15.5),
    ("S3", "SANG", 9.5, 15.0),
    ("S4", "SANG", 9.5, 15.5),
    ("S5", "SANG", 8.0, 15.0),
    ("S6", "SANG", 8.0, 15.5),
    ("S7", "SANG", 8.5, 15.0),
    ("S8", "SANG", 8.5, 15.5),
    ("S9", "SANG", 9.0, 17.0),
    ("S10", "SANG", 8.0, 16.0),
    ("S11", "SANG", 8.0, 17.0),
    ("S12", "SANG", 8.5, 16.5),
    ("S13", "SANG", 9.0, 17.5),
    ("S14", "SANG", 9.5, 17.0),
    ("S15", "SANG", 7.5, 15.5),
    ("C1", "CHIEU", 15.0, 22.0),
    ("C2", "CHIEU", 15.0, 21.5),
    ("C3", "CHIEU", 14.5, 21.5),
    ("C4", "CHIEU", 14.0, 22.0),
    ("C5", "CHIEU", 14.0, 21.0),
    ("C6", "CHIEU", 12.0, 20.0),
    ("C7", "CHIEU", 13.5, 21.5),
    ("C8", "CHIEU", 13.5, 22.0),
    ("C9", "CHIEU", 15.0, 21.0),
    ("C10", "CHIEU", 15.0, 22.5),
    ("OFF", "OFF", 0.0, 0.0),
]

GROUP_LABEL = {
    "FULL": "Ca Full",
    "GAY": "Ca Gãy",
    "GAY_SANG": "Ca Gãy Sáng",
    "GAY_CHIEU": "Ca Gãy Chiều",
    "SANG": "Ca Sáng",
    "CHIEU": "Ca Chiều",
    "OFF": "OFF",
}


def store_xml_id(region, name):
    slug = name.replace("\n", "_").replace(" ", "_").lower()
    slug = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in slug)
    return f"store_{region}_{slug}"


def line_xml_id(region, name, days_key):
    return f"{store_xml_id(region, name)}_{days_key}"


def ref_field(fname, code):
    if not code:
        return ""
    return f'            <field name="{fname}" ref="{xml_id(code)}"/>\n'


def store_record(region, seq, name, note=""):
    xid = store_xml_id(region, name)
    name_xml = name.replace("&", "&amp;")
    # keep newline as entity
    name_xml = name_xml.replace("\n", "&#10;")
    code = name.split("\n")[0]
    note_xml = ""
    if note:
        note_xml = f'        <field name="note">{note}</field>\n'
    return (
        f'    <record id="{xid}" model="linkq.store.schedule">\n'
        f'        <field name="sequence">{seq}</field>\n'
        f'        <field name="name">{name_xml}</field>\n'
        f'        <field name="code">{code}</field>\n'
        f'        <field name="region">{region}</field>\n'
        f"{note_xml}"
        f"    </record>\n"
    )


def line_record(region, name, days_key, apply_days, seq, full=None, gs=None, gc=None, sang=None, chieu=None, note=""):
    xid = line_xml_id(region, name, days_key)
    sid = store_xml_id(region, name)
    body = (
        f'    <record id="{xid}" model="linkq.store.schedule.line">\n'
        f'        <field name="sequence">{seq}</field>\n'
        f'        <field name="schedule_id" ref="{sid}"/>\n'
        f'        <field name="apply_days">{apply_days}</field>\n'
    )
    body += ref_field("shift_full_id", full)
    body += ref_field("shift_split_morning_id", gs)
    body += ref_field("shift_split_afternoon_id", gc)
    body += ref_field("shift_morning_id", sang)
    body += ref_field("shift_afternoon_id", chieu)
    if note:
        body += f'        <field name="note">{note}</field>\n'
    body += "    </record>\n"
    return body


# North: (name, [(days_key, apply_days, seq, full, gs, gc, sang, chieu, note), ...])
NORTH = [
    ("AEHD_DDL", [
        ("t2t5", "T2 - T5", 10, "F8", None, "GC1", "S4", "C1", ""),
        ("t6", "T6", 11, "F12", None, "GC4", "S4", "C10", ""),
        ("t7", "T7", 12, "F4", None, "GC4", "S8", "C10", ""),
        ("cnle", "CN, Lễ", 13, "F4", None, "GC1", "S8", "C1", ""),
    ]),
    ("AELB_DDL", [
        ("t2t6", "T2 - T6", 10, "F8", None, "GC1", "S4", "C1", ""),
        ("t7cnle", "T7, CN, Lễ", 11, "F4", None, "GC1", "S8", "C1", "Mở 9h, đi ca 8h30"),
    ]),
    ("LUG_AEHD", [
        ("t2t6", "T2 - T6", 10, "F8", None, "GC1", "S4", "C1", ""),
        ("t7cnle", "T7, CN, Lễ", 11, "F4", None, "GC1", "S8", "C1", ""),
    ]),
    ("AELB_ECH\nLUG_AELB_L2", [
        ("t2t6", "T2 - T6", 10, "F8", None, "GC1", "S4", "C1", ""),
        ("t7cnle", "T7, CN, Lễ", 11, "F4", None, "GC1", "S8", "C1", ""),
    ]),
    ("GDM_DDL", [
        ("t2t6", "T2 - T6", 10, "F7", "GS3", "GC1", "S2", "C1", "Dương Tú: GS3"),
        ("t7cnle", "T7, CN, Lễ", 11, "F4", None, "GC1", "S8", "C1", ""),
    ]),
    ("LUG_IPH", [
        ("t2t6", "T2 - T6", 10, "F8", None, "GC1", "S4", "C1", ""),
        ("t7cnle", "T7, CN, Lễ", 11, "F7", None, "GC1", "S2", "C1", ""),
    ]),
    ("GO_TLONG", [
        ("t2t5", "T2 - T5", 10, "F2", None, "GC1", "S5", "C1", ""),
        ("t6cn", "T6 - CN", 11, None, None, "GC4", "S5", "C10", "Full 08:00-22:30"),
    ]),
    ("LTKM_DDL", [
        ("week", "Cả tuần", 10, "F7", None, "GC1", "S2", "C1", ""),
    ]),
    ("LUG_LTKM", [
        ("week", "Cả tuần", 10, "F7", "GS4", "GC1", "S2", "C1", "GS4 cho quầy LUG_LTKM_COU"),
    ]),
    ("LUG_LTTH", [
        ("week", "Cả tuần", 10, "F7", None, "GC1", "S2", "C1", ""),
    ]),
    ("LUG_VCROYAL", [
        ("t2t6", "T2 - T6", 10, "F8", None, "GC1", "S4", "C1", ""),
        ("t7cnle", "T7, CN, Lễ", 11, "F7", None, "GC1", "S2", "C1", ""),
    ]),
    ("AEHP_DDL", [
        ("t2t6", "T2 - T6", 10, "F8", None, "GC1", "S4", "C1", ""),
        ("t7cnle", "T7, CN, Lễ", 11, "F4", None, "GC1", "S8", "C1", ""),
    ]),
    ("LUG_AEHP", [
        ("t2t6", "T2 - T6", 10, "F8", None, "GC1", "S2", "C1", ""),
        ("t7cnle", "T7, CN, Lễ", 11, "F4", None, "GC1", "S8", "C1", ""),
    ]),
    ("GO_HPHONG", [
        ("week", "Cả tuần", 10, "F2", None, "GC1", "S6", "C1", ""),
    ]),
    ("LUG_MGW", [
        ("t2t5", "T2 - T5", 10, "F5", "GS3", "GC3", "S2", "C9", ""),
        ("t6cn", "T6 - CN", 11, "F6", None, "GC2", "S2", "C2", ""),
    ]),
    ("LUG_KTOWN", [
        ("t2t7", "T2 - T7", 10, None, None, None, "S13", None, ""),
        ("cn", "CN", 11, "OFF", None, None, "OFF", None, ""),
    ]),
    ("LUG_VCPNT24", [
        ("t2t6", "T2 - T6", 10, "F8", None, "GC1", "S4", "C1", ""),
        ("t7cnle", "T7, CN, Lễ", 11, "F7", None, "GC1", "S2", "C1", ""),
    ]),
    ("LUG_VCTDH", [
        ("t2t6", "T2 - T6", 10, "F8", None, "GC1", "S4", "C1", ""),
        ("t7cnle", "T7, CN, Lễ", 11, "F7", None, "GC1", "S2", "C1", ""),
    ]),
    ("DIA_VCBT", [
        ("t2t6", "T2 - T6", 10, "F8", None, "GC1", "S4", "C1", ""),
        ("t7cnle", "T7, CN, Lễ", 11, "F7", None, "GC1", "S2", "C1", ""),
    ]),
    ("LUG_VCTIC25", [
        ("t2t6", "T2 - T6", 10, "F8", None, "GC1", "S4", "C1", ""),
        ("t7cnle", "T7, CN, Lễ", 11, "F7", None, "GC1", "S2", "C1", ""),
    ]),
    ("LUG_AEHP_L1", [
        ("t2t6", "T2 - T6", 10, "F8", None, "GC1", "S2", "C1", ""),
        ("t7cnle", "T7, CN, Lễ", 11, "F4", None, "GC1", "S8", "C1", ""),
    ]),
]

SOUTH_STORES = [
    "AETL", "AETP", "LUG_AETL", "LUG_AETP", "LUG_CH", "LUG_DC", "TAKA_DDL",
    "CRM_ALL", "HOLDALL_VC32", "LUG_SCVIVO", "LUG_CRESCENT", "LUG_PNT",
    "GO_Q7", "LUG_GOTA", "AE_BINHTAN", "LUG_NSH", "LUG_NOWZONE", "LUG_SGCT",
    "LUG_LANDMARK81", "LUG_GIGA", "LUG_ESTELLA", "LUG_VCTD", "LUG_PARKSON",
    "LUG_VINCOM_DK", "AEON_TANPHU", "LUG_AEON_TD",
]

DTT_STORES = [
    "AEBD", "LUG_AEBD", "LUG_BCM_NEW", "LUG_BMT_NVC", "GO_DANANG", "GO_CANTHO",
    "AEHUE_DDL", "LUG_AEHUE", "GO_BIENHOA", "GO_VUNGTAU", "GO_NHATRANG",
    "GO_QUINHON", "LUG_VSIP_BD", "LUG_VINCOM_DN", "LUG_VINCOM_CT",
    "LUG_VINCOM_HUE", "AE_BINHDUONG", "AE_DANANG", "LUG_BIGC_DN",
    "LUG_COOPMART_CT", "LUG_VINCOM_NT", "LUG_VINCOM_VT", "LUG_AEON_HUE",
    "LUG_VINCOM_BH", "LUG_LOTTE_DN", "LUG_VINCOM_QNH",
]


def mall_lines():
    return [
        ("t2t6", "T2 - T6", 10, "F8", None, "GC1", "S4", "C1", ""),
        ("t7cnle", "T7, CN, Lễ", 11, "F4", None, "GC1", "S8", "C1", ""),
    ]


def emit_codes():
    lines = ["    <!-- 51 mã ca -->\n"]
    seq = 10
    for code, group, tin, tout in CODES:
        if group == "OFF":
            name = "OFF"
        else:
            name = f"{GROUP_LABEL[group]} {hhmm(tin)} - {hhmm(tout)}"
        lines.append(
            f'    <record id="{xml_id(code)}" model="linkq.shift.code">\n'
            f'        <field name="sequence">{seq}</field>\n'
            f'        <field name="code">{code}</field>\n'
            f'        <field name="name">{name}</field>\n'
            f'        <field name="shift_group">{group}</field>\n'
            f'        <field name="time_in">{tin}</field>\n'
            f'        <field name="time_out">{tout}</field>\n'
            f"    </record>\n"
        )
        seq += 1
    return "".join(lines)


def emit_region(region, stores_spec, start_seq=10):
    chunks = [f"    <!-- Cửa hàng {region} -->\n"]
    seq = start_seq
    if region == "north":
        for name, lines in stores_spec:
            chunks.append(store_record(region, seq, name))
            for item in lines:
                chunks.append(line_record(region, name, *item))
            seq += 10
    else:
        for name in stores_spec:
            chunks.append(store_record(region, seq, name))
            for item in mall_lines():
                chunks.append(line_record(region, name, *item))
            seq += 10
    return "".join(chunks)


def main():
    assert len(CODES) == 51, len(CODES)
    assert len(NORTH) == 21, len(NORTH)
    assert len(SOUTH_STORES) == 26, len(SOUTH_STORES)
    assert len(DTT_STORES) == 26, len(DTT_STORES)
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<odoo noupdate="1">\n'
        + emit_codes()
        + emit_region("north", NORTH)
        + emit_region("south", SOUTH_STORES)
        + emit_region("dtt", DTT_STORES)
        + "</odoo>\n"
    )
    OUT.write_text(xml, encoding="utf-8")
    print(f"Wrote {OUT} ({xml.count('<record ')} records)")


if __name__ == "__main__":
    main()
