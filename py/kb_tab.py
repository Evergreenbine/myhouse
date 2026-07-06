# -*- coding: utf-8 -*-
"""知识库管理 Tab —— 上传文档、查看、删除"""
import flet as ft
import os
import threading

BLUE = "#3370FF"; BLUE_LIGHT = "#E8F0FE"
GREEN = "#34C759"; RED = "#F54A45"; ORANGE = "#FF9500"
TEXT = "#1F2329"; TEXT_SEC = "#646A73"; TEXT_THIRD = "#8F959E"
BORDER = "#E5E6EB"; WHITE = "#FFFFFF"; BG = "#F2F3F5"


class KnowledgeBaseTab:
    def __init__(self, page: ft.Page):
        self.page = page
        self.doc_list = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
        self.status_text = ft.Text("", size=12, color=TEXT_SEC)

        # 文件选择器
        self.file_picker = ft.FilePicker(on_result=self._on_file_picked)
        page.overlay.append(self.file_picker)

        self.content = ft.Container(ft.Column([
            ft.Text("📚 公司知识库", size=18, weight=ft.FontWeight.BOLD, color=TEXT),
            ft.Text("上传公司规章制度、SOP、文档，AI助手自动检索回答", size=12, color=TEXT_THIRD),
            ft.Container(height=12),

            # 上传区域
            ft.Container(ft.Column([
                ft.Text("📤 上传文档", size=14, weight=ft.FontWeight.BOLD, color=TEXT),
                ft.Text("支持 .txt .md .pdf .docx .py .csv .json", size=11, color=TEXT_THIRD),
                ft.Container(height=8),
                ft.Row([
                    ft.FilledButton("选择文件上传", icon=ft.icons.UPLOAD_FILE,
                                    on_click=lambda e: self.file_picker.pick_files(
                                        allowed_extensions=["txt", "md", "pdf", "docx", "py", "csv", "json"])),
                    self.status_text,
                ], spacing=12),
            ]), padding=16, bgcolor=BLUE_LIGHT, border_radius=12),

            ft.Container(height=16),

            # 已上传列表
            ft.Text("📋 已上传文档", size=14, weight=ft.FontWeight.BOLD, color=TEXT),
            ft.Container(height=8),
            self.doc_list,
        ], expand=True),
            padding=ft.padding.all(24), expand=True, bgcolor=WHITE,
            margin=ft.margin.all(16), border_radius=12, border=ft.border.all(1, BORDER))

    def load(self):
        """刷新文档列表"""
        self.doc_list.controls.clear()
        from knowledge_base import kb
        docs = kb.list_documents()
        total = kb.total_chunks()

        if not docs:
            self.doc_list.controls.append(
                ft.Text("📭 还没有上传任何文档，点上面按钮上传吧~", size=13, color=TEXT_THIRD))
            self.doc_list.controls.append(
                ft.Text(f"💡 上传后，在AI助手里问「年假怎么请」就能自动检索答案", size=12, color=TEXT_SEC, italic=True))
        else:
            for doc in docs:
                title = doc["title"]
                chunks = doc["chunks"]
                self.doc_list.controls.append(
                    ft.Container(
                        ft.Row([
                            ft.Icon(ft.icons.DESCRIPTION, size=18, color=BLUE),
                            ft.Container(width=8),
                            ft.Column([
                                ft.Text(title, size=13, weight=ft.FontWeight.W_500, color=TEXT),
                                ft.Text(f"{chunks} 个片段", size=11, color=TEXT_THIRD),
                            ], expand=True),
                            ft.IconButton(ft.icons.DELETE_OUTLINE, icon_size=18, icon_color=RED,
                                         on_click=lambda e, t=title: self._delete_doc(t),
                                         tooltip="删除"),
                        ], spacing=4),
                        padding=ft.padding.symmetric(vertical=8, horizontal=4),
                        border=ft.border.only(bottom=ft.border.BorderSide(0.5, BORDER)),
                    )
                )

            self.doc_list.controls.append(ft.Container(height=8))
            self.doc_list.controls.append(
                ft.Text(f"共 {len(docs)} 个文档，{total} 个片段 | AI助手已自动连接知识库", size=11, color=TEXT_THIRD, italic=True))

        self.page.update()

    def _on_file_picked(self, e: ft.FilePickerResultEvent):
        if not e.files:
            return
        from knowledge_base import kb

        success = 0
        for f in e.files:
            try:
                count = kb.add_file(f.path)
                if count > 0:
                    success += 1
                    self.status_text.value = f"✅ {f.name} 已添加 ({count}片段)"
                    self.status_text.color = GREEN
                else:
                    self.status_text.value = f"⚠ {f.name} 内容为空"
                    self.status_text.color = ORANGE
            except Exception as ex:
                self.status_text.value = f"❌ {f.name}: {str(ex)[:80]}"
                self.status_text.color = RED
            try:
                self.status_text.update()
            except:
                pass

        if success > 0:
            self.page.show_snack_bar(ft.SnackBar(
                ft.Text(f"✅ 成功上传 {success} 个文档", size=13), bgcolor=GREEN))
        self.load()

    def _delete_doc(self, title):
        from knowledge_base import kb

        def confirm(e):
            kb.delete_document(title)
            self.page.close(dlg)
            self.page.show_snack_bar(ft.SnackBar(
                ft.Text(f"已删除「{title}」", size=13), bgcolor=GREEN))
            self.load()

        dlg = ft.AlertDialog(
            title=ft.Text("确认删除", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Text(f"确定要删除「{title}」吗？删除后AI将无法检索此文档。"),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.close(dlg)),
                ft.FilledButton("删除", on_click=confirm, style=ft.ButtonStyle(bgcolor=RED, color=WHITE)),
            ],
        )
        self.page.open(dlg)
