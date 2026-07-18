# -*- coding: utf-8 -*-
"""本地数据库访问层。

默认使用 SQLite；设置 DB_BACKEND=mysql 或提供 db_config.local.env 后使用 MySQL。
"""
import sqlite3
import os
import json
import re
import threading
import time
import hashlib
from datetime import datetime, date
from decimal import Decimal
from functools import wraps

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "local.db")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "db_config.local.env")


def _load_env_file(path):
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


_LOCAL_DB_CONFIG = _load_env_file(CONFIG_PATH)
DB_BACKEND = (
    os.environ.get("DB_BACKEND")
    or _LOCAL_DB_CONFIG.get("DB_BACKEND")
    or ("mysql" if _LOCAL_DB_CONFIG.get("MYSQL_HOST") else "sqlite")
).lower()
_MYSQL_ENGINE = None
_MYSQL_ENGINE_LOCK = threading.Lock()
_REDIS_CLIENT = None
_REDIS_LOCK = threading.Lock()
_REDIS_UNAVAILABLE_UNTIL = 0
_CACHE_MISS = object()
_RENTAL_CACHE_PREFIX = "myhouse:rental"


class _Row(dict):
    def __init__(self, keys, values):
        super().__init__(zip(keys, values))
        self._values = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class _MySQLCursor:
    def __init__(self, cursor, owner):
        self._cursor = cursor
        self._owner = owner

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def execute(self, sql, params=None):
        translated = _translate_mysql_sql(sql)
        if translated is None:
            return self
        try:
            self._cursor.execute(translated, params or ())
        except Exception:
            self._owner._broken = True
            raise
        self._owner.lastrowid = self._cursor.lastrowid
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        keys = [col[0] for col in self._cursor.description or []]
        return _Row(keys, row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        keys = [col[0] for col in self._cursor.description or []]
        return [_Row(keys, row) for row in rows]

    def __iter__(self):
        return iter(self.fetchall())

    def close(self):
        self._cursor.close()


class _MySQLConnection:
    def __init__(self, conn, pooled=True):
        self._conn = conn
        self._pooled = pooled
        self._closed = False
        self._broken = False
        self.lastrowid = None

    def execute(self, sql, params=None):
        return self.cursor().execute(sql, params)

    def cursor(self):
        return _MySQLCursor(self._conn.cursor(), self)

    def commit(self):
        self._conn.commit()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._broken:
            try:
                self._conn.invalidate()
            except Exception:
                pass
        else:
            try:
                self._conn.rollback()
            except Exception:
                pass
        try:
            self._conn.close()
        except Exception:
            pass


def _translate_mysql_sql(sql):
    stripped = sql.strip()
    upper = stripped.upper()
    if upper.startswith("PRAGMA"):
        return None
    sql = re.sub(r"\bINSERT\s+OR\s+REPLACE\s+INTO\b", "REPLACE INTO", sql, flags=re.IGNORECASE)
    sql = sql.replace("datetime('now','localtime')", "NOW()")
    sql = sql.replace("date('now')", "CURDATE()")
    sql = re.sub(r"CAST\(([^)]+?)\s+AS\s+INTEGER\)", r"CAST(\1 AS UNSIGNED)", sql, flags=re.IGNORECASE)
    sql = re.sub(r"(?<!`)\bkey\b(?!`)", "`key`", sql, flags=re.IGNORECASE)
    sql = sql.replace("?", "%s")
    return sql


def _mysql_settings():
    cfg = dict(_LOCAL_DB_CONFIG)
    for key in ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD"):
        if os.environ.get(key) is not None:
            cfg[key] = os.environ[key]
    return {
        "host": cfg.get("MYSQL_HOST", "127.0.0.1"),
        "port": int(cfg.get("MYSQL_PORT", "3306")),
        "database": cfg.get("MYSQL_DATABASE", "myhouse"),
        "user": cfg.get("MYSQL_USER", "myhouse"),
        "password": cfg.get("MYSQL_PASSWORD", ""),
    }


def _config_value(key, default=""):
    return os.environ.get(key) or _LOCAL_DB_CONFIG.get(key) or default


def _int_config(key, default, minimum=None):
    value = _config_value(key, str(default))
    try:
        number = int(value)
    except ValueError:
        number = default
    if minimum is not None:
        number = max(minimum, number)
    return number


def _mysql_engine():
    global _MYSQL_ENGINE
    if _MYSQL_ENGINE is not None:
        return _MYSQL_ENGINE
    with _MYSQL_ENGINE_LOCK:
        if _MYSQL_ENGINE is not None:
            return _MYSQL_ENGINE
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.engine import URL
            from sqlalchemy.pool import QueuePool
        except ImportError as exc:
            raise RuntimeError("MySQL 模式需要安装 SQLAlchemy 和 PyMySQL：pip install SQLAlchemy PyMySQL") from exc
        settings = _mysql_settings()
        url = URL.create(
            "mysql+pymysql",
            username=settings["user"],
            password=settings["password"],
            host=settings["host"],
            port=settings["port"],
            database=settings["database"],
        )
        _MYSQL_ENGINE = create_engine(
            url,
            poolclass=QueuePool,
            pool_pre_ping=True,
            pool_size=_int_config("MYSQL_POOL_SIZE", 5, 1),
            max_overflow=_int_config("MYSQL_MAX_OVERFLOW", 10, 0),
            pool_recycle=_int_config("MYSQL_POOL_RECYCLE", 1800, 1),
            pool_timeout=_int_config("MYSQL_POOL_TIMEOUT", 30, 1),
            connect_args={"charset": "utf8mb4", "autocommit": False},
            future=True,
        )
        return _MYSQL_ENGINE


def _mysql_conn():
    try:
        conn = _mysql_engine().raw_connection()
    except ImportError as exc:
        raise RuntimeError("MySQL 模式需要安装 PyMySQL：pip install PyMySQL") from exc
    return _MySQLConnection(conn)


def _conn():
    if DB_BACKEND == "mysql":
        return _mysql_conn()
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _redis_url():
    return _config_value("REDIS_URL", "")


def _cache_ttl_seconds():
    return _int_config("CACHE_TTL_SECONDS", 20, 1)


def _redis_client():
    global _REDIS_CLIENT, _REDIS_UNAVAILABLE_UNTIL
    if not _redis_url() or time.time() < _REDIS_UNAVAILABLE_UNTIL:
        return None
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    with _REDIS_LOCK:
        if _REDIS_CLIENT is not None:
            return _REDIS_CLIENT
        try:
            import redis
            _REDIS_CLIENT = redis.Redis.from_url(
                _redis_url(),
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
                health_check_interval=30,
            )
            _REDIS_CLIENT.ping()
            return _REDIS_CLIENT
        except Exception:
            _REDIS_UNAVAILABLE_UNTIL = time.time() + 30
            _REDIS_CLIENT = None
            return None


def _cache_key(name, args, kwargs):
    raw = json.dumps({"name": name, "args": args, "kwargs": kwargs}, ensure_ascii=False, sort_keys=True, default=_json_default)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"{_RENTAL_CACHE_PREFIX}:{name}:{digest}"


def _cache_get(key):
    client = _redis_client()
    if client is None:
        return _CACHE_MISS
    try:
        value = client.get(key)
        if value is None:
            return _CACHE_MISS
        return json.loads(value)
    except Exception:
        return _CACHE_MISS


def _cache_set(key, value, ttl=None):
    client = _redis_client()
    if client is None:
        return
    try:
        client.setex(key, int(ttl or _cache_ttl_seconds()), json.dumps(value, ensure_ascii=False, default=_json_default))
    except Exception:
        pass


def _cached_rental(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        key = _cache_key(func.__name__, args, kwargs)
        cached = _cache_get(key)
        if cached is not _CACHE_MISS:
            return cached
        value = func(*args, **kwargs)
        _cache_set(key, value)
        return value
    return wrapper


def clear_rental_cache():
    client = _redis_client()
    if client is None:
        return
    try:
        keys = list(client.scan_iter(f"{_RENTAL_CACHE_PREFIX}:*"))
        if keys:
            client.delete(*keys)
    except Exception:
        pass


def init():
    if DB_BACKEND == "mysql":
        c = _conn()
        try:
            c.execute("SELECT 1 FROM buildings LIMIT 1")
            try:
                c.execute("ALTER TABLE contracts ADD COLUMN other_fee_details TEXT")
            except Exception:
                pass
            c.commit()
        finally:
            c.close()
        return

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
    c.execute("""CREATE TABLE IF NOT EXISTS ai_thread_state (
        thread_id TEXT PRIMARY KEY,
        state TEXT DEFAULT '{}',
        updated_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS ai_trace (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        thread_id TEXT DEFAULT '',
        event TEXT DEFAULT '',
        payload TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")

    # AI 知识库表（向量存储用 SQLite 文本，实际用 TF-IDF）
    c.execute("""CREATE TABLE IF NOT EXISTS ai_knowledge (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        category TEXT DEFAULT '',
        embedding TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")

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
    try:
        c.execute("ALTER TABLE tenants ADD COLUMN room_id INTEGER REFERENCES rooms(id)")
    except:
        pass
    try:
        c.execute("ALTER TABLE tenants ADD COLUMN room_id TEXT")
    except:
        pass
    # 如果 room_id 字段存在外键约束，则重建表去掉约束
    cols = [row[1] for row in c.execute("PRAGMA table_info(tenants)").fetchall()]
    if 'room_id' in cols:
        fks = c.execute("PRAGMA foreign_key_list(tenants)").fetchall()
        room_has_fk = any(fk[3] == 'room_id' for fk in fks)
        if room_has_fk:
            c.execute("PRAGMA foreign_keys=OFF")
            c.execute("""
                CREATE TABLE tenants_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    building_id INTEGER REFERENCES buildings(id),
                    phone TEXT DEFAULT '',
                    id_card TEXT DEFAULT '',
                    status TEXT DEFAULT 'active',
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    room_id TEXT
                )
            """)
            c.execute("INSERT INTO tenants_new (id,name,building_id,phone,id_card,status,created_at,room_id) SELECT id,name,building_id,phone,id_card,status,created_at,room_id FROM tenants")
            c.execute("DROP TABLE tenants")
            c.execute("ALTER TABLE tenants_new RENAME TO tenants")
            c.execute("PRAGMA foreign_keys=ON")
    c.execute("""CREATE TABLE IF NOT EXISTS contracts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL REFERENCES tenants(id),
        room_id INTEGER NOT NULL REFERENCES rooms(id),
        start_date TEXT NOT NULL, end_date TEXT DEFAULT '',
        monthly_rent REAL DEFAULT 0,
        water_unit_price REAL DEFAULT 0,
        electric_unit_price REAL DEFAULT 0,
        deposit REAL DEFAULT 0, contract_file TEXT DEFAULT '',
        other_fee_details TEXT DEFAULT '[]',
        water_meter_id INTEGER, electric_meter_id INTEGER,
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    try:
        c.execute("ALTER TABLE contracts ADD COLUMN other_fee_details TEXT DEFAULT '[]'")
    except: pass
    try:
        c.execute("ALTER TABLE contracts ADD COLUMN water_meter_id INTEGER")
    except: pass
    try:
        c.execute("ALTER TABLE contracts ADD COLUMN electric_meter_id INTEGER")
    except: pass
    c.execute("""CREATE TABLE IF NOT EXISTS meters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id INTEGER NOT NULL REFERENCES rooms(id),
        type TEXT NOT NULL CHECK(type IN ('water','electric')),
        meter_no TEXT DEFAULT '', init_reading REAL DEFAULT 0,
        photo TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    try:
        c.execute("ALTER TABLE meters ADD COLUMN photo TEXT DEFAULT ''")
    except: pass
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
        other_fee_details TEXT DEFAULT '[]',
        total_amount REAL DEFAULT 0, status TEXT DEFAULT 'unpaid',
        water_last_reading REAL DEFAULT 0, water_current_reading REAL DEFAULT 0,
        electric_last_reading REAL DEFAULT 0, electric_current_reading REAL DEFAULT 0,
        water_photo TEXT DEFAULT '', electric_photo TEXT DEFAULT '',
        remark TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    try:
        c.execute("ALTER TABLE bills ADD COLUMN water_last_reading REAL DEFAULT 0")
    except: pass
    try:
        c.execute("ALTER TABLE bills ADD COLUMN water_current_reading REAL DEFAULT 0")
    except: pass
    try:
        c.execute("ALTER TABLE bills ADD COLUMN electric_last_reading REAL DEFAULT 0")
    except: pass
    try:
        c.execute("ALTER TABLE bills ADD COLUMN electric_current_reading REAL DEFAULT 0")
    except: pass
    try:
        c.execute("ALTER TABLE bills ADD COLUMN water_photo TEXT DEFAULT ''")
    except: pass
    try:
        c.execute("ALTER TABLE bills ADD COLUMN electric_photo TEXT DEFAULT ''")
    except: pass
    try:
        c.execute("ALTER TABLE bills ADD COLUMN other_fee_details TEXT DEFAULT '[]'")
    except: pass
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




def load_chats(search='', archived=False):
    c = _conn()
    wh = ["archived=?"]
    params = [1 if archived else 0]
    if search:
        wh.append("(title LIKE ? OR messages LIKE ?)")
        like = "%" + str(search) + "%"
        params.extend([like, like])
    rows = c.execute(
        "SELECT id, title, messages, created_at, archived FROM chat_history "
        "WHERE " + " AND ".join(wh) + " ORDER BY created_at DESC LIMIT 80",
        params,
    ).fetchall()
    c.close()
    return [{"id": r["id"], "title": r["title"], "messages": json.loads(r["messages"]), "time": r["created_at"], "archived": bool(r["archived"])} for r in rows]

def delete_chat(conv_id):
    c = _conn()
    c.execute("DELETE FROM chat_history WHERE id=?", (conv_id,))
    c.commit()
    c.close()

def set_chat_archived(conv_id, archived=True):
    c = _conn()
    c.execute("UPDATE chat_history SET archived=? WHERE id=?", (1 if archived else 0, conv_id))
    c.commit()
    c.close()

def save_chat(title, messages):
    c = _conn()
    c.execute("INSERT INTO chat_history (title, messages, created_at) VALUES (?,?,datetime('now','localtime'))", (title, json.dumps(messages, ensure_ascii=False)))
    c.commit()
    conv_id = c.lastrowid
    c.close()
    return conv_id

def update_chat(conv_id, title, messages):
    c = _conn()
    c.execute(
        "UPDATE chat_history SET title=?, messages=?, created_at=datetime('now','localtime') WHERE id=?",
        (title, json.dumps(messages, ensure_ascii=False), conv_id),
    )
    c.commit()
    c.close()


def load_ai_thread_state(thread_id):
    if not thread_id:
        return {}
    c = _conn()
    row = c.execute("SELECT state FROM ai_thread_state WHERE thread_id=?", (str(thread_id),)).fetchone()
    c.close()
    if not row:
        return {}
    try:
        state = json.loads(row["state"] or "{}")
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def save_ai_thread_state(thread_id, state):
    if not thread_id:
        return False
    payload = json.dumps(state if isinstance(state, dict) else {}, ensure_ascii=False, default=str)
    c = _conn()
    c.execute(
        "INSERT OR REPLACE INTO ai_thread_state (thread_id, state, updated_at) VALUES (?,?,datetime('now','localtime'))",
        (str(thread_id), payload),
    )
    c.commit()
    c.close()
    return True


def append_ai_trace(thread_id, event, payload=None):
    c = _conn()
    c.execute(
        "INSERT INTO ai_trace (thread_id, event, payload, created_at) VALUES (?,?,?,datetime('now','localtime'))",
        (
            str(thread_id or ""),
            str(event or ""),
            json.dumps(payload if isinstance(payload, dict) else {}, ensure_ascii=False, default=str),
        ),
    )
    c.commit()
    c.close()
    return True


def load_ai_trace(thread_id, limit=80):
    c = _conn()
    rows = c.execute(
        "SELECT id, thread_id, event, payload, created_at FROM ai_trace WHERE thread_id=? ORDER BY id DESC LIMIT ?",
        (str(thread_id or ""), int(limit or 80)),
    ).fetchall()
    c.close()
    items = []
    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}
        items.append({
            "id": row["id"],
            "thread_id": row["thread_id"],
            "event": row["event"],
            "payload": payload,
            "time": row["created_at"],
        })
    return list(reversed(items))


# ============================================================
# 租房管理 CRUD
# ============================================================

def add_building(name, address=''):
    c = _conn()
    cur = c.execute("INSERT INTO buildings (name, address) VALUES (?,?)", (name, address))
    c.commit(); pk = cur.lastrowid; c.close()
    clear_rental_cache()
    return pk

@_cached_rental
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
    clear_rental_cache()

def delete_building(bid):
    c = _conn()
    c.execute("DELETE FROM buildings WHERE id=?", (bid,))
    c.commit(); c.close()
    clear_rental_cache()

def add_room(building_id, room_number, floor=1, status='idle'):
    c = _conn()
    cur = c.execute("INSERT INTO rooms (building_id, room_number, floor, status) VALUES (?,?,?,?)", (building_id, room_number, floor, status))
    c.commit(); pk = cur.lastrowid; c.close()
    clear_rental_cache()
    return pk

@_cached_rental
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
    clear_rental_cache()

def add_tenant(name, phone='', id_card='', status='active', building_id=None, room_id=None):
    c = _conn()
    cur = c.execute("INSERT INTO tenants (name, phone, id_card, status, building_id, room_id) VALUES (?,?,?,?,?,?)", (name, phone, id_card, status, building_id, room_id))
    c.commit(); pk = cur.lastrowid; c.close()
    clear_rental_cache()
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

def update_tenant(tid, name, phone, id_card, status='active', building_id=None, room_id=None):
    c = _conn()
    c.execute("UPDATE tenants SET name=?,phone=?,id_card=?,status=?,building_id=?,room_id=? WHERE id=?", (name, phone, id_card, status, building_id, room_id, tid))
    c.commit(); c.close()
    clear_rental_cache()

def set_tenant_status(tid, status):
    c = _conn()
    c.execute("UPDATE tenants SET status=? WHERE id=?", (status, tid))
    c.commit(); c.close()
    clear_rental_cache()

def add_contract(tenant_id, room_id, start_date, end_date='',
                 monthly_rent=0, water_price=0, electric_price=0,
                 deposit=0, contract_file='', status='active',
                 water_meter_id=None, electric_meter_id=None,
                 other_fee_details='[]'):
    c = _conn()
    cur = c.execute("""INSERT INTO contracts
        (tenant_id,room_id,start_date,end_date,monthly_rent,
         water_unit_price,electric_unit_price,deposit,contract_file,status,
         water_meter_id,electric_meter_id,other_fee_details)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (tenant_id, room_id, start_date, end_date, monthly_rent,
         water_price, electric_price, deposit, contract_file, status,
         water_meter_id, electric_meter_id, other_fee_details or '[]'))
    if room_id:
        c.execute("UPDATE rooms SET status=? WHERE id=?", ("rented" if status == "active" else "idle", room_id))
    c.commit(); pk = cur.lastrowid; c.close()
    clear_rental_cache()
    return pk

@_cached_rental
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
                    deposit=0, contract_file='', status='active',
                    water_meter_id=None, electric_meter_id=None,
                    other_fee_details='[]'):
    c = _conn()
    c.execute("""UPDATE contracts SET tenant_id=?,room_id=?,start_date=?,end_date=?,
        monthly_rent=?,water_unit_price=?,electric_unit_price=?,deposit=?,
        contract_file=?,status=?,water_meter_id=?,electric_meter_id=?,other_fee_details=? WHERE id=?""",
        (tenant_id, room_id, start_date, end_date, monthly_rent,
         water_price, electric_price, deposit, contract_file, status,
         water_meter_id, electric_meter_id, other_fee_details or '[]', cid))
    if room_id:
        c.execute("UPDATE rooms SET status=? WHERE id=?", ("rented" if status == "active" else "idle", room_id))
    c.commit(); c.close()
    clear_rental_cache()

def end_contract(cid, end_date=''):
    c = _conn()
    row = c.execute("SELECT room_id FROM contracts WHERE id=?", (cid,)).fetchone()
    if end_date:
        c.execute("UPDATE contracts SET status='ended',end_date=? WHERE id=?", (end_date, cid))
    else:
        c.execute("UPDATE contracts SET status='ended' WHERE id=?", (cid,))
    if row and row["room_id"]:
        c.execute("UPDATE rooms SET status='idle' WHERE id=?", (row["room_id"],))
    c.commit(); c.close()
    clear_rental_cache()

def add_meter(room_id, mtype, meter_no='', init_reading=0.0, photo=''):
    c = _conn()
    cur = c.execute("INSERT INTO meters (room_id,type,meter_no,init_reading,photo) VALUES (?,?,?,?,?)",
              (room_id, mtype, meter_no, init_reading, photo))
    c.commit(); pk = cur.lastrowid; c.close()
    clear_rental_cache()
    return pk

@_cached_rental
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

def update_meter(mid, room_id, mtype, meter_no='', init_reading=0.0, photo=None):
    c = _conn()
    if photo is not None:
        c.execute("UPDATE meters SET room_id=?,type=?,meter_no=?,init_reading=?,photo=? WHERE id=?",
                  (room_id, mtype, meter_no, init_reading, photo, mid))
    else:
        c.execute("UPDATE meters SET room_id=?,type=?,meter_no=?,init_reading=? WHERE id=?",
                  (room_id, mtype, meter_no, init_reading, mid))
    c.commit(); c.close()
    clear_rental_cache()

def add_reading(meter_id, reading_date, reading, photo='', remark=''):
    c = _conn()
    c.execute("INSERT INTO meter_readings (meter_id,reading_date,reading,photo,remark) VALUES (?,?,?,?,?)",
              (meter_id, reading_date, reading, photo, remark))
    c.commit(); pk = c.lastrowid; c.close()
    clear_rental_cache()
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

@_cached_rental
def get_monthly_meter_readings(mtype='water', building_id=None, month='', meter_id=None):
    month = (month or '')[:7]
    c = _conn()
    params = [mtype]
    sql = ("SELECT m.*,r.building_id,r.room_number,r.floor,b.name AS building_name "
           "FROM meters m JOIN rooms r ON m.room_id=r.id "
           "JOIN buildings b ON r.building_id=b.id WHERE m.type=?")
    if meter_id:
        sql += " AND m.id=?"
        params.append(meter_id)
    if building_id:
        sql += " AND r.building_id=?"
        params.append(building_id)
    sql += " ORDER BY b.id,COALESCE(r.floor,1),CAST(r.room_number AS INTEGER),r.room_number,m.id"
    meters = c.execute(sql, params).fetchall()
    result = []
    for m in meters:
        current = None
        if month:
            current = c.execute(
                "SELECT * FROM meter_readings WHERE meter_id=? AND substr(reading_date,1,7)=? ORDER BY id DESC LIMIT 1",
                (m["id"], month)
            ).fetchone()
        previous = None
        if month:
            previous = c.execute(
                "SELECT * FROM meter_readings WHERE meter_id=? AND substr(reading_date,1,7)<? ORDER BY substr(reading_date,1,7) DESC, reading_date DESC, id DESC LIMIT 1",
                (m["id"], month)
            ).fetchone()
        else:
            previous = c.execute(
                "SELECT * FROM meter_readings WHERE meter_id=? ORDER BY reading_date DESC, id DESC LIMIT 1",
                (m["id"],)
            ).fetchone()
        prev_reading = float(previous["reading"]) if previous else float(m["init_reading"] or 0)
        curr_reading = float(current["reading"]) if current else None
        usage = None if curr_reading is None else round(max(0, curr_reading - prev_reading), 2)
        item = dict(m)
        item.update({
            "reading_id": current["id"] if current else None,
            "reading_date": current["reading_date"] if current else month,
            "reading": curr_reading,
            "previous_reading": prev_reading,
            "previous_date": previous["reading_date"] if previous else "",
            "usage": usage,
            "photo": current["photo"] if current else "",
            "remark": current["remark"] if current else "",
            "status": "recorded" if current else "pending",
        })
        result.append(item)
    c.close()
    return result

def save_monthly_meter_reading(meter_id, month, reading, photo='', remark=''):
    month = (month or '')[:7]
    c = _conn()
    existing = c.execute(
        "SELECT id FROM meter_readings WHERE meter_id=? AND substr(reading_date,1,7)=? ORDER BY id DESC LIMIT 1",
        (meter_id, month)
    ).fetchone()
    if existing:
        c.execute(
            "UPDATE meter_readings SET reading_date=?,reading=?,photo=?,remark=? WHERE id=?",
            (month, reading, photo or '', remark or '', existing["id"])
        )
        pk = existing["id"]
    else:
        cur = c.execute(
            "INSERT INTO meter_readings (meter_id,reading_date,reading,photo,remark) VALUES (?,?,?,?,?)",
            (meter_id, month, reading, photo or '', remark or '')
        )
        pk = cur.lastrowid
    c.commit(); c.close()
    clear_rental_cache()
    return {"id": pk, "success": True}

def _month_range(start_month, end_month):
    try:
        sy, sm = [int(x) for x in (start_month or "2026-06")[:7].split("-")]
        ey, em = [int(x) for x in (end_month or start_month or "2026-06")[:7].split("-")]
    except:
        sy, sm, ey, em = 2026, 6, 2026, 6
    if (ey, em) < (sy, sm):
        ey, em = sy, sm
    months = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y += 1
            m = 1
    return months

def get_meter_reading_overview(mtype='water', building_id=None, start_month='2026-06', end_month=''):
    months = _month_range(start_month, end_month or start_month)
    c = _conn()
    params = [mtype]
    sql = ("SELECT m.*,r.building_id,r.room_number,r.floor,b.name AS building_name "
           "FROM meters m JOIN rooms r ON m.room_id=r.id "
           "JOIN buildings b ON r.building_id=b.id WHERE m.type=?")
    if building_id:
        sql += " AND r.building_id=?"
        params.append(building_id)
    sql += " ORDER BY b.id,COALESCE(r.floor,1),CAST(r.room_number AS INTEGER),r.room_number,m.id"
    meters = c.execute(sql, params).fetchall()
    rows = []
    for m in meters:
        reading_map = {month: None for month in months}
        if months:
            readings = c.execute(
                "SELECT id,substr(reading_date,1,7) AS month,reading FROM meter_readings "
                "WHERE meter_id=? AND substr(reading_date,1,7)>=? AND substr(reading_date,1,7)<=? "
                "ORDER BY substr(reading_date,1,7),id",
                (m["id"], months[0], months[-1])
            ).fetchall()
            for r in readings:
                reading_map[r["month"]] = float(r["reading"])
        item = dict(m)
        item["readings"] = reading_map
        rows.append(item)
    c.close()
    return {"months": months, "rows": rows}

def add_bill(contract_id, billing_month, rent_amount, water_fee=0,
             electric_fee=0, other_fee=0, remark='',
             water_last=0, water_curr=0, electric_last=0, electric_curr=0,
             water_photo='', electric_photo='', other_fee_details='[]'):
    total = round(rent_amount + water_fee + electric_fee + other_fee, 2)
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""INSERT INTO bills
        (contract_id,billing_month,rent_amount,water_fee,electric_fee,
         other_fee,other_fee_details,total_amount,remark,
         water_last_reading,water_current_reading,
         electric_last_reading,electric_current_reading,
         water_photo,electric_photo)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (contract_id, billing_month, rent_amount, water_fee,
         electric_fee, other_fee, other_fee_details or '[]', total, remark,
         water_last, water_curr, electric_last, electric_curr,
         water_photo, electric_photo))
    pk = cur.lastrowid
    conn.commit(); conn.close()
    clear_rental_cache()
    return pk

@_cached_rental
def get_bills(month=None, contract_id=None, include_photos=True):
    c = _conn()
    where, params = [], []
    if month:
        where.append("b.billing_month=?"); params.append(month)
    if contract_id:
        where.append("b.contract_id=?"); params.append(contract_id)
    wh = (" WHERE " + " AND ".join(where)) if where else ''
    bill_columns = (
        "b.*" if include_photos else
        "b.id,b.contract_id,b.billing_month,b.rent_amount,b.water_fee,b.electric_fee,"
        "b.other_fee,b.other_fee_details,b.total_amount,b.remark,b.status,"
        "b.water_last_reading,b.water_current_reading,"
        "b.electric_last_reading,b.electric_current_reading"
    )
    sql = ("SELECT " + bill_columns + ",t.name AS tenant_name,r.room_number,bld.id AS building_id,bld.name AS building_name "
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
    r = c.execute("SELECT b.*,t.name AS tenant_name,r.room_number,bld.id AS building_id,bld.name AS building_name "
                  "FROM bills b "
                  "JOIN contracts c ON b.contract_id=c.id "
                  "JOIN tenants t ON c.tenant_id=t.id "
                  "JOIN rooms r ON c.room_id=r.id "
                  "JOIN buildings bld ON r.building_id=bld.id "
                  "WHERE b.id=?", (bid,)).fetchone()
    c.close()
    return dict(r) if r else None

def update_bill(bid, contract_id=None, billing_month=None, rent_amount=None,
                water_fee=None, electric_fee=None, other_fee=None, remark=None,
                water_last=None, water_curr=None, electric_last=None, electric_curr=None,
                water_photo=None, electric_photo=None, other_fee_details=None):
    c = _conn()
    sets, params = [], []
    if contract_id is not None: sets.append("contract_id=?"); params.append(contract_id)
    if billing_month is not None: sets.append("billing_month=?"); params.append(billing_month)
    if rent_amount is not None: sets.append("rent_amount=?"); params.append(rent_amount)
    if water_fee is not None: sets.append("water_fee=?"); params.append(water_fee)
    if electric_fee is not None: sets.append("electric_fee=?"); params.append(electric_fee)
    if other_fee is not None: sets.append("other_fee=?"); params.append(other_fee)
    if other_fee_details is not None: sets.append("other_fee_details=?"); params.append(other_fee_details)
    if remark is not None: sets.append("remark=?"); params.append(remark)
    if water_last is not None: sets.append("water_last_reading=?"); params.append(water_last)
    if water_curr is not None: sets.append("water_current_reading=?"); params.append(water_curr)
    if electric_last is not None: sets.append("electric_last_reading=?"); params.append(electric_last)
    if electric_curr is not None: sets.append("electric_current_reading=?"); params.append(electric_curr)
    if water_photo is not None: sets.append("water_photo=?"); params.append(water_photo)
    if electric_photo is not None: sets.append("electric_photo=?"); params.append(electric_photo)
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
    clear_rental_cache()

def update_bill_status(bid, status):
    c = _conn()
    c.execute("UPDATE bills SET status=? WHERE id=?", (status, bid))
    c.commit(); c.close()
    clear_rental_cache()

def add_payment(bill_id, amount, pay_date=None, pay_method='', remark=''):
    if pay_date is None:
        from datetime import date; pay_date = date.today().isoformat()
    c = _conn()
    cur = c.execute("INSERT INTO payments (bill_id,amount,pay_date,pay_method,remark) VALUES (?,?,?,?,?)",
                    (bill_id, amount, pay_date, pay_method, remark))
    c.commit(); pk = cur.lastrowid; c.close()
    _update_bill_payment_status(bill_id)
    clear_rental_cache()
    return pk

def update_payment(pid, amount=None, pay_date=None, pay_method=None, remark=None):
    c = _conn()
    row = c.execute("SELECT bill_id FROM payments WHERE id=?", (pid,)).fetchone()
    if not row:
        c.close()
        return {"success": False, "error": "payment not found"}
    sets, params = [], []
    if amount is not None: sets.append("amount=?"); params.append(amount)
    if pay_date is not None: sets.append("pay_date=?"); params.append(pay_date)
    if pay_method is not None: sets.append("pay_method=?"); params.append(pay_method)
    if remark is not None: sets.append("remark=?"); params.append(remark)
    if sets:
        params.append(pid)
        c.execute("UPDATE payments SET " + ",".join(sets) + " WHERE id=?", params)
    c.commit(); c.close()
    _update_bill_payment_status(row["bill_id"])
    clear_rental_cache()
    return {"success": True}

def get_payments(bill_id=None, month=None, building_id=None, keyword='', start_date=None, end_date=None, pay_method=None):
    c = _conn()
    where, params = [], []
    if bill_id:
        where.append("p.bill_id=?"); params.append(bill_id)
    if month:
        where.append("b.billing_month=?"); params.append(month)
    if building_id:
        where.append("bld.id=?"); params.append(building_id)
    if start_date:
        where.append("p.pay_date>=?"); params.append(start_date)
    if end_date:
        where.append("p.pay_date<=?"); params.append(end_date)
    if pay_method:
        where.append("p.pay_method=?"); params.append(pay_method)
    kw = str(keyword or '').strip()
    if kw:
        where.append("(t.name LIKE ? OR r.room_number LIKE ? OR bld.name LIKE ? OR p.remark LIKE ?)")
        like = f"%{kw}%"
        params.extend([like, like, like, like])
    wh = (" WHERE " + " AND ".join(where)) if where else ''
    order = " ORDER BY p.pay_date ASC,p.id ASC LIMIT 500"
    rows = c.execute(
        "SELECT p.*,b.billing_month,b.total_amount,b.status AS bill_status,"
        "t.name AS tenant_name,r.room_number,bld.id AS building_id,bld.name AS building_name "
        "FROM payments p "
        "JOIN bills b ON p.bill_id=b.id "
        "JOIN contracts c ON b.contract_id=c.id "
        "JOIN tenants t ON c.tenant_id=t.id "
        "JOIN rooms r ON c.room_id=r.id "
        "JOIN buildings bld ON r.building_id=bld.id" + wh + order,
        params
    ).fetchall()
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
    clear_rental_cache()

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
    clear_rental_cache()

# === AI 知识库 ===
def save_knowledge(title, content, category=""):
    c = _conn()
    c.execute("INSERT INTO ai_knowledge (title, content, category) VALUES (?,?,?)", (title, content, category))
    c.commit(); c.close()

def get_all_knowledge():
    c = _conn()
    rows = c.execute("SELECT id, title, content, category FROM ai_knowledge ORDER BY id").fetchall()
    c.close()
    return [{"id":r["id"],"title":r["title"],"content":r["content"],"category":r["category"]} for r in rows]

def clear_knowledge():
    c = _conn()
    c.execute("DELETE FROM ai_knowledge")
    c.commit(); c.close()
