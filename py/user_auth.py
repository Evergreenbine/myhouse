# -*- coding: utf-8 -*-
"""
注册/登录系统 - 配置文件 + MAC 绑定 + 密码保护
"""
import os
import json
import hashlib
import uuid
import socket
from dataclasses import dataclass, asdict
from typing import Optional

CONFIG_DIR = os.path.dirname(__file__)
USER_FILE = os.path.join(CONFIG_DIR, "user_config.json")


def get_mac_address():
    """获取本机 MAC 地址"""
    mac = uuid.getnode()
    return ':'.join(['{:02x}'.format((mac >> ele) & 0xff) for ele in range(0, 8 * 6, 8)][::-1])


def hash_password(password: str) -> str:
    """密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()


@dataclass
class UserConfig:
    """用户配置"""
    empno: str = ""           # 工号，如 1103141
    empname: str = ""         # 姓名，如 吴钦腾
    password_hash: str = ""   # 密码哈希
    mac_address: str = ""     # 绑定 MAC
    api_key: str = ""
    ai_model: str = "deepseek-v4-flash"
    ai_persona: str = "warm"
    is_registered: bool = False
    is_logged_in: bool = False  # 是否已登录
    avatar_path: str = "cat_icon.png"  # 头像路径


def load_user_config() -> Optional[UserConfig]:
    """加载用户配置"""
    if os.path.exists(USER_FILE):
        try:
            with open(USER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return UserConfig(**data)
        except Exception:
            return None
    return None


def save_user_config(config: UserConfig):
    """保存用户配置"""
    with open(USER_FILE, "w", encoding="utf-8") as f:
        json.dump(asdict(config), f, ensure_ascii=False, indent=2)


def register(empno: str, empname: str, password: str) -> UserConfig:
    """注册新用户，绑定当前 MAC"""
    mac = get_mac_address()
    config = UserConfig(
        empno=empno,
        empname=empname,
        password_hash=hash_password(password),
        mac_address=mac,
        is_registered=True,
        is_logged_in=True,
    )
    save_user_config(config)
    return config


def login(empno: str, password: str) -> Optional[UserConfig]:
    """登录验证：密码+MAC双重校验，登录成功后更新MAC绑定"""
    config = load_user_config()
    if not config or not config.is_registered:
        return None
    if config.empno != empno:
        return None
    if config.password_hash != hash_password(password):
        return None
    # 登录成功后更新 MAC 绑定（防止配置被拷贝到别的电脑）
    current_mac = get_mac_address()
    if config.mac_address != current_mac:
        config.mac_address = current_mac
    config.is_logged_in = True
    save_user_config(config)
    return config

def quick_login() -> Optional[UserConfig]:
    """一键登录：配置存在、MAC匹配、已注册即可"""
    config = load_user_config()
    if not config or not config.is_registered:
        return None
    if config.mac_address != get_mac_address():
        return None  # 换了设备
    config.is_logged_in = True
    save_user_config(config)
    return config

def is_logged_in() -> bool:
    """当前是否已登录"""
    config = load_user_config()
    return config is not None and config.is_logged_in and config.mac_address == get_mac_address()

def is_registered() -> bool:
    """是否已注册（配置存在、已注册、且 MAC 匹配）"""
    config = load_user_config()
    if not config or not config.is_registered:
        return False
    if config.mac_address != get_mac_address():
        return False
    return True

def logout():
    """退出登录，保留配置但标记未登录"""
    config = load_user_config()
    if config:
        config.is_logged_in = False
        save_user_config(config)

def clear_user_config():
    """删除用户配置文件（彻底清除）"""
    if os.path.exists(USER_FILE):
        os.remove(USER_FILE)
