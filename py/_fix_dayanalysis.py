# -*- coding: utf-8 -*-
with open('D:\\code\\overtime-app\\api_server.py', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace(
    "                            from attendance import DayAnalysis\n",
    ""
)
with open('D:\\code\\overtime-app\\api_server.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed')
