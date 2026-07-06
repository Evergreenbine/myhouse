# -*- coding: utf-8 -*-
"""加班事项标签页 - 显示当月所有加班记录及理由"""
import json
import threading
import flet as ft
from datetime import date, timedelta
from attendance import get_company_month_range, get_company_month_label
from user_auth import load_user_config
from ai_service import ai_svc

BLUE = "#3370FF"; BLUE_LIGHT = "#E8F0FE"
GREEN = "#34C759"; ORANGE = "#FF9500"; RED = "#F54A45"
TEXT = "#1F2329"; TEXT_SEC = "#646A73"; TEXT_THIRD = "#8F959E"
BORDER = "#E5E6EB"; WHITE = "#FFFFFF"; BG = "#F2F3F5"


class OvertimeNotesTab:
    def __init__(self, page: ft.Page):
        self.page = page
        self.current_date = date.today()
        self.list_view = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
        self._items = []  # 存储当前加班数据供AI使用

        self.month_label = ft.Text("", size=18, weight=ft.FontWeight.BOLD, color=TEXT)
        self.summary_text = ft.Text("", size=13, color=TEXT_SEC)
        self._update_labels()

        self.ai_trend_text = ft.Text("", size=12, color=TEXT_SEC)

        self.content = ft.Container(ft.Column([
            ft.Row([
                ft.IconButton(ft.icons.ARROW_BACK, icon_size=24, on_click=lambda e: self._prev_month()),
                self.month_label,
                ft.IconButton(ft.icons.ARROW_FORWARD, icon_size=24, on_click=lambda e: self._next_month()),
                ft.Container(width=8),
                ft.Chip(label=ft.Text("🧠 AI趋势预测", size=11), bgcolor="#FFF8E1",
                        leading=ft.Icon(ft.icons.TRENDING_UP, size=14, color=ORANGE),
                        on_click=lambda e: self._ai_trend()),
                ft.Chip(label=ft.Text("📋 AI加班总结", size=11), bgcolor="#FFF8E1",
                        leading=ft.Icon(ft.icons.AUTO_AWESOME, size=14, color=ORANGE),
                        on_click=lambda e: self._ai_summary()),
            ], alignment=ft.MainAxisAlignment.CENTER, wrap=True),
            ft.Divider(height=1, color=BORDER),
            ft.Container(height=8),
            self.summary_text,
            ft.Container(height=4),
            self.ai_trend_text,
            ft.Container(height=8),
            ft.Row([
                ft.Text("日期", size=12, color=TEXT_SEC, width=100),
                ft.Text("类型", size=12, color=TEXT_SEC, width=60),
                ft.Text("加班", size=12, color=TEXT_SEC, width=60),
                ft.Text("工资", size=12, color=TEXT_SEC, width=70),
                ft.Text("理由", size=12, color=TEXT_SEC),
            ], spacing=8),
            ft.Divider(height=0.5, color=BORDER),
            self.list_view,
        ], expand=True), padding=ft.padding.all(24), expand=True, bgcolor=WHITE,
        margin=ft.margin.all(16), border_radius=12, border=ft.border.all(1, BORDER))

    def _update_labels(self):
        self.month_label.value = get_company_month_label(self.current_date)

    def _prev_month(self):
        s, _ = get_company_month_range(self.current_date)
        self.current_date = s - timedelta(days=1)
        self._update_labels()
        self.load()

    def _next_month(self):
        _, e = get_company_month_range(self.current_date)
        self.current_date = e + timedelta(days=1)
        self._update_labels()
        self.load()

    def load(self):
        self.list_view.controls.clear()
        cfg = load_user_config()
        if not cfg:
            self.list_view.controls.append(ft.Text("请先登录", size=13, color=TEXT_THIRD))
            self.page.update(); return

        # 从数据库加载考勤数据
        from database import query_work_records_range
        from attendance import DayAnalysis, get_company_month_range
        from calendar_2026 import get_day_type_label

        s, e = get_company_month_range(self.current_date)
        try:
            recs = query_work_records_range(cfg.empname, s.isoformat(), e.isoformat())
        except Exception:
            self.list_view.controls.append(ft.Text("加载失败", size=13, color=RED))
            self.page.update(); return

        # 加载加班备注
        try:
            notes = json.loads(cfg.overtime_notes)
        except:
            notes = {}

        total_hours = 0.0; total_pay = 0.0; count = 0
        items = []
        d = s
        while d <= e:
            ds = d.isoformat()
            a = DayAnalysis(d, recs.get(ds, []), cfg)
            if a.overtime_hours > 0:
                note = notes.get(ds, "")
                items.append((d, a, note))
                total_hours += a.overtime_hours
                total_pay += a.overtime_pay
                count += 1
            d += timedelta(days=1)

        items.reverse()  # 倒序，最近的在最上面
        self._items = items  # 存储供AI使用
        if not items:
            self.list_view.controls.append(ft.Text("本月暂无加班记录", size=13, color=TEXT_THIRD))
            self.summary_text.value = "本月无加班"
        else:
            self.summary_text.value = (
                f"加班 {count} 天  |  共 {total_hours:.1f}h  |  合计 ¥{total_pay:.2f}"
            )
            for d, a, note in items:
                ds = d.isoformat()
                wn = ["周一","周二","周三","周四","周五","周六","周日"][d.weekday()]
                has_note = bool(note)
                note_color = TEXT if has_note else TEXT_THIRD
                note_text = note if has_note else "（未记录）"

                self.list_view.controls.append(
                    ft.Container(ft.Column([
                        ft.Row([
                            ft.Text(f"{ds[-5:]} {wn}", size=13, color=TEXT, width=100),
                            ft.Text(a.day_type_label, size=12,
                                   color=RED if a.day_type_label=="节假日" else (ORANGE if a.day_type_label=="补班日" else TEXT_SEC),
                                   width=60),
                            ft.Text(f"{a.overtime_hours:.1f}h", size=13, weight=ft.FontWeight.BOLD, width=60),
                            ft.Text(f"¥{a.overtime_pay:.2f}", size=13, color=BLUE, width=70),
                            ft.Text(note_text, size=13, color=note_color, expand=True),
                        ], spacing=8),
                    ]), padding=ft.padding.symmetric(vertical=4),
                    border=ft.border.only(bottom=ft.border.BorderSide(0.5, BORDER)),
                    bgcolor=BLUE_LIGHT if has_note else None)
                )

        self.page.update()

    # ==================== AI 加班分析 ====================

    def _ai_trend(self):
        """AI 预测加班趋势"""
        if not self._items:
            self.page.show_snack_bar(ft.SnackBar(ft.Text("本月暂无加班数据~", size=13), bgcolor=GREEN))
            return
        lines = []
        for d, a, note in self._items:
            lines.append(f"- {d.isoformat()[-5:]} {a.day_type_label} {a.overtime_hours:.1f}h")
        prompt = f"本月加班记录（已排序）：\n" + "\n".join(lines[-15:]) + "\n\n用猫咪语气预测下个月加班趋势，给3条建议（简短，带emoji）。"
        self.ai_trend_text.value = "🐱 预测中..."
        try: self.ai_trend_text.update()
        except: pass
        def _run():
            r = ai_svc.call(prompt, system_prompt="你是数据分析猫咪。", max_tokens=200, temperature=0.8, timeout=12)
            self.ai_trend_text.value = r
            try: self.ai_trend_text.update()
            except: pass
        threading.Thread(target=_run, daemon=True).start()

    def _ai_summary(self):
        """AI 加班总结"""
        if not self._items:
            self.page.show_snack_bar(ft.SnackBar(ft.Text("本月暂无加班数据~", size=13), bgcolor=GREEN))
            return
        total_h = sum(a.overtime_hours for _, a, _ in self._items)
        total_p = sum(a.overtime_pay for _, a, _ in self._items)
        count = len(self._items)
        types = {}
        for _, a, _ in self._items:
            t = a.day_type_label
            types[t] = types.get(t, 0) + 1
        type_str = "，".join([f"{k}{v}天" for k, v in types.items()])
        prompt = f"本月加班{count}天，共{total_h:.1f}h，加班费¥{total_p:.2f}。类型分布：{type_str}。用猫咪语气总结并给一句话建议。"
        self.ai_trend_text.value = "🐱 总结中..."
        try: self.ai_trend_text.update()
        except: pass
        def _run():
            r = ai_svc.call(prompt, system_prompt="你是猫咪加班顾问。", max_tokens=150, temperature=0.8, timeout=12)
            self.ai_trend_text.value = r
            try: self.ai_trend_text.update()
            except: pass
        threading.Thread(target=_run, daemon=True).start()
