using System;
using System.IO;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using CineCadiz.ViewModels;

namespace CineCadiz.Services
{
    /// <summary>
    /// Servidor HTTP embebido usando TcpListener (sin privilegios de administrador).
    /// Abre http://{IP_LAN}:7979 desde el móvil para controlar la app.
    /// </summary>
    public class RemoteService
    {
        private static readonly RemoteService _instance = new();
        public static RemoteService Instance => _instance;

        public const int Port = 7979;

        private TcpListener? _listener;
        private CancellationTokenSource? _cts;

        public string LocalIp  { get; private set; } = "localhost";
        public string RemoteUrl => $"http://{LocalIp}:{Port}";
        public bool   IsRunning => _cts != null && !_cts.IsCancellationRequested;

        public void Start()
        {
            LocalIp = GetLocalIp();
            _cts = new CancellationTokenSource();

            // TcpListener can bind to any IP without admin rights
            _listener = new TcpListener(IPAddress.Any, Port);
            try
            {
                _listener.Start();
            }
            catch
            {
                // Port taken — try a different one
                try
                {
                    _listener = new TcpListener(IPAddress.Any, Port + 1);
                    _listener.Start();
                }
                catch { return; }
            }

            _ = AcceptLoopAsync(_cts.Token);
        }

        public void Stop()
        {
            _cts?.Cancel();
            _listener?.Stop();
        }

        private async Task AcceptLoopAsync(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    var client = await _listener!.AcceptTcpClientAsync(ct);
                    _ = Task.Run(() => HandleClientAsync(client), ct);
                }
                catch { break; }
            }
        }

        private async Task HandleClientAsync(TcpClient client)
        {
            client.SendTimeout    = 5000;
            client.ReceiveTimeout = 5000;
            try
            {
                using var stream = client.GetStream();

                // Read request line
                var requestLine = await ReadLineAsync(stream);
                if (string.IsNullOrWhiteSpace(requestLine)) return;

                var parts = requestLine.Split(' ');
                if (parts.Length < 2) return;
                var method   = parts[0].ToUpperInvariant();
                var fullPath = parts[1];

                // Split path and query string
                var qi    = fullPath.IndexOf('?');
                var path  = qi >= 0 ? fullPath[..qi] : fullPath;
                var query = qi >= 0 ? fullPath[(qi + 1)..] : "";

                // Drain remaining headers (until blank line)
                string? hdr;
                while (!string.IsNullOrEmpty(hdr = await ReadLineAsync(stream))) { }

                // Handle CORS preflight
                if (method == "OPTIONS")
                {
                    await WriteResponseAsync(stream, 204, "text/plain", "");
                    return;
                }

                // Dispatch
                var (code, ct2, body) = await DispatchAsync(method, path, query);
                await WriteResponseAsync(stream, code, ct2, body);
            }
            catch { }
            finally
            {
                client.Close();
            }
        }

        private async Task<(int code, string ct, string body)> DispatchAsync(
            string method, string path, string query)
        {
            // ── GET / → mobile remote HTML ──────────────────────────────
            if (path is "/" or "")
                return (200, "text/html", RemoteHtml);

            // ── GET /api/status ─────────────────────────────────────────
            if (path == "/api/status" && method == "GET")
            {
                var p = PlayerViewModel.Instance;
                var json = JsonSerializer.Serialize(new
                {
                    title     = p.Title,
                    isPlaying = p.IsPlaying,
                    isLive    = p.IsLive,
                    isVisible = p.IsVisible,
                    position  = p.CurrentPosition,
                    duration  = p.TotalDuration,
                    volume    = p.Volume
                });
                return (200, "application/json", json);
            }

            // ── POST commands ────────────────────────────────────────────
            if (method == "POST")
            {
                await Application.Current.Dispatcher.InvokeAsync(() =>
                {
                    var player = PlayerViewModel.Instance;
                    var mainVm = Application.Current.MainWindow?.DataContext as MainViewModel;

                    switch (path)
                    {
                        case "/api/playpause":
                            player.TogglePlayPauseCommand.Execute(null);
                            break;
                        case "/api/close":
                            player.CloseCommand.Execute(null);
                            break;
                        case "/api/seek":
                            if (int.TryParse(GetParam(query, "s"), out var secs))
                                player.SeekSeconds(secs);
                            break;
                        case "/api/volume":
                            if (int.TryParse(GetParam(query, "v"), out var vol))
                                player.SetVolume(vol);
                            break;
                        case "/api/navigate":
                            if (mainVm == null) break;
                            switch (GetParam(query, "page"))
                            {
                                case "home":   mainVm.NavigateHomeCommand.Execute(null);   break;
                                case "movies": mainVm.NavigateMoviesCommand.Execute(null); break;
                                case "series": mainVm.NavigateSeriesCommand.Execute(null); break;
                                case "live":   mainVm.NavigateLiveCommand.Execute(null);   break;
                            }
                            break;
                    }
                });
                return (200, "application/json", "{\"ok\":true}");
            }

            return (404, "text/plain", "Not found");
        }

        // ── Helpers ────────────────────────────────────────────────────

        private static string? GetParam(string query, string key)
        {
            foreach (var part in query.Split('&'))
            {
                var kv = part.Split('=', 2);
                if (kv.Length == 2 && kv[0] == key)
                    return Uri.UnescapeDataString(kv[1]);
            }
            return null;
        }

        private static async Task<string?> ReadLineAsync(NetworkStream stream)
        {
            var sb  = new StringBuilder();
            var buf = new byte[1];
            while (true)
            {
                int n;
                try { n = await stream.ReadAsync(buf, 0, 1); }
                catch { return null; }
                if (n == 0) break;
                var c = (char)buf[0];
                if (c == '\n') break;
                if (c != '\r') sb.Append(c);
            }
            return sb.ToString();
        }

        private static async Task WriteResponseAsync(
            NetworkStream stream, int code, string contentType, string body)
        {
            var bodyBytes = Encoding.UTF8.GetBytes(body);
            var codeText  = code switch { 200 => "OK", 204 => "No Content", 404 => "Not Found", _ => "OK" };
            var header = $"HTTP/1.1 {code} {codeText}\r\n" +
                         $"Content-Type: {contentType}; charset=utf-8\r\n" +
                         $"Content-Length: {bodyBytes.Length}\r\n" +
                         $"Access-Control-Allow-Origin: *\r\n" +
                         $"Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n" +
                         $"Connection: close\r\n\r\n";
            var headerBytes = Encoding.ASCII.GetBytes(header);
            await stream.WriteAsync(headerBytes);
            if (bodyBytes.Length > 0)
                await stream.WriteAsync(bodyBytes);
            await stream.FlushAsync();
        }

        private static string GetLocalIp()
        {
            foreach (var ni in NetworkInterface.GetAllNetworkInterfaces())
            {
                if (ni.OperationalStatus != OperationalStatus.Up) continue;
                if (ni.NetworkInterfaceType == NetworkInterfaceType.Loopback) continue;
                foreach (var addr in ni.GetIPProperties().UnicastAddresses)
                {
                    if (addr.Address.AddressFamily == AddressFamily.InterNetwork)
                        return addr.Address.ToString();
                }
            }
            return "localhost";
        }

        // ─── Mobile remote HTML ─────────────────────────────────────────
        private const string RemoteHtml = @"<!DOCTYPE html>
<html lang='es'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no'>
<meta name='mobile-web-app-capable' content='yes'>
<meta name='apple-mobile-web-app-capable' content='yes'>
<title>CineCadiz Remote</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{background:#111;color:#fff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;min-height:100vh}
#status{background:#1a1a1a;padding:14px 18px 10px;border-bottom:2px solid #e53935;position:sticky;top:0;z-index:10}
#title{font-size:15px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:7px}
#prog-wrap{background:#2a2a2a;border-radius:3px;height:4px}
#prog{background:#e53935;height:100%;width:0;transition:width .8s linear;border-radius:3px}
#time-row{display:flex;justify-content:space-between;margin-top:5px;font-size:11px;color:#555}
.pad{padding:20px}
#play-btn{display:flex;align-items:center;justify-content:center;width:80px;height:80px;background:#e53935;border-radius:50%;border:none;cursor:pointer;margin:0 auto 22px;font-size:32px;color:#fff;transition:transform .1s;box-shadow:0 4px 20px #e5393544}
#play-btn:active{transform:scale(.91)}
.seek-row{display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:18px}
.seek-btn{background:#1e1e1e;border:1px solid #333;border-radius:10px;color:#ccc;font-size:12px;font-weight:600;padding:10px 14px;cursor:pointer;text-align:center;min-width:56px}
.seek-btn:active{background:#333}
.seek-icon{font-size:16px;display:block;margin-bottom:2px}
.vol-section{padding:0 20px 18px}
.sec-lbl{font-size:11px;font-weight:600;color:#555;text-transform:uppercase;letter-spacing:1px;margin-bottom:9px;display:flex;justify-content:space-between}
input[type=range]{width:100%;height:4px;-webkit-appearance:none;background:#2a2a2a;border-radius:2px;outline:none}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:22px;height:22px;border-radius:50%;background:#e53935;cursor:pointer}
#close-btn{display:block;width:calc(100% - 40px);margin:0 20px 18px;background:#1a1a1a;border:1px solid #333;border-radius:10px;color:#e53935;font-size:14px;font-weight:600;padding:13px;cursor:pointer;text-align:center}
#close-btn:active{background:#2a2a2a}
.nav-section{padding:0 20px 28px}
.nav-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}
.nav-btn{background:#1a1a1a;border:1px solid #252525;border-radius:10px;padding:13px 4px 11px;text-align:center;cursor:pointer;font-size:11px;color:#aaa}
.nav-btn:active{background:#2a2a2a;border-color:#e53935;color:#fff}
.nav-icon{font-size:22px;display:block;margin-bottom:5px}
#offline{display:none;position:fixed;inset:0;background:#111;align-items:center;justify-content:center;flex-direction:column;gap:14px;z-index:99}
#offline.show{display:flex}
.spin{width:32px;height:32px;border:3px solid #333;border-top-color:#e53935;border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<div id='status'>
  <div id='title'>CineCadiz</div>
  <div id='prog-wrap'><div id='prog'></div></div>
  <div id='time-row'><span id='cur'>0:00</span><span id='dur'>0:00</span></div>
</div>
<div class='pad'>
  <button id='play-btn' onclick=""cmd('playpause')"">&#9654;</button>
  <div class='seek-row'>
    <button class='seek-btn' onclick=""cmd('seek?s=-30')""><span class='seek-icon'>&#8634;</span>30s</button>
    <button class='seek-btn' onclick=""cmd('seek?s=-10')""><span class='seek-icon'>&#8634;</span>10s</button>
    <button class='seek-btn' onclick=""cmd('seek?s=10')""><span class='seek-icon'>&#8635;</span>10s</button>
    <button class='seek-btn' onclick=""cmd('seek?s=30')""><span class='seek-icon'>&#8635;</span>30s</button>
  </div>
</div>
<div class='vol-section'>
  <div class='sec-lbl'><span>&#128264; Volumen</span><span id='vol-lbl'>80%</span></div>
  <input type='range' id='vol' min='0' max='100' value='80'
    oninput=""document.getElementById('vol-lbl').textContent=this.value+'%'""
    onchange=""cmd('volume?v='+this.value)"">
</div>
<button id='close-btn' onclick=""cmd('close')"">&#8592; Cerrar reproductor</button>
<div class='nav-section'>
  <div class='sec-lbl' style='margin-bottom:12px'><span>Navegar</span></div>
  <div class='nav-grid'>
    <div class='nav-btn' onclick=""nav('home')""><span class='nav-icon'>&#127968;</span>Inicio</div>
    <div class='nav-btn' onclick=""nav('movies')""><span class='nav-icon'>&#127916;</span>Peliculas</div>
    <div class='nav-btn' onclick=""nav('series')""><span class='nav-icon'>&#128250;</span>Series</div>
    <div class='nav-btn' onclick=""nav('live')""><span class='nav-icon'>&#128225;</span>En vivo</div>
  </div>
</div>
<div id='offline'><div class='spin'></div><span style='color:#555;font-size:13px'>Conectando...</span></div>
<script>
async function cmd(a){try{await fetch('/api/'+a,{method:'POST'})}catch(e){showOff()}}
async function nav(p){try{await fetch('/api/navigate?page='+p,{method:'POST'})}catch(e){}}
function fmt(ms){var s=Math.floor(ms/1000),m=Math.floor(s/60),h=Math.floor(m/60);if(h>0)return h+':'+pad(m%60)+':'+pad(s%60);return m+':'+pad(s%60)}
function pad(n){return String(n).padStart(2,'0')}
function showOff(){document.getElementById('offline').classList.add('show')}
function hideOff(){document.getElementById('offline').classList.remove('show')}
async function poll(){
  try{
    var r=await fetch('/api/status');var d=await r.json();hideOff();
    document.getElementById('title').textContent=d.title||'CineCadiz';
    document.getElementById('play-btn').innerHTML=d.isPlaying?'&#9646;&#9646;':'&#9654;';
    if(!d.isLive&&d.duration>0){
      document.getElementById('prog').style.width=(d.position/d.duration*100).toFixed(1)+'%';
      document.getElementById('cur').textContent=fmt(d.position);
      document.getElementById('dur').textContent=fmt(d.duration);
    }else if(d.isLive){
      document.getElementById('prog').style.width='100%';
      document.getElementById('cur').textContent='EN VIVO';document.getElementById('dur').textContent='';
    }
    var sl=document.getElementById('vol');if(Math.abs(sl.value-d.volume)>2){sl.value=d.volume;document.getElementById('vol-lbl').textContent=d.volume+'%'}
  }catch(e){showOff()}
}
poll();setInterval(poll,1500);
</script>
</body></html>";
    }
}
