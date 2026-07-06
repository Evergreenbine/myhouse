# -*- coding: utf-8 -*-
from car_db import query_car_records
from user_auth import load_user_config

cfg = load_user_config()
plate = cfg.car_plate if cfg and cfg.car_plate else "粤S0Q780"
print("Plate:", plate)

rows = query_car_records(plate, "202606")
print("202606 records:", len(rows))
for r in rows[:5]:
    t = r["ch_crosstime"]
    print(f"  {t} out={r['ch_out']}")
