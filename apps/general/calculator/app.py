"""calculator —— 双模式计算器 (参考 Windows 计算器设计)"""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import os

PORT = int(os.environ.get("LAUNCHER_APP_PORT", 0))

HTML = r"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title> 计算器</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0b1120;color:#fff;min-height:100vh;display:flex;justify-content:center;align-items:center;
     background-image:radial-gradient(at 0% 0%,rgba(99,102,241,0.25) 0px,transparent 50%),
                      radial-gradient(at 100% 100%,rgba(236,72,153,0.2) 0px,transparent 50%)}
.calc{width:320px;background:rgba(255,255,255,0.06);backdrop-filter:blur(20px);
      border:1px solid rgba(255,255,255,0.1);border-radius:12px;padding:16px;
      box-shadow:0 20px 40px rgba(0,0,0,0.3)}
.mode-switch{display:flex;gap:8px;margin-bottom:16px}
.mode-btn{flex:1;padding:8px;background:rgba(255,255,255,0.08);border:none;
          border-radius:6px;color:#fff;cursor:pointer;font-size:13px;transition:0.2s}
.mode-btn.active{background:#818cf8}
.display{background:rgba(0,0,0,0.3);border-radius:8px;padding:16px;margin-bottom:16px;text-align:right}
.display-input{font-size:32px;font-family:Consolas,monospace;min-height:40px;word-break:break-all}
.display-hex{font-size:11px;color:#94a3b8;margin-top:4px;min-height:16px}
.keys{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.key{padding:14px;border:none;border-radius:6px;background:rgba(255,255,255,0.08);
     color:#fff;font-size:16px;cursor:pointer;transition:0.15s}
.key:hover{background:rgba(255,255,255,0.15)}
.key:active{transform:scale(0.95)}
.key.op{color:#818cf8;font-weight:600}
.key.eq{background:#818cf8;grid-column:span 2}
.key.prog{font-size:13px}
.hidden{display:none}
</style></head><body>
<div class="calc">
  <div class="mode-switch">
    <button class="mode-btn active" onclick="setMode('std')">标准</button>
    <button class="mode-btn" onclick="setMode('prog')">程序员</button>
  </div>
  <div class="display">
    <div class="display-input" id="disp">0</div>
    <div class="display-hex" id="hex"></div>
  </div>
  <div class="keys" id="keys"></div>
</div>
<script>
let mode='std',current='0',prev=null,op=null,newEntry=true,base=10;
const stdKeys=[['C','±','%','÷'],['7','8','9','×'],['4','5','6','-'],['1','2','3','+'],['0','.','=']];
const progKeys=[['HEX','DEC','OCT','BIN'],['A','B','C','D'],['E','F','AND','OR'],['XOR','NOT','<<','>>'],
                ['7','8','9','÷'],['4','5','6','×'],['1','2','3','-'],['0','.','=']];

function setMode(m){
  mode=m;document.querySelectorAll('.mode-btn').forEach((b,i)=>b.classList.toggle('active',(m==='std'&&!i)||(m==='prog'&&i)));
  current='0';prev=null;op=null;newEntry=true;base=10;
  renderKeys();updateDisplay();
}

function renderKeys(){
  const keys=mode==='std'?stdKeys:progKeys;
  document.getElementById('keys').innerHTML=keys.flat().map(k=>{
    const cls=['÷','×','-','+','='].includes(k)?'op':'';
    return `<button class="key ${cls}${mode==='prog'&&!/^[0-9.]$/.test(k)?' prog':''}" onclick="press('${k}')">${k}</button>`;
  }).join('');
}

function press(k){
  if(mode==='prog'&&['HEX','DEC','OCT','BIN'].includes(k)){
    base={'HEX':16,'DEC':10,'OCT':8,'BIN':2}[k];updateHex();return;
  }
  if(mode==='prog'&&k==='NOT'){current=String(~parseInt(current,base));updateDisplay();return;}
  if(mode==='prog'&&['AND','OR','XOR','<<','>>'].includes(k)){
    prev=parseInt(current,base);op=k;newEntry=true;return;
  }
  if(k==='C'){current='0';prev=null;op=null;newEntry=true;}
  else if(k==='±'){current=String(-parseFloat(current));}
  else if(k==='%'){current=String(parseFloat(current)/100);}
  else if(['÷','×','-','+'].includes(k)){
    if(op&&!newEntry){calculate();}
    prev=parseFloat(current);op=k;newEntry=true;
  }
  else if(k==='='){
    if(op&&prev!==null){calculate();op=null;prev=null;}
  }
  else if(k==='.'){
    if(newEntry){current='0.';newEntry=false;}
    else if(!current.includes('.'))current+='.';
  }
  else{
    if(newEntry){current=k;newEntry=false;}
    else{current+=k;}
  }
  updateDisplay();
}

function calculate(){
  if(prev===null)return;
  let curr=parseFloat(current);
  switch(op){
    case '÷':if(curr!==0)current=String(prev/curr);break;
    case '×':current=String(prev*curr);break;
    case '-':current=String(prev-curr);break;
    case '+':current=String(prev+curr);break;
    case 'AND':current=String(prev&curr);break;
    case 'OR':current=String(prev|curr);break;
    case 'XOR':current=String(prev^curr);break;
    case '<<':current=String(prev<<curr);break;
    case '>>':current=String(prev>>curr);break;
  }
  prev=null;newEntry=true;
}

function updateDisplay(){
  document.getElementById('disp').textContent=current;
  updateHex();
}

function updateHex(){
  try{
    const val=parseInt(current,base);
    if(!isNaN(val)){
      document.getElementById('hex').textContent=
        `HEX:${val.toString(16).toUpperCase()} BIN:${val.toString(2)}`;
    }
  }catch{}
}

renderKeys();
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode("utf-8"))
    def log_message(self, *a): pass

if __name__ == "__main__":
    print(f"[Calculator] http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()