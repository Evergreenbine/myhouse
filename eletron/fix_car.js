const fs = require('fs');
let h = fs.readFileSync('renderer/index.html', 'utf8');
const s = h.indexOf('<script>') + 8;
const js = h.slice(s, h.lastIndexOf('</script>'));

const start = js.indexOf('async function loadCar(){');
const end = js.indexOf('\n// ========== 喝水记录', start);
const before = h.substring(0, s + start);
const after = h.substring(s + end);

const newLoadCar = `
function buildCarSubTabs(tab,abnCount){var r="";r+="<div style=\\"display:flex;align-items:center;gap:12px;margin-bottom:16px\\">";r+="<div style=\\"display:flex;background:var(--white);border-radius:10px;border:1px solid var(--border);overflow:hidden;flex:1\\">";r+="<div onclick=\\"S.carTab=\\\\'records\\\\';loadCar()\\" style=\\"flex:1;text-align:center;padding:12px;cursor:pointer;font-size:14px;";r+=tab==="records"?"background:var(--blue);color:white;font-weight:bold":"background:var(--white);color:var(--text-sec)";r+=\\"\\">🚗 全部记录</div>";r+="<div onclick=\\"S.carTab=\\\\'abnormal\\\\';loadCar()\\" style=\\"flex:1;text-align:center;padding:12px;cursor:pointer;font-size:14px;";r+=tab==="abnormal"?"background:var(--red);color:white;font-weight:bold":"background:var(--white);color:var(--text-sec)";r+=\\"\\">⚠ 异常记录";if(abnCount>0)r+=" <span style=\\"background:rgba(255,255,255,0.3);border-radius:10px;padding:1px 7px;font-size:11px;margin-left:4px\\">"+abnCount+"</span>";r+="</div></div></div>";return r}

function buildCarRecords(data){var h="<div style=\\"max-height:500px;overflow-y:auto\\">";if(!data||!data.length)return h+"<div style=\\"color:var(--text-third);text-align:center;padding:32px\\">暂无记录</div></div>";var byDate={};data.forEach(function(r){var d=r.time.split(" ")[0];if(!byDate[d])byDate[d]={date:d,\\"in\\":[],out:[]};if(r.direction==="进")byDate[d]["in"].push(r);else byDate[d].out.push(r)});var dates=Object.keys(byDate).sort().reverse();var days=["日","一","二","三","四","五","六"];dates.forEach(function(d){var day=byDate[d];var max=Math.max(day["in"].length,day.out.length,1);h+="<div style=\\"border-bottom:1px solid var(--border)\\">";h+="<div style=\\"padding:8px 16px;font-size:12px;color:var(--text-sec);font-weight:bold;background:var(--bg)\\">"+d+" 周"+days[new Date(d+"T00:00:00").getDay()]+"</div>";for(var i=0;i<max;i++){h+="<div style=\\"display:flex;padding:6px 16px;"+(i<max-1?"border-bottom:0.5px solid var(--border)":"")+"\\">";h+="<div style=\\"flex:1;display:flex;align-items:center;gap:8px\\">";if(day["in"][i]){h+="<span style=\\"display:inline-block;width:28px;height:22px;line-height:22px;text-align:center;border-radius:5px;font-size:10px;font-weight:bold;background:#E8F5E9;color:var(--green)\\">进</span>";h+="<span style=\\"font-family:monospace;font-size:12px\\">"+(day["in"][i].time.split(" ")[1]||"")+"</span>";h+="<button class=\\"btn btn-sm btn-outline\\" style=\\"padding:1px 6px;font-size:10px\\" onclick=\\"editCar(""+day["in"][i].ch_id+"",""+day["in"][i].time+"","进",""+d+"")\\">✏</button>"}h+="</div>";h+="<div style=\\"flex:1;display:flex;align-items:center;gap:8px;border-left:1px solid var(--border);padding-left:16px\\">";if(day.out[i]){h+="<span style=\\"display:inline-block;width:28px;height:22px;line-height:22px;text-align:center;border-radius:5px;font-size:10px;font-weight:bold;background:#E8F0FE;color:var(--blue)\\">出</span>";h+="<span style=\\"font-family:monospace;font-size:12px\\">"+(day.out[i].time.split(" ")[1]||"")+"</span>";h+="<button class=\\"btn btn-sm btn-outline\\" style=\\"padding:1px 6px;font-size:10px\\" onclick=\\"editCar(""+day.out[i].ch_id+"",""+day.out[i].time+"","出",""+d+"")\\">✏</button>"}h+="</div></div>"}h+="</div>"});h+="</div>";return h}

function buildCarAbnormal(data){var h="<div style=\\"max-height:500px;overflow-y:auto\\">";if(!data||!data.length)return h+"<div style=\\"color:var(--green);text-align:center;padding:32px\\">🎉 暂无异常</div></div>";data.forEach(function(r){var d=r.time.split(" ")[0];var t=r.time.split(" ")[1]||"";h+="<div style=\\"display:flex;align-items:center;padding:10px 16px;border-bottom:0.5px solid var(--border);font-size:13px\\">";h+="<span style=\\"width:80px;font-size:12px;color:var(--text-sec)\\">"+d+"</span>";h+="<span class=\\"tag tag-red\\" style=\\"margin-right:8px\\">"+r.reason+"</span>";h+="<span style=\\"display:inline-block;width:32px;height:24px;line-height:24px;text-align:center;border-radius:6px;font-size:11px;font-weight:bold;background:#E8F0FE;color:var(--blue);margin-right:12px\\">"+r.direction+"</span>";h+="<span style=\\"flex:1;font-family:monospace\\">"+t+"</span>";h+="</div>"});h+="</div>";return h}

async function loadCar(){var df=S.carDateFrom||new Date().toISOString().split("T")[0].replace(/-\\d{2}$/,"-01");var dt=S.carDateTo||new Date().toISOString().split("T")[0];var tab=S.carTab||"records";var url=tab==="records"?"/api/car/records?from="+df+"&to="+dt:"/api/car/abnormal?from="+df+"&to="+dt;var data=await api(url);var abnCount=0;if(tab==="records"){try{var ad=await api("/api/car/abnormal?from="+df+"&to="+dt);abnCount=ad.length}catch(e){}}else{abnCount=data.length}var h="";h+=buildCarSubTabs(tab,abnCount);h+="<div class=\\"card\\" style=\\"padding:12px 16px;margin-bottom:16px\\"><div style=\\"display:flex;gap:8px;align-items:center;flex-wrap:wrap\\">";h+="<span style=\\"font-size:13px;color:var(--text-sec);white-space:nowrap\\">📅 筛选</span>";h+="<input type=\\"date\\" id=\\"car-from\\" value=\\""+df+"\\" onchange=\\"S.carDateFrom=this.value;loadCar()\\" style=\\"width:140px\\">";h+="<span style=\\"color:var(--text-third)\\">至</span>";h+="<input type=\\"date\\" id=\\"car-to\\" value=\\""+dt+"\\" onchange=\\"S.carDateTo=this.value;loadCar()\\" style=\\"width:140px\\">";h+="<span style=\\"color:var(--text-third);margin-left:4px\\">|</span>";h+="<input type=\\"date\\" id=\\"car-single\\" onchange=\\"S.carDateFrom=this.value;S.carDateTo=this.value;loadCar()\\" style=\\"width:140px\\" placeholder=\\"单日查询\\">";h+="<div style=\\"flex:1;text-align:right;font-size:12px;color:var(--text-third)\\">"+(tab==="records"?"共 "+data.length+" 条":"")+"</div>";h+="</div></div>";h+="<div class=\\"card\\" style=\\"padding:0;overflow:hidden\\">";h+=tab==="records"?buildCarRecords(data):buildCarAbnormal(data);h+="</div>";document.getElementById("car-content").innerHTML=h}
`;

h = before + newLoadCar + after;
fs.writeFileSync('renderer/index.html', h);

// Verify
const h2 = fs.readFileSync('renderer/index.html', 'utf8');
const s2 = h2.indexOf('<script>') + 8;
const e2 = h2.lastIndexOf('</script>');
const js2 = h2.slice(s2, e2);
try {
  new Function(js2);
  console.log('JS SYNTAX OK!');
} catch(ex) {
  console.log('SYNTAX ERROR:', ex.message);
}
