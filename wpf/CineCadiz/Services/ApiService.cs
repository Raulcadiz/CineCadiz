using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using CineCadiz.Models;

namespace CineCadiz.Services
{
    public class ApiService
    {
        private static readonly HttpClient _httpClient;
        private static readonly JsonSerializerOptions _jsonOptions;

        static ApiService()
        {
            _httpClient = new HttpClient();
            _httpClient.DefaultRequestHeaders.Add("User-Agent", "CineCadiz-WPF/1.0");
            _httpClient.Timeout = TimeSpan.FromSeconds(30);

            _jsonOptions = new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            };
        }

        private static readonly ApiService _instance = new();
        public static ApiService Instance => _instance;

        private ApiService() { }

        private string BuildUrl(string path) => $"{AppConfig.BaseUrl}{path}";

        public async Task<ApiResponse<ContentItem>> GetMoviesAsync(int page = 1, int limit = 25, string query = "")
        {
            var url = BuildUrl($"/api/peliculas?page={page}&limit={limit}");
            if (!string.IsNullOrWhiteSpace(query))
                url += $"&q={Uri.EscapeDataString(query)}";

            var json = await _httpClient.GetStringAsync(url);
            return JsonSerializer.Deserialize<ApiResponse<ContentItem>>(json, _jsonOptions)
                   ?? new ApiResponse<ContentItem>();
        }

        public async Task<ApiResponse<SeriesItem>> GetSeriesAsync(int page = 1, int limit = 25, string query = "")
        {
            var url = BuildUrl($"/api/series-agrupadas?page={page}&limit={limit}");
            if (!string.IsNullOrWhiteSpace(query))
                url += $"&q={Uri.EscapeDataString(query)}";

            var json = await _httpClient.GetStringAsync(url);
            return JsonSerializer.Deserialize<ApiResponse<SeriesItem>>(json, _jsonOptions)
                   ?? new ApiResponse<SeriesItem>();
        }

        public async Task<List<ContentItem>> GetSeriesEpisodesAsync(string title)
        {
            var url = BuildUrl($"/api/serie-episodios?titulo={Uri.EscapeDataString(title)}");
            var json = await _httpClient.GetStringAsync(url);
            return JsonSerializer.Deserialize<List<ContentItem>>(json, _jsonOptions)
                   ?? new List<ContentItem>();
        }

        public async Task<List<LiveGroup>> GetLiveGroupsAsync(string query = "", string category = "", int? listaId = null)
        {
            var parts = new List<string>();
            if (!string.IsNullOrWhiteSpace(query))
                parts.Add($"q={Uri.EscapeDataString(query)}");
            if (!string.IsNullOrWhiteSpace(category))
                parts.Add($"categoria={Uri.EscapeDataString(category)}");
            if (listaId.HasValue)
                parts.Add($"lista_id={listaId.Value}");

            var url = BuildUrl("/api/live-agrupados") + (parts.Count > 0 ? "?" + string.Join("&", parts) : "");
            var json = await _httpClient.GetStringAsync(url);
            return JsonSerializer.Deserialize<List<LiveGroup>>(json, _jsonOptions)
                   ?? new List<LiveGroup>();
        }

        public async Task<List<string>> GetLiveCategoriasAsync(int? listaId = null)
        {
            var url = BuildUrl("/api/live-categorias");
            if (listaId.HasValue) url += $"?lista_id={listaId.Value}";
            var json = await _httpClient.GetStringAsync(url);
            return JsonSerializer.Deserialize<List<string>>(json, _jsonOptions)
                   ?? new List<string>();
        }

        public async Task<List<Models.LiveListInfo>> GetLiveListasAsync()
        {
            var url = BuildUrl("/api/live-listas");
            var json = await _httpClient.GetStringAsync(url);
            return JsonSerializer.Deserialize<List<Models.LiveListInfo>>(json, _jsonOptions)
                   ?? new List<Models.LiveListInfo>();
        }

        /// <summary>
        /// Fetches and parses an M3U playlist from a URL, returning a flat list of LiveGroups.
        /// </summary>
        public async Task<List<LiveGroup>> GetLiveFromM3uAsync(string m3uUrl)
        {
            var groups = new List<LiveGroup>();
            try
            {
                var content = await _httpClient.GetStringAsync(m3uUrl);
                var lines   = content.Split('\n');

                LiveGroup? current = null;
                int fakeId = -1_000_000; // negative IDs won't clash with backend IDs

                foreach (var rawLine in lines)
                {
                    var line = rawLine.Trim();

                    if (line.StartsWith("#EXTINF:", StringComparison.OrdinalIgnoreCase))
                    {
                        current    = new LiveGroup { Id = fakeId-- };

                        // tvg-name
                        var m = Regex.Match(line, @"tvg-name=""([^""]*)""");
                        if (m.Success) current.Title = m.Groups[1].Value;

                        // tvg-logo
                        m = Regex.Match(line, @"tvg-logo=""([^""]*)""");
                        if (m.Success) current.Image = m.Groups[1].Value;

                        // group-title
                        m = Regex.Match(line, @"group-title=""([^""]*)""");
                        if (m.Success) current.GroupTitle = m.Groups[1].Value;

                        // Fallback title: text after last comma
                        if (string.IsNullOrEmpty(current.Title))
                        {
                            var ci = line.LastIndexOf(',');
                            if (ci >= 0) current.Title = line[(ci + 1)..].Trim();
                        }
                    }
                    else if (!line.StartsWith('#') && !string.IsNullOrWhiteSpace(line) && current != null)
                    {
                        current.StreamUrl = line;
                        groups.Add(current);
                        current = null;
                    }
                }
            }
            catch { }
            return groups;
        }

        public async Task<List<ContentItem>> GetTrendingAsync()
        {
            var url = BuildUrl("/api/trending");
            var json = await _httpClient.GetStringAsync(url);
            return JsonSerializer.Deserialize<List<ContentItem>>(json, _jsonOptions)
                   ?? new List<ContentItem>();
        }

        public async Task PostWatchAsync(int contenidoId)
        {
            try
            {
                var payload = new { session_key = AppConfig.SessionKey, contenido_id = contenidoId };
                var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
                await _httpClient.PostAsync(BuildUrl("/api/watch"), content);
            }
            catch
            {
                // Fire and forget - ignore errors
            }
        }

        public async Task<string?> ReportLiveDownAsync(int id, string url)
        {
            try
            {
                var payload = new { url };
                var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
                var response = await _httpClient.PostAsync(BuildUrl($"/api/live/{id}/report-down"), content);
                if (response.IsSuccessStatusCode)
                {
                    var json = await response.Content.ReadAsStringAsync();
                    using var doc = JsonDocument.Parse(json);
                    if (doc.RootElement.TryGetProperty("next_url", out var nextUrl))
                        return nextUrl.GetString();
                }
            }
            catch { }
            return null;
        }
    }
}
