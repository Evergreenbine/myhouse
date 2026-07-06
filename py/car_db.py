# -*- coding: utf-8 -*-
"""车辆出入记录 - PostgreSQL 查询与修改"""
import psycopg2
from config import PG_CONFIG


def get_connection():
    return psycopg2.connect(
        host=PG_CONFIG["host"],
        port=PG_CONFIG["port"],
        database=PG_CONFIG["database"],
        user=PG_CONFIG["user"],
        password=PG_CONFIG["password"],
        connect_timeout=5,
    )


def query_car_records(plate, year_month):
    """查询指定月份车辆出入记录"""
    table = f"tb_crosshistory_{year_month}"
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            f'SELECT ch_id, ch_plate, ch_crosstime, ch_out, ch_cartype, p_id '
            f'FROM {table} WHERE ch_plate=%s ORDER BY ch_crosstime DESC',
            (plate,)
        )
        cols = [d[0] for d in c.description]
        rows = [dict(zip(cols, r)) for r in c.fetchall()]
        return rows
    finally:
        conn.close()


def update_car_record(ch_id, year_month, new_time=None, new_out=None):
    """修改车辆出入记录：时间和进出方式"""
    table = f"tb_crosshistory_{year_month}"
    conn = get_connection()
    try:
        c = conn.cursor()
        if new_time is not None:
            c.execute(f"UPDATE {table} SET ch_crosstime=%s WHERE ch_id=%s", (new_time, ch_id))
        if new_out is not None:
            c.execute(f"UPDATE {table} SET ch_out=%s WHERE ch_id=%s", (new_out, ch_id))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()
