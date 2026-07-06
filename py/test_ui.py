# -*- coding: utf-8 -*-
import math
from datetime import date, timedelta
import flet as ft
from attendance import get_company_month_range, get_company_month_label
from calendar_2026 import get_day_type, get_day_type_label


def main(page: ft.Page):
    page.title = "Calendar Test"
    page.window.width = 800
    page.window.height = 600

    current_date = date.today()
    start, end = get_company_month_range(current_date)

    print(f"Company month: {start} ~ {end}")
    print(f"Total days: {(end - start).days + 1}")

    today = date.today()
    first_weekday = start.weekday()
    offset = (first_weekday + 1) % 7
    total_days = (end - start).days + 1
    total_cells = offset + total_days
    rows = math.ceil(total_cells / 7)

    print(f"Offset: {offset}, Rows: {rows}")

    # Weekday header
    week_header = ft.Row(spacing=2)
    for i, w in enumerate(["日", "一", "二", "三", "四", "五", "六"]):
        week_header.controls.append(ft.Text(w, size=12, width=52, text_align=ft.TextAlign.CENTER))

    page.add(
        ft.Text(f"公司月: {get_company_month_label(current_date)}", size=18),
        week_header,
    )

    for row in range(rows):
        row_ctrl = ft.Row(spacing=2)
        for col in range(7):
            i = row * 7 + col
            if i < offset or (i - offset) >= total_days:
                row_ctrl.controls.append(ft.Container(width=52, height=40))
                continue
            d = start + timedelta(days=i - offset)
            day_type = get_day_type(d)
            bg = "#ffffff"
            if day_type == "holiday": bg = "#ffcccc"
            elif day_type == "makeup": bg = "#ffffcc"
            elif day_type == "weekend": bg = "#cceeff"
            cell = ft.Container(
                content=ft.Text(str(d.day), size=14),
                width=52, height=40,
                bgcolor=bg,
                border=ft.border.all(1, "#cccccc"),
                border_radius=4,
                alignment=ft.alignment.center,
            )
            row_ctrl.controls.append(cell)
        page.add(row_ctrl)

    page.update()
    print("UI rendered")

ft.app(target=main)
