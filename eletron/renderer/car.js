// 车辆出入 — 工具函数
function formatDate(d){return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')}
function setCarCompanyMonth(tab){
  var n=new Date(),y=n.getFullYear(),m=n.getMonth(),d=n.getDate();
  if(!S.carF)S.carF={};if(!S.carF[tab])S.carF[tab]={};
  if(d>=24){S.carF[tab].from=formatDate(new Date(y,m,24));S.carF[tab].to=formatDate(new Date(y,m+1,23))}
  else{S.carF[tab].from=formatDate(new Date(y,m-1,24));S.carF[tab].to=formatDate(new Date(y,m,23))}
  S.carF[tab].mode='range';loadCar()
}
// 车辆出入 — 辅助函数
function buildCarSubTabs(tab, abnCount) {
  var r = '';
  r += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">';
  r += '<div style="display:flex;background:var(--white);border-radius:10px;border:1px solid var(--border);overflow:hidden;flex:1">';
  var tabs = [
    {id:'records',label:'🚗 全部记录',color:'var(--blue)'},
    {id:'abnormal',label:'⚠ 异常',color:'var(--red)'},
    {id:'timeline',label:'⏱ 轨迹',color:'var(--orange)'}
  ];
  tabs.forEach(function(t){
    var sel = tab===t.id;
    r += '<div onclick="S.carTab=\''+t.id+'\';loadCar()" style="flex:1;text-align:center;padding:12px;cursor:pointer;font-size:14px;';
    r += sel?'background:'+t.color+';color:white;font-weight:bold':'background:var(--white);color:var(--text-sec)';
    r += '">'+t.label;
    if(t.id==='abnormal'&&abnCount>0) r += ' <span style="background:rgba(255,255,255,0.3);border-radius:10px;padding:1px 7px;font-size:11px;margin-left:4px">'+abnCount+'</span>';
    r += '</div>';
  });
  r += '</div></div>';
  return r;
}

function buildCarRecords(data, punchTimes) {
  var pt = punchTimes || {};
  var h = '<div style="max-height:500px;overflow-y:auto">';
  if (!data || !data.length) return h + '<div style="color:var(--text-third);text-align:center;padding:32px">暂无记录</div></div>';

  var byDate = {};
  data.forEach(function(r) {
    var d = r.date || r.time.split(' ')[0];  // 用完整日期 YYYY-MM-DD
    if (!byDate[d]) byDate[d] = { date: d, 'in': [], out: [] };
    if (r.direction === '进') byDate[d]['in'].push(r);
    else byDate[d].out.push(r);
  });
  // 进和出各自按时间从早到晚排序
  Object.keys(byDate).forEach(function(d) {
    byDate[d]['in'].sort(function(a,b){return a.time.localeCompare(b.time)});
    byDate[d].out.sort(function(a,b){return a.time.localeCompare(b.time)});
  });

  var dates = Object.keys(byDate).sort().reverse();
  var days = ['日', '一', '二', '三', '四', '五', '六'];

  dates.forEach(function(d) {
    var day = byDate[d];
    var max = Math.max(day['in'].length, day.out.length, 1);
    h += '<div style="border-bottom:1px solid var(--border)">';
    var p = pt[d];
    var dtLabel = ''; var dtColor = 'var(--text-sec)';
    if (p && p.day_type) {
      var t = p.day_type;
      if (t.indexOf('休息日')>=0) dtColor = 'var(--orange)';
      else if (t.indexOf('补班')>=0 || t.indexOf('调休')>=0) dtColor = '#E67E22';
      else if (t.indexOf('节假日')>=0) dtColor = 'var(--red)';
      else dtColor = 'var(--text-sec)';
      dtLabel = ' <span style="font-weight:normal;color:'+dtColor+';font-size:10px">· '+t+'</span>';
    }
    var extra = p && p.earliest ? ' <span style="font-weight:normal;color:#8F959E;font-size:10px">| <span style="color:#34C759">⏱ '+p.earliest+'</span> ~ <span style="color:#3370FF">'+p.latest+'</span></span>' : '';
    h += '<div style="padding:8px 16px;font-size:12px;color:var(--text-sec);font-weight:bold;background:var(--bg)">' + d + ' 周' + days[new Date(d + 'T00:00:00').getDay()] + dtLabel + extra + '</div>';
    for (var i = 0; i < max; i++) {
      h += '<div style="display:flex;padding:6px 16px;' + (i < max - 1 ? 'border-bottom:0.5px solid var(--border)' : '') + '">';
      h += '<div style="flex:1;display:flex;align-items:center;gap:8px">';
      if (day['in'][i]) {
        h += '<span style="display:inline-block;width:28px;height:22px;line-height:22px;text-align:center;border-radius:5px;font-size:10px;font-weight:bold;background:#E8F5E9;color:var(--green)">进</span>';
        h += '<span style="font-family:monospace;font-size:12px">' + (day['in'][i].time.split(' ')[1] || '') + '</span>';
        h += '<button class="btn btn-sm btn-outline" style="padding:1px 6px;font-size:10px" onclick="editCar(\'' + day['in'][i].ch_id + '\',\'' + day['in'][i].time + '\',\'进\',\'' + d + '\')">✏</button>';
      }
      h += '</div>';
      h += '<div style="flex:1;display:flex;align-items:center;gap:8px;border-left:1px solid var(--border);padding-left:16px">';
      if (day.out[i]) {
        h += '<span style="display:inline-block;width:28px;height:22px;line-height:22px;text-align:center;border-radius:5px;font-size:10px;font-weight:bold;background:#E8F0FE;color:var(--blue)">出</span>';
        h += '<span style="font-family:monospace;font-size:12px">' + (day.out[i].time.split(' ')[1] || '') + '</span>';
        h += '<button class="btn btn-sm btn-outline" style="padding:1px 6px;font-size:10px" onclick="editCar(\'' + day.out[i].ch_id + '\',\'' + day.out[i].time + '\',\'出\',\'' + d + '\')">✏</button>';
      }
      h += '</div></div>';
    }
    h += '</div>';
  });
  h += '</div>';
  return h;
}

function buildCarAbnormal(data, punchTimes) {
  var pt = punchTimes || {};
  var h = '<div style="max-height:500px;overflow-y:auto">';
  if (!data || !data.length) return h + '<div style="color:var(--green);text-align:center;padding:32px">🎉 暂无异常</div></div>';

  var byDate = {};
  data.forEach(function(r) {
    var d = r.date || r.time.split(' ')[0];
    if (!byDate[d]) byDate[d] = { date: d, 'in': [], out: [] };
    if (r.direction === '进') byDate[d]['in'].push(r);
    else byDate[d].out.push(r);
  });
  // 进和出各自按时间排序
  Object.keys(byDate).forEach(function(d) {
    byDate[d]['in'].sort(function(a,b){return a.time.localeCompare(b.time)});
    byDate[d].out.sort(function(a,b){return a.time.localeCompare(b.time)});
  });

  var dates = Object.keys(byDate).sort().reverse();
  var days = ['日', '一', '二', '三', '四', '五', '六'];

  dates.forEach(function(d) {
    var day = byDate[d];
    var max = Math.max(day['in'].length, day.out.length, 1);
    var showDate = d.length === 10 ? d : '2026-' + d;
    var weekDay = days[new Date(showDate + 'T00:00:00').getDay()];
    h += '<div style="border-bottom:1px solid var(--border)">';
    var key = d.length === 10 ? d : '2026-' + d;
    var p2 = pt[key];
    var dt2='', dc2='var(--text-sec)';
    if(p2&&p2.day_type){var t2=p2.day_type;if(t2.indexOf('休息日')>=0)dc2='var(--orange)';else if(t2.indexOf('补班')>=0||t2.indexOf('调休')>=0)dc2='#E67E22';else if(t2.indexOf('节假日')>=0)dc2='var(--red)';else dc2='var(--text-sec)';dt2=' <span style="font-weight:normal;color:'+dc2+';font-size:10px">· '+t2+'</span>'}
    var ex2 = p2 && p2.earliest ? ' <span style="font-weight:normal;color:#8F959E;font-size:10px">| <span style="color:#34C759">⏱ '+p2.earliest+'</span> ~ <span style="color:#3370FF">'+p2.latest+'</span></span>' : '';
    h += '<div style="padding:8px 12px;font-size:12px;color:var(--text-sec);font-weight:bold;background:var(--bg)">' + d + ' 周' + weekDay + dt2 + ex2 + '</div>';
    for (var i = 0; i < max; i++) {
      h += '<div style="display:flex;padding:6px 12px;' + (i < max - 1 ? 'border-bottom:0.5px solid var(--border)' : '') + '">';
      // 进 - 左列
      h += '<div style="flex:1;display:flex;align-items:center;gap:6px;min-width:0">';
      if (day['in'][i]) {
        h += '<span class="tag tag-red" style="font-size:10px;white-space:nowrap">' + (day['in'][i].reason || '异常') + '</span>';
        h += '<span style="display:inline-block;width:24px;height:20px;line-height:20px;text-align:center;border-radius:4px;font-size:10px;font-weight:bold;background:#E8F5E9;color:var(--green)">进</span>';
        h += '<span style="font-family:monospace;font-size:12px">' + (day['in'][i].time.split(' ')[1] || '') + '</span>';
        h += '<button class="btn btn-sm btn-outline" style="padding:0 5px;font-size:10px" onclick="editCar(\'' + day['in'][i].ch_id + '\',\'' + day['in'][i].time + '\',\'进\',\'' + d + '\')">✏</button>';
      }
      h += '</div>';
      // 出 - 右列
      h += '<div style="flex:1;display:flex;align-items:center;gap:6px;border-left:1px solid var(--border);padding-left:12px;min-width:0">';
      if (day.out[i]) {
        h += '<span class="tag tag-red" style="font-size:10px;white-space:nowrap">' + (day.out[i].reason || '异常') + '</span>';
        h += '<span style="display:inline-block;width:24px;height:20px;line-height:20px;text-align:center;border-radius:4px;font-size:10px;font-weight:bold;background:#E8F0FE;color:var(--blue)">出</span>';
        h += '<span style="font-family:monospace;font-size:12px">' + (day.out[i].time.split(' ')[1] || '') + '</span>';
        h += '<button class="btn btn-sm btn-outline" style="padding:0 5px;font-size:10px" onclick="editCar(\'' + day.out[i].ch_id + '\',\'' + day.out[i].time + '\',\'出\',\'' + d + '\')">✏</button>';
      }
      h += '</div></div>';
    }
    h += '</div>';
  });
  h += '</div>';
  return h;
}

// 车辆出入 — 主函数
// 车辆出入 — 主函数
async function loadCar() {
  var tab = S.carTab || 'records';
  // 每个tab独立的筛选状态
  if (!S.carF) S.carF = {};
  var f = S.carF[tab] = S.carF[tab] || {};
  if (!f.from) {
    var n=new Date(),y=n.getFullYear(),m=n.getMonth(),d=n.getDate();
    if(d>=24){f.from=formatDate(new Date(y,m,24));f.to=formatDate(new Date(y,m+1,23))}
    else{f.from=formatDate(new Date(y,m-1,24));f.to=formatDate(new Date(y,m,23))}
  }
  if (!f.mode) f.mode = 'range';

  // 轨迹tab走独立逻辑
  if (tab === 'timeline') {
    var tlData = await api('/api/car/records?from=' + f.from + '&to=' + f.to);
    var tlAbn = [];
    try { tlAbn = await api('/api/car/abnormal?from=' + f.from + '&to=' + f.to); } catch(e) {}
    // 给全部记录的每条标记是否异常
    var abnMap = {};
    tlAbn.forEach(function(r){ abnMap[r.time+'-'+r.direction] = true; });
    tlData.forEach(function(r){ r.abnormal = !!abnMap[r.time+'-'+r.direction]; });
    // 获取打卡时间
    try { S._carPunchTimes = await api('/api/punch/times-range?from=' + f.from + '&to=' + f.to); } catch(e) {}
    var h2 = buildCarSubTabs(tab, 0);
    h2 += '<div class="card" style="padding:8px;overflow:hidden">';
    h2 += buildCarTimeline(tlData);
    h2 += '</div>';
    document.getElementById('car-content').innerHTML = h2;
    return;
  }

  var df = f.from, dt = f.to, isRange = f.mode === 'range';
  var url = tab === 'records' ? '/api/car/records?from=' + df + '&to=' + dt : '/api/car/abnormal?from=' + df + '&to=' + dt;
  var data = await api(url);
  var abnCount = 0;
  if (tab === 'records') {
    try { var ad = await api('/api/car/abnormal?from=' + df + '&to=' + dt); abnCount = ad.length; } catch (e) {}
  } else {
    abnCount = data.length;
  }

  var h = buildCarSubTabs(tab, abnCount);

  // 筛选栏
  var todayStr = new Date().toISOString().split('T')[0];
  h += '<div class="card" style="padding:12px 16px;margin-bottom:16px">';
  h += '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px">';
  h += '<span style="font-size:12px;color:var(--text-third)">模式</span>';
  h += '<span class="chip" onclick="S.carF.' + tab + '.mode=\'range\';loadCar()" style="cursor:pointer;' + (isRange ? 'background:var(--blue);color:white;border-color:var(--blue)' : '') + '">范围</span>';
  h += '<span class="chip" onclick="S.carF.' + tab + '.mode=\'single\';loadCar()" style="cursor:pointer;' + (!isRange ? 'background:var(--blue);color:white;border-color:var(--blue)' : '') + '">单日</span>';
  h += '<span class="chip" onclick="S.carF.' + tab + '.from=\'' + todayStr + '\';S.carF.' + tab + '.to=\'' + todayStr + '\';S.carF.' + tab + '.mode=\'single\';loadCar()" style="cursor:pointer">今天</span>';
  h += '<span class="chip" onclick="setCarCompanyMonth(\'' + tab + '\')" style="cursor:pointer">当月</span>';
  h += '<span style="flex:1"></span>';
  h += '<span style="font-size:12px;color:var(--text-third)">' + (tab === 'records' ? '共 ' + data.length + ' 条' : '') + '</span>';
  h += '</div>';
  h += '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">';
  if (isRange) {
    h += '<input type="date" value="' + df + '" onchange="S.carF.' + tab + '.from=this.value;loadCar()" style="width:140px">';
    h += '<span style="color:var(--text-third)">至</span>';
    h += '<input type="date" value="' + dt + '" onchange="S.carF.' + tab + '.to=this.value;loadCar()" style="width:140px">';
  } else {
    h += '<input type="date" value="' + df + '" onchange="S.carF.' + tab + '.from=this.value;S.carF.' + tab + '.to=this.value;loadCar()" style="width:160px">';
  }
  h += '</div></div>';

  // 获取打卡时间
  var punchTimes = {};
  try { punchTimes = await api('/api/punch/times-range?from=' + df + '&to=' + dt); } catch(e) {}

  // 异常桌面提醒（仅公司月范围且首次加载）
  if (!S.carAbnNotified && abnCount > 0) {
    S.carAbnNotified = true;
    try {
      var nt = new Notification('🚗 车辆异常提醒', {
        body: '本月有 ' + abnCount + ' 条异常出入记录，请查看车辆出入页面',
        icon: 'cat_icon.png',
        requireInteraction: true
      });
      setTimeout(function(){ nt.close(); }, 8000);
    } catch(e) {}
  }

  // 记录列表
  h += '<div class="card" style="padding:0;overflow:hidden">';
  h += tab === 'records' ? buildCarRecords(data, punchTimes) : buildCarAbnormal(data, punchTimes);
  h += '</div>';

  document.getElementById('car-content').innerHTML = h;
}

function buildCarTimeline(data) {
  var id = 'tl2d-' + Date.now();
  if (!data || !data.length) return '<div style="color:var(--text-third);text-align:center;padding:32px">暂无记录</div>';
  var h = '<div id="'+id+'" style="width:100%;height:550px;position:relative;overflow:hidden;border-radius:12px;background:#f8f9fb"><canvas id="'+id+'-c" style="width:100%;height:100%;display:block"></canvas></div>';
  setTimeout(function(){ initMapTimeline(id, data); }, 200);
  return h;
}

function initMapTimeline(divId, data) {
  var div = document.getElementById(divId);
  var canvas = document.getElementById(divId+'-c');
  if (!div || !canvas) return;
  
  var dpr = window.devicePixelRatio || 1;
  var W = div.clientWidth, H = 550;
  canvas.width = W * dpr; canvas.height = H * dpr;
  var ctx = canvas.getContext('2d');
  ctx.setTransform(dpr,0,0,dpr,0,0);
  
  var offsetX = 0, offsetY = 0, scale = 1;
  var dragging = false, dragStart = {x:0,y:0}, dragOff = {x:0,y:0};
  var hoverNode = null;
  
  var dates = [];
  data.forEach(function(r){var d=r.date||r.time.split(' ')[0];if(dates.indexOf(d)<0)dates.push(d)});
  dates.sort().reverse();
  var days = ['日','一','二','三','四','五','六'];
  
  var nodes = [];
  data.forEach(function(r){
    var t = r.time.split(' ')[1]||'', parts = t.split(':');
    var hr = parseInt(parts[0])+parseInt(parts[1])/60;
    var d = r.date||r.time.split(' ')[0];
    var di = dates.indexOf(d);
    var abn = !!r.abnormal;
    nodes.push({
      x: hr, y: di + 0.5,
      time: t.substring(0,8),
      date: d,
      dir: r.direction,
      abn: abn,
      color: abn ? '#F54A45' : (r.direction==='进' ? '#34C759' : '#3370FF')
    });
  });
  
  var segments = [];
  dates.forEach(function(d, di){
    var dayNodes = nodes.filter(function(n){return n.date===d}).sort(function(a,b){return a.x-b.x});
    var stack = [];
    dayNodes.forEach(function(n){
      if(n.dir==='进') stack.push(n);
      else if(stack.length){var inn=stack.shift();segments.push({x1:inn.x,x2:n.x,y:di+0.5,abn:inn.abn||n.abn,inNode:inn,outNode:n})}
    });
    stack.forEach(function(n){segments.push({x1:n.x,x2:24,y:di+0.5,abn:true,inNode:n,outNode:null,open:true})});
  });
  
  var totalDays = dates.length;
  var worldW = 26, worldH = totalDays + 2;
  var fitScaleY = (H - 80) / (worldH * 60);
  var fitScaleX = (W - 160) / (worldW * 60);
  var autoScale = Math.min(fitScaleX, fitScaleY, 1.2);
  scale = autoScale;
  offsetX = 90;
  offsetY = 50;
  
  function toScreen(wx, wy) {
    return {x: (wx+0.8)*60*scale + offsetX, y: (wy+0.3)*60*scale + offsetY};
  }
  
  function dist(px,py,nx,ny){var dx=px-nx,dy=py-ny;return Math.sqrt(dx*dx+dy*dy)}
  
  function draw() {
    ctx.clearRect(0,0,W,H);
    ctx.save();
    
    ctx.fillStyle = '#f8f9fb';
    ctx.fillRect(0,0,W,H);
    
    for (var di=0; di<totalDays; di++) {
      var top = toScreen(0, di).y, bot = toScreen(0, di+1).y;
      if (di%2===0) { ctx.fillStyle='rgba(0,0,0,0.02)'; ctx.fillRect(0,top,W,bot-top); }
    }
    
    for (var h=0; h<=24; h++) {
      var sx = toScreen(h, 0).x;
      ctx.strokeStyle = h%6===0 ? 'rgba(0,0,0,0.1)' : 'rgba(0,0,0,0.04)';
      ctx.lineWidth = h%6===0 ? 1 : 0.5;
      ctx.beginPath(); ctx.moveTo(sx, toScreen(0,0).y); ctx.lineTo(sx, toScreen(0,totalDays).y); ctx.stroke();
    }
    
    for (var di=0; di<=totalDays; di++) {
      var sy = toScreen(0, di).y;
      ctx.strokeStyle = 'rgba(0,0,0,0.08)'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(toScreen(-1,di).x, sy); ctx.lineTo(toScreen(25,di).x, sy); ctx.stroke();
    }
    
    ctx.font = 'bold 12px -apple-system,sans-serif'; ctx.textAlign = 'right';
    for (var di=0; di<totalDays; di++) {
      var p = toScreen(-0.5, di+0.5);
      var d = dates[di], dateKey = d.length===10?d:'2026-'+d;
      ctx.fillStyle = '#646A73';
      ctx.fillText(d+' 周'+days[new Date(dateKey+'T00:00:00').getDay()], p.x-8, p.y+4);
    }
    
    ctx.font = '10px -apple-system,sans-serif'; ctx.textAlign = 'center'; ctx.fillStyle = '#8F959E';
    for (var h=0; h<=24; h+=3) {
      var p = toScreen(h, -0.3);
      ctx.fillText(h+':00', p.x, p.y);
    }
    
    ctx.lineCap = 'round';
    segments.forEach(function(seg) {
      var p1 = toScreen(seg.x1, seg.y), p2 = toScreen(seg.x2||24, seg.y);
      ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y);
      ctx.strokeStyle = seg.abn ? 'rgba(245,74,69,0.4)' : 'rgba(52,199,89,0.5)';
      ctx.lineWidth = Math.max(3*scale, 2);
      ctx.stroke();
      if (seg.abn) {
        ctx.setLineDash([4,4]);
        ctx.strokeStyle = 'rgba(245,74,69,0.3)';
        ctx.lineWidth = Math.max(6*scale, 3);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    });
    
    nodes.forEach(function(n) {
      var p = toScreen(n.x, n.y);
      var r = Math.max(6*scale, 4);
      var grad = ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,r*2);
      grad.addColorStop(0, n.color); grad.addColorStop(1, 'transparent');
      ctx.fillStyle = grad;
      ctx.beginPath(); ctx.arc(p.x, p.y, r*2.5, 0, Math.PI*2); ctx.fill();
      ctx.fillStyle = n.color;
      ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI*2); ctx.fill();
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5;
      ctx.stroke();
      if (scale > 0.6) {
        ctx.fillStyle = n.color; ctx.font = '9px -apple-system,sans-serif'; ctx.textAlign = 'center';
        ctx.fillText(n.dir+' '+n.time.substring(0,5), p.x, p.y-r-6);
      }
      if (hoverNode === n) {
        ctx.strokeStyle = n.color; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(p.x, p.y, r+4, 0, Math.PI*2); ctx.stroke();
      }
    });
    
    ctx.restore();
    
    if (hoverNode) {
      var p = toScreen(hoverNode.x, hoverNode.y);
      var abnTag = hoverNode.abn ? ' ⚠异常' : '';
      var txt = hoverNode.date + ' ' + hoverNode.dir + ' ' + hoverNode.time + abnTag;
      ctx.font = '12px -apple-system,sans-serif';
      var tw = ctx.measureText(txt).width + 16;
      ctx.fillStyle = 'rgba(0,0,0,0.8)';
      ctx.beginPath(); ctx.roundRect(p.x-tw/2, p.y-30, tw, 22, 6); ctx.fill();
      ctx.fillStyle = '#fff'; ctx.textAlign = 'center';
      ctx.fillText(txt, p.x, p.y-15);
    }
  }
  
  canvas.addEventListener('mousedown', function(e) {
    dragging = true;
    dragStart = {x:e.clientX, y:e.clientY};
    dragOff = {x:offsetX, y:offsetY};
    div.style.cursor = 'grabbing';
  });
  window.addEventListener('mouseup', function(){dragging=false;div.style.cursor='grab'});
  canvas.addEventListener('mousemove', function(e) {
    if (dragging) {
      offsetX = dragOff.x + (e.clientX - dragStart.x);
      offsetY = dragOff.y + (e.clientY - dragStart.y);
      draw();
      return;
    }
    var mx = e.clientX - canvas.getBoundingClientRect().left;
    var my = e.clientY - canvas.getBoundingClientRect().top;
    var oldHover = hoverNode;
    hoverNode = null;
    for (var i=nodes.length-1;i>=0;i--) {
      var p = toScreen(nodes[i].x, nodes[i].y);
      if (dist(mx,my,p.x,p.y) < 15) { hoverNode = nodes[i]; break; }
    }
    if (hoverNode !== oldHover) draw();
  });
  canvas.addEventListener('wheel', function(e) {
    e.preventDefault();
    var zf = e.deltaY < 0 ? 1.15 : 0.87;
    var newScale = Math.min(Math.max(scale*zf, 0.3), 4);
    var mx = e.clientX - canvas.getBoundingClientRect().left;
    var my = e.clientY - canvas.getBoundingClientRect().top;
    offsetX = mx - (mx - offsetX) * (newScale/scale);
    offsetY = my - (my - offsetY) * (newScale/scale);
    scale = newScale;
    draw();
  });
  
  offsetX = (W - worldW * scale * 60) / 2;
  offsetY = (H - worldH * scale * 60) / 2;
  draw();
  
  window.addEventListener('resize', function() {
    W = div.clientWidth;
    canvas.width = W*dpr; canvas.height = H*dpr;
    ctx.setTransform(dpr,0,0,dpr,0,0);
    draw();
  });
}

