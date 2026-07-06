var fs=require('fs'),path=require('path');
var h=fs.readFileSync(path.join(__dirname,'renderer','index.html'),'utf8');
var s='<script>';
var e='<script type="module">';
var i=h.indexOf(s)+s.length;
var j=h.indexOf(e);
var js=h.slice(i,j);
try{
  new Function(js);
  console.log('OK');
}catch(err){
  var m=err.stack.match(/<anonymous>:(\d+)/);
  if(m) console.log('Line',m[1],':',err.message.substring(0,200));
  else console.log(err.message.substring(0,300));
}
