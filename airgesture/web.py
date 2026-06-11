"""HTTP UI for the AirGesture control service."""

import json
from http import server
from socketserver import ThreadingMixIn


PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AirGesture K230 Control</title>
<style>
  html,body{margin:0;min-height:100%;background:#101417;color:#eef5f2;font-family:Arial,"Microsoft YaHei",sans-serif;}
  body{display:grid;grid-template-rows:auto 1fr;}
  header{padding:10px 14px;background:#1a2327;border-bottom:1px solid #2e3b41;display:flex;gap:8px;align-items:center;flex-wrap:wrap;}
  h1{font-size:16px;margin:0 8px 0 0;color:#fff;}
  .pill{font-size:12px;line-height:1;color:#cbd8d4;background:#253138;border:1px solid #3a484e;padding:7px 9px;border-radius:4px;}
  .ok{color:#89f5b0;}
  .no{color:#ff9d9d;}
  .ready{color:#ffd36d;}
  .exec{color:#92d8ff;}
  main{padding:16px;display:grid;grid-template-columns:minmax(260px,520px) minmax(260px,1fr);gap:16px;align-items:start;}
  section{border:1px solid #2f3d42;background:#151c20;border-radius:6px;padding:14px;}
  h2{font-size:15px;margin:0 0 12px;color:#fff;font-weight:700;}
  .grid{display:grid;grid-template-columns:120px 1fr;gap:10px 12px;font-size:14px;}
  .key{color:#8fa19c;}
  .value{color:#eef5f2;word-break:break-word;}
  .big{font-size:32px;font-weight:700;letter-spacing:0;margin:8px 0 4px;}
  .sub{color:#9eb0ac;font-size:13px;}
  table{width:100%;border-collapse:collapse;font-size:13px;}
  th,td{padding:8px;border-bottom:1px solid #273338;text-align:left;}
  th{color:#9fb0ad;font-weight:600;}
  td{color:#eef5f2;}
  @media(max-width:760px){main{grid-template-columns:1fr;padding:10px;} .big{font-size:26px;}}
</style>
</head>
<body>
<header>
  <h1>AirGesture K230</h1>
  <span class="pill" id="serial">Serial --</span>
  <span class="pill" id="data">Data --</span>
  <span class="pill" id="face">Face --</span>
  <span class="pill" id="wave">Wave --</span>
  <span class="pill" id="gesture">Gesture --</span>
  <span class="pill" id="state">State IDLE</span>
  <span class="pill" id="event">Event --</span>
</header>
<main>
  <section>
    <h2>Control</h2>
    <div class="big" id="command">--</div>
    <div class="sub" id="summary">Waiting for K230 data</div>
    <div class="grid" style="margin-top:16px">
      <div class="key">Power</div><div class="value" id="acPower">--</div>
      <div class="key">Temp</div><div class="value" id="acTemp">--</div>
      <div class="key">Mode</div><div class="value" id="acMode">--</div>
      <div class="key">Fan</div><div class="value" id="acFan">--</div>
      <div class="key">Last Action</div><div class="value" id="lastAction">--</div>
      <div class="key">LED</div><div class="value" id="led">--</div>
      <div class="key">K230 FPS</div><div class="value" id="fps">--</div>
      <div class="key">Last RX</div><div class="value" id="age">--</div>
      <div class="key">Raw</div><div class="value" id="raw">--</div>
    </div>
  </section>
  <section>
    <h2>History</h2>
    <table>
      <thead><tr><th>Time</th><th>Command</th><th>Gesture</th><th>Action</th></tr></thead>
      <tbody id="history"></tbody>
    </table>
  </section>
</main>
<script>
async function refresh(){
  try{
    const data = await fetch('/health', {cache:'no-store'}).then(r=>r.json());
    const serial = document.getElementById('serial');
    serial.textContent = 'Serial ' + (data.serial_ok ? 'OK' : 'NO');
    serial.className = 'pill ' + (data.serial_ok ? 'ok' : 'no');
    const dataPill = document.getElementById('data');
    dataPill.textContent = data.data_timeout ? 'Data TIMEOUT' : 'Data LIVE';
    dataPill.className = 'pill ' + (data.data_timeout ? 'no' : 'ok');
    const face = document.getElementById('face');
    face.textContent = 'Face ' + (data.face ? 'YES' : 'NO');
    face.className = 'pill ' + (data.face ? 'ok' : 'no');
    const wave = document.getElementById('wave');
    wave.textContent = 'Wave ' + (data.wave ? 'YES' : 'NO');
    wave.className = 'pill ' + (data.wave ? 'ready' : '');
    document.getElementById('gesture').textContent = 'Gesture ' + (data.gesture || 'NONE');
    const st = document.getElementById('state');
    st.textContent = 'State ' + (data.state || 'IDLE') + (data.ready_remaining ? ' ' + Number(data.ready_remaining).toFixed(1) + 's' : '');
    st.className = 'pill ' + (data.state === 'READY' ? 'ready' : data.state === 'EXECUTE' ? 'exec' : '');
    document.getElementById('event').textContent = data.event ? ('Event ' + data.event) : 'Event --';
    document.getElementById('command').textContent = data.command || '--';
    document.getElementById('summary').textContent = data.state === 'IDLE' ? 'Wave to activate' : data.state === 'READY' ? 'Show a stable right-hand gesture' : 'Command executed';
    const ac = data.ac || {};
    document.getElementById('acPower').textContent = ac.power ? 'ON' : 'OFF';
    document.getElementById('acTemp').textContent = (ac.temp || '--') + ' C';
    document.getElementById('acMode').textContent = ac.mode || '--';
    document.getElementById('acFan').textContent = ac.fan || '--';
    document.getElementById('lastAction').textContent = data.last_action || '--';
    document.getElementById('led').textContent = data.led || '--';
    document.getElementById('fps').textContent = Number(data.k230_fps || 0).toFixed(1);
    document.getElementById('age').textContent = data.last_rx_age == null ? '--' : Number(data.last_rx_age).toFixed(1) + 's';
    document.getElementById('raw').textContent = data.raw || '--';
    const rows = (data.history || []).map(x => `<tr><td>${x.time}</td><td>${x.command}</td><td>${x.gesture}</td><td>${x.action || ''}</td></tr>`).join('');
    document.getElementById('history').innerHTML = rows || '<tr><td colspan="4">No command yet</td></tr>';
  }catch(e){}
}
setInterval(refresh, 300);
refresh();
</script>
</body>
</html>""".encode("utf-8")


class ThreadedHTTPServer(ThreadingMixIn, server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_handler(state, state_lock):
    class Handler(server.BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(PAGE)))
                self.end_headers()
                self.wfile.write(PAGE)
                return
            if self.path == "/health":
                with state_lock:
                    body_state = dict(state)
                body = (json.dumps(body_state, ensure_ascii=False) + "\n").encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(404)

    return Handler
