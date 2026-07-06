# -*- coding: utf-8 -*-
"""趣味功能 Tab 页：加班趋势、工资倒计时、成就、心情、番茄钟/会议倒计时"""
import flet as ft
import json
import os
import threading
import time as _time
from datetime import date, datetime, timedelta
from fun_features import (
    ACHIEVEMENTS, check_achievements,
    load_mood_data, save_mood_data, set_mood, get_mood,
    load_achievements, unlock_achievement,
)
from ai_service import ai_svc

BLUE = "#3370FF"; BLUE_LIGHT = "#E8F0FE"
RED = "#F54A45"; GREEN = "#34C759"; ORANGE = "#FF9500"
PURPLE = "#CE93D8"
TEXT = "#1F2329"; TEXT_SEC = "#646A73"; TEXT_THIRD = "#8F959E"
BORDER = "#E5E6EB"; BG = "#F2F3F5"; WHITE = "#FFFFFF"

class FunTab:
    def __init__(self, page: ft.Page, app):
        self.page = page
        self.app = app
        self.today = date.today()

        # === 下班倒计时 ===
        self.countdown_text = ft.Text("", size=28, weight=ft.FontWeight.BOLD, color=BLUE)
        self.ot_estimate_text = ft.Text("", size=12, color=TEXT_SEC)

        # === 工资倒计时 ===
        self.salary_countdown_text = ft.Text("", size=14, weight=ft.FontWeight.W_500, color=ORANGE)
        self._update_salary_countdown()

        # === 加班趋势（简单文本柱状图） ===
        self.trend_col = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO)

        # === 成就 ===
        self.achievement_col = ft.Column(spacing=4)

        # === 心情日历 ===
        self.mood_col = ft.Column(spacing=4)

        # === 番茄钟 / 会议倒计时 ===
        self.timer_mode = ft.Dropdown(
            options=[ft.dropdown.Option("pomodoro", "番茄钟 25min"), ft.dropdown.Option("meeting", "会议倒计时")],
            value="pomodoro", width=160, dense=True, text_size=13)
        self.timer_display = ft.Text("25:00", size=48, weight=ft.FontWeight.BOLD, color=BLUE, text_align=ft.TextAlign.CENTER)
        self.timer_status = ft.Text("准备开始", size=12, color=TEXT_THIRD, text_align=ft.TextAlign.CENTER)
        self.timer_progress = ft.ProgressBar(value=0, width=300, color=BLUE, bgcolor=BORDER)
        self.meeting_minutes = ft.TextField(value="30", label="会议时长(分钟)", width=120, text_size=13, text_align=ft.TextAlign.CENTER)
        self._timer_running = False
        self._timer_paused = False
        self._timer_thread = None
        self._timer_seconds = 0
        self._timer_total = 0

        self._build_ui()

    def _build_ui(self):
        self.ai_fun_text = ft.Text("", size=12, color=TEXT_SEC, italic=True)

        self.content = ft.Column([
            ft.Container(height=4),
            # AI 趣味解读栏
            ft.Container(
                ft.Row([
                    ft.Icon(ft.icons.AUTO_AWESOME, size=16, color=ORANGE),
                    ft.Container(width=6),
                    self.ai_fun_text,
                    ft.Container(width=8),
                    ft.Chip(label=ft.Text("🎲 今日运势", size=11), bgcolor="#FFF8E1",
                            leading=ft.Icon(ft.icons.CASINO, size=14, color=ORANGE),
                            on_click=lambda e: self._ai_fortune()),
                    ft.Chip(label=ft.Text("💼 摸鱼指南", size=11), bgcolor="#FFF8E1",
                            leading=ft.Icon(ft.icons.BEDTIME, size=14, color=ORANGE),
                            on_click=lambda e: self._ai_fish_guide()),
                ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(horizontal=16, vertical=6),
                bgcolor="#FFF8E1", border_radius=10,
                margin=ft.margin.only(bottom=8),
            ),
            ft.Container(height=4),

            ft.ResponsiveRow([
                # 左列：下班倒计时 + 工资倒计时 + 加班趋势
                ft.Column(col={"lg": 7, "md": 12}, controls=[
                    ft.Row([
                        self._card("⏰ 下班倒计时", ft.Column([
                            self.countdown_text,
                            self.ot_estimate_text,
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
                            col=6),
                        self._card("💰 发薪倒计时", ft.Column([
                            self.salary_countdown_text,
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                            col=6),
                    ], spacing=12, wrap=True),
                    ft.Container(height=12),
                    self._card("📊 本月加班趋势", self.trend_col, col=12),
                ], spacing=0),
                # 右列：番茄钟 + 成就 + 心情
                ft.Column(col={"lg": 5, "md": 12}, controls=[
                    self._card("⏲ 番茄钟 / 会议倒计时", ft.Column([
                        self.timer_mode,
                        ft.Container(height=8),
                        self.timer_display,
                        self.timer_status,
                        ft.Container(height=8),
                        self.timer_progress,
                        ft.Container(height=8),
                        self.meeting_minutes,
                        ft.Container(height=8),
                        ft.Row([
                            ft.FilledButton("开始", icon=ft.icons.PLAY_ARROW, on_click=lambda e: self._start_timer()),
                            ft.OutlinedButton("暂停", icon=ft.icons.PAUSE, on_click=lambda e: self._pause_timer()),
                            ft.OutlinedButton("重置", icon=ft.icons.STOP, on_click=lambda e: self._reset_timer()),
                        ], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER), col=12),
                    ft.Container(height=12),
                    self._card("🏆 成就徽章", self.achievement_col, col=12),
                    ft.Container(height=12),
                    self._card("😊 心情日历", self.mood_col, col=12),
                ], spacing=0),
            ], spacing=12, expand=True),
        ], scroll=ft.ScrollMode.AUTO, expand=True)

    def _card(self, title, content, col=12):
        return ft.Container(
            ft.Column([
                ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=TEXT_SEC),
                ft.Container(height=8),
                content,
            ], spacing=2),
            padding=16, bgcolor=WHITE, border_radius=12, border=ft.border.all(1, BORDER),
            col=col,
        )

    # ===== 下班倒计时 + 加班预估 =====
    def _start_countdown_loop(self):
        def _run():
            while True:
                now = datetime.now()
                if now.weekday() >= 5:
                    self.countdown_text.value = "🎉 周末快乐!"
                    self.countdown_text.color = GREEN
                    self.ot_estimate_text.value = ""
                else:
                    off = now.replace(hour=18, minute=0, second=0, microsecond=0)
                    if now >= off:
                        self.countdown_text.value = "已下班! 🏃"
                        self.countdown_text.color = GREEN
                    else:
                        remaining = off - now
                        h = remaining.seconds // 3600
                        m = (remaining.seconds % 3600) // 60
                        s = remaining.seconds % 60
                        self.countdown_text.value = f"{h:02d}:{m:02d}:{s:02d}"
                        self.countdown_text.color = ORANGE if remaining.seconds < 3600 else BLUE
                    # 加班预估
                    self._update_ot_estimate(now)
                try:
                    self.countdown_text.update()
                    self.ot_estimate_text.update()
                except:
                    pass
                _time.sleep(1)
        threading.Thread(target=_run, daemon=True).start()

    def _update_ot_estimate(self, now):
        """根据今天已打卡记录预估加班"""
        ds = date.today().isoformat()
        if hasattr(self.app, 'analysis_map') and ds in self.app.analysis_map:
            a = self.app.analysis_map[ds]
            if a.overtime_hours > 0:
                self.ot_estimate_text.value = f"今日已加班 {a.overtime_hours:.1f}h  ¥{a.overtime_pay:.2f}"
                self.ot_estimate_text.color = GREEN
            else:
                self.ot_estimate_text.value = "今天还没加班"
                self.ot_estimate_text.color = TEXT_THIRD

    # ===== 工资倒计时 =====
    def _update_salary_countdown(self):
        """计算距离发薪日(每月5号)还有几天"""
        today = date.today()
        if today.day <= 5:
            payday = date(today.year, today.month, 5)
        else:
            if today.month == 12:
                payday = date(today.year + 1, 1, 5)
            else:
                payday = date(today.year, today.month + 1, 5)
        days = (payday - today).days
        if days == 0:
            self.salary_countdown_text.value = "🎉 今天发工资!"
        elif days == 1:
            self.salary_countdown_text.value = f"⏳ 明天发工资!"
        else:
            self.salary_countdown_text.value = f"还有 {days} 天发工资"

    # ===== 加班趋势 =====
    def load_trend(self):
        self.trend_col.controls.clear()
        if not hasattr(self.app, 'analysis_map') or not self.app.analysis_map:
            self.trend_col.controls.append(ft.Text("暂无数据", size=12, color=TEXT_THIRD))
            return
        # 按日期排序，计算累计加班
        items = sorted(self.app.analysis_map.items())
        max_h = max((a.overtime_hours for _, a in items), default=0)
        if max_h == 0:
            self.trend_col.controls.append(ft.Text("本月暂无加班", size=12, color=TEXT_THIRD))
            return

        for ds, a in items:
            if a.overtime_hours <= 0:
                continue
            bar_w = max(int(a.overtime_hours / max_h * 200), 4)
            color = GREEN if a.is_rest else (ORANGE if a.is_makeup else BLUE)
            label = "休" if a.is_rest else ("补" if a.is_makeup else "平")
            self.trend_col.controls.append(
                ft.Row([
                    ft.Text(ds[-5:], size=10, color=TEXT_THIRD, width=45),
                    ft.Container(ft.Text(f"{a.overtime_hours:.1f}h", size=10, color=WHITE),
                                 width=bar_w, height=18, bgcolor=color, border_radius=4,
                                 padding=ft.padding.only(left=4), alignment=ft.alignment.center_left),
                    ft.Text(label, size=10, color=TEXT_THIRD, width=20),
                ], spacing=4)
            )
        if not self.trend_col.controls:
            self.trend_col.controls.append(ft.Text("本月暂无加班", size=12, color=TEXT_THIRD))

    # ===== 成就 =====
    def load_achievements(self):
        self.achievement_col.controls.clear()
        unlocked = load_achievements()
        # 构建统计
        stats = self._build_stats()
        # 检查新成就
        new_achs = check_achievements(stats, unlocked)
        for na in new_achs:
            unlock_achievement(na["key"])
            unlocked.add(na["key"])

        if not unlocked:
            self.achievement_col.controls.append(ft.Text("还没有解锁成就，加油！", size=12, color=TEXT_THIRD))
            return

        all_achs = []
        for key, ach in ACHIEVEMENTS.items():
            earned = key in unlocked
            all_achs.append((earned, ach))

        # 已获得的在前，按定义顺序
        all_achs.sort(key=lambda x: (not x[0], list(ACHIEVEMENTS.keys()).index(list(ACHIEVEMENTS.keys())[list(ACHIEVEMENTS.values()).index(x[1])]) if x[1] in ACHIEVEMENTS.values() else 99))

        for earned, ach in all_achs:
            if isinstance(ach, str):
                continue
            icon = ach["icon"] if earned else "🔒"
            name = ach["name"]
            color = TEXT if earned else TEXT_THIRD
            bg = BLUE_LIGHT if earned else BG
            self.achievement_col.controls.append(
                ft.Container(
                    ft.Row([ft.Text(icon, size=18), ft.Text(name, size=12, color=color, weight=ft.FontWeight.W_500 if earned else None)],
                           spacing=6),
                    padding=ft.padding.symmetric(horizontal=8, vertical=6), bgcolor=bg, border_radius=8,
                )
            )

        if new_achs:
            self.app.page.show_snack_bar(ft.SnackBar(
                ft.Text(f"🎉 新成就解锁: {new_achs[0]['icon']} {new_achs[0]['name']}", size=13),
                bgcolor=ORANGE, duration=5000))

    def _build_stats(self):
        """构建成就统计"""
        stats = {}
        # 连续打卡
        stats["streak"] = self._calc_streak()
        # 累计加班
        if self.app.analysis_map:
            stats["total_ot"] = sum(a.overtime_hours for a in self.app.analysis_map.values())
            stats["missed"] = sum(1 for a in self.app.analysis_map.values() if a.missed)
            stats["total_days"] = len(self.app.analysis_map)
        else:
            stats["total_ot"] = 0; stats["missed"] = 0; stats["total_days"] = 0
        # 喝水
        cfg = self.app.user_config
        if cfg:
            try:
                wh = json.loads(cfg.water_history)
            except:
                wh = {}
            water_streak = 0
            d = date.today() - timedelta(days=1)
            while d.isoformat() in wh and wh[d.isoformat()] >= 8:
                water_streak += 1
                d -= timedelta(days=1)
            if cfg.water_date == date.today().isoformat() and cfg.water_count >= 8:
                water_streak += 1
            stats["water_streak"] = water_streak
            # 护眼
            stats["eye_minutes"] = cfg.eye_rest_minutes if cfg.eye_date == date.today().isoformat() else 0
        else:
            stats["water_streak"] = 0; stats["eye_minutes"] = 0
        # 待办
        from todo_manager import todo_mgr
        all_items = []
        for d in todo_mgr.get_all_dates():
            all_items.extend(todo_mgr.get_items(d))
        stats["todo_done"] = sum(1 for i in all_items if i.done)
        # 周五
        stats["is_friday"] = date.today().weekday() == 4
        return stats

    def _calc_streak(self):
        """计算连续打卡天数"""
        if not self.app.analysis_map:
            return 0
        today = date.today()
        streak = 0
        d = today
        while True:
            ds = d.isoformat()
            if ds in self.app.analysis_map and not self.app.analysis_map[ds].missed:
                streak += 1
                d -= timedelta(days=1)
            else:
                break
        return streak

    # ===== 心情日历 =====
    def load_mood(self):
        self.mood_col.controls.clear()
        moods = load_mood_data()
        today_ds = date.today().isoformat()

        # 当前心情
        current = moods.get(today_ds)
        if current:
            self.mood_col.controls.append(ft.Text(f"今天的心情: {current}", size=16, color=TEXT))
        else:
            self.mood_col.controls.append(ft.Text("今天心情如何？", size=14, color=TEXT_SEC))

        # 心情选择
        mood_btns = ft.Row(spacing=4, wrap=True)
        for m in ["😊", "😎", "🥱", "😫", "😤", "🤬", "😭", "🤩", "🥳", "😐", "🤯", "❤"]:
            selected = m == current
            mood_btns.controls.append(
                ft.Container(
                    ft.Text(m, size=22),
                    width=40, height=40, alignment=ft.alignment.center,
                    border_radius=20, bgcolor=BLUE_LIGHT if selected else WHITE,
                    border=ft.border.all(2, BLUE if selected else BORDER),
                    on_click=lambda e, emoji=m: self._set_mood(emoji),
                    ink=True, tooltip="设置心情",
                )
            )
        self.mood_col.controls.append(mood_btns)
        ft.Container(height=8)

        # 近7天心情回顾
        self.mood_col.controls.append(ft.Text("近7天回顾", size=12, color=TEXT_SEC))
        review = ft.Row(spacing=4)
        for i in range(6, -1, -1):
            d = date.today() - timedelta(days=i)
            ds = d.isoformat()
            m = moods.get(ds, "❓")
            day_label = d.strftime("%m/%d")
            review.controls.append(
                ft.Column([
                    ft.Text(m, size=18),
                    ft.Text(day_label, size=9, color=TEXT_THIRD),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0)
            )
        self.mood_col.controls.append(review)

    def _set_mood(self, emoji):
        set_mood(date.today().isoformat(), emoji)
        self.load_mood()
        self.page.update()

    # ===== 番茄钟 / 会议倒计时 =====
    def _start_timer(self):
        if self._timer_running:
            return
        mode = self.timer_mode.value
        if mode == "pomodoro":
            self._timer_total = 25 * 60
            self._timer_seconds = 25 * 60
            self.timer_status.value = "专注中..."
        else:
            try:
                mins = int(self.meeting_minutes.value.strip())
            except:
                mins = 30
            self._timer_total = mins * 60
            self._timer_seconds = mins * 60
            self.timer_status.value = f"会议倒计时 {mins}min"

        self._timer_running = True
        self._timer_paused = False
        self._update_timer_display()
        threading.Thread(target=self._timer_loop, daemon=True).start()

    def _pause_timer(self):
        self._timer_paused = not self._timer_paused
        self.timer_status.value = "已暂停" if self._timer_paused else "继续中..."
        self.timer_status.update()

    def _reset_timer(self):
        self._timer_running = False
        self._timer_seconds = 0
        self.timer_display.value = "25:00"
        self.timer_display.color = BLUE
        self.timer_progress.value = 0
        self.timer_status.value = "准备开始"
        try:
            self.timer_display.update()
            self.timer_progress.update()
            self.timer_status.update()
        except:
            pass

    def _update_timer_display(self):
        m, s = divmod(self._timer_seconds, 60)
        self.timer_display.value = f"{m:02d}:{s:02d}"
        self.timer_progress.value = 1 - self._timer_seconds / self._timer_total if self._timer_total > 0 else 0
        if self._timer_seconds < 60:
            self.timer_display.color = RED
        elif self._timer_seconds < 300:
            self.timer_display.color = ORANGE
        else:
            self.timer_display.color = BLUE
        try:
            self.timer_display.update()
            self.timer_progress.update()
        except:
            pass

    def _timer_loop(self):
        while self._timer_running and self._timer_seconds > 0:
            if not self._timer_paused:
                _time.sleep(1)
                self._timer_seconds -= 1
                self._update_timer_display()
            else:
                _time.sleep(0.1)

        if self._timer_seconds <= 0 and self._timer_running:
            self._timer_running = False
            self.timer_status.value = "⏰ 时间到!"
            self.timer_display.value = "00:00"
            self.timer_progress.value = 1
            self.timer_display.color = RED
            try:
                self.timer_status.update()
                self.timer_display.update()
                self.timer_progress.update()
            except:
                pass
            self.app._toast("哈基米曼波 计时器", "⏰ 时间到！")

    def load_all(self):
        """加载所有数据"""
        self.load_trend()
        self.load_achievements()
        self.load_mood()
        self._update_salary_countdown()
        try:
            self.salary_countdown_text.update()
        except:
            pass
        self._ai_fun_default()
        self.page.update()

    # ==================== AI 摸鱼趣味 ====================

    def _ai_fun_default(self):
        """默认AI趣味语"""
        quotes = ["🎲 点我查看今日运势~", "💼 想知道最佳摸鱼时间吗？", "🐱 喵~ 今天也是元气满满的一天！"]
        import random
        self.ai_fun_text.value = random.choice(quotes)
        try: self.ai_fun_text.update()
        except: pass

    def _ai_fortune(self):
        """AI 今日运势"""
        now = datetime.now()
        prompt = f"今天是{now.year}年{now.month}月{now.day}日，星期{['一','二','三','四','五','六','日'][now.weekday()]}。请给打工人写一段有趣的今日运势，包含：整体运势(⭐评分)、工作运、摸鱼指数、幸运颜色、一句话提醒。用猫咪语气，带emoji，150字以内。"
        self.ai_fun_text.value = "🐱 占卜中..."
        try: self.ai_fun_text.update()
        except: pass
        def _run():
            r = ai_svc.call(prompt, system_prompt="你是猫咪占卜师，有趣幽默。", max_tokens=250, temperature=0.95, timeout=12)
            if r and len(r) > 20:
                self.ai_fun_text.value = r.strip()
                try: self.ai_fun_text.update()
                except: pass
        threading.Thread(target=_run, daemon=True).start()

    def _ai_fish_guide(self):
        """AI 摸鱼指南"""
        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()
        time_desc = "早上" if hour < 12 else ("下午" if hour < 18 else "晚上")
        prompt = f"现在是{time_desc}，星期{['一','二','三','四','五','六','日'][weekday]}。请给打工人推荐现在最适合的摸鱼方式，要具体可操作、有趣、带emoji，100字以内。"
        self.ai_fun_text.value = "🐱 策划中..."
        try: self.ai_fun_text.update()
        except: pass
        def _run():
            r = ai_svc.call(prompt, system_prompt="你是摸鱼大师猫咪，给出有趣实用的摸鱼建议。", max_tokens=200, temperature=0.9, timeout=12)
            if r and len(r) > 15:
                self.ai_fun_text.value = r.strip()
                try: self.ai_fun_text.update()
                except: pass
        threading.Thread(target=_run, daemon=True).start()
