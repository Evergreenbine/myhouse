# -*- coding: utf-8 -*-
from car_db import query_car_records
from database import query_work_records_range
from user_auth import load_user_config
from datetime import date

cfg = load_user_config()
plate = cfg.car_plate

# 查6月11日车辆记录
car_rows = query_car_records(plate, "202606")
day_car = [r for r in car_rows if r["ch_crosstime"].date() == date(2026,6,11)]

print("=== 6月11日 车辆出入 ===")
for r in day_car:
    t = r["ch_crosstime"]
    print(f"  {t} out={r['ch_out']}")

# 查6月11日打卡记录
recs = query_work_records_range(cfg.empname, "2026-06-11", "2026-06-11")
day_recs = recs.get("2026-06-11", [])
times = []
for r in day_recs:
    wt = r.get("worktime")
    if wt and hasattr(wt, "strftime"):
        times.append(wt)

print(f"\n=== 6月11日 打卡 ===")
print(f"  打卡次数: {len(times)}")
if times:
    print(f"  最早: {min(times)}")
    print(f"  最晚: {max(times)}")
    latest = max(times)
    print(f"\n=== 异常判断 ===")
    for r in day_car:
        t = r["ch_crosstime"]
        if t.hour >= 18:
            is_abn = t > latest
            print(f"  {t} {'异常' if is_abn else '正常'} (最晚打卡={latest})")
