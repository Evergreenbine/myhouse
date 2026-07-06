# -*- coding: utf-8 -*-
"""
数据库和应用配置
请在此文件中填写实际的数据库连接信息
"""

# ==================== 数据库配置 ====================
DB_CONFIG = {
    "server": "10.3.10.86",      # 数据库服务器地址
    "port": 1433,                 # SQL Server 端口
    "database": "G4PRO",          # 数据库名
    "user": "Oa13",               # 用户名
    "password": "Oa13sql788",     # 密码
}

# ==================== 应用配置 ====================
# 员工姓名（用于查询考勤记录）
EMP_NAME = "吴钦腾"

# 加班费率（元/小时）
OVERTIME_RATE = {
    "weekday": 20.5,   # 平日加班
    "weekend": 27.5,   # 休息日加班
    "makeup":  41.0,   # 补班日加班
}

# 下班时间
OFF_WORK_HOUR = 18  # 18:00

# 17:30 之后才算加班
OVERTIME_START_HOUR = 17
OVERTIME_START_MINUTE = 30

# 加班取整单位（小时）
OVERTIME_ROUND = 0.5

# ==================== PostgreSQL 车辆出入数据库 ====================
PG_CONFIG = {
    "host": "10.3.10.156",
    "port": 7092,
    "database": "pms_pmsdb",
    "user": "pms_pmsdb_user",
    "password": "tWjfoaNe75shFRax",
}

# 默认查询车牌
CAR_PLATE = "粤S0Q780"
