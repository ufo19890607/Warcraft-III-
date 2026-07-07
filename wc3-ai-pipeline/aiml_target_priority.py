# -*- coding: utf-8 -*-
"""
攻击目标优先级配置。

修改此文件即可动态调整剑圣 HUNT / 齐射 (Salvo) 的目标优先级，
无需修改注入脚本。重新出包后生效。

格式：
    TARGET_PRIORITY = [
        ('ubsp', '毁灭者'),
        ('uobs', '黑曜石雕像'),
        ...
    ]
"""

TARGET_PRIORITY = [
    ('ubsp', '毁灭者 (Destroyer)'),
    ('uobs', '黑曜石雕像 (Obsidian Statue)'),
    ('uban', '女妖 (Banshee)'),
    ('ucry', '穴居恶魔/蜘蛛 (Crypt Fiend)'),
    ('ugho', '食尸鬼 (Ghoul)'),
]

# 残血英雄始终最高优先级 (不在列表里，硬编码)
HERO_SCAN_RANGE_SQ = 4000000.0  # 2000^2
HERO_HP_THRESHOLD = 300.0
UNIT_SCAN_RANGE_SQ = 640000.0  # 800^2


def get_target_id_list():
    """返回优先级 unit ID 列表 (str)"""
    return [uid for uid, _ in TARGET_PRIORITY]


def get_target_name(uid):
    """根据 unit ID 返回中文名"""
    for tid, name in TARGET_PRIORITY:
        if tid == uid:
            return name
    return uid
