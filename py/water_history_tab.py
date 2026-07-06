# -*- coding: utf-8 -*-
"""喝水记录标签页 - 每日喝水打卡 + 喝水杯数和毫升数统计"""
import json
import threading
import flet as ft
from datetime import date, timedelta
from user_auth import load_user_config, save_user_config
from ai_service import ai_svc

BLUE = "#3370FF"; BLUE_LIGHT = "#E8F0FE"
GREEN = "#34C759"; ORANGE = "#FF9500"
TEXT = "#1F2329"; TEXT_SEC = "#646A73"; TEXT_THIRD = "#8F959E"
BORDER = "#E5E6EB"; WHITE = "#FFFFFF"

# 科学喝水时间表
WATER_SCHEDULE = [
    (8, 0, "🌅 起床一杯，唤醒身体"),
    (9, 0, "☀ 开始工作，补充水分"),
    (11, 0, "🕚 午饭前，促进消化"),
    (13, 0, "🍽 午饭后半小时，帮助代谢"),
    (15, 0, "😴 下午提神，缓解疲劳"),
    (17, 0, "⏰ 下班前，保持活力"),
    (19, 0, "🌙 晚饭后，助消化"),
    (21, 0, "🛌 睡前两小时，避免水肿"),
]


class WaterHistoryTab:
    def __init__(self, page: ft.Page):
        self.page = page
        self.list_view = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)
        self.punch_row = ft.Row(spacing=6, wrap=True, alignment=ft.MainAxisAlignment.CENTER)
        self.punch_label = ft.Text("", size=14, weight=ft.FontWeight.W_500, color=TEXT)
        self.punch_progress = ft.ProgressBar(value=0, width=300, color=BLUE, bgcolor=BORDER)
        self._update_punch_ui()

        # 月份导航
        self.current_month = date.today().replace(day=1)
        self.month_text = ft.Text("", size=18, weight=ft.FontWeight.BOLD, color=TEXT)
        self._update_month_label()

        self.summary_text = ft.Text("", size=13, color=TEXT_SEC)

        self.content = ft.Container(ft.Column([
            # 喝水打卡区域
            ft.Container(ft.Column([
                ft.Text("💧 今日喝水打卡", size=15, weight=ft.FontWeight.BOLD, color=TEXT),
                ft.Container(height=8),
                self.punch_label,
                ft.Container(height=4),
                self.punch_progress,
                ft.Container(height=8),
                self.punch_row,
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=16, bgcolor=BLUE_LIGHT, border_radius=12, margin=ft.margin.only(bottom=12)),

            ft.Divider(height=1, color=BORDER),
            ft.Container(height=8),
            # 月份导航
            ft.Row([
                ft.IconButton(ft.icons.ARROW_BACK, icon_size=24, on_click=lambda e: self._prev_month()),
                self.month_text,
                ft.IconButton(ft.icons.ARROW_FORWARD, icon_size=24, on_click=lambda e: self._next_month()),
            ], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=8),
            self.summary_text,
            ft.Container(height=8),
            ft.Row([
                ft.Text("日期", size=12, color=TEXT_SEC, width=100),
                ft.Text("杯数", size=12, color=TEXT_SEC, width=60),
                ft.Text("毫升", size=12, color=TEXT_SEC, width=80),
                ft.Text("进度", size=12, color=TEXT_SEC),
            ], spacing=8),
            ft.Divider(height=0.5, color=BORDER),
            ft.Container(self.list_view, expand=True),
        ], expand=True), padding=ft.padding.all(24), expand=True, bgcolor=WHITE,
        margin=ft.margin.all(16), border_radius=12, border=ft.border.all(1, BORDER))

    def _update_punch_ui(self):
        """更新喝水打卡UI"""
        cfg = load_user_config()
        today = date.today().isoformat()
        is_today = cfg and cfg.water_date == today
        count = cfg.water_count if is_today else 0
        total_ml = count * (cfg.water_ml if cfg else 300)

        self.punch_row.controls.clear()
        for i, (h, m, tip) in enumerate(WATER_SCHEDULE):
            filled = i < count
            self.punch_row.controls.append(
                ft.Container(
                    ft.Column([
                        ft.Text("💧" if filled else "🥛", size=22, text_align=ft.TextAlign.CENTER),
                        ft.Text(f"{h:02d}:{m:02d}", size=9, color=TEXT_THIRD),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                    width=52, height=52, alignment=ft.alignment.center,
                    border_radius=10,
                    bgcolor=BLUE_LIGHT if filled else WHITE,
                    border=ft.border.all(2, BLUE if filled else BORDER),
                    on_click=lambda e, idx=i: self._drink_water(idx),
                    ink=True, tooltip=tip,
                )
            )

        self.punch_progress.value = count / 8
        self.punch_label.value = f"已喝 {count}/8 杯 ({total_ml}ml)" if count < 8 else f"🎉 今日达标! 8/8 杯 ({total_ml}ml)"

    def _drink_water(self, idx):
        """点击喝水打卡"""
        cfg = load_user_config()
        if not cfg:
            return
        today = date.today().isoformat()
        if cfg.water_date != today:
            cfg.water_count = 0
            cfg.water_date = today

        if idx < cfg.water_count:
            cfg.water_count = idx  # 取消
        else:
            cfg.water_count = idx + 1  # 喝到这一杯

        # 更新历史
        try:
            history = json.loads(cfg.water_history)
        except:
            history = {}
        history[today] = cfg.water_count
        cfg.water_history = json.dumps(history, ensure_ascii=False)
        save_user_config(cfg)
        self._update_punch_ui()
        self.load()
        self.page.update()

    def _update_month_label(self):
        self.month_text.value = self.current_month.strftime("%Y年%m月")

    def _prev_month(self):
        if self.current_month.month == 1:
            self.current_month = self.current_month.replace(year=self.current_month.year - 1, month=12)
        else:
            self.current_month = self.current_month.replace(month=self.current_month.month - 1)
        self._update_month_label()
        self.load()

    def _next_month(self):
        if self.current_month.month == 12:
            self.current_month = self.current_month.replace(year=self.current_month.year + 1, month=1)
        else:
            self.current_month = self.current_month.replace(month=self.current_month.month + 1)
        self._update_month_label()
        self.load()

    def load(self):
        self.list_view.controls.clear()
        cfg = load_user_config()
        if not cfg:
            self.list_view.controls.append(ft.Text("请先登录", size=13, color=TEXT_THIRD))
            self.page.update(); return

        ml_per_cup = cfg.water_ml
        try:
            history = json.loads(cfg.water_history)
        except:
            history = {}

        # 当月所有日期
        ym = self.current_month
        if ym.month == 12:
            next_m = ym.replace(year=ym.year + 1, month=1)
        else:
            next_m = ym.replace(month=ym.month + 1)
        days_in_month = (next_m - ym).days

        total_cups = 0
        total_ml = 0
        goal_days = 0
        today_ds = date.today().isoformat()

        for d in range(days_in_month):
            cur = ym + timedelta(days=d)
            ds = cur.isoformat()
            cups = history.get(ds, 0)
            mls = cups * ml_per_cup
            total_cups += cups
            total_ml += mls
            if cups >= 8:
                goal_days += 1
            progress = min(cups / 8, 1.0)
            pct = f"{int(progress * 100)}%"
            bar_color = GREEN if cups >= 8 else (BLUE if cups > 0 else TEXT_THIRD)
            is_today = ds == today_ds

            self.list_view.controls.append(
                ft.Container(ft.Column([
                    ft.Row([
                        ft.Text(ds[-5:], size=13, color=TEXT, weight=ft.FontWeight.BOLD if is_today else None, width=100),
                        ft.Text(str(cups), size=13, color=TEXT, width=60),
                        ft.Text(f"{mls}ml", size=13, color=TEXT, width=80),
                        ft.Column([
                            ft.ProgressBar(value=progress, width=120, color=bar_color, bgcolor=BORDER),
                            ft.Text(pct, size=10, color=TEXT_THIRD),
                        ], spacing=2),
                    ], spacing=8),
                ]), padding=ft.padding.symmetric(vertical=3),
                border=ft.border.only(bottom=ft.border.BorderSide(0.5, BORDER)),
                bgcolor=BLUE_LIGHT if is_today else (BLUE_LIGHT if cups >= 8 else None),
                key=f"day_{ds}")
            )

        self.summary_text.value = (
            f"本月共喝水 {total_cups} 杯 / {total_ml}ml  |  "
            f"达标 {goal_days}/{days_in_month} 天  |  "
            f"每杯 {ml_per_cup}ml"
        )
        self._update_punch_ui()
        self.page.update()

    # ==================== AI 喝水鼓励 ====================

    def _ai_water_cheer(self):
        """AI个性化喝水鼓励"""
        cfg = load_user_config()
        today = date.today().isoformat()
        history = {}
        if cfg and cfg.water_history:
            try: history = json.loads(cfg.water_history)
            except: pass
        cups = history.get(today, 0)
        ml_per_cup = int(cfg.water_ml) if cfg and hasattr(cfg, 'water_ml') and cfg.water_ml else 300

        if cups >= 8:
            prompt = f"主人今天已经喝了{cups}杯水，共{cups*ml_per_cup}ml，达标啦！用猫咪语气夸奖一句（带emoji，20字以内）。"
        elif cups == 0:
            prompt = "主人今天还没喝水！用猫咪撒娇+担心的语气催喝水（带emoji，20字以内）。"
        else:
            remaining = 8 - cups
            prompt = f"主人今天喝了{cups}杯水，还差{remaining}杯（{remaining*ml_per_cup}ml）。用猫咪语气温柔提醒继续喝（带emoji，20字以内）。"

        def _run():
            r = ai_svc.call(prompt, system_prompt="你是关心主人健康的猫咪。", max_tokens=80, temperature=0.9, timeout=8)
            if r and len(r) < 120:
                self.page.show_snack_bar(ft.SnackBar(ft.Text(r.strip(), size=13), bgcolor=BLUE, duration=5000))
            else:
                if cups >= 8:
                    self.page.show_snack_bar(ft.SnackBar(ft.Text("🐱 喵！主人今天喝水满分！太棒啦~ 💙", size=13), bgcolor=GREEN))
                elif cups == 0:
                    self.page.show_snack_bar(ft.SnackBar(ft.Text("🐱 喵呜~ 主人快喝水！身体要干掉了 😿", size=13), bgcolor=ORANGE))
                else:
                    self.page.show_snack_bar(ft.SnackBar(ft.Text(f"🐱 还差{8-cups}杯哦，继续加油~ 💧", size=13), bgcolor=BLUE))
        threading.Thread(target=_run, daemon=True).start()
