# -*- coding: utf-8 -*-
"""
2026年 惠州市华阳多媒体电子有限公司 年历
数据来源：2026年华阳多媒体年历.pdf
"""
from datetime import date

# ==================== 法定节假日（含调休，这些日期休息） ====================
HOLIDAYS_2026 = {
    # 元旦：1月1日-1月3日
    date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3),
    # 春节：2月13日(年廿六)-2月23日(初七)
    *[date(2026, 2, d) for d in range(13, 24)],
    # 清明节：4月4日-4月6日
    date(2026, 4, 4), date(2026, 4, 5), date(2026, 4, 6),
    # 劳动节：5月1日-5月5日
    *[date(2026, 5, d) for d in range(1, 6)],
    # 端午节：6月19日-6月21日
    date(2026, 6, 19), date(2026, 6, 20), date(2026, 6, 21),
    # 中秋节：9月25日-9月27日
    date(2026, 9, 25), date(2026, 9, 26), date(2026, 9, 27),
    # 国庆节：10月1日-10月7日
    *[date(2026, 10, d) for d in range(1, 8)],
}

# ==================== 补班日（这些周末需要上班） ====================
MAKEUP_WORKDAYS_2026 = {
    date(2026, 1, 4),    # 元旦补班
    date(2026, 1, 31),   # 春节补班
    date(2026, 2, 7),    # 春节补班
    date(2026, 2, 28),   # 春节补班
    date(2026, 5, 9),    # 劳动节补班
    date(2026, 9, 20),   # 国庆节补班
    date(2026, 10, 10),  # 国庆节补班
}


def get_day_type(d: date) -> str:
    """
    判断某天是什么类型
    返回: 'holiday' | 'makeup' | 'weekend' | 'weekday'
    """
    if d in HOLIDAYS_2026:
        return "holiday"
    if d in MAKEUP_WORKDAYS_2026:
        return "makeup"
    if d.weekday() >= 5:  # 周六=5, 周日=6
        return "weekend"
    return "weekday"


def is_rest_day(d: date) -> bool:
    """
    判断是否为休息日（节假日/普通周末且非补班日）
    """
    if d in HOLIDAYS_2026:
        return True
    if d in MAKEUP_WORKDAYS_2026:
        return False
    return d.weekday() >= 5


def is_workday(d: date) -> bool:
    """判断是否为工作日"""
    return not is_rest_day(d)


def get_day_type_label(d: date) -> str:
    """获取日期类型的中文标签"""
    type_map = {
        "holiday": "节假日",
        "makeup":  "补班日",
        "weekend": "休息日",
        "weekday": "平日",
    }
    return type_map[get_day_type(d)]


def get_holiday_name(d: date) -> str:
    """获取节日名称，不是节日返回空字符串"""
    names = {
        date(2026, 1, 1): "元旦",
        date(2026, 1, 2): "元旦",
        date(2026, 1, 3): "元旦",
        date(2026, 2, 13): "春节",
        date(2026, 2, 14): "春节",
        date(2026, 2, 15): "春节",
        date(2026, 2, 16): "春节",
        date(2026, 2, 17): "除夕",
        date(2026, 2, 18): "春节",
        date(2026, 2, 19): "春节",
        date(2026, 2, 20): "春节",
        date(2026, 2, 21): "春节",
        date(2026, 2, 22): "春节",
        date(2026, 2, 23): "春节",
        date(2026, 4, 4): "清明",
        date(2026, 4, 5): "清明",
        date(2026, 4, 6): "清明",
        date(2026, 5, 1): "劳动节",
        date(2026, 5, 2): "劳动节",
        date(2026, 5, 3): "劳动节",
        date(2026, 5, 4): "劳动节",
        date(2026, 5, 5): "劳动节",
        date(2026, 6, 19): "端午",
        date(2026, 6, 20): "端午",
        date(2026, 6, 21): "端午",
        date(2026, 9, 25): "中秋",
        date(2026, 9, 26): "中秋",
        date(2026, 9, 27): "中秋",
        date(2026, 10, 1): "国庆",
        date(2026, 10, 2): "国庆",
        date(2026, 10, 3): "国庆",
        date(2026, 10, 4): "国庆",
        date(2026, 10, 5): "国庆",
        date(2026, 10, 6): "国庆",
        date(2026, 10, 7): "国庆",
    }
    return names.get(d, "")
