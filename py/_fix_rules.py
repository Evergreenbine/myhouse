
import sys, os
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\code\\overtime-app\\api_server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Build the replacement
old_block_start = '                sys_prompt = ('
old_block_end = '                if body.get("messages"):'

start_idx = content.find(old_block_start)
end_idx = content.find(old_block_end, start_idx)

if start_idx < 0 or end_idx < 0:
    print("Pattern not found")
    sys.exit(1)

old_block = content[start_idx:end_idx]

new_block = '''                p_desc = "温柔暖心，喜欢鼓励用户。" if persona == "warm" else "毒舌傲娇，喜欢吐槽用户。"
                rules_content = ""
                try:
                    with open(os.path.join(os.path.dirname(__file__), 'business_rules.md'), 'r', encoding='utf-8') as rf:
                        rules_content = rf.read()
                except:
                    pass
                sys_prompt = (
                    "你是一个名叫哈基米的猫咪AI助手，运行在一个加班考勤管理应用中。\n"
                    "你的性格是" + persona + "，" + p_desc + "\n\n"
                    "=== 应用规则（必须遵守）=== \n"
                    "1. 这是一个加班考勤管理应用，用户通过打卡记录来统计加班工时和加班费。\n"
                    "2. 用户叫\"吴钦腾\"，工号M03141。\n"
                    "3. 当前系统日期是2026年，不是2025年，回答日期相关问题时基于2026年。\n"
                    "4. 如果要查询数据，请通过工具函数获取，不要自行编造数据。\n"
                    "5. 回答用中文，保持轻松可爱的语气，适当使用emoji。\n"
                    "6. 以下是本应用的业务规则，请熟记并根据这些规则回答问题：\n"
                    + rules_content
                )
                '''

content = content.replace(old_block, new_block)

with open('D:\\code\\overtime-app\\api_server.py', 'w', encoding='utf-8') as f:
    f.write(content)

import ast
ast.parse(content)
print('Syntax OK')
print(f'Replaced block from line {content[:start_idx].count(chr(10))} to {content[:end_idx].count(chr(10))}')
