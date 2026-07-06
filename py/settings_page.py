# -*- coding: utf-8 -*-
"""设置页面 - 个人信息配置、头像更换、喝水提醒开关、喝水记录"""
import os
import json
import shutil
import flet as ft
from datetime import date
from user_auth import load_user_config, save_user_config

BLUE = "#3370FF"; BLUE_LIGHT = "#E8F0FE"
RED = "#F54A45"; GREEN = "#34C759"; ORANGE = "#FF9500"
TEXT = "#1F2329"; TEXT_SEC = "#646A73"; TEXT_THIRD = "#8F959E"
BORDER = "#E5E6EB"; BG = "#F2F3F5"; WHITE = "#FFFFFF"

CONFIG_DIR = os.path.dirname(__file__)
AVATAR_DIR = os.path.join(CONFIG_DIR, "avatars")

def ensure_avatar_dir():
    os.makedirs(AVATAR_DIR, exist_ok=True)

def get_avatar_src(config):
    """获取头像路径"""
    if config and config.avatar_path:
        path = config.avatar_path
        if os.path.exists(path):
            return path
        full = os.path.join(CONFIG_DIR, path)
        if os.path.exists(full):
            return full
    return "cat_icon.png"

def _load_ai_config():
    path = os.path.join(CONFIG_DIR, "ai_config.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def _build_ai_section():
    ai_cfg = _load_ai_config()
    ai_key = ft.TextField(label="DeepSeek API Key", value=ai_cfg.get("api_key", ""),
                           password=True, can_reveal_password=True, text_size=13, width=320)
    ai_model = ft.Dropdown(
        options=[ft.dropdown.Option("deepseek-v4-pro", "DeepSeek-V4 Pro"),
                 ft.dropdown.Option("deepseek-v4-flash", "DeepSeek-V4 Flash"),
                 ft.dropdown.Option("deepseek-chat", "DeepSeek-V3"),
                 ft.dropdown.Option("deepseek-reasoner", "DeepSeek-R1")],
        value=ai_cfg.get("model", "deepseek-v4-flash"), width=180, dense=True, text_size=13)
    ai_msg = ft.Text("", size=12, color=GREEN)

    def save(e):
        ai_cfg["api_key"] = ai_key.value.strip()
        ai_cfg["model"] = ai_model.value
        path = os.path.join(CONFIG_DIR, "ai_config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ai_cfg, f, ensure_ascii=False, indent=2)
        ai_msg.value = "AI 配置已保存 ✓"
        ai_msg.update()

    return ft.Container(ft.Column([
        ft.Text("🤖 AI 助手配置", size=15, weight=ft.FontWeight.BOLD, color=TEXT),
        ft.Container(height=8),
        ai_key,
        ft.Container(height=4),
        ft.Row([ft.Text("模型:", size=13, color=TEXT_SEC, width=50), ai_model], spacing=8),
        ft.Container(height=8),
        ft.Row([ft.FilledButton("保存配置", icon=ft.icons.SAVE, on_click=save), ai_msg], spacing=12),
    ], spacing=2), padding=16, bgcolor=WHITE, border_radius=12, border=ft.border.all(1, BORDER))


def show_settings_page(page: ft.Page, on_back, user_config, water_callback=None):
    """显示设置页面"""
    cfg = user_config
    ensure_avatar_dir()

    avatar_src = get_avatar_src(cfg)
    if avatar_src and not os.path.isabs(avatar_src):
        avatar_src = os.path.abspath(os.path.join(CONFIG_DIR, avatar_src))
    avatar_img = ft.Image(src=avatar_src, width=100, height=100, fit=ft.ImageFit.COVER)
    avatar = ft.Container(avatar_img, width=100, height=100, border_radius=50,
                          clip_behavior=ft.ClipBehavior.ANTI_ALIAS, bgcolor=BLUE_LIGHT)
    avatar_container = ft.Container(avatar, on_click=lambda e: _pick_avatar(page, cfg, avatar_img),
                                     ink=True, border_radius=50, tooltip="点击更换头像")
    # 文件选择器
    file_picker = ft.FilePicker(on_result=lambda e: _on_avatar_picked(e, cfg, avatar_img, page))
    page.overlay.append(file_picker)

    # 基本信息
    name_text = ft.Text(cfg.empname, size=24, weight=ft.FontWeight.BOLD, color=TEXT)
    empno_text = ft.Text(f"工号: {cfg.empno}", size=13, color=TEXT_SEC)
    plate_text = ft.Text(f"车牌: {cfg.car_plate}", size=13, color=TEXT_SEC)

    # 时薪设置
    salary_field = ft.TextField(label="加班时薪基数", value=str(cfg.base_salary),
                                text_size=14, width=200, prefix_text="¥")
    salary_save_btn = ft.FilledButton("保存", icon=ft.icons.SAVE, on_click=lambda e: _save_salary(
        salary_field, cfg, page))

    # 费率显示
    def _rate_text():
        wd = cfg.weekday_rate; we = cfg.weekend_rate; mk = cfg.makeup_rate
        return f"平日 ¥{wd:.2f}/h  |  休息日 ¥{we:.2f}/h  |  补班日 ¥{mk:.2f}/h"
    rate_text = ft.Text(_rate_text(), size=12, color=TEXT_SEC)

    # 8杯水开关
    water_sw = ft.Switch(value=cfg.water_enabled, label="开启科学喝水提醒",
                         active_color=BLUE, on_change=lambda e: _toggle_water(e, cfg))
    water_desc = ft.Text("每天 8:00-21:00 科学喝水时间表提醒", size=11, color=TEXT_THIRD)

    # 每杯毫升数
    ml_field = ft.TextField(value=str(cfg.water_ml), label="每杯(ml)", text_size=13, width=100,
                            text_align=ft.TextAlign.CENTER)
    ml_save_btn = ft.IconButton(ft.icons.SAVE, icon_size=18, tooltip="保存杯量",
                                on_click=lambda e: _save_water_ml(ml_field, cfg, page))

    # 护眼设置
    eye_sw = ft.Switch(value=cfg.eye_enabled, label="开启护眼提醒",
                      active_color=BLUE, on_change=lambda e: _toggle_eye(e, cfg))
    eye_desc = ft.Text("每2小时提醒休息3分钟，放松眼睛", size=11, color=TEXT_THIRD)
    eye_today = date.today().isoformat()
    eye_is_today = (cfg.eye_date == eye_today)
    eye_minutes = cfg.eye_rest_minutes if eye_is_today else 0
    eye_label = ft.Text(f"👁 今日已休息 {eye_minutes} 分钟", size=14, weight=ft.FontWeight.W_500, color=TEXT)
    eye_tip = ft.Text(
        "💡 每2小时提醒一次，到点弹出3分钟倒计时" if eye_minutes < 15 else "👍 今日护眼目标达成！",
        size=11, color=TEXT_THIRD)

    # 密码修改
    old_pwd = ft.TextField(label="旧密码", password=True, can_reveal_password=True, text_size=13, width=200)
    new_pwd = ft.TextField(label="新密码", password=True, can_reveal_password=True, text_size=13, width=200)
    new_pwd2 = ft.TextField(label="确认新密码", password=True, can_reveal_password=True, text_size=13, width=200)
    pwd_msg = ft.Text("", size=12, color=RED)

    def _change_pwd(e):
        import hashlib
        if hashlib.sha256(old_pwd.value.encode()).hexdigest() != cfg.password_hash:
            pwd_msg.value = "旧密码错误"; pwd_msg.update(); return
        if new_pwd.value != new_pwd2.value:
            pwd_msg.value = "两次密码不一致"; pwd_msg.update(); return
        if len(new_pwd.value) < 4:
            pwd_msg.value = "密码至少4位"; pwd_msg.update(); return
        cfg.password_hash = hashlib.sha256(new_pwd.value.encode()).hexdigest()
        save_user_config(cfg)
        pwd_msg.value = "密码已修改"; pwd_msg.color = GREEN; pwd_msg.update()
        old_pwd.value = new_pwd.value = new_pwd2.value = ""
        page.show_snack_bar(ft.SnackBar(ft.Text("密码已修改"), bgcolor=GREEN))

    # 布局
    content = ft.Column([
        ft.Container(height=16),
        # 返回按钮
        ft.Row([ft.IconButton(ft.icons.ARROW_BACK, icon_size=28, on_click=lambda e: on_back(),
                              tooltip="返回主页")]),
        ft.Divider(height=1, color=BORDER),

        # 头像 + 基本信息
        ft.Row([
            avatar_container,
            ft.Container(width=20),
            ft.Column([name_text, empno_text, plate_text, ft.Container(height=4),
                       ft.Text("点击头像更换图片", size=11, color=TEXT_THIRD)], spacing=2),
        ], spacing=0),

        ft.Divider(height=16, color=ft.colors.TRANSPARENT),

        # 时薪 + 费率
        ft.Container(ft.Column([
            ft.Text("加班工资设置", size=15, weight=ft.FontWeight.BOLD, color=TEXT),
            ft.Container(height=8),
            ft.Row([salary_field, salary_save_btn], spacing=12),
            ft.Container(height=4),
            rate_text,
        ], spacing=2), padding=16, bgcolor=WHITE, border_radius=12, border=ft.border.all(1, BORDER)),

        ft.Divider(height=12, color=ft.colors.TRANSPARENT),

        # 喝水设置
        ft.Container(ft.Column([
            ft.Text("科学喝水提醒", size=15, weight=ft.FontWeight.BOLD, color=TEXT),
            ft.Row([water_sw, water_desc]),
            ft.Container(height=8),
            ft.Row([ft.Text("每杯水量:", size=13, color=TEXT_SEC), ml_field, ml_save_btn], spacing=8),
        ], spacing=2), padding=16, bgcolor=WHITE, border_radius=12, border=ft.border.all(1, BORDER)),

        ft.Divider(height=12, color=ft.colors.TRANSPARENT),

        # 护眼设置
        ft.Container(ft.Column([
            ft.Text("护眼提醒", size=15, weight=ft.FontWeight.BOLD, color=TEXT),
            ft.Row([eye_sw, eye_desc]),
            ft.Divider(height=8),
            eye_label,
            ft.Container(height=4),
            eye_tip,
        ], spacing=2), padding=16, bgcolor=WHITE, border_radius=12, border=ft.border.all(1, BORDER)),

        ft.Divider(height=12, color=ft.colors.TRANSPARENT),

        # AI 配置
        _build_ai_section(),
        ft.Divider(height=12, color=ft.colors.TRANSPARENT),

        # 密码修改
        ft.Container(ft.Column([
            ft.Text("修改密码", size=15, weight=ft.FontWeight.BOLD, color=TEXT),
            ft.Container(height=8),
            old_pwd, new_pwd, new_pwd2,
            ft.Row([ft.FilledButton("修改密码", icon=ft.icons.LOCK, on_click=_change_pwd), pwd_msg], spacing=12),
        ], spacing=4), padding=16, bgcolor=WHITE, border_radius=12, border=ft.border.all(1, BORDER)),

        ft.Divider(height=12, color=ft.colors.TRANSPARENT),

        # 退出账户
        ft.Container(ft.Column([
            ft.Text("账户管理", size=15, weight=ft.FontWeight.BOLD, color=TEXT),
            ft.Container(height=8),
            ft.Row([ft.OutlinedButton("退出账户", icon=ft.icons.LOGOUT, on_click=lambda e: _logout(cfg, page))]),
        ], spacing=4), padding=16, bgcolor=WHITE, border_radius=12, border=ft.border.all(1, BORDER)),

    ], scroll=ft.ScrollMode.AUTO, expand=True)

    return ft.Container(content, padding=ft.Padding(left=40, top=0, right=40, bottom=0), expand=True, bgcolor=BG)

def _pick_avatar(page, cfg, avatar_ctrl):
    """打开文件选择器"""
    for ctrl in page.overlay:
        if isinstance(ctrl, ft.FilePicker):
            ctrl.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.IMAGE)
            return

def _on_avatar_picked(e: ft.FilePickerResultEvent, cfg, avatar_img, page):
    """头像选择回调"""
    if not e.files: return
    src = e.files[0].path
    ensure_avatar_dir()
    ext = os.path.splitext(src)[1] or ".png"
    dst = os.path.join(AVATAR_DIR, f"avatar_{cfg.empno}{ext}")
    try:
        shutil.copy2(src, dst)
        cfg.avatar_path = dst
        save_user_config(cfg)
        avatar_img.src = os.path.abspath(dst)
        avatar_img.update()
        page.show_snack_bar(ft.SnackBar(ft.Text("头像已更新"), bgcolor=GREEN))
    except Exception as ex:
        page.show_snack_bar(ft.SnackBar(ft.Text(f"保存失败: {ex}"), bgcolor=RED))

def _save_salary(field, cfg, page):
    """保存时薪"""
    try:
        val = float(field.value.strip())
        if val <= 0:
            page.show_snack_bar(ft.SnackBar(ft.Text("请输入正数"), bgcolor=RED)); return
        cfg.base_salary = val
        save_user_config(cfg)
        page.show_snack_bar(ft.SnackBar(ft.Text("时薪已保存"), bgcolor=GREEN))
        # 重建页面以刷新费率
        page.clean()
        from main_flet import OvertimeApp
        app = OvertimeApp(); app.user_config = cfg
        app.main(page)
    except ValueError:
        page.show_snack_bar(ft.SnackBar(ft.Text("请输入有效数字"), bgcolor=RED))

def _toggle_water(e, cfg):
    """切换喝水提醒"""
    cfg.water_enabled = e.control.value
    save_user_config(cfg)

def _toggle_eye(e, cfg):
    """切换护眼提醒"""
    cfg.eye_enabled = e.control.value
    save_user_config(cfg)

def _save_water_ml(field, cfg, page):
    """保存每杯毫升数"""
    try:
        val = int(field.value.strip())
        if val <= 0 or val > 2000:
            page.show_snack_bar(ft.SnackBar(ft.Text("请输入 1~2000"), bgcolor=RED)); return
        cfg.water_ml = val
        save_user_config(cfg)
        page.show_snack_bar(ft.SnackBar(ft.Text(f"每杯 {val}ml 已保存"), bgcolor=GREEN))
    except ValueError:
        page.show_snack_bar(ft.SnackBar(ft.Text("请输入整数"), bgcolor=RED))

def _logout(cfg, page):
    """退出账户，回到登录页（保留配置信息）"""
    def confirm(e):
        page.close(dlg)
        from user_auth import logout
        logout()
        from login_page import show_login_page
        page.clean()
        show_login_page(page, lambda config: _on_relogin(page, config))

    def cancel(e):
        page.close(dlg)

    dlg = ft.AlertDialog(
        title=ft.Text("退出账户", size=16, weight=ft.FontWeight.BOLD),
        content=ft.Text("退出后点击头像即可一键登录，确定要退出吗？", size=13, color=TEXT_SEC),
        actions=[
            ft.TextButton("取消", on_click=cancel),
            ft.FilledButton("确定退出", on_click=confirm, style=ft.ButtonStyle(bgcolor=RED)),
        ],
    )
    page.open(dlg)

def _on_relogin(page, config):
    """重新登录后重建主页"""
    from main_flet import OvertimeApp
    app = OvertimeApp()
    app.user_config = config
    app.main(page)
