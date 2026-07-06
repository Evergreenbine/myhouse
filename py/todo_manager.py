# -*- coding: utf-8 -*-
"""
待办事项管理 - JSON 文件存储 + Windows 原生桌面提醒
"""
import json
import os
import subprocess
import threading
import time
from datetime import date, datetime, timedelta
from dataclasses import dataclass, asdict, field


def _win_notify(title, message):
    """Windows 原生通知（PowerShell方式，兼容 Win10/Win11）"""
    try:
        ps_script = f'''
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $textNodes = $template.GetElementsByTagName("text")
        $textNodes.Item(0).AppendChild($template.CreateTextNode("{title}")) > $null
        $textNodes.Item(1).AppendChild($template.CreateTextNode("{message}")) > $null
        $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("哈基米曼波").Show($toast)
        '''
        subprocess.run(["powershell", "-Command", ps_script], capture_output=True, timeout=5)
    except Exception:
        pass
from typing import List, Dict

DATA_FILE = os.path.join(os.path.dirname(__file__), "todos.json")


@dataclass
class TodoItem:
    date: str           # "2026-06-15"
    time: str           # "09:00" 提醒时间
    content: str        # 待办内容
    done: bool = False
    reminded: bool = False  # 是否已提醒过
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"{self.date}_{self.time}_{hash(self.content)}"


class TodoManager:
    def __init__(self):
        self._items: Dict[str, List[TodoItem]] = {}  # date -> [items]
        self._load()
        self._running = True
        self._on_remind = None  # 提醒回调
        self._start_reminder()

    def set_remind_callback(self, callback):
        """设置提醒回调函数 callback(title, message)"""
        self._on_remind = callback

    def _load(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for date_str, items in data.items():
                    self._items[date_str] = [TodoItem(**i) for i in items]
            except Exception:
                self._items = {}

    def _save(self):
        data = {k: [asdict(v) for v in items] for k, items in self._items.items()}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_items(self, date_str: str) -> List[TodoItem]:
        return sorted(self._items.get(date_str, []), key=lambda x: x.time)

    def get_all_items(self) -> List[TodoItem]:
        """获取所有待办事项（跨日期）"""
        result = []
        for items in self._items.values():
            result.extend(items)
        return sorted(result, key=lambda x: (x.date, x.time))

    def get_all_dates(self) -> List[str]:
        """获取所有有待办的日期"""
        return list(self._items.keys())

    def add_item(self, date_str: str, time_str: str, content: str):
        item = TodoItem(date=date_str, time=time_str, content=content)
        if date_str not in self._items:
            self._items[date_str] = []
        self._items[date_str].append(item)
        self._save()

    def remove_item(self, date_str: str, item_id: str):
        if date_str in self._items:
            self._items[date_str] = [i for i in self._items[date_str] if i.id != item_id]
            if not self._items[date_str]:
                del self._items[date_str]
            self._save()

    def toggle_done(self, date_str: str, item_id: str):
        if date_str in self._items:
            for i in self._items[date_str]:
                if i.id == item_id:
                    i.done = not i.done
                    break
            self._save()

    def get_upcoming(self) -> List[TodoItem]:
        """获取今天和未来未完成的待办"""
        today = date.today().isoformat()
        result = []
        for ds, items in self._items.items():
            if ds >= today:
                for i in items:
                    if not i.done:
                        result.append(i)
        return sorted(result, key=lambda x: (x.date, x.time))

    def get_today_items(self) -> List[TodoItem]:
        return self.get_items(date.today().isoformat())

    def _start_reminder(self):
        """后台线程定时检查提醒"""
        def _check():
            while self._running:
                now = datetime.now()
                today_str = now.strftime("%Y-%m-%d")
                current_time = now.strftime("%H:%M")

                items = self._items.get(today_str, [])
                for item in items:
                    if not item.done and not item.reminded and item.time == current_time:
                        item.reminded = True
                        self._save()
                        _win_notify("哈基米曼波 提醒", item.content)
                        if self._on_remind:
                            self._on_remind("哈基米曼波 提醒", f"\u23F0 {item.time}\n{item.content}")

                time.sleep(30)  # 每30秒检查一次

        t = threading.Thread(target=_check, daemon=True)
        t.start()

    def check_and_remind(self):
        """手动检查提醒（供UI定时器调用，线程安全）"""
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M")
        items = self._items.get(today_str, [])
        reminded_any = False
        for item in items:
            if not item.done and not item.reminded and item.time == current_time:
                item.reminded = True
                self._save()
                if self._on_remind:
                    self._on_remind("哈基米曼波 提醒", f"\u23F0 {item.time}\n{item.content}")
                reminded_any = True
        return reminded_any

    def stop(self):
        self._running = False


# 全局单例
todo_mgr = TodoManager()
