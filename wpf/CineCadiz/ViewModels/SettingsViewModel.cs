using System.Collections.ObjectModel;
using System.Windows;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using CineCadiz.Services;

namespace CineCadiz.ViewModels
{
    public partial class SettingsViewModel : ObservableObject
    {
        [ObservableProperty] private string _appVersion   = "1.0.0";
        [ObservableProperty] private string _watchedCount;
        [ObservableProperty] private string _serverUrl;
        [ObservableProperty] private string _newM3uUrl    = string.Empty;
        [ObservableProperty] private bool   _isRefreshing;

        public ObservableCollection<string> CustomM3uList { get; } = new();

        public string RemoteUrl  => RemoteService.Instance.RemoteUrl;
        public int    RemotePort => RemoteService.Port;

        public SettingsViewModel()
        {
            _watchedCount = $"{ProgressService.Instance.GetRecentlyWatched(100).Count} elementos";
            _serverUrl    = AppConfig.BaseUrl;

            // Load persisted M3U URLs
            foreach (var url in AppConfig.CustomM3uUrls)
                CustomM3uList.Add(url);
        }

        // ── Server ──────────────────────────────────────────────────
        [RelayCommand]
        private void SaveServer()
        {
            var url = ServerUrl?.Trim().TrimEnd('/');
            if (string.IsNullOrEmpty(url))
            {
                MessageBox.Show("Introduce una URL válida.", "CineCadiz",
                    MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }
            if (!url.StartsWith("http://") && !url.StartsWith("https://"))
                url = "https://" + url;

            AppConfig.BaseUrl = url;
            ServerUrl = url;
            MessageBox.Show($"Servidor guardado:\n{url}\n\nReinicia la aplicación para aplicar el cambio.",
                "CineCadiz", MessageBoxButton.OK, MessageBoxImage.Information);
        }

        [RelayCommand]
        private void ResetServer()
        {
            AppConfig.BaseUrl = AppConfig.DefaultBaseUrl;
            ServerUrl = AppConfig.DefaultBaseUrl;
        }

        // ── Refresh content ─────────────────────────────────────────
        [RelayCommand]
        private async System.Threading.Tasks.Task RefreshContent()
        {
            IsRefreshing = true;
            try
            {
                AppConfig.RequestRefresh();
                // Give it a moment to start loading
                await System.Threading.Tasks.Task.Delay(300);
            }
            finally
            {
                IsRefreshing = false;
            }
        }

        // ── Custom M3U ──────────────────────────────────────────────
        [RelayCommand]
        private void AddM3u()
        {
            var url = NewM3uUrl?.Trim();
            if (string.IsNullOrEmpty(url)) return;
            if (!url.StartsWith("http://") && !url.StartsWith("https://"))
            {
                MessageBox.Show("La URL debe empezar con http:// o https://", "CineCadiz",
                    MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }
            if (CustomM3uList.Contains(url)) return;

            CustomM3uList.Add(url);
            AppConfig.CustomM3uUrls.Clear();
            foreach (var u in CustomM3uList) AppConfig.CustomM3uUrls.Add(u);
            AppConfig.SaveCustomM3uUrls();
            NewM3uUrl = string.Empty;
        }

        [RelayCommand]
        private void RemoveM3u(string? url)
        {
            if (url == null) return;
            CustomM3uList.Remove(url);
            AppConfig.CustomM3uUrls.Clear();
            foreach (var u in CustomM3uList) AppConfig.CustomM3uUrls.Add(u);
            AppConfig.SaveCustomM3uUrls();
        }

        // ── History ─────────────────────────────────────────────────
        [RelayCommand]
        private void ClearHistory()
        {
            ProgressService.Instance.ClearAll();
            WatchedCount = "0 elementos";
            MessageBox.Show("Historial borrado correctamente.", "CineCadiz",
                MessageBoxButton.OK, MessageBoxImage.Information);
        }

        // ── Firewall ─────────────────────────────────────────────────
        [RelayCommand]
        private void OpenFirewallRule()
        {
            try
            {
                var p = new System.Diagnostics.Process
                {
                    StartInfo = new System.Diagnostics.ProcessStartInfo
                    {
                        FileName        = "netsh",
                        Arguments       = $"advfirewall firewall add rule name=\"CineCadiz Remote\" dir=in action=allow protocol=TCP localport={RemotePort}",
                        UseShellExecute = true,
                        Verb            = "runas",   // solicita UAC
                        CreateNoWindow  = true,
                    }
                };
                p.Start();
                p.WaitForExit(5000);
                MessageBox.Show("Regla de firewall añadida. Ahora el móvil debería conectar.",
                    "CineCadiz", MessageBoxButton.OK, MessageBoxImage.Information);
            }
            catch
            {
                MessageBox.Show(
                    $"No se pudo añadir la regla automáticamente.\n\n" +
                    $"Abre PowerShell como Administrador y ejecuta:\n\n" +
                    $"netsh advfirewall firewall add rule name=\"CineCadiz Remote\" " +
                    $"dir=in action=allow protocol=TCP localport={RemotePort}",
                    "CineCadiz", MessageBoxButton.OK, MessageBoxImage.Warning);
            }
        }

        [RelayCommand]
        private void GoBack() => NavigationService.Instance.GoBack();
    }
}
