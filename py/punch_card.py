# -*- coding: utf-8 -*-
"""
补卡模块 - 根据用户选择的时间生成单条打卡 SQL
"""
from datetime import datetime

# 员工信息
EMPNO = "1103141"
EMPNAME = "吴钦腾"
DEPTNO = "41402"
DEPTNAME = "IT信息技术部"
MACNO = "海康考勤打卡"


def generate_sql(date_str, time_str, remark=""):
    """根据日期和时间生成单条补卡 SQL"""
    dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
    worktime = dt.strftime("1900-01-01 %H:%M:%S")
    workdate = f"{date_str} 00:00:00"
    remark = remark or "HY_C6_8F_05_KQ02_门_1"
    sql = (
        f"INSERT INTO kq_workrecord "
        f"(empno, empname, deptno, deptname, repair_sign, worktime, workdate, macno, backup1, remark) "
        f"VALUES ({EMPNO}, '{EMPNAME}', '{DEPTNO}', '{DEPTNAME}', 0, "
        f"'{worktime}', '{workdate}', '{MACNO}', '{MACNO}', '{remark}');"
    )
    return [sql]
