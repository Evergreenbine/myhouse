# -*- coding: utf-8 -*-
import math
import os
import threading
import urllib.request
import json
from datetime import date, timedelta, datetime
import flet as ft
from calendar_2026 import get_day_type, get_day_type_label, get_holiday_name
from attendance import DayAnalysis, get_company_month_range, get_company_month_label
from database import query_work_records_range
from todo_manager import todo_mgr
from car_tab import CarTab
from user_auth import is_logged_in, load_user_config, save_user_config, quick_login
from login_page import show_login_page
from settings_page import show_settings_page, get_avatar_src
from water_history_tab import WaterHistoryTab
from overtime_notes_tab import OvertimeNotesTab
from fun_tab import FunTab
from fun_features import get_random_quote
from tray_icon import start_tray, show_pet, hide_pet
from ai_assistant import AIAssistant
from ai_care import start_ai_care, get_today_focus
from ai_service import ai_svc
from tools import tool_executor
from kb_tab import KnowledgeBaseTab

BLUE = "#3370FF"
BLUE_LIGHT = "#E8F0FE"
RED = "#F54A45"
GREEN = "#34C759"
ORANGE = "#FF9500"
TEXT = "#1F2329"
TEXT_SEC = "#646A73"
TEXT_THIRD = "#8F959E"
BORDER = "#E5E6EB"
BG = "#F2F3F5"
WHITE = "#FFFFFF"
HOLIDAY_BG = "#FFF1F0"
WEEKEND_BG = "#F0F5FF"
MAKEUP_BG = "#FFF7E6"
TODAY_BG = "#E8F0FE"
CARD_BG = "#FFFFFF"


class OvertimeApp:

    def __init__(self):
        self.analysis_map = {}
        self.records_map = {}
        self.current_date = date.today()
        self.selected_date = date.today()
        self.page = None
        self.user_config = None
        self.tab_index = 0

    def main(self, page: ft.Page):
        self.page = page
        ai_svc.set_page(page)  # 让AI服务能弹窗提示额度不足
        page.title = "哈基米曼波 - " + get_random_quote()
        page.window.width = 1200
        page.window.height = 800
        page.window.min_width = 1000
        page.window.min_height = 700
        page.window.center()
        page.bgcolor = BG
        page.padding = 0

        # 最小化到托盘 + 显示萌宠
        def on_window_event(e):
            if e.data == "minimize":
                page.window.skip_task_bar = True
                page.window.visible = False
                page.update()
                show_pet(self)
        page.window.on_event = on_window_event

        # 检查登录状态
        if not is_logged_in():
            show_login_page(page, lambda cfg: self._on_login_success(cfg))
            return
        config = load_user_config()
        if config is None:
            show_login_page(page, lambda cfg: self._on_login_success(cfg))
            return
        self.user_config = config
        self._build_main_ui()

    def _on_login_success(self, config):
        """登录/注册成功后回调"""
        self.user_config = config
        self.page.clean()
        self._build_main_ui()

    def _build_main_ui(self):
        page = self.page
        # 确保窗口事件绑定
        def on_win(e):
            if e.data == "minimize":
                page.window.skip_task_bar = True
                page.window.visible = False
                page.update()
                show_pet(self)
        page.window.on_event = on_win

        cfg = self.user_config
        todo_mgr.set_remind_callback(lambda t, m: self._show_reminder(t, m))

        # 顶部栏
        self.month_label = ft.Text(get_company_month_label(self.current_date), size=20, weight=ft.FontWeight.BOLD, color=TEXT)
        self.weather_text = ft.Text("加载天气...", size=13, color=TEXT_SEC)
        self.quote_top_text = ft.Text(get_random_quote(), size=11, color=TEXT_THIRD, italic=True, width=260, no_wrap=False, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        self.countdown_top_text = ft.Text("", size=16, weight=ft.FontWeight.BOLD, color=BLUE)
        avatar_path = get_avatar_src(cfg)
        if avatar_path and not os.path.isabs(avatar_path):
            avatar_path = os.path.abspath(os.path.join(os.path.dirname(__file__), avatar_path))
        self.avatar_ctrl = ft.Container(
            ft.Image(src=avatar_path, width=40, height=40, fit=ft.ImageFit.COVER),
            width=40, height=40, border_radius=20, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            bgcolor=BLUE_LIGHT)
        top_bar = ft.Container(
            content=ft.Row([
                ft.Container(
                    self.avatar_ctrl,
                    on_click=lambda e: self._show_settings(), ink=True, border_radius=20),
                ft.Container(width=8),
                ft.IconButton(icon=ft.icons.CHEVRON_LEFT, icon_size=24, icon_color=TEXT_SEC, on_click=lambda e: self._prev_month()),
                self.month_label,
                ft.IconButton(icon=ft.icons.CHEVRON_RIGHT, icon_size=24, icon_color=TEXT_SEC, on_click=lambda e: self._next_month()),
                ft.Container(width=4),
                ft.TextButton("今天", icon=ft.icons.TODAY, style=ft.ButtonStyle(color=TEXT_SEC),
                              on_click=lambda e: self._go_today()),
                ft.Container(width=8),
                ft.Container(self.quote_top_text, border_radius=12, bgcolor=BG,
                            padding=ft.padding.symmetric(horizontal=12, vertical=4)),
                ft.Container(expand=True),
                self.countdown_top_text,
                ft.Container(width=4),
                self.weather_text,
                ft.Container(width=8),
            ]),
            padding=ft.padding.symmetric(horizontal=20, vertical=10),
            bgcolor=WHITE, border=ft.border.only(bottom=ft.border.BorderSide(1, BORDER)),
        )

        # === Tab 1: 考勤 ===
        self.calendar_col = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO)
        self.summary_col = ft.Column(spacing=8)
        self.detail_col = ft.Column(spacing=8)
        self.records_col = ft.Column(spacing=4)
        self.car_day_col = ft.Column(spacing=3)
        self.punch_col = ft.Column(spacing=4)
        self._build_calendar()
        self._build_panel()

        def _section_card(col):
            return ft.Container(col, padding=20, bgcolor=CARD_BG, border_radius=12,
                               border=ft.border.all(1, BORDER))

        # AI 每日一句话卡片
        self.ai_daily_text = ft.Text("🐱 AI正在思考今天...", size=12, color=TEXT_THIRD, italic=True)
        ai_daily_card = ft.Container(
            ft.Row([
                ft.Icon(ft.icons.AUTO_AWESOME, size=16, color=ORANGE),
                ft.Container(width=6),
                ft.Column([self.ai_daily_text], expand=True),
                ft.Container(width=4),
                ft.IconButton(ft.icons.REFRESH, icon_size=14, icon_color=TEXT_THIRD,
                             on_click=lambda e: self._refresh_ai_daily()),
            ], spacing=0),
            padding=ft.padding.all(10), bgcolor="#FFF8E1", border_radius=10,
            border=ft.border.all(1, "#FFE082"),
        )

        right_panel = ft.Column([
            ai_daily_card,
            ft.Container(height=12),
            ft.Text("月度汇总", size=14, weight=ft.FontWeight.BOLD, color=TEXT_SEC),
            _section_card(self.summary_col),
            ft.Container(height=12),
            ft.Text("当天详情", size=14, weight=ft.FontWeight.BOLD, color=TEXT_SEC),
            _section_card(self.detail_col),
            ft.Container(height=12),
            ft.Text("打卡记录", size=14, weight=ft.FontWeight.BOLD, color=TEXT_SEC),
            _section_card(self.records_col),
            ft.Container(height=12),
            ft.Text("车辆出入", size=14, weight=ft.FontWeight.BOLD, color=TEXT_SEC),
            _section_card(self.car_day_col),
            ft.Container(height=12),
        ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=0)

        # === 补卡区域（独立管理，避免索引问题） ===
        self.punch_ai_tip = ft.Text("", size=11, color=ORANGE, italic=True, visible=False)
        self.punch_title = ft.Text("补卡操作", size=14, weight=ft.FontWeight.BOLD, color=TEXT_SEC, visible=False)
        self.punch_btn_col = ft.Column(spacing=4)
        self.punch_card = ft.Container(
            self.punch_btn_col, padding=20, bgcolor=CARD_BG, border_radius=12,
            border=ft.border.all(1, BORDER), visible=False)
        self.punch_section = ft.Column([
            self.punch_ai_tip,
            ft.Container(height=4),
            self.punch_title,
            self.punch_card,
        ], visible=False)
        right_panel.controls.append(ft.Container(height=12))
        right_panel.controls.append(self.punch_section)

        attendance_tab = ft.ResponsiveRow([
            ft.Column(col={"lg": 6, "md": 12, "sm": 12}, controls=[
                ft.Container(self.calendar_col, padding=16, bgcolor=CARD_BG, border_radius=12,
                            border=ft.border.all(1, BORDER)),
            ]),
            ft.Column(col={"lg": 6, "md": 12, "sm": 12}, controls=[
                ft.Container(right_panel, padding=20, bgcolor=CARD_BG, border_radius=12,
                            border=ft.border.all(1, BORDER), expand=True),
            ]),
        ], expand=True, spacing=8, run_spacing=8)

        # === Tab 2: 待办 ===
        self.todo_list = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        self.todo_date_text = ft.Text(f"📅 {date.today().isoformat()}", size=14, weight=ft.FontWeight.W_500)
        self.todo_time_text = ft.Text("09:00", size=14)
        self.todo_content_input = ft.TextField(hint_text="输入待办内容...", text_size=14, border=ft.InputBorder.UNDERLINE, expand=True)
        self._todo_time = "09:00"
        self._todo_date = date.today().isoformat()

        # DatePicker
        self.date_picker = ft.DatePicker(
            first_date=date(2026, 1, 1), last_date=date(2027, 12, 31),
            on_change=lambda e: self._on_date_picked(e.control.value))
        page.overlay.append(self.date_picker)

        # TimePicker
        self.time_picker = ft.TimePicker(
            on_change=lambda e: self._on_time_picked(e.control.value))
        page.overlay.append(self.time_picker)

        todo_tab = ft.Container(
            ft.Column([
                ft.Text("待办事项", size=18, weight=ft.FontWeight.BOLD, color=TEXT),
                ft.Container(height=8),
                # AI 智能排程按钮
                ft.Row([
                    ft.Chip(label=ft.Text("🧠 AI帮我排程", size=11), bgcolor="#FFF8E1",
                            leading=ft.Icon(ft.icons.AUTO_AWESOME, size=14, color=ORANGE),
                            on_click=lambda e: self._ai_schedule()),
                    ft.Chip(label=ft.Text("📋 拆解任务", size=11), bgcolor="#FFF8E1",
                            leading=ft.Icon(ft.icons.CALENDAR_VIEW_WEEK, size=14, color=ORANGE),
                            on_click=lambda e: self._ai_breakdown()),
                    ft.Chip(label=ft.Text("⚡ 优先级", size=11), bgcolor="#FFF8E1",
                            leading=ft.Icon(ft.icons.LOW_PRIORITY, size=14, color=ORANGE),
                            on_click=lambda e: self._ai_priority()),
                ], spacing=6, wrap=True),
                ft.Container(height=12),
                ft.Row([
                    ft.Chip(label=ft.Text("选择日期", size=12), leading=ft.Icon(ft.icons.CALENDAR_MONTH, size=14),
                            bgcolor=BG, on_click=lambda e: self.date_picker.pick_date()),
                    self.todo_date_text,
                    ft.Chip(label=ft.Text("选择时间", size=12), leading=ft.Icon(ft.icons.ACCESS_TIME, size=14),
                            bgcolor=BG, on_click=lambda e: self.time_picker.pick_time()),
                    self.todo_time_text,
                ], spacing=8),
                ft.Row([
                    self.todo_content_input,
                    ft.Chip(label=ft.Text("添加", size=12, color=WHITE),
                            leading=ft.Icon(ft.icons.ADD, size=14, color=WHITE),
                            bgcolor=BLUE, on_click=lambda e: self._add_todo_tab()),
                ], spacing=8),
                ft.Divider(height=1, color=BORDER),
                self.todo_list,
            ], expand=True),
            padding=ft.padding.all(24), expand=True, bgcolor=CARD_BG,
            margin=ft.margin.all(16), border_radius=12, border=ft.border.all(1, BORDER),
        )


        # === Tab 3: 车辆出入 ===
        self.car_tab = CarTab(page)
        car_tab = self.car_tab.content

        # === Tab 4: 喝水记录 ===
        self.water_history_tab = WaterHistoryTab(page)
        water_history_tab = self.water_history_tab.content

        # === Tab 5: 加班事项 ===
        self.overtime_notes_tab = OvertimeNotesTab(page)
        overtime_notes_tab = self.overtime_notes_tab.content

        # === Tab 6: 趣味功能（趋势图、成就、心情、番茄钟） ===
        self.fun_tab = FunTab(page, self)
        fun_tab_content = self.fun_tab.content

        # === Tab 7: AI 助手 ===
        self.ai_assistant = AIAssistant(page, self)
        ai_tab_content = self.ai_assistant.content

        # === Tab 8: 知识库 ===
        self.kb_tab = KnowledgeBaseTab(page)

        # Tabs
        tabs = ft.Tabs(
            selected_index=0,
            on_change=lambda e: self._on_tab_change(int(e.control.selected_index)),
            tabs=[
                ft.Tab(text="考勤管理", icon=ft.icons.WORK_HISTORY, content=attendance_tab),
                ft.Tab(text="待办事项", icon=ft.icons.CHECKLIST, content=todo_tab),
                ft.Tab(text="车辆出入", icon=ft.icons.DIRECTIONS_CAR, content=car_tab),
                ft.Tab(text="喝水记录", icon=ft.icons.WATER_DROP, content=water_history_tab),
                ft.Tab(text="加班事项", icon=ft.icons.WORK_OFF, content=overtime_notes_tab),
                ft.Tab(text="摸鱼中心", icon=ft.icons.EMOJI_EMOTIONS, content=fun_tab_content),
                ft.Tab(text="📚 知识库", icon=ft.icons.LIBRARY_BOOKS, content=self.kb_tab.content),
                ft.Tab(text="🤖 AI助手", icon=ft.Image(src="avatars/maodie_avatar.png", width=24, height=24, fit=ft.ImageFit.COVER, border_radius=12), content=ai_tab_content),
            ],
            expand=True,
        )

        # 底部 AI 陪伴栏（自动定时刷新，无需手动操作）
        self.status_text = ft.Text("加载中...", size=11, color=TEXT_THIRD)
        self.ai_bottom_text = ft.Text("🐱 喵~ 今天也是元气满满的一天！", size=11, color=TEXT_SEC, italic=True, expand=True)
        bottom_bar = ft.Container(
            ft.Row([
                self.status_text,
                ft.Container(width=16),
                ft.VerticalDivider(width=1, color=BORDER),
                ft.Container(width=8),
                self.ai_bottom_text,
            ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=16, vertical=5), bgcolor=WHITE,
            border=ft.border.only(top=ft.border.BorderSide(1, BORDER)),
        )
        page.add(top_bar, tabs, bottom_bar)
        page.update()
        self._build_todo_tab()
        self._refresh_data()
        self._load_car_records()
        self._load_weather()
        self._start_water_reminder()
        self._start_eye_reminder()
        self._start_countdown_loop()
        self._start_quote_refresh()
        self._start_ai_bottom_loop()
        tool_executor.set_app(self)
        start_ai_care(self)
        start_tray(page, self)

    # ==================== 日历 ====================

    def _build_calendar(self):
        self.calendar_col.controls.clear()
        start, end = get_company_month_range(self.current_date)
        today = date.today()

        wh = ft.Row(spacing=1)
        for i, w in enumerate(["日", "一", "二", "三", "四", "五", "六"]):
            c = ft.colors.ERROR if i == 0 else (ft.colors.PRIMARY if i == 6 else ft.colors.ON_SURFACE)
            wh.controls.append(ft.Container(ft.Text(w, size=12, weight=ft.FontWeight.BOLD, color=c, text_align=ft.TextAlign.CENTER), width=76, height=28, alignment=ft.alignment.center))
        self.calendar_col.controls.append(wh)
        self.calendar_col.controls.append(ft.Divider(height=1))

        offset = (start.weekday() + 1) % 7
        total_days = (end - start).days + 1
        rows = math.ceil((offset + total_days) / 7)
        for row in range(rows):
            rc = ft.Row(spacing=1)
            for col in range(7):
                i = row * 7 + col
                if i < offset or (i - offset) >= total_days:
                    rc.controls.append(ft.Container(width=76, height=68))
                    continue
                d = start + timedelta(days=i - offset)
                rc.controls.append(self._day_cell(d, today))
            self.calendar_col.controls.append(rc)

    def _day_cell(self, d: date, today: date):
        ds = d.isoformat(); dt = get_day_type(d); holiday = get_holiday_name(d)
        if d == self.selected_date: bg, bc, bw = "#EADDFF", "#6750A4", 2
        elif d == today: bg, bc, bw = TODAY_BG, BLUE, 2
        elif dt == "holiday": bg, bc, bw = HOLIDAY_BG, "#FFCCC7", 1
        elif dt == "makeup": bg, bc, bw = MAKEUP_BG, "#FFE58F", 1
        elif dt == "weekend": bg, bc, bw = WEEKEND_BG, "#ADC6FF", 1
        else: bg, bc, bw = WHITE, "#E0E0E0", 1
        tc = ft.colors.ERROR if d.weekday() == 6 else (ft.colors.PRIMARY if d.weekday() == 5 else ft.colors.ON_SURFACE)
        sub, sub_c = "", tc
        if ds in self.analysis_map:
            a = self.analysis_map[ds]
            if a.missed: sub, sub_c = "漏打卡", RED
            elif a.overtime_hours > 0:
                # 有备注加📝标记
                import json
                try: notes = json.loads(self.user_config.overtime_notes) if self.user_config else {}
                except: notes = {}
                note_mark = "📝" if ds in notes and notes[ds] else ""
                sub, sub_c = f"+{a.overtime_hours}h{note_mark}", GREEN
            elif holiday: sub, sub_c = holiday, RED
            elif dt == "makeup": sub, sub_c = "补班", ORANGE
            elif dt in ("weekend", "holiday"): sub, sub_c = "休息", ft.colors.BLUE_GREY
            else: sub, sub_c = f"{a.card_count}次", tc
        else:
            if holiday: sub, sub_c = holiday, RED
            elif dt == "makeup": sub, sub_c = "补班", ORANGE
            else: sub = get_day_type_label(d)[:2]

        children = [ft.Text(str(d.day), size=16, weight=ft.FontWeight.BOLD, color=tc),
                    ft.Text(sub, size=10, color=sub_c)]

        return ft.Container(
            ft.Column(children, spacing=0, alignment=ft.MainAxisAlignment.CENTER,
                     horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            width=76, height=68, border_radius=7, bgcolor=bg, border=ft.border.all(bw, bc),
            alignment=ft.alignment.center, on_click=lambda e, dd=d: self._on_day_click(dd), ink=True)

    def _on_day_click(self, d: date):
        self.selected_date = d
        self._build_calendar(); self._update_detail(); self.page.update()



    def _show_overtime_note_dialog(self):
        """弹出加班理由记录框"""
        import json as _json
        d = self.selected_date; ds = d.isoformat()
        a = self.analysis_map[ds]
        cfg = self.user_config
        try: notes = _json.loads(cfg.overtime_notes)
        except: notes = {}
        existing = notes.get(ds, "")

        note_field = ft.TextField(value=existing, hint_text="输入加班理由...", multiline=True,
                                  min_lines=2, max_lines=4, text_size=13, width=320)
        info = ft.Text(
            f"📅 {ds}  {a.day_type_label}  加班{a.overtime_hours:.1f}h  ¥{a.overtime_pay:.2f}",
            size=13, color=TEXT_SEC)

        def save(e):
            cfg2 = load_user_config()
            try: n = _json.loads(cfg2.overtime_notes)
            except: n = {}
            val = note_field.value.strip()
            if val: n[ds] = val
            else: n.pop(ds, None)
            cfg2.overtime_notes = _json.dumps(n, ensure_ascii=False)
            save_user_config(cfg2)
            self.user_config = cfg2
            self.page.close(dlg)
            self._build_calendar()
            self._update_detail()
            self.page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("加班记录", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column([info, ft.Container(height=8), note_field], tight=True, width=350),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.close(dlg)),
                ft.FilledButton("保存", on_click=save),
            ],
        )
        self.page.open(dlg)

    # ==================== 考勤详情 ====================

    def _build_panel(self):
        self.summary_col.controls = [ft.Text("请刷新数据", size=13, color=TEXT_THIRD)]
        self.detail_col.controls = [ft.Text("点击日历查看", size=13, color=TEXT_THIRD)]
        self.records_col.controls = [ft.Text("暂无记录", size=13, color=TEXT_THIRD)]

    def _build_punch_buttons(self):
        self.punch_btn_col.controls.clear()
        dt = get_day_type(self.selected_date)
        is_rest = dt in ("weekend", "holiday")
        if is_rest or dt == "makeup":
            cards = [("卡1 早上 08:00-08:30", 0, ft.icons.WB_SUNNY), ("卡2 中午 12:05-13:00", 1, ft.icons.WB_SUNNY),
                     ("卡3 中午 12:05-13:00", 2, ft.icons.WB_SUNNY), ("卡4 下午 17:30-18:00", 3, ft.icons.WB_TWILIGHT),
                     ("卡5 晚上 20:30-22:00", 5, ft.icons.NIGHTS_STAY)]
        else:
            cards = [("卡1 早上 08:00-08:30", 0, ft.icons.WB_SUNNY), ("卡4 下午 17:30-18:00", 3, ft.icons.WB_TWILIGHT),
                     ("卡5 晚上 20:30-22:00", 5, ft.icons.NIGHTS_STAY)]
        for label, idx, icon in cards:
            self.punch_btn_col.controls.append(ft.ElevatedButton(label, icon=icon, on_click=lambda e, i=idx: self._punch_single(i), width=260))

    def _punch_single(self, index):
        """点击补卡按钮 → 弹窗显示AI建议时间 → 用户修改 → 确认补卡"""
        ds = self.selected_date.isoformat()
        # index: 0=卡1, 1=卡2, 2=卡3, 3=卡4, 5=卡5
        name_map = {0: "卡1早上", 1: "卡2中午", 2: "卡3中午", 3: "卡4下午", 5: "卡5晚上"}
        card_name = name_map.get(index, f"卡{index}")

        # 获取当天已有打卡时间，给AI做参考
        records = self.records_map.get(ds, [])
        existing_times = []
        for r in records:
            t = r.get("worktime")
            if t and hasattr(t, "strftime"):
                rm = r.get("remark", "") or ""
                time_str = t.strftime("%H:%M")
                if rm and len(rm) < 20:
                    time_str += f"({rm})"
                existing_times.append(time_str)

        # 随机生成默认时间（与 punch_card.py 逻辑一致）
        time_ranges = [
            (8, 0, 8, 30),
            (12, 5, 13, 0),
            (12, 5, 13, 0),
            (17, 30, 18, 0),
            (20, 30, 22, 0),
        ]
        range_idx = {0: 0, 1: 1, 2: 2, 3: 3, 5: 4}.get(index, 0)
        sh, sm, eh, em = time_ranges[range_idx]
        import random as _random
        start_seconds = (sh * 60 + sm) * 60
        end_seconds = (eh * 60 + em) * 60 - 1  # 不含结束秒
        total_s = _random.randint(start_seconds, end_seconds)
        rh = total_s // 3600
        rm = (total_s % 3600) // 60
        rs = total_s % 60
        default_time = f"{rh:02d}:{rm:02d}:{rs:02d}"
        time_range_label = f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d}"

        # AI 建议
        ai_tip = ft.Text("🐱 建议时间分析中...", size=12, color=TEXT_SEC)
        time_input = ft.TextField(
            value=default_time, label=f"{card_name} 补卡时间",
            hint_text="HH:MM:SS 格式", text_size=14, width=180, text_align=ft.TextAlign.CENTER)

        # 收集本月所有出现过的打卡位置（remark）
        all_remarks = set()
        for day_records in self.records_map.values():
            for r in day_records:
                rm = (r.get("remark") or "").strip()
                if rm:
                    all_remarks.add(rm)
        remark_options = sorted(all_remarks) if all_remarks else ["HY_C6_8F_05_KQ02_门_1"]
        remark_dd = ft.Dropdown(
            options=[ft.dropdown.Option(rm) for rm in remark_options],
            value=remark_options[0], width=260, dense=True, text_size=12)

        def do_punch(e):
            time_str = time_input.value.strip()
            try:
                parts = time_str.split(":")
                h, m = int(parts[0]), int(parts[1])
                s = int(parts[2]) if len(parts) > 2 else 0
                if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59):
                    raise ValueError
            except:
                self.page.show_snack_bar(ft.SnackBar(ft.Text("时间格式错误，请输入 HH:MM:SS"), bgcolor=RED))
                return

            selected_remark = remark_dd.value or remark_options[0]

            from punch_card import format_work_time
            from datetime import datetime as dt
            punch_dt = dt.strptime(f"{ds} {h:02d}:{m:02d}:{s:02d}", "%Y-%m-%d %H:%M:%S")
            worktime_str = format_work_time(punch_dt)

            import pyodbc
            from config import DB_CONFIG
            try:
                conn = pyodbc.connect(
                    f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={DB_CONFIG['server']},{DB_CONFIG['port']};"
                    f"DATABASE={DB_CONFIG['database']};UID={DB_CONFIG['user']};PWD={DB_CONFIG['password']};")
                sql = (
                    f"INSERT INTO kq_workrecord "
                    f"(empno, empname, deptno, deptname, repair_sign, worktime, workdate, macno, backup1, remark) "
                    f"VALUES (1103141, '吴钦腾', '41402', 'IT信息技术部', 0, "
                    f"'{worktime_str}', '{ds} 00:00:00', '海康考勤打卡', '海康考勤打卡', '{selected_remark}');"
                )
                conn.cursor().execute(sql); conn.commit(); conn.close()
                self.page.close(dlg)
                self.page.show_snack_bar(ft.SnackBar(ft.Text(f"✅ {card_name} 补卡成功 ({time_str} @{selected_remark})"), bgcolor=GREEN))
                self._refresh_data()
            except Exception as ex:
                self.page.show_snack_bar(ft.SnackBar(ft.Text(f"失败: {ex}"), bgcolor=RED))

        time_input.width = 180
        remark_dd.width = 280

        dlg = ft.AlertDialog(
            title=ft.Text(f"补卡 - {card_name}", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column([
                ft.Text(f"日期: {ds}", size=13, color=TEXT_SEC),
                ft.Container(height=8),
                ai_tip,
                ft.Container(height=8),
                ft.Text("补卡时间 (HH:MM:SS):", size=12, color=TEXT_SEC),
                time_input,
                ft.Container(height=8),
                ft.Text("打卡位置:", size=12, color=TEXT_SEC),
                remark_dd,
                ft.Container(height=8),
                ft.Text(f"已打卡时间: {', '.join(existing_times) if existing_times else '无'}", size=11, color=TEXT_THIRD),
            ], tight=True, width=400),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.close(dlg)),
                ft.FilledButton("确认补卡", on_click=do_punch),
            ],
        )
        self.page.open(dlg)

        # 异步 AI 建议
        def _ai_suggest():
            prompt = f"日期{ds}，补{card_name}（建议范围{time_range_label}），已有打卡{existing_times}。用猫咪语气建议一个最佳补卡时间点（10字以内，不含时间）。"
            r = ai_svc.call(prompt, system_prompt="你是猫咪考勤专家。", max_tokens=50, temperature=0.8, timeout=8)
            if r and len(r) < 60:
                ai_tip.value = f"🐱 {r.strip()}"
            else:
                ai_tip.value = f"🐱 建议在 {time_range_label} 范围内选择~"
            try: ai_tip.update()
            except: pass
        threading.Thread(target=_ai_suggest, daemon=True).start()

    def _ai_punch_silent(self, ds):
        """AI 静默分析打卡，无感显示一行建议"""
        a = self.analysis_map.get(ds)
        if not a:
            return

        records = self.records_map.get(ds, [])
        times = []
        for r in records:
            t = r.get("worktime")
            if t and hasattr(t, "strftime"):
                times.append(t.strftime("%H:%M"))

        # 先本地快速建议
        if a.missed:
            missing = a.required_cards - a.card_count
            tip = f"🐱 缺{missing}次打卡，建议补卡"
        elif a.card_count >= a.required_cards:
            tip = "🐱 打卡已齐全 ✓"
        else:
            tip = "🐱 打卡正常"

        def _update(val):
            try:
                if self.punch_section.visible:
                    self.punch_ai_tip.value = val
                    self.punch_ai_tip.update()
            except: pass

        _update(tip)

        # 异步AI增强
        dt = get_day_type(self.selected_date)
        is_rest = dt in ("weekend", "holiday")
        is_makeup = dt == "makeup"
        required = 5 if (is_rest or is_makeup) else 3

        # 补卡规则说明
        if is_rest or is_makeup:
            card_rules = "卡1:08:00-08:30 卡2:12:05-13:00 卡3:12:05-13:00 卡4:17:30-18:00 卡5:20:30-22:00"
            card_names = ["卡1早上", "卡2中午", "卡3中午", "卡4下午", "卡5晚上"]
        else:
            card_rules = "卡1:08:00-08:30 卡4:17:30-18:00 卡5:20:30-22:00"
            card_names = ["卡1早上", "卡4下午", "卡5晚上"]

        ctx = json.dumps({
            "打卡时间": times, "应打卡": required, "已打卡": a.card_count,
            "漏打卡": a.missed, "补卡规则": card_rules,
        }, ensure_ascii=False)

        try:
            r = ai_svc.call(
                f"考勤：{ctx}。根据规则分析缺哪张卡，猫咪语气一句话补卡建议（12字以内）。",
                system_prompt="你是猫咪考勤助手。补卡规则：平日3卡(卡1早上8:00-8:30/卡4下午17:30-18:00/卡5晚上20:30-22:00)，休息日和补班日5卡(卡1/卡2中午12:05-13:00/卡3中午12:05-13:00/卡4/卡5)。根据已有打卡时间对比规则，判断缺哪张。回复极短。",
                max_tokens=50, temperature=0.7, timeout=8)
            if r and len(r) < 50 and "error" not in r.lower():
                _update(f"🐱 {r.strip()}")
        except:
            pass  # AI 失败保持本地建议

    def _update_detail(self):
        self.summary_col.controls.clear(); self.detail_col.controls.clear(); self.records_col.controls.clear()
        self._update_summary()
        ds = self.selected_date.isoformat()
        if ds in self.analysis_map:
            a = self.analysis_map[ds]
            self._update_day(a, self.records_map.get(ds, []))
            # 有打卡记录就显示补卡操作（休息日也可能需要补卡）
            show_punch = a.card_count > 0
        else:
            self.detail_col.controls.append(ft.Text("暂无数据", size=13, color=TEXT_THIRD))
            self.records_col.controls.append(ft.Text("暂无打卡记录", size=13, color=TEXT_THIRD))
            show_punch = False
        # 加载当天车辆出入记录
        self._update_car_day()
        # 控制补卡区域显示/隐藏
        self.punch_section.visible = show_punch
        self.punch_title.visible = show_punch
        self.punch_card.visible = show_punch
        self.punch_ai_tip.visible = show_punch
        if show_punch:
            self._build_punch_buttons()
            self.punch_ai_tip.value = "🐱 分析中..."
            try: self.punch_ai_tip.update()
            except: pass
            threading.Thread(target=self._ai_punch_silent, args=(ds,), daemon=True).start()
        else:
            self.punch_ai_tip.value = ""

    def _update_car_day(self):
        """更新当天车辆出入记录"""
        self.car_day_col.controls.clear()
        from car_db import query_car_records
        from config import CAR_PLATE
        plate = self.user_config.car_plate if self.user_config and self.user_config.car_plate else CAR_PLATE
        try:
            ym = self.selected_date.strftime("%Y%m")
            rows = query_car_records(plate, ym)
            day_rows = [r for r in rows if r["ch_crosstime"].strftime("%Y-%m-%d") == self.selected_date.isoformat()]
            if not day_rows:
                self.car_day_col.controls.append(ft.Text("当天无车辆出入", size=12, color=TEXT_THIRD))
                return
            for r in day_rows:
                d = "🚗 进" if r["ch_out"] == 0 else "🚙 出"
                t = r["ch_crosstime"].strftime("%H:%M:%S")
                c = GREEN if r["ch_out"] == 0 else BLUE
                self.car_day_col.controls.append(
                    ft.Container(
                        ft.Row([
                            ft.Text(d, size=12, color=c, width=42),
                            ft.Text(t, size=12),
                            ft.Container(expand=True),
                            ft.IconButton(ft.icons.EDIT, icon_size=14, icon_color=TEXT_THIRD,
                                          on_click=lambda e, rec=r, dt=ym: self._edit_car_time(rec, dt)),
                        ]),
                        padding=ft.padding.symmetric(vertical=2),
                        border=ft.border.only(bottom=ft.border.BorderSide(0.5, BORDER)),
                    )
                )
        except Exception:
            self.car_day_col.controls.append(ft.Text("加载失败", size=12, color=TEXT_THIRD))

    def _edit_car_time(self, record, year_month):
        """编辑车辆出入记录 - 弹出对话框（时间含毫秒+进出方式）"""
        old_time = record["ch_crosstime"].strftime("%H:%M:%S.%f")[:-3]  # HH:MM:SS.FFF
        old_out = record["ch_out"]
        self._edit_car_record = record
        self._edit_car_ym = year_month

        time_input = ft.TextField(value=old_time, hint_text="HH:MM:SS.FFF", text_size=14, width=150, text_align=ft.TextAlign.CENTER)
        out_switch = ft.Switch(value=old_out == 1, label="🚗进" if old_out == 0 else "🚙出",
                               active_color=BLUE, active_track_color=BLUE_LIGHT)

        def save_changes(e):
            from car_db import update_car_record
            val = time_input.value.strip()
            try:
                # 解析 HH:MM:SS.FFF 或 HH:MM:SS
                if "." in val:
                    time_part, ms_part = val.split(".")
                    ms = int(ms_part.ljust(3, "0")[:3]) * 1000  # 转微秒
                else:
                    time_part, ms = val, 0
                parts = time_part.split(":")
                h, m, s = int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0
                new_dt = record["ch_crosstime"].replace(hour=h, minute=m, second=s, microsecond=ms)
                new_out = 1 if out_switch.value else 0
                if update_car_record(record["ch_id"], year_month, new_time=new_dt, new_out=new_out):
                    self.page.show_snack_bar(ft.SnackBar(ft.Text("已修改"), bgcolor=GREEN))
                    dlg.open = False; self.page.update()
                    self._update_car_day()
                    if hasattr(self, 'car_list') and self.car_list.controls:
                        self._load_car_records()
                else:
                    self.page.show_snack_bar(ft.SnackBar(ft.Text("修改失败"), bgcolor=RED))
            except Exception:
                self.page.show_snack_bar(ft.SnackBar(ft.Text("格式: HH:MM:SS.FFF"), bgcolor=RED))

        dlg = ft.AlertDialog(
            title=ft.Text("修改出入记录"),
            content=ft.Column([
                ft.Text(f"原记录: {old_time}  {'进' if old_out==0 else '出'}", size=13, color=TEXT_THIRD),
                ft.Container(height=12),
                ft.Row([ft.Text("时间:", size=13, width=50), time_input]),
                ft.Container(height=8),
                ft.Row([ft.Text("进出:", size=13, width=50), out_switch]),
            ], tight=True, height=150),
            actions=[ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                     ft.FilledButton("保存", on_click=save_changes)],
        )
        self.page.dialog = dlg
        dlg.open = True
        self.page.update()

    def _update_summary(self):
        if not self.analysis_map:
            self.summary_col.controls.append(ft.Text("请先刷新数据", size=13, color=TEXT_THIRD)); return
        total_h = total_pay = wd_h = we_h = mk_h = 0.0; missed = []
        for ds, a in self.analysis_map.items():
            if a.overtime_hours > 0:
                total_h += a.overtime_hours; total_pay += a.overtime_pay
                if a.is_makeup: mk_h += a.overtime_hours
                elif a.is_rest: we_h += a.overtime_hours
                else: wd_h += a.overtime_hours
            if a.missed: missed.append(ds)
        self.summary_col.controls += [
            ft.Row([ft.Text("加班天数", size=13, color=TEXT_SEC), ft.Container(expand=True), ft.Text(f"{sum(1 for a in self.analysis_map.values() if a.overtime_hours>0)} 天", size=16, weight=ft.FontWeight.BOLD)]),
            ft.Row([ft.Text("总小时", size=13, color=TEXT_SEC), ft.Container(expand=True), ft.Text(f"{total_h:.1f}h", size=16, weight=ft.FontWeight.BOLD)]),
            ft.Divider(),
            ft.Row([ft.Text("平日", size=13, color=TEXT_SEC), ft.Text(f"{wd_h:.1f}h x ¥{self.user_config.weekday_rate:.2f}", size=11, color=TEXT_THIRD), ft.Container(expand=True), ft.Text(f"¥{wd_h*self.user_config.weekday_rate:.2f}", size=13, weight=ft.FontWeight.W_500)]),
            ft.Row([ft.Text("休息日", size=13, color=TEXT_SEC), ft.Text(f"{we_h:.1f}h x ¥{self.user_config.weekend_rate:.2f}", size=11, color=TEXT_THIRD), ft.Container(expand=True), ft.Text(f"¥{we_h*self.user_config.weekend_rate:.2f}", size=13, weight=ft.FontWeight.W_500)]),
            ft.Row([ft.Text("补班日", size=13, color=TEXT_SEC), ft.Text(f"{mk_h:.1f}h x ¥{self.user_config.makeup_rate:.2f}", size=11, color=TEXT_THIRD), ft.Container(expand=True), ft.Text(f"¥{mk_h*self.user_config.makeup_rate:.2f}", size=13, weight=ft.FontWeight.W_500)]),
            ft.Divider(),
            ft.Row([ft.Text("总工资", size=14, weight=ft.FontWeight.BOLD), ft.Container(expand=True), ft.Text(f"{total_pay:.2f}", size=22, weight=ft.FontWeight.BOLD, color=BLUE)]),
        ]
        if missed: self.summary_col.controls.append(ft.Text(f"漏打卡 {len(missed)} 天", size=12, color=RED))

    def _update_day(self, a: DayAnalysis, records: list):
        holiday = get_holiday_name(a.date)
        type_text = a.day_type_label + (f" · {holiday}" if holiday else "")
        tc = {"节假日": ft.colors.ERROR, "补班日": ft.colors.AMBER, "休息日": ft.colors.PRIMARY, "平日": ft.colors.GREEN}
        wn = ["周一","周二","周三","周四","周五","周六","周日"]
        self.detail_col.controls += [
            ft.Row([ft.Text("日期", size=13, color=TEXT_SEC, width=70), ft.Text(f"{a.date.isoformat()} {wn[a.date.weekday()]}", size=13, color=TEXT)]),
            ft.Row([ft.Text("类型", size=13, color=TEXT_SEC, width=70), ft.Container(ft.Text(type_text, size=12, color=tc.get(a.day_type_label)), padding=ft.padding.symmetric(horizontal=8, vertical=2), border_radius=10, bgcolor=tc.get(a.day_type_label, ft.colors.GREY)+"20")]),
            ft.Row([ft.Text("打卡", size=13, color=TEXT_SEC, width=70), ft.Text(f"{a.card_count}/{a.required_cards} 次", size=13), ft.Text("漏打卡!", size=12, color=RED) if a.missed else ft.Icon(ft.icons.CHECK_CIRCLE, color=GREEN, size=16)]),
            ft.Divider(),
            ft.Row([ft.Text("加班小时", size=13, color=TEXT_SEC, width=70), ft.Text(f"{a.overtime_hours:.1f} h", size=15, weight=ft.FontWeight.BOLD)]),
            ft.Row([ft.Text("加班费率", size=13, color=TEXT_SEC, width=70), ft.Text(f"{a.overtime_rate:.1f}/h", size=13)]),
            ft.Row([ft.Text("加班工资", size=13, color=TEXT_SEC, width=70), ft.Text(f"{a.overtime_pay:.2f}", size=18, weight=ft.FontWeight.BOLD, color=BLUE)]),
        ]
        # 有加班时显示理由或记录按钮
        if a.overtime_hours > 0:
            ds = a.date.isoformat()
            import json as _json
            try: notes = _json.loads(self.user_config.overtime_notes)
            except: notes = {}
            note = notes.get(ds, "")
            if note:
                self.detail_col.controls.append(
                    ft.Container(ft.Row([
                        ft.Text("加班理由", size=13, color=TEXT_SEC, width=70),
                        ft.Text(note, size=13, color=TEXT, expand=True),
                        ft.IconButton(ft.icons.EDIT, icon_size=14, icon_color=TEXT_THIRD,
                                      on_click=lambda e: self._show_overtime_note_dialog()),
                    ]), padding=ft.padding.symmetric(vertical=4),
                    border=ft.border.only(bottom=ft.border.BorderSide(0.5, BORDER))))
            else:
                self.detail_col.controls.append(
                    ft.Row([ft.Text("加班理由", size=13, color=TEXT_SEC, width=70),
                            ft.TextButton("记录理由", icon=ft.icons.EDIT_NOTE,
                                          on_click=lambda e: self._show_overtime_note_dialog())],
                           spacing=4))
        if a.card_times: self.detail_col.controls.append(ft.Text("打卡: " + "  ".join(t.strftime("%H:%M") for t in a.card_times), size=12, color=TEXT_THIRD))
        if records:
            for i, r in enumerate(records):
                wt = r.get("worktime", ""); ts = wt.strftime("%H:%M:%S") if hasattr(wt, "strftime") else (str(wt)[-8:] if len(str(wt))>=8 else str(wt))
                rm = r.get("remark", "") or ""
                if rm and len(rm) > 30: rm = rm[:30] + "..."
                row_ctls = [ft.Text(f"#{i+1}", size=11, color=TEXT_THIRD, width=30), ft.Text(ts, size=13)]
                if rm:
                    row_ctls.append(ft.Container(width=8))
                    row_ctls.append(ft.Text(rm, size=11, color=TEXT_SEC, italic=True))
                self.records_col.controls.append(ft.Container(ft.Row(row_ctls, spacing=2, wrap=True),
                    padding=ft.padding.symmetric(vertical=4), border=ft.border.only(bottom=ft.border.BorderSide(0.5, ft.colors.OUTLINE_VARIANT))))
        else: self.records_col.controls.append(ft.Text("当天无打卡记录", size=13, color=TEXT_THIRD))

    # ==================== 待办 Tab ====================

    def _on_date_picked(self, d):
        if d:
            self._todo_date = d.isoformat()
            self.todo_date_text.value = f"📅 {d.isoformat()}"
            self._build_todo_tab()
            self.page.update()

    def _on_time_picked(self, t):
        if t:
            self._todo_time = t.strftime("%H:%M")
            self.todo_time_text.value = self._todo_time
            self.page.update()

    def _add_todo_tab(self):
        content = self.todo_content_input.value.strip()
        if not content:
            self.page.show_snack_bar(ft.SnackBar(ft.Text("请输入待办内容"), bgcolor=RED)); return
        todo_mgr.add_item(self._todo_date, self._todo_time, content)
        self.todo_content_input.value = ""
        self._build_todo_tab()
        self.page.update()

    def _build_todo_tab(self):
        self.todo_list.controls.clear()
        items = todo_mgr.get_items(self._todo_date)
        if not items:
            self.todo_list.controls.append(ft.Text("暂无待办，添加一个吧~", size=13, color=TEXT_THIRD))
        for item in items:
            icon = ft.icons.CHECK_CIRCLE if item.done else ft.icons.RADIO_BUTTON_UNCHECKED
            color = GREEN if item.done else TEXT_SEC
            style = ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH if item.done else None)
            self.todo_list.controls.append(
                ft.Container(
                    ft.Row([
                        ft.IconButton(icon, icon_size=22, icon_color=color, on_click=lambda e, i=item: self._toggle_todo_tab(i)),
                        ft.Column([
                            ft.Text(item.content, size=14, weight=ft.FontWeight.W_500, color=color, style=style),
                            ft.Text(f"{item.date}  {item.time}", size=11, color=TEXT_THIRD),
                        ], spacing=2, expand=True),
                        ft.IconButton(ft.icons.DELETE_OUTLINE, icon_size=18, icon_color=TEXT_THIRD, on_click=lambda e, i=item: self._delete_todo_tab(i)),
                    ], spacing=8),
                    padding=ft.padding.all(12), border_radius=10,
                    bgcolor=WHITE, border=ft.border.all(1, BORDER),
                )
            )

    def _toggle_todo_tab(self, item):
        todo_mgr.toggle_done(item.date, item.id)
        self._build_todo_tab(); self.page.update()

    def _delete_todo_tab(self, item):
        todo_mgr.remove_item(item.date, item.id)
        self._build_todo_tab(); self.page.update()

    # ==================== AI 待办助手 ====================

    def _ai_schedule(self):
        """AI 智能排程：分析未完成待办，给出最佳时间安排"""
        all_items = todo_mgr.get_all_items()
        undone = [(it.date, it.time, it.content) for it in all_items if not it.done]
        if not undone:
            self.page.show_snack_bar(ft.SnackBar(ft.Text("喵~ 没有待排程的任务哦，先去添加吧！", size=13), bgcolor=GREEN))
            return
        items_text = "\n".join([f"- {d} {t} {c}" for d, t, c in undone])
        prompt = f"我今天的待办事项：\n{items_text}\n\n请用猫咪语气，给出一个合理的执行顺序和每项建议时间（简短，5行以内）。"
        self._show_ai_result_dialog("🧠 AI智能排程", prompt)

    def _ai_breakdown(self):
        """AI 拆解任务：把大任务拆成小步骤"""
        content = self.todo_content_input.value.strip()
        if not content:
            # 拿最近一个未完成任务
            all_items = todo_mgr.get_all_items()
            undone = [it for it in all_items if not it.done]
            if undone:
                content = undone[-1].content
            else:
                self.page.show_snack_bar(ft.SnackBar(ft.Text("请先输入一个任务再拆解~", size=13), bgcolor=ORANGE))
                return
        prompt = f"任务：「{content}」\n请用猫咪语气，把这个任务拆成3-5个小步骤，每步一句话。"
        self._show_ai_result_dialog("📋 任务拆解", prompt)

    def _ai_priority(self):
        """AI 优先级排序"""
        all_items = todo_mgr.get_all_items()
        undone = [(it.date, it.time, it.content) for it in all_items if not it.done]
        if not undone:
            self.page.show_snack_bar(ft.SnackBar(ft.Text("喵~ 没有待处理的任务~", size=13), bgcolor=GREEN))
            return
        items_text = "\n".join([f"- {d} {t} {c}" for d, t, c in undone])
        prompt = f"我的待办：\n{items_text}\n\n请按紧急+重要程度排序，用猫咪语气给出前3优先级的建议（简短）。"
        self._show_ai_result_dialog("⚡ 优先级排序", prompt)

    def _show_ai_result_dialog(self, title, prompt):
        """弹出AI结果对话框"""
        loading = ft.Text("🐱 喵星人思考中...", size=13, color=TEXT_SEC)
        dlg = ft.AlertDialog(
            title=ft.Text(title, size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column([loading], tight=True, width=380, scroll=ft.ScrollMode.AUTO, height=280),
            actions=[ft.TextButton("关闭", on_click=lambda e: self.page.close(dlg))],
        )
        self.page.open(dlg)
        self.page.update()

        def _run():
            try:
                result = ai_svc.call(
                    prompt,
                    system_prompt="你是一只聪明可爱的猫咪助理，帮主人管理任务。回复要简洁、有结构、带emoji。不超过200字。",
                    max_tokens=300, temperature=0.7, timeout=15)
                loading.value = result if result else "🐱 喵~ 没想好，再问一次？"
                loading.update()
                self.page.update()
            except Exception as e:
                loading.value = f"🐱 出错了: {str(e)[:100]}"
                try:
                    loading.update()
                    self.page.update()
                except:
                    pass
        threading.Thread(target=_run, daemon=True).start()

    # ==================== 提醒 ====================

    def _show_reminder(self, title, msg):
        self.page.show_snack_bar(ft.SnackBar(ft.Column([ft.Text(title, weight=ft.FontWeight.BOLD, size=13), ft.Text(msg, size=12)], spacing=2), bgcolor=BLUE, duration=8000))

    def _toast(self, title, body):
        """Windows Toast 通知"""
        import subprocess
        ps = f'''
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $textNodes = $template.GetElementsByTagName("text")
        $textNodes.Item(0).AppendChild($template.CreateTextNode("{title}")) > $null
        $textNodes.Item(1).AppendChild($template.CreateTextNode("{body}")) > $null
        $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("哈基米曼波").Show($toast)
        '''
        subprocess.run(["powershell", "-Command", ps], capture_output=True)

    def _test_reminder(self):
        now = datetime.now().strftime("%H:%M")
        self._toast("哈基米曼波 提醒", f"{now} 这是一条测试提醒！")
        self._show_reminder("哈基米曼波 提醒", f"\u23F0 {now}\n这是一条测试提醒！")

    # ==================== 导航 ====================

    def _on_tab_change(self, index):
        self.tab_index = index
        if index == 3:  # 喝水记录标签
            self.water_history_tab.load()
        elif index == 4:  # 加班事项标签
            self.overtime_notes_tab.load()
        elif index == 5:  # 趣味功能标签
            self.fun_tab.load_all()
        elif index == 6:  # 知识库标签
            self.kb_tab.load()

    def _prev_month(self):
        s, _ = get_company_month_range(self.current_date); self.current_date = s - timedelta(days=1); self._nav()
    def _next_month(self):
        _, e = get_company_month_range(self.current_date); self.current_date = e + timedelta(days=1); self._nav()
    def _go_today(self):
        self.current_date = date.today(); self.selected_date = date.today(); self._nav()
    def _nav(self):
        self.month_label.value = get_company_month_label(self.current_date)
        self._refresh_data()
        # 联动车辆记录月份（与考勤管理一致，使用公司月范围）
        s, e = get_company_month_range(self.current_date)
        self.car_tab.date_from = s
        self.car_tab.date_to = e
        self.car_tab.from_btn.text = s.strftime("%m-%d")
        self.car_tab.to_btn.text = e.strftime("%m-%d")
        self.car_tab.abn_date_from = s
        self.car_tab.abn_date_to = e
        self.car_tab.abn_from_btn.text = s.strftime("%m-%d")
        self.car_tab.abn_to_btn.text = e.strftime("%m-%d")
        self._load_car_records()

    def _refresh_data(self):
        self.status_text.value = "加载中..."; self.page.update()
        try:
            s, e = get_company_month_range(self.current_date)
            recs = query_work_records_range(self.user_config.empname, s.isoformat(), e.isoformat())
            self.records_map = recs; self.analysis_map = {}
            d = s
            while d <= e: ds = d.isoformat(); self.analysis_map[ds] = DayAnalysis(d, recs.get(ds, []), self.user_config); d += timedelta(days=1)
            self._build_calendar(); self._update_detail()
            self.status_text.value = f"已加载 {s} ~ {e}，{len(recs)}天有记录"; self.page.update()
            self._refresh_ai_daily()  # 刷新AI每日卡片
        except Exception as ex:
            self.status_text.value = f"加载失败: {ex}"; self.page.update()

    def _refresh_ai_daily(self):
        """AI 根据当天数据生成一句话点评"""
        ds = self.selected_date.isoformat()
        a = self.analysis_map.get(ds)
        if not a:
            self.ai_daily_text.value = "🐱 今天暂无考勤数据~"
            try: self.ai_daily_text.update()
            except: pass
            return

        # 本地快速生成，不调用AI API（避免频繁调用）
        parts = []
        if a.overtime_hours > 0:
            parts.append(f"加班{a.overtime_hours:.1f}h")
        if a.missed:
            parts.append("⚠漏打卡")
        if not a.overtime_hours and not a.missed:
            if a.is_rest:
                parts.append("休息日🎉")
            else:
                parts.append("准时下班👍")

        tip = ""
        if a.overtime_hours >= 3:
            tip = "辛苦了，记得补充能量！"
        elif a.missed:
            tip = "快去补卡！"
        elif a.is_rest:
            tip = "好好享受休息时光~"
        else:
            tip = "今天效率很棒！"

        self.ai_daily_text.value = f"🐱 {a.day_type_label} | {'，'.join(parts)} | {tip}"
        try: self.ai_daily_text.update()
        except: pass

    def _start_ai_bottom_loop(self):
        """底部AI陪伴语定时自动刷新，每5分钟换一句"""
        import time as _time
        import random
        quotes = [
            "🐱 喵~ 今天也是元气满满的一天！",
            "🐱 代码写累了就喝口水吧~",
            "🐱 劳逸结合，摸鱼也是生产力！",
            "🐱 你已经很棒了，别忘了休息哦~",
            "🐱 滴，摸鱼卡！喵~",
            "🐱 主人，你的颈椎需要活动一下了~",
            "🐱 距离下班还有一小会儿，坚持住！",
            "🐱 打工人的浪漫，就是准时下班~",
            "🐱 今天的水喝够了吗？💧",
            "🐱 做不完的明天再做，别太累~",
        ]
        def _run():
            while True:
                self.ai_bottom_text.value = random.choice(quotes)
                try: self.ai_bottom_text.update()
                except: pass
                _time.sleep(300)  # 每5分钟刷新，纯本地不调API
        threading.Thread(target=_run, daemon=True).start()

    def _check_startup_alerts(self):
        """启动时检查漏打卡和异常出入，弹窗提醒"""
        alerts = []; toast_lines = []
        # 漏打卡检查
        missed_dates = []
        for ds, a in self.analysis_map.items():
            if a.missed:
                missed_dates.append(ds)
        if missed_dates:
            line = f"📋 打卡异常：{len(missed_dates)}天漏打卡 ({', '.join(missed_dates[-3:])}{'...' if len(missed_dates)>3 else ''})"
            alerts.append(line); toast_lines.append(line)

        # 异常出入检查
        abn_count = len(self.car_tab.abnormal_records) if hasattr(self.car_tab, 'abnormal_records') else 0
        if abn_count > 0:
            line = f"🚗 车辆出入异常：{abn_count}条异常记录"
            alerts.append(line); toast_lines.append(line)

        if alerts:
            msg = "\n".join(alerts)
            self.page.show_snack_bar(ft.SnackBar(
                ft.Text(f"⚠ {msg}", size=13), bgcolor=ORANGE, duration=10000))
            self._toast("哈基米曼波 异常提醒", "\n".join(toast_lines))

    def _show_settings(self):
        """打开设置页面"""
        self.page.clean()
        # 重新绑定窗口事件
        def on_win(e):
            if e.data == "minimize":
                self.page.window.skip_task_bar = True
                self.page.window.visible = False
                self.page.update()
                show_pet(self)
        self.page.window.on_event = on_win
        settings = show_settings_page(self.page, self._on_settings_back, self.user_config)
        self.page.add(settings)
        self.page.update()

    def _on_settings_back(self):
        """从设置页返回主页"""
        self.user_config = load_user_config()
        self.page.clean()
        self._build_main_ui()

    # ==================== 车辆出入 ====================

    def _load_car_records(self):
        self.car_tab.load()
        self.car_tab.load_abnormal()
        self._check_startup_alerts()

    # ==================== 天气（多数据源 + 带伞提醒） ====================

    def _fetch_weather(self):
        """后台线程获取天气，多接口容错"""
        data = None
        # 数据源1: wttr.in
        try:
            url = "https://wttr.in/Dongguan?format=j1&lang=zh"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
        except:
            pass
        # 数据源2: Open-Meteo（免费无需API Key）
        if not data:
            try:
                url = "https://api.open-meteo.com/v1/forecast?latitude=23.02&longitude=113.75&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code&timezone=Asia/Shanghai&forecast_days=2"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    raw = json.loads(resp.read().decode())
                cur = raw.get("current", {})
                daily = raw.get("daily", {})
                data = {
                    "current_condition": [{
                        "temp_C": str(cur.get("temperature_2m", "--")),
                        "weatherDesc": [{"value": self._om_weather_code(cur.get("weather_code", 0))}],
                        "humidity": str(cur.get("relative_humidity_2m", "--")),
                        "windspeedKmph": str(cur.get("wind_speed_10m", 0)),
                    }],
                    "weather": [{
                        "maxtempC": str(daily.get("temperature_2m_max", [0])[0]) if daily.get("temperature_2m_max") else "0",
                        "mintempC": str(daily.get("temperature_2m_min", [0])[0]) if daily.get("temperature_2m_min") else "0",
                        "hourly": [{"weatherDesc": [{"value": self._om_weather_code(daily.get("weather_code", [0])[0] if daily.get("weather_code") else 0)}]}],
                    }],
                }
            except:
                pass
        # 数据源3: 本地备用
        if not data:
            self.weather_text.value = "☁ 天气获取失败"
            self.weather_text.update()
            return

        try:
            cur = data["current_condition"][0]
            temp = cur["temp_C"]
            desc_en = cur["weatherDesc"][0]["value"]
            humidity = cur.get("humidity", "--")
            wind = cur.get("windspeedKmph", "0")

            cn_map = {
                "Sunny": "晴", "Clear": "晴", "Partly cloudy": "多云", "Cloudy": "阴",
                "Overcast": "阴", "Mist": "雾", "Fog": "雾", "Freezing fog": "冻雾",
                "Light drizzle": "小雨", "Patchy light drizzle": "小阵雨",
                "Light rain": "小雨", "Moderate rain": "中雨", "Heavy rain": "大雨",
                "Patchy rain possible": "可能有雨", "Light rain shower": "阵雨",
                "Thunderstorm": "雷暴", "Snow": "雪", "Light snow": "小雪",
            }
            desc_cn = cn_map.get(desc_en, desc_en)
            weather_display = f"🌡 {temp}°C  {desc_cn}  💧{humidity}%"

            # 带伞/穿衣提醒
            tips = self._weather_tips(desc_en, float(temp) if temp.replace('.','').replace('-','').isdigit() else 25,
                                       float(wind) if str(wind).replace('.','').isdigit() else 0,
                                       int(humidity) if str(humidity).isdigit() else 50)
            if tips:
                weather_display += f"  {tips}"

            self.weather_text.value = weather_display
            self.weather_text.update()

            # 下班前检查（17:30-18:00），弹提醒
            self._weather_data = {"desc_en": desc_en, "temp": temp, "wind": wind, "tips": tips}
        except:
            self.weather_text.value = "☁ 天气解析失败"
            self.weather_text.update()

    def _om_weather_code(self, code: int) -> str:
        """Open-Meteo weather code 映射"""
        mapping = {
            0: "Clear", 1: "Partly cloudy", 2: "Partly cloudy", 3: "Cloudy",
            45: "Fog", 48: "Fog",
            51: "Light drizzle", 53: "Light drizzle", 55: "Light drizzle",
            61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
            71: "Light snow", 73: "Light snow", 75: "Snow",
            80: "Light rain shower", 81: "Moderate rain", 82: "Heavy rain",
            95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
        }
        return mapping.get(code, "Cloudy")

    def _weather_tips(self, desc_en: str, temp: float, wind: float, humidity: int) -> str:
        """根据天气生成提示"""
        tips = []
        rain_keywords = ["rain", "drizzle", "shower", "thunderstorm", "mist", "fog"]
        if any(k in desc_en.lower() for k in rain_keywords):
            tips.append("🌂带伞")
        if temp > 35:
            tips.append("☀防晒带伞")
        elif temp > 30:
            tips.append("☀注意防晒")
        if wind > 25:
            tips.append("🧥风大添衣")
        elif wind > 15:
            tips.append("💨有风")
        if temp < 15:
            tips.append("🧣天冷加衣")
        elif temp < 10:
            tips.append("🧤注意保暖")
        if humidity > 85:
            tips.append("💦潮湿")
        return " ".join(tips)

    def _start_weather_check_reminder(self):
        """下班前（17:30）根据天气弹提醒"""
        import time as _time
        def _run():
            today_checked = ""
            while True:
                now = datetime.now()
                cur_date = date.today().isoformat()
                if cur_date != today_checked:
                    today_checked = cur_date
                h, m = now.hour, now.minute
                # 17:30 下班提醒
                if h == 17 and m == 30 and cur_date == today_checked and hasattr(self, '_weather_data') and self._weather_data:
                    wd = self._weather_data
                    tips = wd.get("tips", "")
                    if tips:
                        msg = f"下班啦！{tips}"
                        self._toast("哈基米曼波 天气提醒", msg)
                        self.page.show_snack_bar(ft.SnackBar(
                            ft.Text(f"🌤 {msg}", size=13), bgcolor=ORANGE, duration=8000))
                    today_checked = ""  # 避免重复
                _time.sleep(55)
        threading.Thread(target=_run, daemon=True).start()

    def _load_weather(self):
        threading.Thread(target=self._fetch_weather, daemon=True).start()
        self._start_weather_check_reminder()

    # ==================== 8杯水喝水提醒 ====================

    def _start_water_reminder(self):
        """启动喝水提醒后台线程，科学喝水时间：8:00, 9:00, 11:00, 13:00, 15:00, 17:00, 19:00, 21:00，AI生成个性化消息"""
        import time as _time
        def _run():
            tips = [
                "🌅 第1杯水 (8:00) 起床一杯，唤醒身体",
                "☀ 第2杯水 (9:00) 开始工作，补充水分",
                "🕚 第3杯水 (11:00) 午饭前，促进消化",
                "🍽 第4杯水 (13:00) 午饭后，帮助代谢",
                "😴 第5杯水 (15:00) 下午提神，缓解疲劳",
                "⏰ 第6杯水 (17:00) 下班前，保持活力",
                "🌙 第7杯水 (19:00) 晚饭后，助消化",
                "🛌 第8杯水 (21:00) 睡前两小时，避免水肿",
            ]
            alerted = set()
            today = date.today().isoformat()
            while True:
                now = datetime.now()
                if date.today().isoformat() != today:
                    today = date.today().isoformat()
                    alerted.clear()
                cfg = load_user_config()
                if cfg and cfg.water_enabled:
                    h, m = now.hour, now.minute
                    targets = [(8,0),(9,0),(11,0),(13,0),(15,0),(17,0),(19,0),(21,0)]
                    for i, (th, tm) in enumerate(targets):
                        if h == th and m == tm and i not in alerted:
                            alerted.add(i)
                            msg = tips[i]
                            self._toast("哈基米曼波 喝水提醒", f"💧 {msg}")
                            self.page.show_snack_bar(ft.SnackBar(
                                ft.Text(f"🐱 {msg}", size=13), bgcolor=BLUE, duration=5000))
                            break
                _time.sleep(55)
        threading.Thread(target=_run, daemon=True).start()

    # ==================== 护眼提醒 ====================

    def _start_eye_reminder(self):
        """每2小时提醒休息3分钟，带倒计时弹窗"""
        import time as _time
        def _run():
            today = date.today().isoformat()
            last_remind_hour = -1
            while True:
                now = datetime.now()
                cur_date = date.today().isoformat()
                if cur_date != today:
                    today = cur_date
                    last_remind_hour = -1
                cfg = load_user_config()
                if cfg and cfg.eye_enabled and now.weekday() < 5:
                    h = now.hour
                    # 9:00-18:00 每2小时提醒：9, 11, 13, 15, 17
                    remind_hours = [9, 11, 13, 15, 17]
                    if h in remind_hours and now.minute == 0 and h != last_remind_hour:
                        last_remind_hour = h
                        self._toast("哈基米曼波 护眼提醒",
                                    "\U0001f441 该让眼睛休息一下了！请休息3分钟~")
                        self.page.show_snack_bar(ft.SnackBar(
                            ft.Text("\U0001f441 护眼时间到！休息3分钟吧~", size=13),
                            bgcolor=GREEN, duration=8000))
                        # 3分钟倒计时弹窗
                        self._show_eye_rest_dialog()
                _time.sleep(55)
        threading.Thread(target=_run, daemon=True).start()

    def _show_eye_rest_dialog(self):
        """显示3分钟倒计时弹窗"""
        countdown = ft.Text("03:00", size=48, weight=ft.FontWeight.BOLD, color=BLUE, text_align=ft.TextAlign.CENTER)
        tip = ft.Text("闭上眼睛，放松一下 👁", size=14, color=TEXT_SEC, text_align=ft.TextAlign.CENTER)

        def _countdown():
            import time as _time
            for sec in range(180, -1, -1):
                m, s = divmod(sec, 60)
                countdown.value = f"{m:02d}:{s:02d}"
                countdown.update()
                _time.sleep(1)
            # 倒计时结束
            tip.value = "✅ 休息完成！眼睛舒服多了~"
            tip.update()
            # 记录休息分钟数
            cfg = load_user_config()
            if cfg:
                t = date.today().isoformat()
                if cfg.eye_date != t:
                    cfg.eye_rest_minutes = 0
                    cfg.eye_date = t
                cfg.eye_rest_minutes += 3
                save_user_config(cfg)

        dlg = ft.AlertDialog(
            title=ft.Text("护眼休息", size=18, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
            content=ft.Column([countdown, ft.Container(height=12), tip],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER, width=280),
            actions=[ft.FilledButton("完成休息", icon=ft.icons.CHECK, on_click=lambda e: self._close_dlg2(dlg))],
        )
        self.page.dialog = dlg; dlg.open = True; self.page.update()
        threading.Thread(target=_countdown, daemon=True).start()

    def _close_dlg2(self, dlg):
        dlg.open = False; self.page.update()

    # ==================== 下班倒计时 + 语录刷新 ====================

    def _start_countdown_loop(self):
        """顶部栏下班倒计时"""
        import time as _time
        def _run():
            while True:
                try:
                    now = datetime.now()
                    if now.weekday() >= 5:
                        self.countdown_top_text.value = "🎉 周末快乐!"
                        self.countdown_top_text.color = GREEN
                    else:
                        off = now.replace(hour=18, minute=0, second=0, microsecond=0)
                        if now >= off:
                            self.countdown_top_text.value = "已下班 🏃"
                            self.countdown_top_text.color = GREEN
                        else:
                            remaining = off - now
                            h = remaining.seconds // 3600
                            m = (remaining.seconds % 3600) // 60
                            s = remaining.seconds % 60
                            self.countdown_top_text.value = f"⏰ {h:02d}:{m:02d}:{s:02d}"
                            self.countdown_top_text.color = ORANGE if remaining.seconds < 3600 else BLUE
                    self.countdown_top_text.update()
                except:
                    pass
                _time.sleep(1)
        threading.Thread(target=_run, daemon=True).start()

    def _start_quote_refresh(self):
        """每30秒刷新摸鱼语录到标题栏"""
        import time as _time
        def _run():
            while True:
                _time.sleep(30)
                try:
                    q = get_random_quote()
                    self.page.title = "哈基米曼波 - " + q
                    if hasattr(self, 'quote_top_text'):
                        self.quote_top_text.value = q
                        self.quote_top_text.update()
                    self.page.update()
                except:
                    pass
        threading.Thread(target=_run, daemon=True).start()












def main():
    ft.app(target=OvertimeApp().main)

if __name__ == "__main__":
    main()
