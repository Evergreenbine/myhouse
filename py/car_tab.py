# -*- coding: utf-8 -*-
"""车辆出入记录 Tab 页"""
import flet as ft
import threading
from datetime import date, datetime
from car_db import query_car_records, update_car_record
from calendar_2026 import is_rest_day, get_day_type
from user_auth import load_user_config
from ai_service import ai_svc


TEXT = "#1F2329"; TEXT_SEC = "#646A73"; TEXT_THIRD = "#8F959E"
BORDER = "#E5E6EB"; WHITE = "#FFFFFF"; BLUE_LIGHT = "#E8F0FE"
GREEN = "#34C759"; BLUE = "#3370FF"; RED = "#F54A45"
ORANGE = "#FFB74D"; PURPLE = "#CE93D8"

class CarTab:
    def __init__(self, page: ft.Page):
        self.page = page
        from attendance import get_company_month_range
        s, e = get_company_month_range(date.today())
        self.records = []; self.selected = set()
        self.date_from = s; self.date_to = e
        self.abn_date_from = s; self.abn_date_to = e

        # 全部记录筛选
        self.dir_dd = ft.Dropdown(options=[ft.dropdown.Option("all","全部"),ft.dropdown.Option("0","进"),ft.dropdown.Option("1","出")],
                                  value="all",width=80,dense=True,text_size=13,on_change=lambda e:self.load())
        self.from_btn = ft.ElevatedButton(self.date_from.strftime("%m-%d"),icon=ft.icons.CALENDAR_MONTH,on_click=lambda e:self._pick("from"))
        self.to_btn = ft.ElevatedButton(self.date_to.strftime("%m-%d"),icon=ft.icons.CALENDAR_MONTH,on_click=lambda e:self._pick("to"))
        self.from_picker = ft.DatePicker(on_change=lambda e:self._set_date("from",e.control.value))
        self.to_picker = ft.DatePicker(on_change=lambda e:self._set_date("to",e.control.value))
        page.overlay.extend([self.from_picker,self.to_picker])

        # 异常记录筛选
        self.abn_from_btn = ft.ElevatedButton(self.abn_date_from.strftime("%m-%d"),icon=ft.icons.CALENDAR_MONTH,on_click=lambda e:self._pick_abn("from"))
        self.abn_to_btn = ft.ElevatedButton(self.abn_date_to.strftime("%m-%d"),icon=ft.icons.CALENDAR_MONTH,on_click=lambda e:self._pick_abn("to"))
        self.abn_from_picker = ft.DatePicker(on_change=lambda e:self._set_abn_date("from",e.control.value))
        self.abn_to_picker = ft.DatePicker(on_change=lambda e:self._set_abn_date("to",e.control.value))
        page.overlay.extend([self.abn_from_picker,self.abn_to_picker])

        self.list_view = ft.Column(spacing=1,scroll=ft.ScrollMode.AUTO,expand=True)
        self.abnormal_list = ft.Column(spacing=1,scroll=ft.ScrollMode.AUTO,expand=True)
        self.abnormal_records = []

        # 全部记录页
        all_content = ft.Container(ft.Column([
            ft.Row([ft.Text("日期",size=13,color=TEXT_SEC),self.from_btn,self.to_btn,
                    ft.Chip(label=ft.Text("本月",size=12),leading=ft.Icon(ft.icons.TODAY,size=14),
                            bgcolor=BLUE_LIGHT,on_click=lambda e:self._reset_month()),
                    self.dir_dd,
                    ft.OutlinedButton("批量改",icon=ft.icons.EDIT_NOTE,on_click=lambda e:self._batch_edit())],spacing=6),
            ft.Divider(height=1,color=BORDER),ft.Container(height=4),
            ft.Row([ft.Checkbox(value=False,on_change=lambda e:self._sel_all(),scale=0.8),
                    ft.Text("异常",size=11,color=ORANGE,width=24),ft.Text("时间",size=11,color=TEXT_SEC,width=160),
                    ft.Text("进出",size=11,color=TEXT_SEC,width=44),ft.Text("打卡信息",size=11,color=TEXT_SEC),
                    ft.Text("编辑",size=11,color=TEXT_SEC)],spacing=2),
            ft.Divider(height=0.5,color=BORDER),self.list_view,
        ],expand=True),padding=ft.padding.all(24),expand=True,bgcolor=WHITE,margin=ft.margin.all(16),border_radius=12,border=ft.border.all(1,BORDER))

        # 异常记录页
        self.ai_abn_result = ft.Text("", size=12, color=TEXT_SEC)
        abnormal_content = ft.Container(ft.Column([
            ft.Container(height=4),
            ft.Row([ft.Text("从",size=13,color=TEXT_SEC),self.abn_from_btn,ft.Text("至",size=13,color=TEXT_SEC),self.abn_to_btn],spacing=6),
            ft.Divider(height=0.5,color=BORDER),ft.Container(height=4),
            ft.Row([ft.Text("异常",size=11,color=ORANGE,width=30),ft.Text("时间",size=11,color=TEXT_SEC,width=160),
                    ft.Text("进出",size=11,color=TEXT_SEC,width=44),ft.Text("原因",size=11,color=TEXT_SEC,width=100),
                    ft.Text("打卡信息",size=11,color=TEXT_SEC)],spacing=2),
            ft.Divider(height=0.5,color=BORDER),self.abnormal_list,
            ft.Container(height=8),
            ft.Container(
                ft.Row([
                    ft.Chip(label=ft.Text("🧠 AI分析异常", size=11), bgcolor="#FFF8E1",
                            leading=ft.Icon(ft.icons.AUTO_AWESOME, size=14, color=ORANGE),
                            on_click=lambda e: self._ai_analyze_abnormal()),
                ]),
                padding=ft.padding.all(8), bgcolor="#FFF8E1", border_radius=8,
                visible=len(self.abnormal_records) > 0,
            ),
            self.ai_abn_result,
        ],expand=True),padding=ft.padding.all(24),expand=True,bgcolor=WHITE,margin=ft.margin.all(16),border_radius=12,border=ft.border.all(1,BORDER))

        self.content = ft.Tabs(selected_index=0, tabs=[
            ft.Tab(text="全部记录", icon=ft.icons.LIST, content=all_content),
            ft.Tab(text="异常记录", icon=ft.icons.WARNING_AMBER, content=abnormal_content),
        ], expand=True)

    # ===== 筛选操作 =====
    def _reset_month(self):
        from attendance import get_company_month_range
        s, e = get_company_month_range(date.today())
        self.date_from = s; self.date_to = e
        self.from_btn.text = s.strftime("%m-%d"); self.to_btn.text = e.strftime("%m-%d")
        self.load()

    def _pick(self,w): (self.from_picker if w=="from" else self.to_picker).pick_date()
    def _pick_abn(self,w): (self.abn_from_picker if w=="from" else self.abn_to_picker).pick_date()

    def _set_date(self,w,d):
        if not d: return
        if hasattr(d,'date'): d=d.date()
        if w=="from": self.date_from=d; self.from_btn.text=d.strftime("%m-%d")
        else: self.date_to=d; self.to_btn.text=d.strftime("%m-%d")
        self.load()

    def _set_abn_date(self,w,d):
        if not d: return
        if hasattr(d,'date'): d=d.date()
        if w=="from": self.abn_date_from=d; self.abn_from_btn.text=d.strftime("%m-%d")
        else: self.abn_date_to=d; self.abn_to_btn.text=d.strftime("%m-%d")
        self.load_abnormal()

    def _sel_all(self):
        if len(self.selected)==len(self.records) and len(self.records)>0: self.selected.clear()
        else: self.selected=set(range(len(self.records)))
        for i,c in enumerate(self.list_view.controls):
            if hasattr(c,'content') and isinstance(c.content,ft.Row):
                for ch in c.content.controls:
                    if isinstance(ch,ft.Checkbox): ch.value=i in self.selected;break
        self.page.update()

    # ===== 数据加载 =====
    def _load_punch_data(self,df,dt):
        from database import query_work_records_range
        from calendar_2026 import get_day_type_label
        cfg=load_user_config()
        if not cfg: return {}
        recs=query_work_records_range(cfg.empname,df.isoformat(),dt.isoformat())
        result={}
        for ds,day in recs.items():
            times=[r["worktime"] for r in day if r.get("worktime") and hasattr(r["worktime"],"strftime")]
            if times:
                result[ds]={"earliest":min(times),"latest":max(times),"count":len(times),
                            "label":get_day_type_label(date.fromisoformat(ds))}
        return result

    def _fmt_punch(self,pd):
        if not pd: return "无打卡"
        return f"{pd['earliest'].strftime('%H:%M')}~{pd['latest'].strftime('%H:%M')} {pd['label']}"

    def load(self):
        self.list_view.controls.clear(); self.selected.clear()
        cfg=load_user_config(); plate=cfg.car_plate if cfg and cfg.car_plate else "粤S0Q780"
        df=self.dir_dd.value
        rows=[]
        # 按月查询，收集涉及的所有月份
        months=set()
        cur=self.date_from.replace(day=1)
        end=self.date_to.replace(day=1)
        while cur<=end:
            months.add(cur.strftime("%Y%m"))
            if cur.month==12: cur=cur.replace(year=cur.year+1,month=1)
            else: cur=cur.replace(month=cur.month+1)
        for ym in months:
            try:
                for r in query_car_records(plate,ym):
                    if df!="all" and str(r["ch_out"])!=df: continue
                    d=r["ch_crosstime"].date() if hasattr(r["ch_crosstime"],"date") else r["ch_crosstime"]
                    if isinstance(d,datetime): d=d.date()
                    if self.date_from<=d<=self.date_to: rows.append(r)
            except: pass
        rows.sort(key=lambda r:r["ch_crosstime"],reverse=True); self.records=rows
        pd=self._load_punch_data(self.date_from,self.date_to)
        if not rows: self.list_view.controls.append(ft.Text("暂无记录",size=13,color=TEXT_THIRD))
        else: self._render(rows,pd,self.list_view,True)
        self.page.update()

    def load_abnormal(self):
        self.abnormal_list.controls.clear(); self.abnormal_records=[]
        cfg=load_user_config(); plate=cfg.car_plate if cfg and cfg.car_plate else "粤S0Q780"
        rows=[]
        months=set()
        cur=self.abn_date_from.replace(day=1)
        end=self.abn_date_to.replace(day=1)
        while cur<=end:
            months.add(cur.strftime("%Y%m"))
            if cur.month==12: cur=cur.replace(year=cur.year+1,month=1)
            else: cur=cur.replace(month=cur.month+1)
        for ym in months:
            try:
                for r in query_car_records(plate,ym):
                    d=r["ch_crosstime"].date() if hasattr(r["ch_crosstime"],"date") else r["ch_crosstime"]
                    if isinstance(d,datetime): d=d.date()
                    if self.abn_date_from<=d<=self.abn_date_to: rows.append(r)
            except: pass
        pd=self._load_punch_data(self.abn_date_from,self.abn_date_to)
        abn_rows=[]
        for r in rows:
            is_abn, _, _ = self._check_abnormal(r, pd)
            if is_abn:
                abn_rows.append(r)

        self.abnormal_records=abn_rows
        if not abn_rows: self.abnormal_list.controls.append(ft.Text("暂无异常记录 \U0001F389",size=13,color=GREEN))
        else: self._render(abn_rows,pd,self.abnormal_list,False)
        self.page.update()

    def _check_abnormal(self, r, pd):
        """公共方法：判断一条车辆记录是否异常，返回 (是否异常, 原因标签)"""
        t=r["ch_crosstime"]; d=t.date() if hasattr(t,"date") else t; ds=d.isoformat()
        hm=t.hour*60+t.minute
        is_workday = not is_rest_day(d) and get_day_type(d) not in ("holiday","makeup")
        punch = pd.get(ds)

        if is_workday:
            if (8*60+30 <= hm <= 12*60+5) or (13*60+5 <= hm <= 17*60+30):
                return (True, ORANGE, "上班时间外出")
            if t.hour >= 18:
                if punch and punch.get("latest"):
                    ot_end = punch["latest"].hour * 60 + punch["latest"].minute
                    if hm <= ot_end:
                        return (True, PURPLE, "加班时间出入")
                elif not punch:
                    return (True, PURPLE, "晚间出入(无打卡)")
        else:
            if not punch:
                return (False, None, "")
            earliest_hm = punch["earliest"].hour * 60 + punch["earliest"].minute if punch.get("earliest") else None
            latest_hm = punch["latest"].hour * 60 + punch["latest"].minute if punch.get("latest") else None
            if not earliest_hm or not latest_hm:
                return (False, None, "")
            if hm < earliest_hm:
                return (False, None, "")
            if 12*60+5 < hm < 13*60+5:
                return (False, None, "")
            if 17*60+30 < hm < 18*60:
                return (False, None, "")
            if earliest_hm <= hm <= 12*60+5:
                return (True, RED, "休息日班次内出入")
            if 13*60+5 <= hm <= 17*60+30:
                return (True, RED, "休息日班次内出入")
            if hm >= 18*60 and hm <= latest_hm:
                return (True, RED, "休息日班次内出入")

        return (False, None, "")

    def _render(self,rows,pd,target_list,show_check):
        for i,r in enumerate(rows):
            t=r["ch_crosstime"]; ts=t.strftime("%m-%d %H:%M:%S.%f")[:-3] if hasattr(t,"strftime") else str(t)
            d=t.date() if hasattr(t,"date") else t; ds=d.isoformat()
            is_abn, abn_c, reason = self._check_abnormal(r, pd)
            abn = "\u26a0" if is_abn else ""
            dr="进" if r["ch_out"]==0 else "出"; dc=GREEN if r["ch_out"]==0 else BLUE
            bg=(abn_c+"15") if abn_c else None; punch=self._fmt_punch(pd.get(ds,{}))
            chk=i in self.selected
            def mk_chk(idx):
                def h(e):
                    if idx in self.selected: self.selected.discard(idx)
                    else: self.selected.add(idx)
                    e.control.value=idx in self.selected; self.page.update()
                return h
            children=[ft.Text(abn,size=13,color=abn_c,width=30 if not show_check else 24),
                      ft.Text(ts,size=13,width=160),ft.Text(dr,size=13,color=dc,width=44)]
            if not show_check: children.insert(2,ft.Text(reason,size=12,color=abn_c,width=100))
            children.append(ft.Text(punch,size=11,color=TEXT_SEC))
            children.append(ft.IconButton(ft.icons.EDIT,icon_size=14,icon_color=TEXT_THIRD,on_click=lambda e,rec=r:self._edit_one(rec)))
            if show_check: children.insert(0,ft.Checkbox(value=chk,on_change=mk_chk(i),scale=0.8))
            target_list.controls.append(ft.Container(ft.Row(children,spacing=2),
                padding=ft.padding.symmetric(vertical=3),border=ft.border.only(bottom=ft.border.BorderSide(0.5,BORDER)),bgcolor=bg))

    # ===== 编辑 =====
    def _edit_one(self,rec):
        ot=rec["ch_crosstime"].strftime("%H:%M:%S.%f")[:-3]; ym=rec["ch_crosstime"].strftime("%Y%m")
        ti=ft.TextField(value=ot,hint_text="HH:MM:SS.FFF",text_size=14,width=150,text_align=ft.TextAlign.CENTER)
        sw=ft.Switch(value=rec["ch_out"]==1,label="出" if rec["ch_out"]==1 else "进",active_color=BLUE)
        def save(e):
            v=ti.value.strip()
            try:
                if "." in v: tp,mp=v.split("."); ms=int(mp.ljust(3,"0")[:3])*1000
                else: tp,ms=v,0
                p=tp.split(":"); h,m,s=int(p[0]),int(p[1]),int(p[2]) if len(p)>2 else 0
                nd=rec["ch_crosstime"].replace(hour=h,minute=m,second=s,microsecond=ms)
                if update_car_record(rec["ch_id"],ym,new_time=nd,new_out=1 if sw.value else 0):
                    self.page.show_snack_bar(ft.SnackBar(ft.Text("已修改"),bgcolor=GREEN))
                    dlg.open=False; self.page.update(); self.load(); self.load_abnormal()
            except: self.page.show_snack_bar(ft.SnackBar(ft.Text("格式: HH:MM:SS.FFF"),bgcolor=RED))
        dlg=ft.AlertDialog(title=ft.Text("修改"),content=ft.Column([
            ft.Text(f"原: {ot}",size=13,color=TEXT_THIRD),ft.Row([ft.Text("时间:",size=13,width=50),ti]),
            ft.Row([ft.Text("进出:",size=13,width=50),sw])],tight=True,height=150),
            actions=[ft.TextButton("取消",on_click=lambda e:self._close_dlg(dlg)),ft.FilledButton("保存",on_click=save)])
        self.page.dialog=dlg; dlg.open=True; self.page.update()

    def _close_dlg(self, dlg):
        dlg.open=False; self.page.update()

    def _batch_edit(self):
        if not self.selected: self.page.show_snack_bar(ft.SnackBar(ft.Text("请先勾选"),bgcolor=RED));return
        ti=ft.TextField(hint_text="新时间(留空不修改)",text_size=14,width=160,text_align=ft.TextAlign.CENTER)
        sw=ft.Switch(label="修改进出为出",active_color=BLUE,visible=False)
        sw_chg=ft.Checkbox(label="修改进出",value=False,on_change=lambda e:setattr(sw,'visible',sw_chg.value)or self.page.update())
        def save(e):
            cnt=0
            for idx in self.selected:
                r=self.records[idx]; ym=r["ch_crosstime"].strftime("%Y%m"); nt=None; no=None
                v=ti.value.strip()
                if v:
                    try:
                        if "." in v: tp,mp=v.split("."); ms=int(mp.ljust(3,"0")[:3])*1000
                        else: tp,ms=v,0
                        p=tp.split(":"); h,m,s=int(p[0]),int(p[1]),int(p[2]) if len(p)>2 else 0
                        nt=r["ch_crosstime"].replace(hour=h,minute=m,second=s,microsecond=ms)
                    except: self.page.show_snack_bar(ft.SnackBar(ft.Text("格式错误"),bgcolor=RED));return
                if sw_chg.value: no=1 if sw.value else 0
                if nt or no is not None:
                    if update_car_record(r["ch_id"],ym,new_time=nt,new_out=no): cnt+=1
            self.page.show_snack_bar(ft.SnackBar(ft.Text(f"已修改{cnt}条"),bgcolor=GREEN))
            dlg.open=False; self.page.update(); self.load(); self.load_abnormal()
        dlg=ft.AlertDialog(title=ft.Text(f"批量修改({len(self.selected)}条)"),
            content=ft.Column([ft.Row([ft.Text("时间:",size=13,width=60),ti]),ft.Container(height=8),ft.Row([sw_chg,sw])],tight=True,height=130),
            actions=[ft.TextButton("取消",on_click=lambda e:self._close_dlg(dlg)),ft.FilledButton("保存",on_click=save)])
        self.page.dialog=dlg; dlg.open=True; self.page.update()

    # ==================== AI 异常分析 ====================

    def _ai_analyze_abnormal(self):
        """AI分析车辆异常记录"""
        if not self.abnormal_records:
            self.page.show_snack_bar(ft.SnackBar(ft.Text("暂无异常记录~", size=13), bgcolor=GREEN))
            return
        lines = []
        for r in self.abnormal_records:
            lines.append(f"- {r.get('time','?')} {r.get('dir','?')} | {r.get('reason','?')}")
        prompt = f"车辆出入异常记录：\n" + "\n".join(lines) + "\n\n用猫咪语气分析可能的原因和风险（3-5句话，带emoji）。"
        self.ai_abn_result.value = "🐱 喵星人分析中..."
        try: self.ai_abn_result.update()
        except: pass
        def _run():
            r = ai_svc.call(prompt, system_prompt="你是一只细心的猫咪安全顾问。", max_tokens=200, temperature=0.7, timeout=12)
            self.ai_abn_result.value = r
            try: self.ai_abn_result.update()
            except: pass
        threading.Thread(target=_run, daemon=True).start()


