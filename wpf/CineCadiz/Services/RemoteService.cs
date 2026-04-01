using System;
using System.Collections.Generic;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using CineCadiz.ViewModels;

namespace CineCadiz.Services
{
    public class RemoteService
    {
        private static readonly RemoteService _instance = new();
        public static RemoteService Instance => _instance;

        public const int Port = 7979;

        private TcpListener?             _listener;
        private CancellationTokenSource? _cts;
        private int                      _actualPort = Port;

        public string LocalIp  { get; private set; } = "localhost";
        public string RemoteUrl => $"http://{LocalIp}:{_actualPort}";
        public bool   IsRunning => _listener != null && _cts != null && !_cts.IsCancellationRequested;
        public IReadOnlyList<string> AllLocalIps { get; private set; } = Array.Empty<string>();

        // ── Win32 ────────────────────────────────────────────────────
        [DllImport("user32.dll", SetLastError = true)]
        private static extern uint SendInput(uint n, INPUT[] inputs, int size);

        [DllImport("user32.dll")]
        private static extern bool GetCursorPos(out POINT pt);

        [DllImport("user32.dll")]
        private static extern bool SetCursorPos(int x, int y);

        [DllImport("user32.dll")]
        private static extern int GetSystemMetrics(int nIndex);

        private const int SM_CXSCREEN = 0, SM_CYSCREEN = 1;

        [StructLayout(LayoutKind.Sequential)]
        private struct POINT { public int X, Y; }

        // INPUT struct — explicit x64 layout (40 bytes)
        [StructLayout(LayoutKind.Explicit, Size = 40)]
        private struct INPUT
        {
            [FieldOffset(0)]  public uint   type;
            [FieldOffset(8)]  public int    mi_dx;
            [FieldOffset(12)] public int    mi_dy;
            [FieldOffset(16)] public uint   mi_mouseData;
            [FieldOffset(20)] public uint   mi_dwFlags;
            [FieldOffset(24)] public uint   mi_time;
            [FieldOffset(8)]  public ushort ki_wVk;
            [FieldOffset(10)] public ushort ki_wScan;
            [FieldOffset(12)] public uint   ki_dwFlags;
            [FieldOffset(16)] public uint   ki_time;
        }

        private const uint T_MOUSE = 0, T_KEY = 1;
        private const uint MOVE  = 0x0001, LDOWN = 0x0002, LUP  = 0x0004;
        private const uint RDOWN = 0x0008, RUP   = 0x0010, WHEEL = 0x0800;
        private const uint KEYUP = 0x0002;

        private const ushort VK_LEFT = 0x25, VK_UP = 0x26, VK_RIGHT = 0x27, VK_DOWN = 0x28;
        private const ushort VK_PRIOR = 0x21, VK_NEXT = 0x22;
        private const ushort VK_RETURN = 0x0D, VK_BACK = 0x08, VK_ESCAPE = 0x1B, VK_TAB = 0x09;

        private static readonly int _sz = Marshal.SizeOf<INPUT>();

        private static void MouseMove(int dx, int dy) =>
            SendInput(1, new[] { new INPUT { type = T_MOUSE, mi_dx = dx, mi_dy = dy, mi_dwFlags = MOVE } }, _sz);

        private static void MouseClick(bool right = false) =>
            SendInput(2, new[] {
                new INPUT { type = T_MOUSE, mi_dwFlags = right ? RDOWN : LDOWN },
                new INPUT { type = T_MOUSE, mi_dwFlags = right ? RUP   : LUP   }
            }, _sz);

        private static void MouseScroll(int delta) =>
            SendInput(1, new[] { new INPUT { type = T_MOUSE, mi_mouseData = (uint)delta, mi_dwFlags = WHEEL } }, _sz);

        private static void PressKey(ushort vk) =>
            SendInput(2, new[] {
                new INPUT { type = T_KEY, ki_wVk = vk },
                new INPUT { type = T_KEY, ki_wVk = vk, ki_dwFlags = KEYUP }
            }, _sz);

        private static (double cx, double cy) GetCursorPercent()
        {
            GetCursorPos(out var pt);
            var sw = GetSystemMetrics(SM_CXSCREEN);
            var sh = GetSystemMetrics(SM_CYSCREEN);
            if (sw <= 0 || sh <= 0) return (50, 50);
            return (Math.Round(pt.X * 100.0 / sw, 1), Math.Round(pt.Y * 100.0 / sh, 1));
        }

        // ── Server lifecycle ─────────────────────────────────────────
        public void Start()
        {
            var ips = GetAllLocalIps();
            AllLocalIps = ips;
            LocalIp     = ips.Count > 0 ? ips[0] : "localhost";
            _cts        = new CancellationTokenSource();
            foreach (var port in new[] { Port, Port + 1, Port + 2 })
            {
                try { _listener = new TcpListener(IPAddress.Any, port); _listener.Start(); _actualPort = port; break; }
                catch { _listener = null; }
            }
            if (_listener == null) return;
            _ = AcceptLoopAsync(_cts.Token);
        }

        public void Stop() { _cts?.Cancel(); _listener?.Stop(); _listener = null; }

        private async Task AcceptLoopAsync(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                try { var c = await _listener!.AcceptTcpClientAsync(ct); _ = Task.Run(() => HandleClientAsync(c), ct); }
                catch { break; }
            }
        }

        private async Task HandleClientAsync(TcpClient client)
        {
            client.SendTimeout = client.ReceiveTimeout = 5000;
            try
            {
                using var stream = client.GetStream();
                var line = await ReadLineAsync(stream);
                if (string.IsNullOrWhiteSpace(line)) return;
                var parts = line.Split(' ');
                if (parts.Length < 2) return;
                var method = parts[0].ToUpperInvariant();
                var full   = parts[1];
                var qi     = full.IndexOf('?');
                var path   = qi >= 0 ? full[..qi] : full;
                var query  = qi >= 0 ? full[(qi+1)..] : "";
                string? h; while (!string.IsNullOrEmpty(h = await ReadLineAsync(stream))) { }
                if (method == "OPTIONS") { await WriteAsync(stream, 204, "text/plain", ""); return; }
                var (code, ct2, body) = await DispatchAsync(method, path, query);
                await WriteAsync(stream, code, ct2, body);
            }
            catch { }
            finally { client.Close(); }
        }

        private async Task<(int, string, string)> DispatchAsync(string method, string path, string query)
        {
            if (path is "/" or "") return (200, "text/html", RemoteHtml);

            if (path == "/api/status" && method == "GET")
            {
                var p = PlayerViewModel.Instance;
                var (cx, cy) = GetCursorPercent();
                return (200, "application/json", JsonSerializer.Serialize(new {
                    title = p.Title, isPlaying = p.IsPlaying, isLive = p.IsLive,
                    isVisible = p.IsVisible, position = p.CurrentPosition,
                    duration = p.TotalDuration, volume = p.Volume,
                    isFullscreen = p.IsFullscreen,
                    cursorX = cx, cursorY = cy
                }));
            }

            if (method == "POST")
            {
                switch (path)
                {
                    case "/api/mouse":
                        if (int.TryParse(GetParam(query,"dx"), out var mdx) && int.TryParse(GetParam(query,"dy"), out var mdy))
                            MouseMove(mdx, mdy);
                        var (cx2, cy2) = GetCursorPercent();
                        return (200, "application/json", $"{{\"cx\":{cx2},\"cy\":{cy2}}}");

                    case "/api/click":
                        MouseClick(GetParam(query,"btn") == "right");
                        return OK;

                    case "/api/scroll":
                        var amt = int.TryParse(GetParam(query,"amt"), out var a) ? a : 120;
                        MouseScroll(GetParam(query,"dir") == "up" ? amt : -amt);
                        return OK;

                    case "/api/centercursor":
                        await Application.Current.Dispatcher.InvokeAsync(() => {
                            Application.Current.MainWindow?.Activate();
                            var w = Application.Current.MainWindow;
                            if (w != null)
                            {
                                var pt = w.PointToScreen(new Point(w.ActualWidth / 2, w.ActualHeight / 2));
                                SetCursorPos((int)pt.X, (int)pt.Y);
                            }
                        });
                        return OK;

                    case "/api/key":
                        var k = GetParam(query, "k") ?? "";
                        await Application.Current.Dispatcher.InvokeAsync(() =>
                            Application.Current.MainWindow?.Activate());
                        switch (k)
                        {
                            case "up":    MouseScroll( 240); PressKey(VK_UP);     break;
                            case "down":  MouseScroll(-240); PressKey(VK_DOWN);   break;
                            case "left":                     PressKey(VK_LEFT);   break;
                            case "right":                    PressKey(VK_RIGHT);  break;
                            case "enter": MouseClick();      PressKey(VK_RETURN); break;
                            case "back":                     PressKey(VK_BACK);   break;
                            case "esc":                      PressKey(VK_ESCAPE); break;
                            case "tab":                      PressKey(VK_TAB);    break;
                            case "pgup":  MouseScroll( 720); PressKey(VK_PRIOR);  break;
                            case "pgdn":  MouseScroll(-720); PressKey(VK_NEXT);   break;
                        }
                        return OK;
                }

                await Application.Current.Dispatcher.InvokeAsync(() =>
                {
                    var player = PlayerViewModel.Instance;
                    var main   = Application.Current.MainWindow?.DataContext as MainViewModel;
                    switch (path)
                    {
                        case "/api/playpause":  player.TogglePlayPauseCommand.Execute(null);  break;
                        case "/api/close":      player.CloseCommand.Execute(null);             break;
                        case "/api/fullscreen": player.ToggleFullscreenCommand.Execute(null);  break;
                        case "/api/seek":
                            if (int.TryParse(GetParam(query,"s"), out var s)) player.SeekSeconds(s);
                            break;
                        case "/api/volume":
                            if (int.TryParse(GetParam(query,"v"), out var v)) player.SetVolume(v);
                            break;
                        case "/api/navigate":
                            if (main == null) break;
                            switch (GetParam(query,"page"))
                            {
                                case "home":   main.NavigateHomeCommand.Execute(null);   break;
                                case "movies": main.NavigateMoviesCommand.Execute(null); break;
                                case "series": main.NavigateSeriesCommand.Execute(null); break;
                                case "live":   main.NavigateLiveCommand.Execute(null);   break;
                            }
                            break;
                    }
                });
                return OK;
            }

            return (404, "text/plain", "Not found");
        }

        private static readonly (int, string, string) OK = (200, "application/json", "{\"ok\":true}");

        private static string? GetParam(string q, string key)
        {
            foreach (var p in q.Split('&'))
            { var kv = p.Split('=',2); if (kv.Length==2 && kv[0]==key) return Uri.UnescapeDataString(kv[1]); }
            return null;
        }

        private static async Task<string?> ReadLineAsync(NetworkStream s)
        {
            var sb = new StringBuilder(); var buf = new byte[1];
            while (true)
            {
                int n; try { n = await s.ReadAsync(buf, 0, 1); } catch { return null; }
                if (n == 0) break;
                var c = (char)buf[0];
                if (c == '\n') break; if (c != '\r') sb.Append(c);
            }
            return sb.ToString();
        }

        private static async Task WriteAsync(NetworkStream s, int code, string ct, string body)
        {
            var bb = Encoding.UTF8.GetBytes(body);
            var tx = code switch { 200=>"OK", 204=>"No Content", _=>"Not Found" };
            var hdr = $"HTTP/1.1 {code} {tx}\r\nContent-Type: {ct}; charset=utf-8\r\n" +
                      $"Content-Length: {bb.Length}\r\nAccess-Control-Allow-Origin: *\r\n" +
                      $"Access-Control-Allow-Methods: GET, POST, OPTIONS\r\nConnection: close\r\n\r\n";
            await s.WriteAsync(Encoding.ASCII.GetBytes(hdr));
            if (bb.Length > 0) await s.WriteAsync(bb);
            await s.FlushAsync();
        }

        private static List<string> GetAllLocalIps()
        {
            var wifi = new List<string>(); var eth = new List<string>(); var other = new List<string>();
            foreach (var ni in NetworkInterface.GetAllNetworkInterfaces())
            {
                if (ni.OperationalStatus != OperationalStatus.Up) continue;
                if (ni.NetworkInterfaceType is NetworkInterfaceType.Loopback or NetworkInterfaceType.Tunnel) continue;
                var nm = ni.Name + ni.Description;
                if (nm.Contains("VPN",StringComparison.OrdinalIgnoreCase)||nm.Contains("TAP",StringComparison.OrdinalIgnoreCase)||nm.Contains("Hamachi",StringComparison.OrdinalIgnoreCase)) continue;
                foreach (var addr in ni.GetIPProperties().UnicastAddresses)
                {
                    if (addr.Address.AddressFamily != AddressFamily.InterNetwork) continue;
                    var ip = addr.Address.ToString();
                    if (ip.StartsWith("169.254.")||ip.StartsWith("100.")) continue;
                    switch (ni.NetworkInterfaceType)
                    {
                        case NetworkInterfaceType.Wireless80211: wifi.Add(ip);  break;
                        case NetworkInterfaceType.Ethernet:      eth.Add(ip);   break;
                        default:                                 other.Add(ip); break;
                    }
                }
            }
            var r = new List<string>(); r.AddRange(wifi); r.AddRange(eth); r.AddRange(other);
            return r;
        }

        // ─── Mobile remote HTML ─────────────────────────────────────
        private const string RemoteHtml = @"<!DOCTYPE html>
<html lang='es'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no'>
<meta name='mobile-web-app-capable' content='yes'>
<meta name='apple-mobile-web-app-capable' content='yes'>
<title>CineCadiz Remote</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent;user-select:none;-webkit-user-select:none}
body{background:#111;color:#fff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding-bottom:28px;overscroll-behavior:none}

/* Status */
#status{background:#1a1a1a;padding:11px 16px 7px;border-bottom:2px solid #e53935;position:sticky;top:0;z-index:10}
#title{font-size:13px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:5px}
#prog-wrap{background:#2a2a2a;height:3px;border-radius:3px}
#prog{background:#e53935;height:100%;width:0;border-radius:3px;transition:width .8s linear}
#time-row{display:flex;justify-content:space-between;margin-top:3px;font-size:10px;color:#555}

/* Section label */
.sec{font-size:10px;font-weight:700;color:#444;text-transform:uppercase;letter-spacing:.1em;padding:14px 16px 6px;display:flex;align-items:center;gap:8px}
.sec::after{content:'';flex:1;height:1px;background:#1e1e1e}

/* ── Touchpad ── */
#tp-wrap{margin:0 16px;position:relative}
#touchpad{
  background:#161616;border:1.5px solid #2a2a2a;border-radius:16px;
  height:190px;width:100%;display:block;touch-action:none;cursor:none;
  position:relative;overflow:hidden;
}
/* Screen-map overlay (top-right corner) */
#screen-map{
  position:absolute;top:10px;right:10px;
  width:80px;height:50px;
  border:1.5px solid #333;border-radius:5px;background:#0d0d0d;
  overflow:hidden;pointer-events:none;
}
#sm-cur{
  position:absolute;
  width:8px;height:8px;
  background:#e53935;border-radius:50%;
  transform:translate(-50%,-50%);
  transition:left .12s,top .12s;
  box-shadow:0 0 6px #e53935aa;
  left:50%;top:50%;
}
/* Finger dot inside touchpad */
#fp{
  position:absolute;
  width:28px;height:28px;
  border:2.5px solid #e53935;border-radius:50%;
  transform:translate(-50%,-50%);
  pointer-events:none;
  display:none;
  box-shadow:0 0 10px #e5393566;
}
#fp-inner{
  position:absolute;inset:6px;
  background:#e53935;border-radius:50%;
  opacity:.7;
}
/* Touchpad hint text */
#tp-hint{
  position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
  font-size:12px;color:#333;pointer-events:none;text-align:center;line-height:1.6;
}
/* Touch active state */
#touchpad.active{border-color:#e53935;background:#1a1212}
#touchpad.active #tp-hint{opacity:0}

/* Sensitivity row */
.tp-footer{display:flex;align-items:center;gap:10px;margin-top:7px}
.tp-footer label{font-size:10px;color:#555;white-space:nowrap}
.tp-footer input[type=range]{flex:1;height:3px;-webkit-appearance:none;background:#2a2a2a;border-radius:2px;outline:none}
.tp-footer input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:18px;height:18px;border-radius:50%;background:#e53935}
.tp-center{background:#1a1a1a;border:1px solid #252525;border-radius:8px;color:#888;font-size:11px;padding:6px 10px;cursor:pointer;white-space:nowrap;touch-action:manipulation}
.tp-center:active{background:#252525;color:#fff;border-color:#e53935}

/* Click buttons */
.click-row{display:flex;gap:8px;margin:8px 16px 0}
.c-btn{
  flex:1;background:#181818;border:1.5px solid #242424;border-radius:12px;
  color:#bbb;font-size:13px;font-weight:600;padding:14px 6px;
  text-align:center;cursor:pointer;touch-action:manipulation;
  transition:background .1s,border-color .1s,transform .08s;
}
.c-btn:active{background:#252525;border-color:#e53935;color:#fff;transform:scale(.97)}

/* ── D-pad + scroll ── */
.dpad-row{display:flex;align-items:center;justify-content:center;gap:16px;padding:4px 16px 2px}
/* Scroll column */
.scr-col{display:flex;flex-direction:column;gap:8px;align-items:center}
.s-btn{
  width:54px;height:54px;background:#181818;border:1.5px solid #242424;border-radius:13px;
  display:flex;align-items:center;justify-content:center;font-size:22px;color:#bbb;
  cursor:pointer;touch-action:manipulation;transition:background .08s,border-color .08s,transform .08s;
}
.s-btn:active,.s-btn.pressed{background:#252525;border-color:#e53935;color:#fff;transform:scale(.93)}
.s-lbl{font-size:9px;color:#444;text-transform:uppercase;letter-spacing:.05em;margin-top:2px}
/* D-pad grid */
.dpad{display:grid;grid-template-columns:repeat(3,58px);grid-template-rows:repeat(3,58px);gap:5px}
.dp{
  background:#181818;border:1.5px solid #242424;border-radius:13px;
  display:flex;align-items:center;justify-content:center;font-size:21px;color:#bbb;
  cursor:pointer;touch-action:manipulation;
  transition:background .08s,border-color .08s,transform .08s;
  position:relative;overflow:hidden;
}
.dp:active{background:#252525;border-color:#e53935;color:#fff;transform:scale(.92)}
/* Ripple */
.dp::after{
  content:'';position:absolute;width:60px;height:60px;border-radius:50%;
  background:rgba(229,57,53,.25);transform:scale(0);opacity:0;
  transition:transform .3s,opacity .3s;pointer-events:none;
}
.dp:active::after{transform:scale(1.8);opacity:1}
.dp.ok{background:#1e1e1e;border-color:#333;font-size:14px;font-weight:800;letter-spacing:.04em}
.dp.ok:active{background:#e53935;border-color:#e53935;color:#fff}
.dp.x{background:transparent;border:none;pointer-events:none}

/* ── Player ── */
.player-box{margin:0 16px;background:#161616;border:1.5px solid #1e1e1e;border-radius:16px;padding:16px}
#play-btn{
  width:72px;height:72px;background:#e53935;border-radius:50%;border:none;
  cursor:pointer;margin:0 auto 14px;font-size:28px;color:#fff;display:flex;
  align-items:center;justify-content:center;box-shadow:0 4px 20px #e5393555;
  transition:transform .1s;touch-action:manipulation;
}
#play-btn:active{transform:scale(.88)}
.seek-row{display:flex;justify-content:center;gap:7px;margin-bottom:12px}
.sk{
  background:#1e1e1e;border:1.5px solid #252525;border-radius:11px;color:#bbb;
  font-size:11px;font-weight:600;padding:10px 10px 8px;min-width:52px;text-align:center;
  cursor:pointer;touch-action:manipulation;transition:background .08s,border-color .08s;
}
.sk:active{background:#252525;border-color:#e53935;color:#fff}
.sk i{font-size:16px;display:block;margin-bottom:2px}
.vol-row{margin-bottom:12px}
.vol-lbl{font-size:10px;color:#555;text-transform:uppercase;letter-spacing:.08em;display:flex;justify-content:space-between;margin-bottom:7px}
input[type=range]{width:100%;height:5px;-webkit-appearance:none;background:#2a2a2a;border-radius:3px;outline:none}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:24px;height:24px;border-radius:50%;background:#e53935;cursor:pointer}
.act-row{display:flex;gap:8px}
.a-btn{
  flex:1;background:#1e1e1e;border:1.5px solid #252525;border-radius:11px;color:#bbb;
  font-size:11px;font-weight:600;padding:12px 4px;text-align:center;
  cursor:pointer;touch-action:manipulation;transition:background .08s,border-color .08s;
}
.a-btn:active{background:#252525;border-color:#e53935;color:#fff}
.a-btn i{font-size:18px;display:block;margin-bottom:3px}

/* ── Nav ── */
.nav-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:0 16px}
.n-btn{
  background:#161616;border:1.5px solid #1e1e1e;border-radius:14px;
  padding:16px 4px 12px;text-align:center;cursor:pointer;color:#888;
  touch-action:manipulation;transition:background .08s,border-color .08s;
}
.n-btn:active{background:#1e1e1e;border-color:#e53935;color:#fff}
.n-btn i{font-size:26px;display:block;margin-bottom:5px}
.n-btn span{font-size:11px;font-weight:600}

/* Offline */
#offline{display:none;position:fixed;inset:0;background:#111;align-items:center;justify-content:center;flex-direction:column;gap:14px;z-index:99}
#offline.show{display:flex}
.spin{width:32px;height:32px;border:3px solid #333;border-top-color:#e53935;border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>

<!-- STATUS -->
<div id='status'>
  <div id='title'>CineCadiz</div>
  <div id='prog-wrap'><div id='prog'></div></div>
  <div id='time-row'><span id='cur'>0:00</span><span id='dur'>0:00</span></div>
</div>

<!-- TOUCHPAD -->
<div class='sec'>Touchpad</div>
<div id='tp-wrap'>
  <div id='touchpad'>
    <!-- Screen-map: shows real cursor position on PC -->
    <div id='screen-map'>
      <div id='sm-cur'></div>
    </div>
    <!-- Finger dot -->
    <div id='fp'><div id='fp-inner'></div></div>
    <!-- Hint -->
    <div id='tp-hint'>&#128432;<br>Arrastra para mover el cursor<br><small style='color:#2a2a2a'>Doble tap = click</small></div>
  </div>
  <div class='tp-footer'>
    <label>Vel.</label>
    <input type='range' id='sens' min='0.8' max='5' step='0.2' value='2.2'>
    <div class='tp-center' onclick=""centercursor()"">&#8982; Centrar</div>
  </div>
</div>
<div class='click-row'>
  <div class='c-btn' id='lc' onclick=""click_btn(false)"">&#128432; Click izquierdo</div>
  <div class='c-btn' onclick=""click_btn(true)"">&#9776; Click derecho</div>
</div>

<!-- D-PAD -->
<div class='sec'>Navegar / Desplazar</div>
<div class='dpad-row'>
  <div class='scr-col'>
    <div>
      <div class='s-btn' id='su' onpointerdown=""startScroll('up',this)"" onpointerup=""stopScroll()"" onpointercancel=""stopScroll()"">&#9650;</div>
      <div class='s-lbl' style='text-align:center'>Arriba</div>
    </div>
    <div>
      <div class='s-btn' id='sd' onpointerdown=""startScroll('down',this)"" onpointerup=""stopScroll()"" onpointercancel=""stopScroll()"">&#9660;</div>
      <div class='s-lbl' style='text-align:center'>Abajo</div>
    </div>
  </div>

  <div class='dpad'>
    <div class='dp x'></div>
    <div class='dp' onclick=""key('up')"">&#9650;</div>
    <div class='dp' style='font-size:10px;font-weight:700' onclick=""key('pgup')"">Pg<br>Up</div>
    <div class='dp' onclick=""key('left')"">&#9664;</div>
    <div class='dp ok' onclick=""key('enter')"">OK</div>
    <div class='dp' onclick=""key('right')"">&#9654;</div>
    <div class='dp' style='font-size:11px;font-weight:700' onclick=""key('esc')"">ESC</div>
    <div class='dp' onclick=""key('down')"">&#9660;</div>
    <div class='dp' style='font-size:10px;font-weight:700' onclick=""key('pgdn')"">Pg<br>Dn</div>
  </div>
</div>

<!-- PLAYER -->
<div class='sec'>Reproductor</div>
<div class='player-box'>
  <button id='play-btn' onclick=""cmd('playpause')"">&#9654;</button>
  <div class='seek-row'>
    <div class='sk' onclick=""cmd('seek?s=-30')""><i>&#8634;</i>30s</div>
    <div class='sk' onclick=""cmd('seek?s=-10')""><i>&#8634;</i>10s</div>
    <div class='sk' onclick=""cmd('seek?s=10')""><i>&#8635;</i>10s</div>
    <div class='sk' onclick=""cmd('seek?s=30')""><i>&#8635;</i>30s</div>
  </div>
  <div class='vol-row'>
    <div class='vol-lbl'><span>&#128264; Volumen</span><span id='vol-lbl'>80%</span></div>
    <input type='range' id='vol' min='0' max='100' value='80'
      oninput=""document.getElementById('vol-lbl').textContent=this.value+'%'""
      onchange=""cmd('volume?v='+this.value)"">
  </div>
  <div class='act-row'>
    <div class='a-btn' id='fs-btn' onclick=""cmd('fullscreen')""><i>&#x26F6;</i>Pantalla completa</div>
    <div class='a-btn' onclick=""cmd('close')""><i>&#x2190;</i>Cerrar vídeo</div>
  </div>
</div>

<!-- NAV -->
<div class='sec'>Sección</div>
<div class='nav-grid'>
  <div class='n-btn' onclick=""nav('home')""><i>&#127968;</i><span>Inicio</span></div>
  <div class='n-btn' onclick=""nav('movies')""><i>&#127916;</i><span>Películas</span></div>
  <div class='n-btn' onclick=""nav('series')""><i>&#128250;</i><span>Series</span></div>
  <div class='n-btn' onclick=""nav('live')""><i>&#128225;</i><span>En vivo</span></div>
</div>

<div id='offline'><div class='spin'></div><span style='color:#555;font-size:13px'>Conectando...</span></div>

<script>
// ── Utils ─────────────────────────────────────────────────────────
async function post(url){try{var r=await fetch(url,{method:'POST'});return r.ok?await r.json():null}catch(e){showOff();return null}}
function cmd(a){post('/api/'+a)}
function nav(p){post('/api/navigate?page='+p)}
function key(k){post('/api/key?k='+k)}
function click_btn(r){post('/api/click'+(r?'?btn=right':''))}
function centercursor(){post('/api/centercursor')}

// ── Cursor map update ─────────────────────────────────────────────
var smCur = document.getElementById('sm-cur');
function updateCursorMap(cx,cy){
  smCur.style.left = cx+'%';
  smCur.style.top  = cy+'%';
}

// ── Scroll (hold) ─────────────────────────────────────────────────
var _st=null;
function startScroll(dir,el){el.classList.add('pressed');doScroll(dir);_st=setInterval(()=>doScroll(dir),90)}
function stopScroll(){clearInterval(_st);_st=null;document.querySelectorAll('.s-btn').forEach(e=>e.classList.remove('pressed'))}
function doScroll(dir){post('/api/scroll?dir='+dir+'&amt=120')}

// ── Touchpad ──────────────────────────────────────────────────────
(function(){
  var tp   = document.getElementById('touchpad');
  var fp   = document.getElementById('fp');
  var sens = document.getElementById('sens');

  var lx=null,ly=null,ax=0,ay=0,timer=null;
  // Double-tap detection
  var lastTap=0;

  function getSens(){ return parseFloat(sens.value)||2.2 }

  async function flush(){
    if(ax||ay){
      var res = await post('/api/mouse?dx='+Math.round(ax)+'&dy='+Math.round(ay));
      if(res&&res.cx!=null) updateCursorMap(res.cx,res.cy);
      ax=0;ay=0;
    }
    timer=null;
  }

  tp.addEventListener('pointerdown',function(e){
    e.preventDefault();
    tp.setPointerCapture(e.pointerId);
    lx=e.clientX;ly=e.clientY;
    tp.classList.add('active');
    // Show finger dot
    var rect=tp.getBoundingClientRect();
    fp.style.left=(e.clientX-rect.left)+'px';
    fp.style.top =(e.clientY-rect.top)+'px';
    fp.style.display='block';
    // Double tap → click
    var now=Date.now();
    if(now-lastTap<350){ click_btn(false); lastTap=0; }
    else lastTap=now;
  },{passive:false});

  tp.addEventListener('pointermove',function(e){
    if(lx==null)return;
    e.preventDefault();
    var dx=(e.clientX-lx)*getSens();
    var dy=(e.clientY-ly)*getSens();
    lx=e.clientX;ly=e.clientY;
    ax+=dx;ay+=dy;
    // Move finger dot
    var rect=tp.getBoundingClientRect();
    var nx=Math.max(14,Math.min(rect.width-14, e.clientX-rect.left));
    var ny=Math.max(14,Math.min(rect.height-14,e.clientY-rect.top));
    fp.style.left=nx+'px';
    fp.style.top =ny+'px';
    if(!timer)timer=setTimeout(flush,16);
  },{passive:false});

  function end(){lx=null;ly=null;fp.style.display='none';tp.classList.remove('active')}
  tp.addEventListener('pointerup',end);
  tp.addEventListener('pointercancel',end);
})();

// ── Status poll ───────────────────────────────────────────────────
function fmt(ms){var s=Math.floor(ms/1000),m=Math.floor(s/60),h=Math.floor(m/60);return h?h+':'+pd(m%60)+':'+pd(s%60):m+':'+pd(s%60)}
function pd(n){return String(n).padStart(2,'0')}
function showOff(){document.getElementById('offline').classList.add('show')}
function hideOff(){document.getElementById('offline').classList.remove('show')}

async function poll(){
  try{
    var r=await fetch('/api/status'),d=await r.json();hideOff();
    document.getElementById('title').textContent=d.title||'CineCadiz';
    document.getElementById('play-btn').innerHTML=d.isPlaying?'&#9646;&#9646;':'&#9654;';
    document.getElementById('fs-btn').style.borderColor=d.isFullscreen?'#e53935':'';
    updateCursorMap(d.cursorX,d.cursorY);
    if(!d.isLive&&d.duration>0){
      document.getElementById('prog').style.width=(d.position/d.duration*100).toFixed(1)+'%';
      document.getElementById('cur').textContent=fmt(d.position);
      document.getElementById('dur').textContent=fmt(d.duration);
    }else if(d.isLive){
      document.getElementById('prog').style.width='100%';
      document.getElementById('cur').textContent='EN VIVO';
      document.getElementById('dur').textContent='';
    }
    var sl=document.getElementById('vol');
    if(Math.abs(sl.value-d.volume)>2){sl.value=d.volume;document.getElementById('vol-lbl').textContent=d.volume+'%'}
  }catch(e){showOff()}
}
poll();setInterval(poll,1200);
</script>
</body>
</html>";
    }
}
