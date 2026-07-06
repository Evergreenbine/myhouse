const fs=require('fs');
let h=fs.readFileSync('renderer/index.html','utf8');
const s=h.indexOf('<script>')+8;
const m=h.indexOf('<script type="module">');
const js=h.slice(s,m);
try{
  new Function(js);
  console.log('JS OK');
}catch(e){
  console.log('JS ERROR:',e.message.substring(0,120));
}
