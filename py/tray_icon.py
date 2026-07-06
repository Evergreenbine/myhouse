# -*- coding: utf-8 -*-
"""系统托盘 — 最小化到托盘，右键恢复/退出"""
import threading
import os
from PIL import Image

TRAY_ICON_PATH = os.path.join(os.path.dirname(__file__), "cat_icon.png")


def start_tray(page, app_ref):
    """启动系统托盘"""
    import flet as ft

    try:
        import pystray
    except ImportError:
        try:
            page.show_snack_bar(ft.SnackBar(
                ft.Text("需要安装 pystray: pip install pystray pillow"), bgcolor="#FF9500"))
        except:
            pass
        return None

    try:
        img = Image.open(TRAY_ICON_PATH)
    except:
        img = Image.new("RGBA", (64, 64), (255, 165, 0, 255))

    def on_restore(icon, item):
        page.window.skip_task_bar = False
        page.window.visible = True
        page.window.focused = True
        page.window.maximized = False
        page.update()

    def on_quit(icon, item):
        icon.stop()
        page.window.destroy()

    menu = pystray.Menu(
        pystray.MenuItem("恢复窗口", on_restore, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", on_quit),
    )

    icon = pystray.Icon("哈基米曼波", img, "哈基米曼波", menu)

    def run_tray():
        icon.run()

    threading.Thread(target=run_tray, daemon=True).start()
    app_ref._tray_icon = icon

    return icon


def show_pet(app_ref):
    pass


def hide_pet(app_ref):
    pass
