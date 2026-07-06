# -*- coding: utf-8 -*-
"""注册/登录页面"""
import os
import flet as ft
from user_auth import register, login, is_registered, load_user_config, quick_login

BLUE = "#3370FF"
RED = "#F54A45"
GREEN = "#34C759"
TEXT = "#1F2329"
TEXT_SEC = "#646A73"
BG = "#F5F6F7"
WHITE = "#FFFFFF"
BLUE_LIGHT = "#E8F0FE"
CONFIG_DIR = os.path.dirname(__file__)


def show_login_page(page: ft.Page, on_success):
    """显示登录/注册页面，成功后回调 on_success(user_config)"""

    registered = is_registered()
    saved_config = load_user_config()

    # ==================== 注册页 ====================
    empno_field = ft.TextField(label="工号（M开头）", hint_text="如 M03141", width=300, text_size=14)
    name_field = ft.TextField(label="姓名", hint_text="如 吴钦腾", width=300, text_size=14)
    plate_field = ft.TextField(label="车牌", hint_text="如 粤S0Q780", width=300, text_size=14)
    salary_field = ft.TextField(label="加班工资基数（时薪）", hint_text="如 20.5", width=300, text_size=14, value="20.5")
    pwd_field = ft.TextField(label="密码", password=True, can_reveal_password=True, width=300, text_size=14)
    pwd2_field = ft.TextField(label="确认密码", password=True, can_reveal_password=True, width=300, text_size=14)
    error_text = ft.Text("", color=RED, size=12)

    def do_register(e):
        empno = empno_field.value.strip()
        name = name_field.value.strip()
        plate = plate_field.value.strip()
        pwd = pwd_field.value
        pwd2 = pwd2_field.value
        try:
            base = float(salary_field.value.strip())
        except ValueError:
            error_text.value = "工资基数请输入数字"; page.update(); return

        if not empno or not name or not plate or not pwd:
            error_text.value = "请填写所有字段"; page.update(); return
        if not empno.startswith("M") and not empno.startswith("m"):
            error_text.value = "工号必须以 M 开头"; page.update(); return
        if pwd != pwd2:
            error_text.value = "两次密码不一致"; page.update(); return

        try:
            config = register(empno, name, plate, base, pwd)
            page.show_snack_bar(ft.SnackBar(ft.Text("注册成功！"), bgcolor=GREEN))
            on_success(config)
        except Exception as ex:
            error_text.value = f"注册失败: {ex}"; page.update()

    register_view = ft.Column([
        ft.Container(height=40),
        ft.Text("🐱 哈基米曼波", size=28, weight=ft.FontWeight.BOLD, color=BLUE),
        ft.Text("首次使用，请注册", size=14, color=TEXT_SEC),
        ft.Container(height=24),
        empno_field, name_field, plate_field, salary_field, pwd_field, pwd2_field,
        error_text,
        ft.Container(height=8),
        ft.FilledButton("注 册", width=300, style=ft.ButtonStyle(bgcolor=BLUE, shape=ft.RoundedRectangleBorder(radius=8)),
                        on_click=do_register),
    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    # ==================== 一键登录页（已注册过的用户） ====================
    avatar_src = saved_config.avatar_path if saved_config else "cat_icon.png"
    if avatar_src and not os.path.isabs(avatar_src):
        avatar_src = os.path.abspath(os.path.join(CONFIG_DIR, avatar_src))
    if not os.path.exists(avatar_src):
        avatar_src = "cat_icon.png"

    name_display = saved_config.empname if saved_config else ""
    empno_display = saved_config.empno if saved_config else ""

    quick_login_error = ft.Text("", color=RED, size=12)
    # 密码输入（默认隐藏，点击登录才显示）
    quick_pwd = ft.TextField(label="密码", password=True, can_reveal_password=True, width=260, text_size=14, visible=False)
    pwd_row = ft.Row([quick_pwd], alignment=ft.MainAxisAlignment.CENTER, visible=False)

    def do_quick_login(e):
        # 先尝试一键登录
        config = quick_login()
        if config:
            on_success(config)
            return
        quick_login_error.value = "设备不匹配，请重新注册"; page.update()

    def show_pwd_login(e):
        """显示密码输入框"""
        pwd_row.visible = True
        pwd_btn_row.visible = False
        quick_pwd.focus()
        page.update()

    def do_pwd_login(e):
        pwd = quick_pwd.value
        if not pwd:
            quick_login_error.value = "请输入密码"; page.update(); return
        config = login(saved_config.empno, pwd)
        if config:
            on_success(config)
        else:
            quick_login_error.value = "密码错误"; page.update()

    # 头像
    avatar_img = ft.Image(src=avatar_src, width=80, height=80, fit=ft.ImageFit.COVER)
    avatar = ft.Container(avatar_img, width=80, height=80, border_radius=40,
                          clip_behavior=ft.ClipBehavior.ANTI_ALIAS, bgcolor=BLUE_LIGHT)

    # 一键登录按钮行
    pwd_btn_row = ft.Row([
        ft.FilledButton("一键登录", icon=ft.icons.LOGIN, width=260,
                        style=ft.ButtonStyle(bgcolor=BLUE, shape=ft.RoundedRectangleBorder(radius=8)),
                        on_click=do_quick_login),
    ], alignment=ft.MainAxisAlignment.CENTER)

    # 密码登录按钮行（显示密码框后）
    pwd_login_row = ft.Row([
        ft.FilledButton("密码登录", icon=ft.icons.LOCK_OPEN, width=260,
                        style=ft.ButtonStyle(bgcolor=BLUE, shape=ft.RoundedRectangleBorder(radius=8)),
                        on_click=do_pwd_login),
    ], alignment=ft.MainAxisAlignment.CENTER, visible=False)

    quick_login_view = ft.Column([
        ft.Container(height=40),
        ft.Text("🐱 哈基米曼波", size=28, weight=ft.FontWeight.BOLD, color=BLUE),
        ft.Container(height=16),
        avatar,
        ft.Container(height=8),
        ft.Text(name_display, size=22, weight=ft.FontWeight.BOLD, color=TEXT),
        ft.Text(f"工号: {empno_display}", size=13, color=TEXT_SEC),
        ft.Container(height=24),
        pwd_row,
        ft.Container(height=8),
        pwd_btn_row,
        pwd_login_row,
        ft.Container(height=4),
        quick_login_error,
        ft.Container(height=16),
        ft.TextButton("不是本人？重新注册", on_click=lambda e: switch_to_register()),
    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    # ==================== 密码登录页（备用） ====================
    login_empno = ft.TextField(label="工号", width=300, text_size=14,
                                value=saved_config.empno if saved_config else "")
    login_pwd = ft.TextField(label="密码", password=True, can_reveal_password=True, width=300, text_size=14)
    login_error = ft.Text("", color=RED, size=12)

    def do_login(e):
        empno = login_empno.value.strip()
        pwd = login_pwd.value
        if not empno or not pwd:
            login_error.value = "请输入工号和密码"; page.update(); return
        config = login(empno, pwd)
        if config:
            on_success(config)
        else:
            login_error.value = "工号或密码错误"; page.update()

    login_view = ft.Column([
        ft.Container(height=40),
        ft.Text("🐱 哈基米曼波", size=28, weight=ft.FontWeight.BOLD, color=BLUE),
        ft.Text("密码登录", size=14, color=TEXT_SEC),
        ft.Container(height=24),
        login_empno, login_pwd,
        login_error,
        ft.Container(height=8),
        ft.FilledButton("登 录", width=300, style=ft.ButtonStyle(bgcolor=BLUE, shape=ft.RoundedRectangleBorder(radius=8)),
                        on_click=do_login),
        ft.Container(height=16),
        ft.TextButton("还没有账号？注册一个", on_click=lambda e: switch_to_register()),
    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def switch_to_register():
        page.clean()
        page.add(ft.Container(register_view, alignment=ft.alignment.center, expand=True))
        page.update()

    def switch_to_login():
        page.clean()
        page.add(ft.Container(login_view, alignment=ft.alignment.center, expand=True))
        page.update()

    # 显示
    page.clean()
    if registered:
        page.add(ft.Container(quick_login_view, alignment=ft.alignment.center, expand=True))
    else:
        page.add(ft.Container(register_view, alignment=ft.alignment.center, expand=True))
    page.update()
