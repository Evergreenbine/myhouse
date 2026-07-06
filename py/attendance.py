# -*- coding: utf-8 -*-
"""
考勤分析模块 - 加班计算、漏打卡检测
"""
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple
import math

from config import (
    OVERTIME_RATE, OFF_WORK_HOUR,
    OVERTIME_START_HOUR, OVERTIME_START_MINUTE,
    OVERTIME_ROUND,
)
from calendar_2026 import is_rest_day, get_day_type_label, get_day_type


def get_company_month_range(target_date: date = None) -> Tuple[date, date]:
    """
    获取公司月份范围：上月24日 ~ 本月23日

    例如：target_date=2026-06-10 → 2026-05-24 ~ 2026-06-23
    """
    if target_date is None:
        target_date = date.today()

    # 如果当天 < 24号，说明属于上个月的公司月
    if target_date.day < 24:
        # 开始：上上月24日
        first = date(target_date.year, target_date.month, 1)
        prev_month = first - timedelta(days=1)
        start = date(prev_month.year, prev_month.month, 24)
        end = date(target_date.year, target_date.month, 23)
    else:
        # 开始：上月24日
        start = date(target_date.year, target_date.month, 24)
        # 结束：本月23日
        # 找下个月
        if target_date.month == 12:
            end = date(target_date.year + 1, 1, 23)
        else:
            end = date(target_date.year, target_date.month + 1, 23)

    return start, end


def get_company_month_label(target_date: date = None) -> str:
    """获取公司月份标签，如 '2026年6月'"""
    if target_date is None:
        target_date = date.today()
    _, end = get_company_month_range(target_date)
    return f"{end.year}年{end.month}月"


def extract_card_times(records: List[Dict]) -> List[datetime]:
    """
    从考勤记录中提取打卡时间列表（datetime类型）
    按时间升序排列
    """
    times = []
    for r in records:
        wt = r.get("worktime")
        if wt is None:
            continue
        if isinstance(wt, datetime):
            times.append(wt)
        elif isinstance(wt, str):
            try:
                # 尝试多种格式
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f",
                            "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]:
                    try:
                        times.append(datetime.strptime(wt, fmt))
                        break
                    except ValueError:
                        continue
            except Exception:
                pass
    times.sort()
    return times


def calculate_overtime_hours(records: List[Dict], d: date = None) -> float:
    """
    计算当天的加班小时数

    平日逻辑：
    1. 找出当天 17:30 之后的最晚打卡时间
    2. 加班 = 最晚打卡时间 - 18:00
    3. 按 0.5 小时向下取整

    休息日/节假日逻辑：
    1. 最大打卡时间 - 最小打卡时间 - 1小时（午餐休息）
    2. 按 0.5 小时向下取整

    返回: 加班小时数（0.5 的倍数）
    """
    card_times = extract_card_times(records)
    if not card_times:
        return 0.0

    # 判断是否是休息日/节假日
    is_rest = False
    if d is not None:
        day_type = get_day_type(d)
        is_rest = day_type in ("weekend", "holiday")

    if is_rest:
        # 休息日：最大 - 最小 - 午休重叠
        earliest = min(card_times)
        latest = max(card_times)
        diff = latest - earliest
        hours = diff.total_seconds() / 3600.0
        # 只有工作时间覆盖到午休（12:05-13:05）才减
        lunch_start = earliest.replace(hour=12, minute=5, second=0, microsecond=0)
        lunch_end = latest.replace(hour=13, minute=5, second=0, microsecond=0)
        if latest > lunch_start and earliest < lunch_end:
            overlap_start = max(earliest, lunch_start)
            overlap_end = min(latest, lunch_end)
            lunch_overlap = (overlap_end - overlap_start).total_seconds() / 3600.0
            hours -= lunch_overlap
        if hours <= 0:
            return 0.0
    else:
        # 平日：17:30 之后最晚打卡 - 18:00
        cutoff = card_times[0].replace(hour=OVERTIME_START_HOUR, minute=OVERTIME_START_MINUTE, second=0, microsecond=0)
        after_cards = [t for t in card_times if t > cutoff]
        if not after_cards:
            return 0.0
        latest = max(after_cards)
        base = latest.replace(hour=OFF_WORK_HOUR, minute=0, second=0, microsecond=0)
        diff = latest - base
        hours = diff.total_seconds() / 3600.0
        if hours <= 0:
            return 0.0

    # 按 0.5 小时向下取整
    rounded = math.floor(hours / OVERTIME_ROUND) * OVERTIME_ROUND
    return rounded


def get_overtime_rate(d: date, user_config=None) -> float:
    """
    获取某天的加班费率（从用户配置读取基数）

    - 平日：1.5 × 基数
    - 休息日（含节假日）：2.0 × 基数
    - 补班日：3.0 × 基数
    """
    if user_config is not None:
        base = user_config.base_salary
    else:
        base = OVERTIME_RATE["weekday"] / 1.5  # 兜底
    day_type = get_day_type(d)
    if day_type == "makeup":
        return base * 3.0
    elif day_type in ("weekend", "holiday"):
        return base * 2.0
    else:
        return base * 1.5


def check_missed_punch(records: List[Dict], d: date) -> Tuple[bool, int, int]:
    """
    检查是否漏打卡

    返回: (是否漏打卡, 实际打卡次数, 要求打卡次数)
    - 今天及以后的日期：不检查
    - 平日：需要 ≥ 2 次
    - 补班日：需要 ≥ 4 次
    - 休息日/节假日：不检查（非强制上班）
    """
    card_times = extract_card_times(records)
    actual = len(card_times)
    day_type = get_day_type(d)
    today = date.today()

    # 今天及以后的日期不检查漏打卡
    if d >= today:
        return False, actual, 0

    if day_type == "makeup":
        required = 4
    elif day_type in ("weekend", "holiday"):
        # 休息日不强制上班，不检查漏打卡
        required = 0
    else:
        required = 2

    missed = actual < required if required > 0 else False
    return missed, actual, required


class DayAnalysis:
    """某一天的考勤分析结果"""

    def __init__(self, d: date, records: List[Dict], user_config=None):
        self.date = d
        self.records = records
        self.day_type = get_day_type(d)
        self.day_type_label = get_day_type_label(d)
        self.is_rest = is_rest_day(d)
        self.is_makeup = (self.day_type == "makeup")

        # 打卡次数
        card_times = extract_card_times(records)
        self.card_count = len(card_times)
        self.card_times = card_times

        # 漏打卡
        self.missed, _, self.required_cards = check_missed_punch(records, d)

        # 加班（传入日期以区分平日/休息日计算方式）
        self.overtime_hours = calculate_overtime_hours(records, d)
        self.overtime_rate = get_overtime_rate(d, user_config)
        self.overtime_pay = round(self.overtime_hours * self.overtime_rate, 2)

    def to_dict(self) -> Dict:
        return {
            "date": self.date.isoformat(),
            "day_type": self.day_type_label,
            "is_rest": self.is_rest,
            "is_makeup": self.is_makeup,
            "card_count": self.card_count,
            "required_cards": self.required_cards,
            "missed": self.missed,
            "card_times": [t.strftime("%H:%M") for t in self.card_times],
            "overtime_hours": self.overtime_hours,
            "overtime_rate": self.overtime_rate,
            "overtime_pay": self.overtime_pay,
        }
