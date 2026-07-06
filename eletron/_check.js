







const API='http://127.0.0.1:18520';







let S={currentMonth:new Date(),selectedDate:new Date().toISOString().split('T')[0],attendanceData:null,activeTab:0,carDateFrom:'',carDateTo:'',aiPersona:'warm'};















async function api(url,o={}){const ctrl=new AbortController();const t=setTimeout(()=>ctrl.abort(),15000);try{const r=await fetch(API+url,{headers:{'Content-Type':'application/json'},signal:ctrl.signal,...o});clearTimeout(t);if(!r.ok)throw new Error(r.status+' '+r.statusText);return r.json()}catch(e){clearTimeout(t);throw e}}







function M(html){const o=document.createElement('div');o.className='modal-overlay';o.innerHTML=`<div class="modal">${html}</div>`;o.onclick=e=>{if(e.target===o)CM()};document.body.appendChild(o)}







function CM(){const o=document.querySelector('.modal-overlay');if(o)o.remove()}















// Tab切换







document.querySelectorAll('.tab').forEach(t=>{t.addEventListener('click',()=>{const i=parseInt(t.dataset.tab);S.activeTab=i;document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));t.classList.add('active');document.querySelectorAll('.tab-page').forEach(x=>x.classList.remove('active'));document.getElementById('page-'+i).classList.add('active');switch(i){case 0:renderCalendar();break;case 1:loadTodos();break;case 2:loadCar();break;case 3:loadWater();break;case 4:loadOtNotes();break;case 5:loadFun();break;case 6:loadKB();break}})});















// ========== 考勤管理 ==========







async function loadAttendance(){try{const d=await api('/api/attendance/month');S.attendanceData=d;document.getElementById('month-label').textContent=d.month_label||'';renderCalendar()}catch(e){}}







function renderCalendar(){if(!S.attendanceData){return;}var days=S.attendanceData.days,dates=Object.keys(days).sort();if(!dates.length)return;var fd=new Date(dates[0]+'T00:00:00'),sd=fd.getDay(),today=new Date().toISOString().split('T')[0];var h='<table class="calendar"><thead><tr>';var ws=['日','一','二','三','四','五','六'];for(var i=0;i<7;i++)h+='<th style="color:'+(i===0?'var(--red)':i===6?'var(--blue)':'')+'">'+ws[i]+'</th>';h+='</tr></thead><tbody>';var cells=[],idx=0;for(var i=0;i<sd;i++)cells.push({num:'',cls:''});dates.forEach(function(ds){var day=days[ds],d=new Date(ds+'T00:00:00'),cls=[];if(ds===today)cls.push('today');if(ds===S.selectedDate)cls.push('selected');if(day.is_rest&&!day.is_makeup)cls.push('weekend');if(day.holiday_name)cls.push('holiday');if(day.is_makeup)cls.push('makeup');var l='',lc='day-label';if(day.holiday_name){l=day.holiday_name;lc+=' holiday-label'}else if(day.missed){l='漏打卡';lc+=' missed'}else if(day.overtime_hours>0){l='+'+day.overtime_hours.toFixed(1)+'h';lc+=' ot'}else if(day.card_count>0)l='✓';cells.push({num:d.getDate(),cls:cls.join(' '),label:l,lc:lc,ds:ds})});while(cells.length<42)cells.push({num:'',cls:''});for(var r=0;r<6;r++){h+='<tr>';for(var c=0;c<7;c++){var cell=cells[r*7+c];var onclick=cell.ds?' onclick="selectDate(\''+cell.ds+'\')"':'';var tdCls=cell.cls+(cell.num?'':' empty');h+='<td class="'+tdCls+'"'+onclick+'>';if(cell.num)h+='<span class="day-num">'+cell.num+'</span>'+(cell.label?'<span class="'+cell.lc+'">'+cell.label+'</span>':'');h+='</td>'}h+='</tr>'}h+='</tbody></table>';document.getElementById('calendar').innerHTML=h;updateDetail()}







async function selectDate(ds){S.selectedDate=ds;renderCalendar()}







async function updateDetail(){const ds=S.selectedDate,day=S.attendanceData?.days?.[ds];if(!day)return;const days=Object.values(S.attendanceData.days),tH=days.reduce((s,d)=>s+(d.overtime_hours||0),0),tP=days.reduce((s,d)=>s+(d.overtime_pay||0),0),otD=days.filter(d=>d.overtime_hours>0).length,msD=days.filter(d=>d.missed).length;document.getElementById('summary-content').innerHTML=`<div class="info-row"><span class="key">加班天数</span><span class="val">${otD} 天</span></div><div class="info-row"><span class="key">总小时</span><span class="val">${tH.toFixed(1)}h</span></div><div class="info-row"><span class="key">总工资</span><span class="val" style="color:var(--blue);font-size:18px">¥${tP.toFixed(2)}</span></div>${msD>0?`<div style="color:var(--red);font-size:12px">漏打卡 ${msD} 天</div>`:''}`;const wn=['日','一','二','三','四','五','六'][new Date(ds+'T00:00:00').getDay()];document.getElementById('detail-content').innerHTML=`<div class="info-row"><span class="key">日期</span><span class="val">${ds} 周${wn}</span></div><div class="info-row"><span class="key">类型</span><span class="val">${day.type}${day.holiday_name?' · '+day.holiday_name:''}</span></div><div class="info-row"><span class="key">打卡</span><span class="val">${day.card_count}/${day.required_cards} 次 ${day.missed?'<span style="color:var(--red)">漏打卡!</span>':'✓'}</span></div><div class="info-row"><span class="key">加班</span><span class="val">${day.overtime_hours.toFixed(1)}h</span></div><div class="info-row"><span class="key">加班费</span><span class="val" style="color:var(--blue)">¥${day.overtime_pay.toFixed(2)}</span></div><div class="info-row"><span class="key">加班理由</span><span class="val" id="ot-reason-txt" style="font-size:12px;flex:1">加载中...</span><button class="btn btn-sm btn-outline" onclick="editOtReason('${ds}')" style="padding:1px 6px;font-size:10px">✏</button></div>`;setTimeout(async function(){try{var r=await api('/api/ot-reason?date='+ds);var el=document.getElementById('ot-reason-txt');if(el)el.textContent=r.reason||'无';}catch(e){var el2=document.getElementById('ot-reason-txt');if(el2)el2.textContent='无'}},100);const recs=await api('/api/attendance/records?date='+ds);document.getElementById('records-content').innerHTML=recs.length?recs.map((r,i)=>`<div class="info-row"><span>#${i+1}</span><span>${r.time}</span>${r.remark?`<span style="font-size:11px;color:var(--text-sec);font-style:italic">${r.remark}</span>`:''}</div>`).join(''):'当天无打卡记录';try{const cr=await api('/api/car/records?from='+ds+'&to='+ds);document.getElementById('car-day-content').innerHTML=cr.length?cr.map(r=>`<div class="info-row"><span style="color:${r.direction==='出'?'var(--blue)':'var(--green)'}">${r.direction}</span><span>${r.time}</span><button class="btn btn-sm btn-outline" style="padding:1px 4px;font-size:10px" onclick="editCar('${r.ch_id}','${r.time}','${r.direction}','${r.date}')">✏</button></div>`).join(''):'当天无车辆出入'}catch(e){document.getElementById('car-day-content').innerHTML='加载失败'}if(day.card_count>0){document.getElementById('punch-card').style.display='block';const isR=day.is_rest||day.type==='补班日';const cards=isR?[{label:'卡1 早上',idx:0},{label:'卡2 中午',idx:1},{label:'卡3 中午',idx:2},{label:'卡4 下午',idx:3},{label:'卡5 晚上',idx:5}]:[{label:'卡1 早上',idx:0},{label:'卡4 下午',idx:3},{label:'卡5 晚上',idx:5}];document.getElementById('punch-buttons').innerHTML=cards.map(c=>`<button class="btn btn-outline btn-sm" style="width:100%;margin-bottom:4px" onclick="punchCard(${c.idx},'${c.label}')">${c.label}</button>`).join('');const missing=day.required_cards-day.card_count;document.getElementById('ai-punch-tip').textContent=day.missed?`🐱 缺${missing}次打卡，建议补卡`:'🐱 打卡已齐全 ✓'}else document.getElementById('punch-card').style.display='none';let aiP=[];if(day.overtime_hours>0)aiP.push('加班'+day.overtime_hours.toFixed(1)+'h');if(day.missed)aiP.push('⚠漏打卡');if(!day.overtime_hours&&!day.missed)aiP.push(day.is_rest?'休息日🎉':'准时下班👍');let tip=day.overtime_hours>=3?'辛苦了！':(day.missed?'快去补卡！':(day.is_rest?'好好休息~':'效率很棒！'));document.getElementById('ai-daily').innerHTML=`🐱 ${day.type} | ${aiP.join('，')} | ${tip}`}







async function editOtReason(ds){var r='';try{var d=await api('/api/ot-reason?date='+ds);r=d.reason||''}catch(e){}M(`<div class="modal-title">编辑加班理由</div><div style="font-size:12px;color:var(--text-sec);margin-bottom:8px">日期: ${ds}</div><textarea id="ot-reason-editor" style="width:100%;height:80px;resize:vertical">${r.replace(/</g,'&lt;')}</textarea><div class="modal-actions"><button class="btn btn-outline" onclick="CM()">取消</button><button class="btn btn-primary" onclick="saveOtReason('${ds}')">保存</button></div>`)}







async function saveOtReason(ds){var v=document.getElementById('ot-reason-editor').value;await api('/api/ot-reason',{method:'POST',body:JSON.stringify({date:ds,reason:v})});CM();var el=document.getElementById('ot-reason-txt');if(el)el.textContent=v||'无'}















async function punchCard(idx,label){const ds=S.selectedDate;const[recs,remarks]=await Promise.all([api('/api/attendance/records?date='+ds),api('/api/punch/remarks')]);const et=recs.map(r=>r.remark?`${r.time}(${r.remark.slice(-10)})`:r.time).join(', ')||'无';var cfg=S.userConfig||{};var ls=cfg.lunch_start||'12:05',le=cfg.lunch_end||'13:05',ds2=cfg.dinner_start||'17:30',de=cfg.dinner_end||'18:00';var lsp=ls.split(':'),lep=le.split(':'),dsp=ds2.split(':'),dep=de.split(':');var tr={0:'08:00-08:30',1:ls+'-'+le,2:ls+'-'+le,3:ds2+'-'+de,5:'20:30-22:00'};var ranges={0:[8,0,8,30],1:[parseInt(lsp[0]),parseInt(lsp[1]),parseInt(lep[0]),parseInt(lep[1])],2:[parseInt(lsp[0]),parseInt(lsp[1]),parseInt(lep[0]),parseInt(lep[1])],3:[parseInt(dsp[0]),parseInt(dsp[1]),parseInt(dep[0]),parseInt(dep[1])],5:[20,30,22,0]};const ri={0:0,1:1,2:2,3:3,5:4}[idx]||0;const[sh,sm,eh,em]=ranges[Object.keys(ranges)[ri].split(',').map(Number)]||[8,0,8,30];const ts=Math.floor(Math.random()*(eh*3600+em*60-sh*3600-sm*60))+sh*3600+sm*60;const hh=Math.floor(ts/3600),mm=Math.floor((ts%3600)/60),ss=ts%60;const dt=`${String(hh).padStart(2,'0')}:${String(mm).padStart(2,'0')}:${String(ss).padStart(2,'0')}`;M(`<div class="modal-title">补卡 - ${label}</div><div style="font-size:13px;color:var(--text-sec)">日期: ${ds}</div><div style="margin:8px 0;font-size:12px;color:var(--text-sec);font-style:italic" id="punch-ai-tip">🐱 分析中...</div><div style="margin:8px 0"><label style="font-size:12px">补卡时间 (HH:MM:SS):</label><br><input type="time" step="1" id="punch-time" value="${dt}" style="width:100%;margin-top:4px"></div><div style="margin:8px 0"><label style="font-size:12px">打卡位置:</label><br><select id="punch-remark" style="width:100%;margin-top:4px">${remarks.map(r=>`<option>${r}</option>`).join('')}</select></div><div style="font-size:11px;color:var(--text-third)">已打卡: ${et}</div><div class="modal-actions"><button class="btn btn-outline" onclick="CM()">取消</button><button class="btn btn-primary" onclick="doPunch('${ds}')">确认补卡</button></div>`);setTimeout(async()=>{try{const ai=await api('/api/ai/chat',{method:'POST',body:JSON.stringify({prompt:'补'+label+',范围'+tr[idx]+',已有打卡['+et+']',max_tokens:40})});if(ai&&ai.reply){const el=document.getElementById('punch-ai-tip');if(el)el.textContent='🐱 '+ai.reply}}catch(e){}},10)}







async function doPunch(ds){const t=document.getElementById('punch-time').value,r=document.getElementById('punch-remark').value;const res=await api('/api/punch',{method:'POST',body:JSON.stringify({date:ds,time:t,remark:r})});CM();alert(res.success?`✅ 补卡成功 ${t}`:`❌ ${res.msg}`);loadAttendance()}







async function prevMonth(){const d=new Date(S.currentMonth);d.setMonth(d.getMonth()-1);S.currentMonth=d;const data=await api('/api/attendance/month?date='+d.toISOString().split('T')[0]);S.attendanceData=data;document.getElementById('month-label').textContent=data.month_label||'';const newDates=Object.keys(data.days||{}).sort();if(newDates.length&&!data.days[S.selectedDate])S.selectedDate=newDates[0];renderCalendar()}







async function nextMonth(){const d=new Date(S.currentMonth);d.setMonth(d.getMonth()+1);S.currentMonth=d;const data=await api('/api/attendance/month?date='+d.toISOString().split('T')[0]);S.attendanceData=data;document.getElementById('month-label').textContent=data.month_label||'';const newDates=Object.keys(data.days||{}).sort();if(newDates.length&&!data.days[S.selectedDate])S.selectedDate=newDates[0];renderCalendar()}







function goToday(){S.selectedDate=new Date().toISOString().split('T')[0];S.currentMonth=new Date();loadAttendance()}







async function closeSettingsAndSave(){saveSettings();try{await loadAttendance()}catch(e){};var el=document.getElementById('settings-overlay');if(el)el.remove()}







function setTab(id){S.settingsTab=id;openSettings()}







async function openSettings(){var u=await api('/api/user/config');var o=document.createElement('div');o.style.cssText='position:fixed;top:0;left:0;right:0;bottom:0;z-index:9999;background:var(--bg);display:flex';o.id='settings-overlay';S.settingsTab=S.settingsTab||'basic';S._saved=false;var tabs=[{id:'basic',icon:'👤',label:'基本信息'},{id:'remind',icon:'🔔',label:'提醒设置'},{id:'ai',icon:'🤖',label:'AI助手'},{id:'safe',icon:'🔒',label:'安全'}];var nav='';tabs.forEach(function(t){var sel=S.settingsTab===t.id;nav+='<div onclick="setTab(\x27'+t.id+'\x27)" style="padding:10px 16px;margin:2px 8px;border-radius:8px;cursor:pointer;font-size:13px;'+(sel?'background:var(--blue-light);color:var(--blue);font-weight:bold':'color:var(--text-sec)')+'">'+t.icon+' '+t.label+'</div>'});o.innerHTML='<div style="width:200px;background:var(--white);border-right:1px solid var(--border);padding:24px 0;display:flex;flex-direction:column;flex-shrink:0"><div style="padding:0 16px 20px;display:flex;align-items:center;gap:12px"><img id="set-avatar" src="'+(u.avatar||'cat_icon.png')+'" style="width:40px;height:40px;border-radius:20px;object-fit:cover"><div><div style="font-size:13px;font-weight:bold">'+(u.empname||'未设置')+'</div><div style="font-size:10px;color:var(--text-third)">工号 1103141</div></div></div><div style="flex:1">'+nav+'</div><button class="btn btn-outline" id="settings-back-btn" onclick="saveSettings();loadAttendance();var e=document.getElementById(\x27settings-overlay\x27);if(e)e.remove()" style="margin:8px;justify-content:center">← 返回</button></div><div style="flex:1;overflow-y:auto;padding:32px 40px" id="settings-right">'+buildSettingsPanel(u,S.settingsTab)+'</div>';document.body.appendChild(o)}







function buildSettingsPanel(u,tab){







  var m=(u.ai_model||S.aiModel||'deepseek-v4-flash');







  var p=(u.ai_persona||S.aiPersona||'warm');







  if(tab==='basic')return '<div style="font-size:20px;font-weight:bold;margin-bottom:24px">基本信息</div><div style="background:var(--white);border-radius:12px;border:1px solid var(--border);padding:24px"><div style="margin-bottom:16px"><label style="font-size:12px;color:var(--text-sec);display:block;margin-bottom:6px">工号</label><input type="text" value="1103141" disabled style="background:var(--bg);color:var(--text-third)"></div><div style="margin-bottom:16px"><label style="font-size:12px;color:var(--text-sec);display:block;margin-bottom:6px">姓名</label><input type="text" id="set-name" value="'+(u.empname||'')+'" placeholder="输入姓名"></div><div style="margin-bottom:16px"><label style="font-size:12px;color:var(--text-sec);display:block;margin-bottom:6px">车牌号</label><input type="text" id="set-plate" value="'+(u.car_plate||'')+'" placeholder="输入车牌号"></div><div style="margin-bottom:16px"><label style="font-size:12px;color:var(--text-sec);display:block;margin-bottom:6px">加班时薪基数 (元/小时)</label><input type="number" id="set-salary" value="'+(u.base_salary||30)+'" step="0.1" placeholder="30"></div><div style="display:flex;gap:12px;margin-bottom:16px"><div style="flex:1"><label style="font-size:12px;color:var(--text-sec);display:block;margin-bottom:6px">午休开始</label><input type="time" id="set-lunch-start" value="'+(u.lunch_start||'12:05')+'"></div><div style="flex:1"><label style="font-size:12px;color:var(--text-sec);display:block;margin-bottom:6px">午休结束</label><input type="time" id="set-lunch-end" value="'+(u.lunch_end||'13:05')+'"></div></div><div style="display:flex;gap:12px"><div style="flex:1"><label style="font-size:12px;color:var(--text-sec);display:block;margin-bottom:6px">晚饭开始</label><input type="time" id="set-dinner-start" value="'+(u.dinner_start||'17:30')+'"></div><div style="flex:1"><label style="font-size:12px;color:var(--text-sec);display:block;margin-bottom:6px">晚饭结束</label><input type="time" id="set-dinner-end" value="'+(u.dinner_end||'18:00')+'"></div></div></div>';







  if(tab==='remind')return '<div style="font-size:20px;font-weight:bold;margin-bottom:24px">提醒设置</div><div style="background:var(--white);border-radius:12px;border:1px solid var(--border);padding:24px"><div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0"><div><div style="font-size:14px">💧 喝水提醒</div><div style="font-size:11px;color:var(--text-third)">每小时提醒喝水</div></div><label style="display:inline-block;width:44px;height:24px;position:relative"><input type="checkbox" id="set-water" '+(u.water_enabled?'checked':'')+' style="opacity:0;width:0;height:0"><span style="position:absolute;top:0;left:0;right:0;bottom:0;background:'+(u.water_enabled?'var(--blue)':'#ccc')+';border-radius:24px;transition:.3s;pointer-events:none"></span></label></div><div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0"><div><div style="font-size:14px">👁 护眼提醒</div><div style="font-size:11px;color:var(--text-third)">每2小时提醒休息3分钟</div></div><label style="display:inline-block;width:44px;height:24px;position:relative"><input type="checkbox" id="set-eye" '+(u.eye_enabled?'checked':'')+' style="opacity:0;width:0;height:0"><span style="position:absolute;top:0;left:0;right:0;bottom:0;background:'+(u.eye_enabled?'var(--blue)':'#ccc')+';border-radius:24px;transition:.3s;pointer-events:none"></span></label></div><div style="margin-top:12px"><label style="font-size:12px;color:var(--text-sec);display:block;margin-bottom:6px">每杯水毫升</label><input type="number" id="set-waterml" value="'+(u.water_ml||'300')+'" placeholder="300"></div></div>';







  if(tab==='ai')return '<div style="font-size:20px;font-weight:bold;margin-bottom:24px">AI助手</div><div style="background:var(--white);border-radius:12px;border:1px solid var(--border);padding:24px"><div style="margin-bottom:16px"><label style="font-size:12px;color:var(--text-sec);display:block;margin-bottom:6px">🔑 API Key</label><input type="password" id="set-apikey" value="'+(u.api_key||'')+'" placeholder="sk-..."></div><div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0"><div><div style="font-size:14px">🤖 默认模型</div><div style="font-size:11px;color:var(--text-third)">对话使用的AI模型</div></div><select id="set-model" style="width:140px">'+['deepseek-v4-flash','deepseek-v4-pro','deepseek-chat','deepseek-reasoner'].map(function(v){var n=v==='deepseek-v4-flash'?'V4 Flash':v==='deepseek-v4-pro'?'V4 Pro':v==='deepseek-chat'?'V3':'R1';return '<option value="'+v+'"'+(m===v?' selected':'')+'>'+n+'</option>'}).join('')+'</select></div><div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0"><div><div style="font-size:14px">🐱 哈基米性格</div><div style="font-size:11px;color:var(--text-third)">暖心/毒舌</div></div><select id="set-personality" style="width:120px"><option value="warm"'+(p==='warm'?' selected':'')+'>😼 暖心</option><option value="tsundere"'+(p==='tsundere'?' selected':'')+'>😼 毒舌</option></select></div></div>';







  if(tab==='safe')return '<div style="font-size:20px;font-weight:bold;margin-bottom:24px">安全</div><div style="background:var(--white);border-radius:12px;border:1px solid var(--border);padding:24px"><div><label style="font-size:12px;color:var(--text-sec);display:block;margin-bottom:6px">新密码 (留空不修改)</label><input type="password" id="set-pw" placeholder="输入新密码"></div></div>';







  return '';







}







async function saveSettings(){try{var g=function(id){var e=document.getElementById(id);return e?e.value:null};var gc=function(id){var e=document.getElementById(id);return e?e.checked:false};var d={};var nm=g('set-name');if(nm!==null)d.empname=nm;var cp=g('set-plate');if(cp!==null)d.car_plate=cp;var bs=g('set-salary');if(bs!==null&&bs!==''){var pf=parseFloat(bs);if(!isNaN(pf))d.base_salary=pf}var wm=g('set-waterml');if(wm!==null)d.water_ml=parseInt(wm)||300;d.water_enabled=gc('set-water');d.eye_enabled=gc('set-eye');var md=g('set-model');if(md!==null){d.ai_model=md;S.aiModel=md}var ps=g('set-personality');if(ps!==null){d.ai_persona=ps;S.aiPersona=ps}var ak=g('set-apikey');if(ak!==null)d.api_key=ak;var ls=g('set-lunch-start');if(ls!==null)d.lunch_start=ls;var le=g('set-lunch-end');if(le!==null)d.lunch_end=le;var ds=g('set-dinner-start');if(ds!==null)d.dinner_start=ds;var de=g('set-dinner-end');if(de!==null)d.dinner_end=de;S.userConfig=Object.assign(S.userConfig||{},d);var pw=g('set-pw');if(pw)d.password=pw;await api('/api/user/update',{method:'POST',body:JSON.stringify(d)})}catch(e){}}







async function saveSettings(){const d={empname:document.getElementById('set-name').value,car_plate:document.getElementById('set-plate').value,base_salary:parseFloat(document.getElementById('set-salary').value)||30,water_ml:parseInt(document.getElementById('set-waterml').value)||300,water_enabled:document.getElementById('set-water').checked,eye_enabled:document.getElementById('set-eye').checked};const pw=document.getElementById('set-pw').value;if(pw)d.password=pw;await api('/api/user/update',{method:'POST',body:JSON.stringify(d)});alert('✅ 已保存');loadSettings()}







async function editCar(chId,time,direction,dateStr){const ym=dateStr.replace(/-/g,'').substring(0,6);const fullTime=time.split(' ')[1]||time;const d=dateStr;M(`<div class="modal-title">修改车辆记录</div><div style="font-size:13px;color:var(--text-sec)">${dateStr} ${fullTime} ${direction}</div><div style="margin:8px 0"><label style="font-size:12px">时间 (HH:MM:SS.FFF)</label><input type="text" id="car-edit-time" value="${fullTime}"></div><div style="margin:8px 0"><label style="font-size:12px">进出</label><select id="car-edit-dir"><option value="0" ${direction==='进'?'selected':''}>进</option><option value="1" ${direction==='出'?'selected':''}>出</option></select></div><div class="modal-actions"><button class="btn btn-outline" onclick="CM()">取消</button><button class="btn btn-primary" onclick="saveCarEdit('${chId}','${ym}','${d}')">保存</button></div>`)}







async function saveCarEdit(chId,ym,d){const t=document.getElementById('car-edit-time').value;const dir=parseInt(document.getElementById('car-edit-dir').value);const newTime=`${d} ${t}`;const res=await api('/api/car/update',{method:'POST',body:JSON.stringify({ch_id:chId,ym,new_time:newTime,new_out:dir})});CM();alert(res.success?'✅ 已修改':'❌ 失败');loadCar();updateDetail()}















// ========== 待办事项 ==========







async function loadTodos(){const d=await api('/api/todos');const today=new Date().toISOString().split('T')[0];const items=d.filter(x=>!x.done);document.getElementById('todo-content').innerHTML=`<div class="card"><div class="card-title">待办事项</div><div style="margin-bottom:8px;display:flex;gap:8px"><input type="text" id="todo-input" placeholder="输入待办内容..." style="flex:1"><input type="date" id="todo-date" value="${today}" style="width:130px"><input type="time" id="todo-time" value="09:00" style="width:100px"><button class="btn btn-primary btn-sm" onclick="addTodo()">添加</button></div><div id="todo-list">${items.length?items.map(it=>`<div class="info-row"><span style="color:${it.date===today?'var(--blue)':''}">${it.date} ${it.time}</span><span style="flex:1;margin:0 8px">${it.content}</span><button class="btn btn-success btn-sm" onclick="toggleTodo('${it.date}','${it.id}')">✓</button><button class="btn btn-danger btn-sm" onclick="delTodo('${it.date}','${it.id}')">✕</button></div>`).join(''):'<div style="color:var(--text-third);font-size:13px">暂无待办，添加一个吧~</div>'}</div></div>`}







async function addTodo(){const c=document.getElementById('todo-input').value.trim();if(!c)return alert('请输入内容');const d=document.getElementById('todo-date').value,t=document.getElementById('todo-time').value;await api('/api/todos/add',{method:'POST',body:JSON.stringify({date:d,time:t,content:c})});loadTodos()}







async function toggleTodo(date,id){await api('/api/todos/toggle',{method:'POST',body:JSON.stringify({date,id})});loadTodos()}







async function delTodo(date,id){await api('/api/todos/delete',{method:'POST',body:JSON.stringify({date,id})});loadTodos()}















// ========== 车辆出入 ==========















// ========== 喝水记录 ==========







async function loadWater(){var d=await api('/api/water/status');var cups=d.cups,ml=d.total_ml,pct=Math.min(cups/8*100,100);var target=parseInt(d.ml_per_cup)||300;var times=['08:00','09:00','11:00','13:00','15:00','17:00','19:00','21:00'];







var h='';







h+='<div class="card" style="text-align:center;padding:32px"><div style="font-size:64px;margin-bottom:8px">';







if(cups>=8)h+='🏆';else if(cups>=5)h+='💧';else if(cups>=2)h+='🥛';else h+='🍼';







h+='</div>';







h+='<div style="font-size:36px;font-weight:bold;color:var(--blue)">'+ml+'<span style="font-size:16px;color:var(--text-sec)"> / '+target*8+'ml</span></div>';







h+='<div style="font-size:14px;color:var(--text-sec);margin:4px 0 16px">'+cups+' / 8 杯 · 目标每日 '+target*8+'ml</div>';







h+='<div style="height:12px;background:#E5E6EB;border-radius:6px;overflow:hidden;max-width:360px;margin:0 auto 24px"><div style="height:100%;width:'+pct+'%;background:linear-gradient(90deg,#3370FF,#5B9BFF);border-radius:6px;transition:width 0.5s"></div></div>';







h+='<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;max-width:400px;margin:0 auto">';







times.forEach(function(t,i){







  var done=i<cups;var icon=done?'💙':'🤍';







  h+='<div onclick="punchWater('+i+')" style="padding:12px 8px;border-radius:12px;cursor:pointer;transition:all 0.2s;background:'+(done?'var(--blue-light)':'var(--bg)')+';border:2px solid '+(done?'var(--blue)':'var(--border)')+'">';







  h+='<div style="font-size:24px">'+icon+'</div>';







  h+='<div style="font-size:11px;color:var(--text-sec);margin-top:4px">'+t+'</div>';







  h+='<div style="font-size:10px;color:var(--text-third)">第'+(i+1)+'杯</div>';







  h+='</div>';







});







h+='</div>';







if(cups>=8)h+='<div style="margin-top:16px;color:var(--green);font-size:14px">🎉 今天的喝水目标已完成！太棒了！</div>';







else h+='<div style="margin-top:16px;color:var(--text-third);font-size:13px">点击水杯打卡喝水 ~</div>';







h+='</div>';







document.getElementById('water-content').innerHTML=h;







}







async function punchWater(idx){await api('/api/water/punch',{method:'POST',body:JSON.stringify({index:idx})});loadWater()}















// ========== 加班事项 ==========







async function loadOtNotes(){const days=S.attendanceData?Object.values(S.attendanceData.days).filter(d=>d.overtime_hours>0).reverse():[];var reasons={};try{var r=await api('/api/ot-reasons-bulk');reasons=r||{}}catch(e){}var h='<div class="card" style="padding:0;overflow:hidden"><div class="card-title" style="padding:16px 16px 12px">📝 本月加班</div>';if(!days.length){h+='<div style="color:var(--text-third);text-align:center;padding:32px">本月暂无加班</div></div>'}else{h+='<table style="width:100%;border-collapse:collapse;font-size:13px"><thead><tr style="color:var(--text-sec);font-size:11px;border-bottom:2px solid var(--border)"><th style="padding:10px 16px;text-align:left;width:70px">日期</th><th style="padding:10px 8px;text-align:left;width:80px">类型</th><th style="padding:10px 8px;text-align:right;width:70px">小时</th><th style="padding:10px 8px;text-align:right;width:80px">加班费</th><th style="padding:10px 16px;text-align:left">加班理由</th></tr></thead><tbody>';days.forEach(function(d,i){var ds=Object.keys(S.attendanceData.days).find(function(k){return S.attendanceData.days[k]===d})||'';var reason=reasons[ds]||'';var bg=i%2===0?'transparent':'rgba(0,0,0,0.02)';h+='<tr style="background:'+bg+';border-bottom:0.5px solid var(--border)"><td style="padding:10px 16px;font-weight:bold;white-space:nowrap">'+ds.slice(-5)+'</td><td style="padding:10px 8px"><span class="tag '+(d.type.indexOf('休息日')>=0?'tag-orange':d.type.indexOf('补班')>=0?'tag-blue':'tag-green')+'">'+d.type+'</span></td><td style="padding:10px 8px;text-align:right;font-family:monospace">'+d.overtime_hours.toFixed(1)+'h</td><td style="padding:10px 8px;text-align:right;font-weight:bold;color:var(--blue);white-space:nowrap">¥'+d.overtime_pay.toFixed(2)+'</td><td style="padding:10px 16px;font-size:12px;color:var(--text-sec);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="'+reason+'">'+reason+'</td></tr>'});h+='</tbody></table></div>'}document.getElementById('ot-notes-content').innerHTML=h}















// ========== 摸鱼中心 ==========







async function loadFun(){const moods=await api('/api/fun/moods');const ach=await api('/api/fun/achievements');const today=new Date().toISOString().split('T')[0];const moodEmojis=['😊','😎','🥱','😫','😤','🤬','😭','🤩','🥳','😐','🤯','❤'];const next5=new Date();next5.setMonth(next5.getMonth()+1);next5.setDate(5);if(next5<=new Date())next5.setMonth(next5.getMonth()+1);const daysToPay=Math.ceil((next5-new Date())/86400000);document.getElementById('fun-content').innerHTML=`<div class="grid2"><div class="card" style="text-align:center"><div class="card-title">💰 发薪倒计时</div><div style="font-size:28px;color:var(--orange);font-weight:bold">${daysToPay}天</div><div style="font-size:12px;color:var(--text-third)">距离${next5.getFullYear()}-${String(next5.getMonth()+1).padStart(2,'0')}-05</div></div><div class="card" style="text-align:center"><div class="card-title">⏲ 番茄钟</div><div style="font-size:36px;color:var(--blue);font-weight:bold" id="pomodoro">25:00</div><div style="font-size:12px;color:var(--text-third);margin-bottom:8px" id="pomo-status">准备开始</div><div style="display:flex;gap:4px;justify-content:center"><button class="btn btn-sm btn-primary" onclick="startPomo()">▶</button><button class="btn btn-sm btn-outline" onclick="pausePomo()">⏸</button><button class="btn btn-sm btn-outline" onclick="resetPomo()">⏹</button></div></div></div><div class="card"><div class="card-title">😊 心情日历</div><div style="margin-bottom:8px">${moodEmojis.map(m=>`<span class="mood-btn${moods.current===m?' selected':''}" onclick="setMood('${m}')">${m}</span>`).join('')}</div><div style="font-size:12px;color:var(--text-sec)">近7天: ${Object.entries(moods.recent||{}).map(([k,v])=>`${k.slice(-5)} ${v||'❓'}`).join(' ')}</div></div><div class="card"><div class="card-title">🏆 成就徽章</div>${(ach.achievements||[]).map(a=>`<div style="display:inline-block;padding:4px 8px;margin:4px;border-radius:8px;background:${(ach.unlocked||[]).includes(a.key)?'var(--blue-light)':'var(--bg)'};font-size:12px">${a.icon} ${a.name}</div>`).join('')}</div>`}







async function setMood(m){await api('/api/fun/mood',{method:'POST',body:JSON.stringify({mood:m})});loadFun()}







let pomo={running:false,paused:false,seconds:25*60,total:25*60,timer:null};







function startPomo(){if(pomo.running)return;pomo.running=true;pomo.paused=false;document.getElementById('pomo-status').textContent='专注中...';pomo.timer=setInterval(()=>{if(pomo.paused)return;pomo.seconds--;const m=Math.floor(pomo.seconds/60),s=pomo.seconds%60;document.getElementById('pomodoro').textContent=`${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;if(pomo.seconds<=0){clearInterval(pomo.timer);pomo.running=false;document.getElementById('pomodoro').textContent='00:00';document.getElementById('pomo-status').textContent='⏰ 时间到!';}},1000)}







function pausePomo(){pomo.paused=!pomo.paused;document.getElementById('pomo-status').textContent=pomo.paused?'已暂停':'继续中...'}







function resetPomo(){clearInterval(pomo.timer);pomo.running=false;pomo.seconds=25*60;document.getElementById('pomodoro').textContent='25:00';document.getElementById('pomo-status').textContent='准备开始'}















// ========== 知识库 ==========







function loadKB(){document.getElementById('kb-content').innerHTML=`<div class="card"><div class="card-title">📚 公司知识库</div><div style="color:var(--text-third);font-size:13px">知识库功能开发中，请使用原 Flet 版本上传文档。<br>上传后在哈基米 AI 中自动检索回答。</div></div>`}















// ========== 哈基米 AI 浮窗 ==========







var aiOpen=false;







async function openAIChat(){







  if(aiOpen){closeAIChat();return}







  var p=S.aiPersona||'warm';







  var models=[{v:'deepseek-v4-flash',l:'V4 Flash'},{v:'deepseek-v4-pro',l:'V4 Pro'},{v:'deepseek-chat',l:'V3'},{v:'deepseek-reasoner',l:'R1'}];







  var quicks=['📝周报','📔日记','🔮算命','📊分析','⚠漏打卡','💡摸鱼'];







  var o=document.createElement('div');o.id='ai-chat-panel';







  o.style.cssText='position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);width:560px;height:620px;z-index:9998;background:rgba(255,255,255,0.85);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-radius:16px;box-shadow:0 12px 60px rgba(0,0,0,0.15);display:flex;flex-direction:column;overflow:hidden;border:1px solid rgba(255,255,255,0.3)'







  o.innerHTML='<div style="padding:14px 18px;border-bottom:1px solid rgba(0,0,0,0.06);display:flex;align-items:center;gap:10px;flex-shrink:0;background:rgba(255,255,255,0.5)"><span style="font-weight:bold;font-size:16px">🐱 哈基米</span><span style="font-size:11px;color:var(--text-third)">'+(p==='warm'?'😼暖心':'😼毒舌')+' · '+(S.aiModel||'V4 Flash')+'</span><div style="flex:1"></div><button class="btn btn-sm btn-outline" onclick="closeAIChat();openSettings()" style="font-size:13px">⚙</button><button class="btn btn-sm btn-outline" onclick="closeAIChat()" style="font-size:18px;padding:2px 10px;border-radius:8px">✕</button></div><div style="display:flex;flex-wrap:wrap;gap:4px;padding:10px 14px;border-bottom:1px solid rgba(0,0,0,0.06);flex-shrink:0;background:rgba(255,255,255,0.3)">'+quicks.map(function(q){return '<span class="chip" onclick="quickAIChat(\''+q+'\')">'+q+'</span>'}).join('')+'</div><div id="ai-chat-list" style="flex:1;overflow-y:auto;padding:14px"></div><div style="padding:10px 14px;border-top:1px solid rgba(0,0,0,0.06);display:flex;gap:8px;flex-shrink:0;background:rgba(255,255,255,0.5)"><input type="text" id="ai-chat-input" placeholder="问哈基米..." style="flex:1" onkeydown="if(event.key===\'Enter\')sendAIChat()"><button class="btn btn-primary btn-sm" onclick="sendAIChat()">发送</button></div>';







  document.body.appendChild(o);







  aiOpen=true;







}







function closeAIChat(){var p=document.getElementById('ai-chat-panel');if(p)p.remove();aiOpen=false}







async function sendAIChat(){







  var inp=document.getElementById('ai-chat-input');var q=inp.value.trim();if(!q)return;inp.value='';







  var cl=document.getElementById('ai-chat-list');







  cl.innerHTML+='<div class="chat-msg user">'+q.replace(/</g,'&lt;')+'</div>';







  var thinkId='ai-think-'+Date.now();







  cl.innerHTML+='<div class="chat-msg ai" id="'+thinkId+'" style="font-size:11px;color:var(--text-third);font-style:italic">🐱 哈基米思考中...</div>';







  cl.scrollTop=cl.scrollHeight;







  // 模拟思考更新







  var dots=0;







  var thinkTimer=setInterval(function(){dots=(dots+1)%4;var td=document.getElementById(thinkId);if(td)td.textContent='🐱 哈基米思考中'+'.'.repeat(dots)},500);







  try{







    var model=S.aiModel||'deepseek-v4-flash';







    var r=await api('/api/ai/chat',{method:'POST',body:JSON.stringify({prompt:q,model:model,use_tools:true,personality:S.aiPersona||'warm'})});







    clearInterval(thinkTimer);







    var td=document.getElementById(thinkId);if(td)td.remove();







    var steps='';







    if(r.thinking&&r.thinking.length)steps='<div style="font-size:11px;color:var(--text-third);margin-bottom:6px;font-style:italic">'+r.thinking.map(function(s){return '🔧 '+s}).join('<br>')+'</div>';







    cl.innerHTML+=steps+'<div class="chat-msg ai">'+(r.reply||'🐱 哈基米卡住了...').replace(/\n/g,'<br>')+'</div>';







    cl.scrollTop=cl.scrollHeight;







  }catch(e){







    clearInterval(thinkTimer);







    var td=document.getElementById(thinkId);if(td)td.textContent='🐱 出错了: '+e.message;







  }







}







function quickAIChat(tag){







  var prompts={'📝周报':'帮我写一份本周工作总结，包含加班情况','📔日记':'用猫咪第一人称视角，根据考勤数据写一篇打工日记，100字','🔮算命':'根据加班模式，算算今天加班概率？幽默玄学','📊分析':'分析本月考勤数据，给优化建议','⚠漏打卡':'列出本月所有漏打卡日期','💡摸鱼':'推荐最佳摸鱼时间段'};







  var inp=document.getElementById('ai-chat-input');inp.value=prompts[tag]||'';sendAIChat()







}















// ========== 全局 ==========







function showToast(msg){var t=document.createElement('div');t.textContent=msg;t.style.cssText='position:fixed;top:20px;left:50%;transform:translateX(-50%);z-index:99999;background:#333;color:#fff;padding:10px 24px;border-radius:10px;font-size:14px;opacity:1;transition:opacity 0.4s;pointer-events:none';document.body.appendChild(t);setTimeout(function(){t.style.opacity='0';setTimeout(function(){if(t.parentNode)t.parentNode.removeChild(t)},400)},2000)}





function getFestiveEmoji(name){for(var k in holidayEmoji){if(name&&name.indexOf(k)>=0)return holidayEmoji[k]}return''}





function spawnCoinRain(ds){  var td=document.querySelector('td[onclick*="'+ds+'"]');  if(!td)return;var rect=td.getBoundingClientRect();  var emojis=['💰','💵','💎','💴','🪙'];  for(var i=0;i<8;i++){(function(j){    setTimeout(function(){      var e=document.createElement('span');e.textContent=emojis[j%emojis.length];      e.style.cssText='position:fixed;z-index:9999;font-size:18px;pointer-events:none;transition:all 1.2s ease-in;left:'+(rect.left+rect.width/2+Math.random()*60-30)+'px;top:'+rect.top+'px;opacity:1';      document.body.appendChild(e);      requestAnimationFrame(function(){e.style.top=(rect.top+100+Math.random()*80)+'px';e.style.opacity='0';e.style.transform='rotate('+(Math.random()*360)+'deg)'});      setTimeout(function(){if(e.parentNode)e.parentNode.removeChild(e)},1300);    },j*100)  })(i)}}





function toggleTag(tag){var el=document.getElementById('capsule-note');if(!el)return;var v=el.value;if(v.indexOf(tag)>=0){el.value=v.replace(tag,'').replace(/\s+/g,' ').trim()}else{el.value=(v?', ':'')+tag;el.value=el.value.replace(/^, /,'')}el.dispatchEvent(new Event('input'))}





async function loadCapsuleOverview(){  var m=S.currentMonth?S.currentMonth.toISOString().slice(0,7):new Date().toISOString().slice(0,7);  var caps={};try{caps=await api('/api/capsule/month?month='+m)}catch(e){}  var ma=S.moodAnalysis||{};var pressure=ma.pressure||0;  var entries=[];for(var k in caps)entries.push({date:k,mood:caps[k]});entries.sort(function(a,b){return a.date<b.date?1:-1});  var moodEmojis=['😊','😤','😭','😴','🥳','🤩','😰','😡'];var moodNames={};  var h='<div class="card" style="padding:0;overflow:hidden"><div class="card-title" style="padding:16px 16px 12px">📅 时间胶囊 - '+m+'</div>';  // 压力概览?  h+='<div style="padding:12px 16px;border-bottom:1px solid var(--border)">';  h+='<div style="display:flex;align-items:center;gap:12px">';  h+='<div style="font-size:32px">'+pressure+'</div>';  h+='<div><div style="font-size:14px;font-weight:bold">压力指数 /10</div><div style="font-size:11px;color:var(--text-third)">'+ma.smart_advice+'</div></div>';  h+='</div></div>';  // 心情时间线?  if(!entries.length)h+='<div style="text-align:center;padding:32px;color:var(--text-third)">">你还没有心情记录，点日历格子的时间胶囊开始吧~</div>';  else h+='<table style="width:100%;border-collapse:collapse;font-size:13px"><thead><tr style="color:var(--text-sec);font-size:11px;border-bottom:2px solid var(--border)"><th style="padding:10px 16px;text-align:left;width:80px">日期</th><th style="padding:10px 8px;text-align:center;width:60px">心情</th><th style="padding:10px 16px;text-align:left">事件</th></tr></thead><tbody>';  entries.forEach(function(e,i){    var bg=i%2===0?'transparent':'rgba(0,0,0,0.02)';    var moodShow=e.mood||'';    // 多种显示：取最高分    if(moodShow.indexOf(':')>=0){var bestE='',bestV=0;moodShow.split(' ').forEach(function(p){if(p.indexOf(':')>=0){var kv=p.split(':');var vv=parseInt(kv[1])||0;if(vv>bestV){bestV=vv;bestE=kv[0]}}});moodShow=bestE+''+bestV}    h+='<tr style="background:'+bg+';border-bottom:0.5px solid var(--border)"><td style="padding:10px 16px;font-weight:bold">'+e.date.slice(-5)+'</td><td style="padding:10px 8px;text-align:center;font-size:22px">'+moodShow+'</td><td style="padding:10px 16px;font-size:12px;color:var(--text-sec)">加载中..</td></tr>'  });  h+='</tbody></table>';  h+='</div>';  document.getElementById('capsule-overview-content').innerHTML=h;};  // 异步加载笔记;async function loadNotes(){entries.forEach(function(e,i){    setTimeout(async function(){      try{var c=await api('/api/capsule?date='+e.date);var note=c.note||''; var rows=document.querySelectorAll('#capsule-overview-content tbody tr');      if(rows[i])rows[i].cells[2].textContent=note.substring(0,40)+(note.length>40?'...':'')      }catch(e){}    },i*100)  }}};var note=c.note||'';      var rows=document.querySelectorAll('#capsule-overview-content tbody tr');      if(rows[i])rows[i].cells[2].textContent=note.substring(0,40)+(note.length>40?'...':'')      }catch(e){}    },i*100)  });}





async function loadMoodMap(){if(_loadingMood)return;_loadingMood=true;try{var m=S.currentMonth?S.currentMonth.toISOString().slice(0,7):new Date().toISOString().slice(0,7);S.moodMap=await api('/api/capsule/month?month='+m);renderCalendar()}catch(e){}finally{_loadingMood=false}}





async function loadWeather(){try{var m=S.currentMonth?S.currentMonth.toISOString().slice(0,7):new Date().toISOString().slice(0,7);S.weatherMap=await api('/api/weather/month?month='+m)}catch(e){}}





function moodAdd(em){  if(!_moodVals[em])_moodVals[em]=0;  if(_moodVals[em]<10)_moodVals[em]=Math.min(_moodVals[em]+1,10);  var v=_moodVals[em],el=document.getElementById('mv-'+em);if(el)el.textContent=v;  var mc=document.getElementById('mc-'+em);var icon=mc.querySelector('span');  var sc=1+v*0.12;  icon.style.transform='scale('+sc+')';  if(v>=10){icon.style.textShadow='0 0 8px #FFD700, 0 0 16px #FFD700, 0 0 32px #FFA500, 0 0 48px #FFA500';icon.style.filter='brightness(1.3)'}else{icon.style.textShadow='';icon.style.filter=''}  var barEl=mc.querySelector('.bar-fill');if(barEl)barEl.style.width=(v*10)+'%';  // 粒子  var rect=icon.getBoundingClientRect();var cnt=Math.min(v,10);  for(var i=0;i<cnt;i++){(function(j){    setTimeout(function(){      var p=document.createElement('span');p.textContent=em;      var fromSz=10,toSz=16+v*2;      p.style.cssText='position:fixed;z-index:9999;font-size:'+fromSz+'px;pointer-events:none;transition:all 0.5s ease-out;left:'+(rect.left+Math.random()*30-15)+'px;top:'+rect.top+'px;opacity:1';      document.body.appendChild(p);      requestAnimationFrame(function(){requestAnimationFrame(function(){        p.style.top=(rect.top-20-Math.random()*50)+'px';p.style.left=(rect.left+Math.random()*60-30)+'px';        p.style.opacity='0';p.style.fontSize=toSz+'px'      })});      setTimeout(function(){if(p.parentNode)p.parentNode.removeChild(p)},600)    },j*30)  })(i)}  // // 同时 S._moodPick  var pkParts=[];for(var k in _moodVals)if(_moodVals[k]>0)pkParts.push(k+':'+_moodVals[k]);S._moodPick=pkParts.join(' ')}





function moodReset(em){_moodVals[em]=0;var el=document.getElementById('mv-'+em);if(el)el.textContent='0';var mc=document.getElementById('mc-'+em);if(mc){var icon=mc.querySelector('span');icon.style.transform='scale(1)';icon.style.textShadow='';icon.style.filter='';var barEl=mc.querySelector('.bar-fill');if(barEl)barEl.style.width='0%'};var parts=[];for(var k in _moodVals)if(_moodVals[k]>0)parts.push(k+':'+_moodVals[k]);S._moodPick=parts.join(' ')}





async function saveCapsule(ds){var note=document.getElementById('capsule-note').value;var mood=S._moodPick||(S.capsuleData&&S.capsuleData.mood?S.capsuleData.mood:'');S.capsuleData={mood:mood,note:note};await api('/api/capsule',{method:'POST',body:JSON.stringify({date:ds,mood:mood,note:note})});try{var ma=await api('/api/mood/analysis');S.moodAnalysis=ma;showMoodAdvice()}catch(e){}loadMoodMap()}





function showMoodAdvice(){if(!S.moodAnalysis)return;var a=S.moodAnalysis;var el=document.getElementById('ai-daily');if(el&&a.smart_advice)el.innerHTML='🐱 '+a.smart_advice}











async function init(){try{const q=await api('/api/quote');document.getElementById('quote-text').textContent=q.quote}catch(e){}try{const u=await api('/api/user/config');document.getElementById('avatar').src=u.avatar||'cat_icon.png';S.userConfig=u}catch(e){}try{var r=await api('/api/weather');document.getElementById('weather').textContent=r.weather||'🌤 26°C'}catch(e){document.getElementById('weather').textContent='🌤 26°C'}await loadAttendance();var quotes=['喵~ 今天也是元气满满的一天！','代码写累了就喝口水吧~','劳逸结合，摸鱼也是生产力！','你已经很棒了，别忘了休息哦~','滴，摸鱼卡！喵~','主人，你的颈椎需要活动一下了~','距离下班还有一小会儿，坚持住！','打工人的浪漫，就是准时下班~','今天的水喝够了吗？💧','做不完的明天再做，别太累~'];document.getElementById('bottom-ai').textContent='🐱 '+quotes[Math.floor(Math.random()*quotes.length)];setInterval(function(){document.getElementById('bottom-ai').textContent='🐱 '+quotes[Math.floor(Math.random()*quotes.length)]},300000);setInterval(()=>{const now=new Date();if(now.getDay()>=6){document.getElementById('countdown').textContent='🎉 周末快乐!';return}const off=new Date(now);off.setHours(18,0,0,0);if(now>=off){document.getElementById('countdown').textContent='已下班! 🏃';return}const diff=off-now,h=Math.floor(diff/3600000),m=Math.floor((diff%3600000)/60000),s=Math.floor((diff%60000)/1000);document.getElementById('countdown').textContent=`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`},1000);document.getElementById('bottom-status').textContent='已就绪'}







init();







