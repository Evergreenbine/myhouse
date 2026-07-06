# -*- coding: utf-8 -*-
"""本地 SQLite 数据库 — 存储应用配置、加班理由等"""
import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "local.db")

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init():
    c = _conn()
    
    # 基础设施表
    c.execute("CREATE TABLE IF NOT EXISTS user_config (key TEXT PRIMARY KEY, value TEXT DEFAULT '')")
    c.execute("CREATE TABLE IF NOT EXISTS app_user (key TEXT PRIMARY KEY, value TEXT DEFAULT '')")
    c.execute("""CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT DEFAULT '',
        messages TEXT DEFAULT '[]', created_at TEXT DEFAULT ''
    )""")
    try:
        c.execute("ALTER TABLE chat_history ADD COLUMN archived INTEGER DEFAULT 0")
    except:
        pass

    # 租房管理表
    c.execute("""CREATE TABLE IF NOT EXISTS buildings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        address TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        building_id INTEGER NOT NULL REFERENCES buildings(id),
        room_number TEXT NOT NULL,
        floor INTEGER DEFAULT 1,
        status TEXT DEFAULT 'idle',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    try:
        c.execute("ALTER TABLE rooms ADD COLUMN floor INTEGER DEFAULT 1")
    except:
        pass
    try:
        c.execute("ALTER TABLE rooms ADD COLUMN status TEXT DEFAULT 'idle'")
    except:
        pass
    c.execute("""CREATE TABLE IF NOT EXISTS tenants (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        building_id INTEGER REFERENCES buildings(id),
        phone TEXT DEFAULT '', id_card TEXT DEFAULT '',
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    try:
        c.execute("ALTER TABLE tenants ADD COLUMN building_id INTEGER REFERENCES buildings(id)")
    except:
        pass
    c.execute("""CREATE TABLE IF NOT EXISTS contracts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL REFERENCES tenants(id),
        room_id INTEGER NOT NULL REFERENCES rooms(id),
        start_date TEXT NOT NULL, end_date TEXT DEFAULT '',
        monthly_rent REAL DEFAULT 0,
        water_unit_price REAL DEFAULT 0,
        electric_unit_price REAL DEFAULT 0,
        deposit REAL DEFAULT 0, contract_file TEXT DEFAULT '',
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS meters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id INTEGER NOT NULL REFERENCES rooms(id),
        type TEXT NOT NULL CHECK(type IN ('water','electric')),
        meter_no TEXT DEFAULT '', init_reading REAL DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS meter_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meter_id INTEGER NOT NULL REFERENCES meters(id),
        reading_date TEXT NOT NULL, reading REAL NOT NULL,
        photo TEXT DEFAULT '', remark TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS bills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contract_id INTEGER NOT NULL REFERENCES contracts(id),
        billing_month TEXT NOT NULL,
        rent_amount REAL DEFAULT 0, water_fee REAL DEFAULT 0,
        electric_fee REAL DEFAULT 0, other_fee REAL DEFAULT 0,
        total_amount REAL DEFAULT 0, status TEXT DEFAULT 'unpaid',
        remark TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_id INTEGER NOT NULL REFERENCES bills(id),
        amount REAL NOT NULL,
        pay_date TEXT DEFAULT (date('now')),
        pay_method TEXT DEFAULT '', remark TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")

    c.execute("DROP TABLE IF EXISTS ot_reasons")
    c.commit()
    c.close()


# === 用户配置 ===
def get_config(key, default=""):
    c = _conn()
    row = c.execute("SELECT value FROM user_config WHERE key=?", (key,)).fetchone()
    c.close()
    return row["value"] if row else default

def set_config(key, value):
    c = _conn()
    c.execute("INSERT OR REPLACE INTO user_config (key, value) VALUES (?,?)", (key, str(value)))
    c.commit()
    c.close()

def get_all_config():
    c = _conn()
    rows = c.execute("SELECT key, value FROM user_config").fetchall()
    c.close()
    return {r["key"]: r["value"] for r in rows}

# === app_user 表（基本信息 / 用户设置，key-value 存储） ===
def save_app_user(data: dict):
    """将 dict 逐字段写入 app_user 表"""
    c = _conn()
    for k, v in data.items():
        val = str(v) if not isinstance(v, str) else v
        c.execute("INSERT OR REPLACE INTO app_user (key, value) VALUES (?,?)", (k, val))
    c.commit()
    c.close()

def load_app_user() -> dict:
    """从 app_user 表读取全部字段，返回 dict"""
    c = _conn()
    rows = c.execute("SELECT key, value FROM app_user").fetchall()
    c.close()
    return {r["key"]: r["value"] for r in rows}




def load_chats():
    c = _conn()
    rows = c.execute("SELECT id, title, messages, created_at, archived FROM chat_history ORDER BY created_at DESC LIMIT 50").fetchall()
    c.close()
    return [{"id": r["id"], "title": r["title"], "messages": json.loads(r["messages"]), "time": r["created_at"], "archived": bool(r["archived"])} for r in rows]

def delete_chat(conv_id):
    c = _conn()
    c.execute("DELETE FROM chat_history WHERE id=?", (conv_id,))
    c.commit()
    c.close()


# ============================================================
# 租房管理 CRUD
# ============================================================

def add_building(name, address=''):
    c = _conn()
    cur = c.execute("INSERT INTO buildings (name, address) VALUES (?,?)", (name, address))
    c.commit(); pk = cur.lastrowid; c.close()
    return pk

def get_buildings():
    c = _conn()
    rows = c.execute("SELECT * FROM buildings ORDER BY id").fetchall()
    c.close()
    return [dict(r) for r in rows]

def get_building(bid):
    c = _conn()
    r = c.execute("SELECT * FROM buildings WHERE id=?", (bid,)).fetchone()
    c.close()
    return dict(r) if r else None

def update_building(bid, name, address):
    c = _conn()
    c.execute("UPDATE buildings SET name=?,address=? WHERE id=?", (name, address, bid))
    c.commit(); c.close()

def delete_building(bid):
    c = _conn()
    c.execute("DELETE FROM buildings WHERE id=?", (bid,))
    c.commit(); c.close()

def add_room(building_id, room_number, floor=1, status='idle'):
    c = _conn()
    cur = c.execute("INSERT INTO rooms (building_id, room_number, floor, status) VALUES (?,?,?,?)", (building_id, room_number, floor, status))
    c.commit(); pk = cur.lastrowid; c.close()
    return pk

def get_rooms(building_id=None):
    c = _conn()
    if building_id:
        rows = c.execute("SELECT r.*,b.name AS building_name FROM rooms r JOIN buildings b ON r.building_id=b.id WHERE r.building_id=? ORDER BY COALESCE(r.floor,1), CAST(r.room_number AS INTEGER), r.room_number", (building_id,)).fetchall()
    else:
        rows = c.execute("SELECT r.*,b.name AS building_name FROM rooms r JOIN buildings b ON r.building_id=b.id ORDER BY b.id,COALESCE(r.floor,1),CAST(r.room_number AS INTEGER),r.room_number").fetchall()
    c.close()
    return [dict(r) for r in rows]

def get_room(rid):
    c = _conn()
    r = c.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
    c.close()
    return dict(r) if r else None

def update_room(rid, building_id, room_number, floor=1, status='idle'):
    c = _conn()
    c.execute("UPDATE rooms SET building_id=?,room_number=?,floor=?,status=? WHERE id=?", (building_id, room_number, floor, status, rid))
    c.commit(); c.close()

def add_tenant(name, phone='', id_card='', status='active', building_id=None):
    c = _conn()
    cur = c.execute("INSERT INTO tenants (name, phone, id_card, status, building_id) VALUES (?,?,?,?,?)", (name, phone, id_card, status, building_id))
    c.commit(); pk = cur.lastrowid; c.close()
    return pk

def get_tenants(active_only=True, building_id=None):
    c = _conn()
    wh = []
    params = []
    if active_only:
        wh.append("t.status='active'")
    if building_id:
        wh.append("t.building_id=?")
        params.append(building_id)
    sql = "SELECT t.*,b.name AS building_name FROM tenants t LEFT JOIN buildings b ON t.building_id=b.id"
    if wh:
        sql += " WHERE " + " AND ".join(wh)
    sql += " ORDER BY t.id"
    rows = c.execute(sql, params).fetchall()
    c.close()
    return [dict(r) for r in rows]

def get_tenant(tid):
    c = _conn()
    r = c.execute("SELECT t.*,b.name AS building_name FROM tenants t LEFT JOIN buildings b ON t.building_id=b.id WHERE t.id=?", (tid,)).fetchone()
    c.close()
    return dict(r) if r else None

def update_tenant(tid, name, phone, id_card, status='active', building_id=None):
    c = _conn()
    c.execute("UPDATE tenants SET name=?,phone=?,id_card=?,status=?,building_id=? WHERE id=?", (name, phone, id_card, status, building_id, tid))
    c.commit(); c.close()

def set_tenant_status(tid, status):
    c = _conn()
    c.execute("UPDATE tenants SET status=? WHERE id=?", (status, tid))
    c.commit(); c.close()

def add_contract(tenant_id, room_id, start_date, end_date='',
                 monthly_rent=0, water_price=0, electric_price=0,
                 deposit=0, contract_file='', status='active'):
    c = _conn()
    cur = c.execute("""INSERT INTO contracts
        (tenant_id,room_id,start_date,end_date,monthly_rent,
         water_unit_price,electric_unit_price,deposit,contract_file,status)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (tenant_id, room_id, start_date, end_date, monthly_rent,
         water_price, electric_price, deposit, contract_file, status))
    c.commit(); pk = cur.lastrowid; c.close()
    return pk

def get_contracts(active_only=True, building_id=None):
    c = _conn()
    sql = ("SELECT c.*,t.name AS tenant_name,t.phone AS tenant_phone,"
           "r.room_number,b.name AS building_name "
           "FROM contracts c "
           "JOIN tenants t ON c.tenant_id=t.id "
           "JOIN rooms r ON c.room_id=r.id "
           "JOIN buildings b ON r.building_id=b.id")
    wh = []
    params = []
    if active_only:
        wh.append("c.status='active'")
    if building_id:
        wh.append("r.building_id=?")
        params.append(building_id)
    if wh:
        sql += " WHERE " + " AND ".join(wh)
    sql += " ORDER BY c.id DESC"
    rows = c.execute(sql, params).fetchall()
    c.close()
    return [dict(r) for r in rows]

def get_contract(cid):
    c = _conn()
    r = c.execute("SELECT c.*,t.name AS tenant_name,t.phone AS tenant_phone,"
                  "r.room_number,b.name AS building_name "
                  "FROM contracts c "
                  "JOIN tenants t ON c.tenant_id=t.id "
                  "JOIN rooms r ON c.room_id=r.id "
                  "JOIN buildings b ON r.building_id=b.id "
                  "WHERE c.id=?", (cid,)).fetchone()
    c.close()
    return dict(r) if r else None

def update_contract(cid, tenant_id, room_id, start_date, end_date='',
                    monthly_rent=0, water_price=0, electric_price=0,
                    deposit=0, contract_file='', status='active'):
    c = _conn()
    c.execute("""UPDATE contracts SET tenant_id=?,room_id=?,start_date=?,end_date=?,
        monthly_rent=?,water_unit_price=?,electric_unit_price=?,deposit=?,
        contract_file=?,status=? WHERE id=?""",
        (tenant_id, room_id, start_date, end_date, monthly_rent,
         water_price, electric_price, deposit, contract_file, status, cid))
    c.commit(); c.close()

def end_contract(cid):
    c = _conn()
    c.execute("UPDATE contracts SET status='ended' WHERE id=?", (cid,))
    c.commit(); c.close()

def add_meter(room_id, mtype, meter_no='', init_reading=0.0):
    c = _conn()
    cur = c.execute("INSERT INTO meters (room_id,type,meter_no,init_reading) VALUES (?,?,?,?)",
              (room_id, mtype, meter_no, init_reading))
    c.commit(); pk = cur.lastrowid; c.close()
    return pk

def get_meters(room_id=None, building_id=None, mtype=None):
    c = _conn()
    wh = []
    params = []
    if room_id:
        wh.append("m.room_id=?")
        params.append(room_id)
    if building_id:
        wh.append("r.building_id=?")
        params.append(building_id)
    if mtype:
        wh.append("m.type=?")
        params.append(mtype)
    sql = ("SELECT m.*,r.room_number,r.floor,b.name AS building_name "
           "FROM meters m JOIN rooms r ON m.room_id=r.id "
           "JOIN buildings b ON r.building_id=b.id")
    if wh:
        sql += " WHERE " + " AND ".join(wh)
    sql += " ORDER BY COALESCE(r.floor,1),CAST(r.room_number AS INTEGER),r.room_number,m.type"
    rows = c.execute(sql, params).fetchall()
    c.close()
    return [dict(r) for r in rows]

def get_meter(mid):
    c = _conn()
    r = c.execute("SELECT m.*,r.building_id,r.room_number,r.floor,b.name AS building_name FROM meters m JOIN rooms r ON m.room_id=r.id JOIN buildings b ON r.building_id=b.id WHERE m.id=?", (mid,)).fetchone()
    c.close()
    return dict(r) if r else None

def update_meter(mid, room_id, mtype, meter_no='', init_reading=0.0):
    c = _conn()
    c.execute("UPDATE meters SET room_id=?,type=?,meter_no=?,init_reading=? WHERE id=?",
              (room_id, mtype, meter_no, init_reading, mid))
    c.commit(); c.close()

def add_reading(meter_id, reading_date, reading, photo='', remark=''):
    c = _conn()
    c.execute("INSERT INTO meter_readings (meter_id,reading_date,reading,photo,remark) VALUES (?,?,?,?,?)",
              (meter_id, reading_date, reading, photo, remark))
    c.commit(); pk = c.lastrowid; c.close()
    return pk

def get_readings(meter_id=None, limit=100):
    c = _conn()
    if meter_id:
        rows = c.execute("SELECT mr.*,m.meter_no,m.type FROM meter_readings mr JOIN meters m ON mr.meter_id=m.id WHERE mr.meter_id=? ORDER BY mr.reading_date DESC LIMIT ?", (meter_id, limit)).fetchall()
    else:
        rows = c.execute("SELECT mr.*,m.meter_no,m.type,r.room_number FROM meter_readings mr JOIN meters m ON mr.meter_id=m.id JOIN rooms r ON m.room_id=r.id ORDER BY mr.reading_date DESC LIMIT ?", (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]

def get_latest_reading(meter_id):
    c = _conn()
    r = c.execute("SELECT * FROM meter_readings WHERE meter_id=? ORDER BY reading_date DESC LIMIT 1", (meter_id,)).fetchone()
    c.close()
    return dict(r) if r else None

def add_bill(contract_id, billing_month, rent_amount, water_fee=0,
             electric_fee=0, other_fee=0, remark=''):
    total = round(rent_amount + water_fee + electric_fee + other_fee, 2)
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""INSERT INTO bills
        (contract_id,billing_month,rent_amount,water_fee,electric_fee,
         other_fee,total_amount,remark)
        VALUES (?,?,?,?,?,?,?,?)""",
        (contract_id, billing_month, rent_amount, water_fee,
         electric_fee, other_fee, total, remark))
    pk = cur.lastrowid
    conn.commit(); conn.close()
    return pk

def get_bills(month=None, contract_id=None):
    c = _conn()
    where, params = [], []
    if month:
        where.append("b.billing_month=?"); params.append(month)
    if contract_id:
        where.append("b.contract_id=?"); params.append(contract_id)
    wh = (" WHERE " + " AND ".join(where)) if where else ''
    sql = ("SELECT b.*,t.name AS tenant_name,r.room_number,bld.name AS building_name "
           "FROM bills b "
           "JOIN contracts c ON b.contract_id=c.id "
           "JOIN tenants t ON c.tenant_id=t.id "
           "JOIN rooms r ON c.room_id=r.id "
           "JOIN buildings bld ON r.building_id=bld.id") + wh + " ORDER BY b.id DESC"
    rows = c.execute(sql, params).fetchall()
    c.close()
    return [dict(r) for r in rows]

def get_bill(bid):
    c = _conn()
    r = c.execute("SELECT b.*,t.name AS tenant_name,r.room_number,bld.name AS building_name "
                  "FROM bills b "
                  "JOIN contracts c ON b.contract_id=c.id "
                  "JOIN tenants t ON c.tenant_id=t.id "
                  "JOIN rooms r ON c.room_id=r.id "
                  "JOIN buildings bld ON r.building_id=bld.id "
                  "WHERE b.id=?", (bid,)).fetchone()
    c.close()
    return dict(r) if r else None

def update_bill(bid, contract_id=None, billing_month=None, rent_amount=None,
                water_fee=None, electric_fee=None, other_fee=None, remark=None):
    c = _conn()
    sets, params = [], []
    if contract_id is not None: sets.append("contract_id=?"); params.append(contract_id)
    if billing_month is not None: sets.append("billing_month=?"); params.append(billing_month)
    if rent_amount is not None: sets.append("rent_amount=?"); params.append(rent_amount)
    if water_fee is not None: sets.append("water_fee=?"); params.append(water_fee)
    if electric_fee is not None: sets.append("electric_fee=?"); params.append(electric_fee)
    if other_fee is not None: sets.append("other_fee=?"); params.append(other_fee)
    if remark is not None: sets.append("remark=?"); params.append(remark)
    if sets:
        rent = rent_amount if rent_amount is not None else 0
        wf = water_fee if water_fee is not None else 0
        ef = electric_fee if electric_fee is not None else 0
        of = other_fee if other_fee is not None else 0
        cur = c.execute("SELECT rent_amount,water_fee,electric_fee,other_fee FROM bills WHERE id=?", (bid,)).fetchone()
        if cur:
            r = rent_amount if rent_amount is not None else cur["rent_amount"]
            w = water_fee if water_fee is not None else cur["water_fee"]
            e = electric_fee if electric_fee is not None else cur["electric_fee"]
            o = other_fee if other_fee is not None else cur["other_fee"]
            total = round(r + w + e + o, 2)
            sets.append("total_amount=?"); params.append(total)
        params.append(bid)
        c.execute("UPDATE bills SET "+",".join(sets)+" WHERE id=?", params)
    c.commit(); c.close()

def update_bill_status(bid, status):
    c = _conn()
    c.execute("UPDATE bills SET status=? WHERE id=?", (status, bid))
    c.commit(); c.close()

def add_payment(bill_id, amount, pay_date=None, pay_method='', remark=''):
    if pay_date is None:
        from datetime import date; pay_date = date.today().isoformat()
    c = _conn()
    c.execute("INSERT INTO payments (bill_id,amount,pay_date,pay_method,remark) VALUES (?,?,?,?,?)",
              (bill_id, amount, pay_date, pay_method, remark))
    c.commit(); pk = c.lastrowid; c.close()
    _update_bill_payment_status(bill_id)
    return pk

def get_payments(bill_id=None):
    c = _conn()
    if bill_id:
        rows = c.execute("SELECT p.*,b.billing_month FROM payments p JOIN bills b ON p.bill_id=b.id WHERE p.bill_id=? ORDER BY p.pay_date", (bill_id,)).fetchall()
    else:
        rows = c.execute("SELECT p.*,b.billing_month,b.total_amount FROM payments p JOIN bills b ON p.bill_id=b.id ORDER BY p.pay_date DESC LIMIT 100").fetchall()
    c.close()
    return [dict(r) for r in rows]

def delete_payment(pid):
    c = _conn()
    r = c.execute("SELECT bill_id FROM payments WHERE id=?", (pid,)).fetchone()
    bill_id = r["bill_id"] if r else None
    c.execute("DELETE FROM payments WHERE id=?", (pid,))
    c.commit(); c.close()
    if bill_id:
        _update_bill_payment_status(bill_id)

def _update_bill_payment_status(bill_id):
    c = _conn()
    bill = c.execute("SELECT total_amount FROM bills WHERE id=?", (bill_id,)).fetchone()
    if not bill: c.close(); return
    paid = c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE bill_id=?", (bill_id,)).fetchone()[0]
    if paid >= bill["total_amount"]:
        c.execute("UPDATE bills SET status='paid' WHERE id=?", (bill_id,))
    elif paid > 0:
        c.execute("UPDATE bills SET status='partial' WHERE id=?", (bill_id,))
    else:
        c.execute("UPDATE bills SET status='unpaid' WHERE id=?", (bill_id,))
    c.commit(); c.close()
