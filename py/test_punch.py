from database import query_work_records_range
r = query_work_records_range('1103141', '2026-06-13', '2026-06-14')
print('dates:', len(r))
for k, v in r.items():
    times = [x["worktime"] for x in v if x.get("worktime") and hasattr(x["worktime"], "strftime")]
    print(k, len(v), 'records, times:', [t.strftime("%H:%M") for t in times])
