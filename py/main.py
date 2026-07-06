# -*- coding: utf-8 -*-
"""
加班工资桌面应用 - 主界面
PyQt5 实现，包含日历视图和考勤分析
"""
import sys
import math
from datetime import date, timedelta
from collections import defaultdict

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox, QSplitter,
    QMessageBox, QStatusBar, QFrame, QSizePolicy, QAbstractItemView,
)
from PyQt5.QtCore import Qt, QDate, QSize
from PyQt5.QtGui import QFont, QColor, QPalette

from config import EMP_NAME
from calendar_2026 import get_day_type, get_day_type_label
from attendance import (
    DayAnalysis, get_company_month_range, get_company_month_label,
    is_rest_day, calculate_overtime_hours, get_overtime_rate,
    check_missed_punch,
)
from database import query_work_records_range


# ==================== 颜色定义 ====================
COLOR_WEEKDAY = QColor(255, 255, 255)       # 平日 白色
COLOR_WEEKEND = QColor(200, 230, 255)        # 休息日 浅蓝
COLOR_HOLIDAY = QColor(255, 200, 200)        # 节假日 浅红
COLOR_MAKEUP = QColor(255, 255, 200)         # 补班日 浅黄
COLOR_TODAY = QColor(100, 200, 100)          # 今天 绿色
COLOR_SELECTED = QColor(150, 200, 255)       # 选中 蓝色
COLOR_MISSED = QColor(255, 100, 100)         # 漏打卡 红色
COLOR_OVERTIME = QColor(100, 255, 100)       # 有加班 绿色
COLOR_TEXT_DEFAULT = QColor(0, 0, 0)          # 默认文字
COLOR_TEXT_SUNDAY = QColor(200, 0, 0)         # 周日文字 红色
COLOR_TEXT_SATURDAY = QColor(0, 0, 200)       # 周六文字 蓝色


class CalendarWidget(QWidget):
    """自定义日历组件，显示公司月历"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_date = date.today()
        self.selected_date = date.today()
        self.analysis_data = {}  # {date_str: DayAnalysis}
        self.day_buttons = {}     # {date: QPushButton}
        self.init_ui()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(3)

        # 顶部导航栏
        nav_layout = QHBoxLayout()

        self.prev_btn = QPushButton("◀ 上月")
        self.prev_btn.setFixedWidth(80)
        self.prev_btn.clicked.connect(self.prev_month)

        self.month_label = QLabel()
        self.month_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.month_label.setFont(font)

        self.next_btn = QPushButton("下月 ▶")
        self.next_btn.setFixedWidth(80)
        self.next_btn.clicked.connect(self.next_month)

        self.today_btn = QPushButton("今天")
        self.today_btn.setFixedWidth(60)
        self.today_btn.clicked.connect(self.go_today)

        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.month_label)
        nav_layout.addWidget(self.next_btn)
        nav_layout.addWidget(self.today_btn)
        self.main_layout.addLayout(nav_layout)

        # 星期标题
        week_layout = QHBoxLayout()
        weekdays = ["日", "一", "二", "三", "四", "五", "六"]
        for i, w in enumerate(weekdays):
            lbl = QLabel(w)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedHeight(25)
            if i == 0:
                lbl.setStyleSheet("color: red; font-weight: bold;")
            elif i == 6:
                lbl.setStyleSheet("color: blue; font-weight: bold;")
            else:
                lbl.setStyleSheet("font-weight: bold;")
            week_layout.addWidget(lbl)
        self.main_layout.addLayout(week_layout)

        # 日历网格
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(1)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.grid_widget)

        # 图例
        legend_layout = QHBoxLayout()
        legends = [
            ("平日", COLOR_WEEKDAY),
            ("休息日", COLOR_WEEKEND),
            ("节假日", COLOR_HOLIDAY),
            ("补班日", COLOR_MAKEUP),
            ("漏打卡", COLOR_MISSED),
            ("有加班", COLOR_OVERTIME),
        ]
        for text, color in legends:
            box = QLabel()
            box.setFixedSize(16, 16)
            box.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #999;")
            lbl = QLabel(text)
            lbl.setStyleSheet("font-size: 11px;")
            legend_layout.addWidget(box)
            legend_layout.addWidget(lbl)
            legend_layout.addSpacing(8)
        legend_layout.addStretch()
        self.main_layout.addLayout(legend_layout)

        self.update_calendar()

    def set_analysis_data(self, data: dict):
        """设置考勤分析数据"""
        self.analysis_data = data
        self.update_calendar()

    def update_calendar(self):
        """刷新日历显示"""
        start, end = get_company_month_range(self.current_date)
        self.month_label.setText(get_company_month_label(self.current_date))

        # 清空网格
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        self.day_buttons.clear()

        # 计算起始偏移（周几）
        first_weekday = start.weekday()
        # Python: 周一=0, 周日=6，我们日历周日是第一列
        offset = (first_weekday + 1) % 7

        total_days = (end - start).days + 1
        total_cells = offset + total_days
        rows = math.ceil(total_cells / 7)

        today = date.today()

        for i in range(total_cells):
            row = i // 7
            col = i % 7

            if i < offset or (i - offset) >= total_days:
                # 空白格
                lbl = QLabel("")
                self.grid_layout.addWidget(lbl, row, col)
                continue

            d = start + timedelta(days=i - offset)
            btn = QPushButton()
            btn.setFixedSize(70, 50)
            btn.setCursor(Qt.PointingHandCursor)

            # 构建显示文字
            date_str = d.isoformat()
            day_num = str(d.day)

            # 判断颜色
            day_type = get_day_type(d)
            bg_color = COLOR_WEEKDAY
            text_color = COLOR_TEXT_DEFAULT

            if day_type == "holiday":
                bg_color = COLOR_HOLIDAY
            elif day_type == "makeup":
                bg_color = COLOR_MAKEUP
            elif day_type == "weekend":
                bg_color = COLOR_WEEKEND

            if d.weekday() == 6:  # 周日
                text_color = COLOR_TEXT_SUNDAY
            elif d.weekday() == 5:  # 周六
                text_color = COLOR_TEXT_SATURDAY

            if d == today:
                bg_color = COLOR_TODAY

            if d == self.selected_date:
                bg_color = COLOR_SELECTED

            # 构建按钮文本
            lines = [day_num]
            type_label = get_day_type_label(d)

            # 如果有分析数据，加上打卡信息
            if date_str in self.analysis_data:
                analysis = self.analysis_data[date_str]
                if analysis.missed:
                    lines.append("⚠漏打卡")
                    if d == self.selected_date:
                        pass  # 选中的用选中色
                    else:
                        bg_color = COLOR_MISSED
                elif analysis.overtime_hours > 0:
                    lines.append(f"+{analysis.overtime_hours}h")
                    if d != self.selected_date and d != today:
                        bg_color = COLOR_OVERTIME
                else:
                    lines.append(f"✓{analysis.card_count}次")
            else:
                lines.append(type_label[:2])

            btn.setText("\n".join(lines))

            # 设置样式
            style = f"""
                QPushButton {{
                    background-color: {bg_color.name()};
                    color: {text_color.name()};
                    border: 1px solid #ccc;
                    border-radius: 3px;
                    font-size: 10px;
                    padding: 2px;
                }}
                QPushButton:hover {{
                    border: 2px solid #3399ff;
                }}
            """
            btn.setStyleSheet(style)

            # 绑定点击事件
            btn.clicked.connect(lambda checked, dd=d: self.on_day_clicked(dd))

            self.grid_layout.addWidget(btn, row, col)
            self.day_buttons[d] = btn

    def on_day_clicked(self, d: date):
        """日期点击事件"""
        self.selected_date = d
        self.update_calendar()
        # 通知父窗口
        parent = self.window()
        if hasattr(parent, "on_date_selected"):
            parent.on_date_selected(d)

    def prev_month(self):
        """上个月"""
        start, _ = get_company_month_range(self.current_date)
        self.current_date = start - timedelta(days=1)
        self.update_calendar()

    def next_month(self):
        """下个月"""
        _, end = get_company_month_range(self.current_date)
        self.current_date = end + timedelta(days=1)
        self.update_calendar()

    def go_today(self):
        """回到今天"""
        self.current_date = date.today()
        self.selected_date = date.today()
        self.update_calendar()
        parent = self.window()
        if hasattr(parent, "on_date_selected"):
            parent.on_date_selected(self.selected_date)


class DetailPanel(QWidget):
    """右侧详情面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # 月份汇总
        self.summary_group = QGroupBox("本月汇总")
        summary_layout = QVBoxLayout()

        self.summary_label = QLabel("请选择日期查看详情")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px;")
        summary_layout.addWidget(self.summary_label)

        self.summary_group.setLayout(summary_layout)
        layout.addWidget(self.summary_group)

        # 当天详情
        self.detail_group = QGroupBox("当天详情")
        detail_layout = QVBoxLayout()

        self.detail_label = QLabel("点击日历中的日期查看")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("font-size: 12px;")
        detail_layout.addWidget(self.detail_label)

        self.detail_group.setLayout(detail_layout)
        layout.addWidget(self.detail_group)

        # 打卡记录表
        self.record_group = QGroupBox("打卡记录")
        record_layout = QVBoxLayout()

        self.record_table = QTableWidget()
        self.record_table.setColumnCount(3)
        self.record_table.setHorizontalHeaderLabels(["序号", "打卡时间", "备注"])
        self.record_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.record_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.record_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        record_layout.addWidget(self.record_table)

        self.record_group.setLayout(record_layout)
        layout.addWidget(self.record_group)

        # 刷新按钮
        self.refresh_btn = QPushButton("刷新数据")
        self.refresh_btn.setMinimumHeight(35)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        layout.addWidget(self.refresh_btn)

    def show_summary(self, analysis_map: dict):
        """显示月度汇总"""
        total_overtime = 0.0
        total_pay = 0.0
        missed_days = []
        overtime_days = 0

        for date_str, analysis in analysis_map.items():
            if analysis.overtime_hours > 0:
                total_overtime += analysis.overtime_hours
                total_pay += analysis.overtime_pay
                overtime_days += 1
            if analysis.missed:
                missed_days.append(date_str)

        text = f"""
        <table style='font-size:13px; line-height:1.8;'>
        <tr><td><b>加班天数：</b></td><td>{overtime_days} 天</td></tr>
        <tr><td><b>加班总小时：</b></td><td>{total_overtime:.1f} h</td></tr>
        <tr><td><b>加班总工资：</b></td><td style='color:red; font-size:16px;'><b>¥ {total_pay:.2f}</b></td></tr>
        <tr><td><b>漏打卡天数：</b></td><td style='color:red;'>{len(missed_days)} 天</td></tr>
        </table>
        """
        if missed_days:
            text += "<br><span style='color:red; font-size:11px;'>漏打卡日期：" + ", ".join(missed_days) + "</span>"

        self.summary_label.setText(text)

    def show_detail(self, analysis: DayAnalysis, records: list):
        """显示当天详情"""
        d = analysis.date
        type_color = {"节假日": "red", "补班日": "orange", "休息日": "blue", "平日": "green"}

        text = f"""
        <table style='font-size:12px; line-height:1.8;'>
        <tr><td><b>日期：</b></td><td>{d.isoformat()} ({d.strftime('%A')})</td></tr>
        <tr><td><b>类型：</b></td>
            <td style='color:{type_color.get(analysis.day_type_label, "black")};'>
                <b>{analysis.day_type_label}</b>
            </td></tr>
        <tr><td><b>打卡次数：</b></td><td>{analysis.card_count} / {analysis.required_cards} 次
            {'<span style=\"color:red;\"> ⚠ 漏打卡!</span>' if analysis.missed else ' ✓'}
        </td></tr>
        <tr><td><b>加班小时：</b></td><td>{analysis.overtime_hours:.1f} h</td></tr>
        <tr><td><b>加班费率：</b></td><td>¥ {analysis.overtime_rate}/h</td></tr>
        <tr><td><b>加班工资：</b></td><td style='color:red; font-size:14px;'><b>¥ {analysis.overtime_pay:.2f}</b></td></tr>
        </table>
        """

        # 显示打卡时间列表
        if analysis.card_times:
            text += "<br><b>打卡时间：</b><br>"
            for t in analysis.card_times:
                text += f"  • {t.strftime('%H:%M:%S')}<br>"

        self.detail_label.setText(text)

        # 打卡记录表
        self.record_table.setRowCount(len(records))
        for i, r in enumerate(records):
            self.record_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            wt = r.get("worktime", "")
            if hasattr(wt, "strftime"):
                wt_str = wt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                wt_str = str(wt)
            self.record_table.setItem(i, 1, QTableWidgetItem(wt_str))
            remark = r.get("remark", "") or ""
            if hasattr(remark, "strftime"):
                remark = str(remark)
            self.record_table.setItem(i, 2, QTableWidgetItem(str(remark)))


class OvertimeApp(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.emp_name = EMP_NAME
        self.analysis_map = {}  # {date_str: DayAnalysis}
        self.records_map = {}   # {date_str: [records]}
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("华阳多媒体 - 加班工资查询")
        self.setMinimumSize(1100, 700)

        # 中央控件
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        # 左侧日历
        self.calendar = CalendarWidget()
        main_layout.addWidget(self.calendar, stretch=3)

        # 右侧面板
        self.detail_panel = DetailPanel()
        self.detail_panel.refresh_btn.clicked.connect(self.refresh_data)
        main_layout.addWidget(self.detail_panel, stretch=2)

        # 状态栏
        self.statusBar().showMessage("就绪 - 点击「刷新数据」加载考勤记录")

    def refresh_data(self):
        """从数据库刷新考勤数据"""
        self.statusBar().showMessage("正在从数据库加载考勤数据...")
        QApplication.processEvents()

        try:
            start, end = get_company_month_range(self.calendar.current_date)

            # 查询数据库
            all_records = query_work_records_range(self.emp_name, start.isoformat(), end.isoformat())

            self.records_map = all_records

            # 分析每一天
            self.analysis_map = {}
            d = start
            while d <= end:
                date_str = d.isoformat()
                records = all_records.get(date_str, [])
                analysis = DayAnalysis(d, records)
                self.analysis_map[date_str] = analysis
                d += timedelta(days=1)

            # 更新UI
            self.calendar.set_analysis_data(self.analysis_map)
            self.detail_panel.show_summary(self.analysis_map)

            # 更新选中日期详情
            self.on_date_selected(self.calendar.selected_date)

            self.statusBar().showMessage(
                f"数据加载完成 - {start.isoformat()} ~ {end.isoformat()}，共 {len(all_records)} 天有打卡记录"
            )

        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载数据失败：\n{str(e)}")
            self.statusBar().showMessage("加载失败")

    def on_date_selected(self, d: date):
        """日期选中回调"""
        date_str = d.isoformat()
        if date_str in self.analysis_map:
            analysis = self.analysis_map[date_str]
            records = self.records_map.get(date_str, [])
            self.detail_panel.show_detail(analysis, records)
        else:
            self.detail_panel.detail_label.setText(f"暂无 {date_str} 的数据")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 全局字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    window = OvertimeApp()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
