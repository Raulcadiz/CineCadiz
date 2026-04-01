using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace CineCadiz
{
    public static class AppConfig
    {
        public const string AppName      = "CineCadiz";
        public const string DefaultBaseUrl = "https://cinecadiz.servegame.com";

        private static string? _sessionKey;

        public static string DataFolder =>
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), AppName);

        public static string SessionFile  => Path.Combine(DataFolder, "session.txt");
        public static string ProgressFile => Path.Combine(DataFolder, "progress.json");
        private static string ConfigFile  => Path.Combine(DataFolder, "config.json");

        // ── Unified persisted config ────────────────────────────────
        private class ConfigData
        {
            [JsonPropertyName("baseUrl")]
            public string? BaseUrl { get; set; }

            [JsonPropertyName("customM3uUrls")]
            public List<string>? CustomM3uUrls { get; set; }
        }

        private static ConfigData? _cfg;

        private static ConfigData Cfg
        {
            get
            {
                if (_cfg != null) return _cfg;
                try
                {
                    if (File.Exists(ConfigFile))
                    {
                        var json = File.ReadAllText(ConfigFile);
                        _cfg = JsonSerializer.Deserialize<ConfigData>(json);
                    }
                }
                catch { }
                return _cfg ??= new ConfigData();
            }
        }

        private static void SaveCfg()
        {
            try
            {
                Directory.CreateDirectory(DataFolder);
                var json = JsonSerializer.Serialize(Cfg, new JsonSerializerOptions { WriteIndented = true });
                File.WriteAllText(ConfigFile, json);
            }
            catch { }
        }

        // ── BaseUrl ─────────────────────────────────────────────────
        public static string BaseUrl
        {
            get
            {
                var url = Cfg.BaseUrl;
                return !string.IsNullOrWhiteSpace(url) ? url.TrimEnd('/') : DefaultBaseUrl;
            }
            set
            {
                if (string.IsNullOrWhiteSpace(value)) return;
                Cfg.BaseUrl = value.TrimEnd('/');
                SaveCfg();
            }
        }

        // ── Custom M3U URLs ─────────────────────────────────────────
        public static List<string> CustomM3uUrls
            => Cfg.CustomM3uUrls ??= new List<string>();

        public static void SaveCustomM3uUrls() => SaveCfg();

        // ── Content refresh event ───────────────────────────────────
        public static event Action? RefreshRequested;
        public static void RequestRefresh() => RefreshRequested?.Invoke();

        // ── Session key ─────────────────────────────────────────────
        public static string SessionKey
        {
            get
            {
                if (_sessionKey != null) return _sessionKey;
                Directory.CreateDirectory(DataFolder);
                if (File.Exists(SessionFile))
                {
                    _sessionKey = File.ReadAllText(SessionFile).Trim();
                    if (!string.IsNullOrEmpty(_sessionKey)) return _sessionKey;
                }
                _sessionKey = Guid.NewGuid().ToString();
                File.WriteAllText(SessionFile, _sessionKey);
                return _sessionKey;
            }
        }
    }
}
