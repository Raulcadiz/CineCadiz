using System.Net.Http.Json;
using System.Text.Json;
using CineCadizConsole.Models;

namespace CineCadizConsole.Services;

class ApiService
{
    readonly HttpClient _http;
    static readonly JsonSerializerOptions Opts = new() { PropertyNameCaseInsensitive = true };

    public ApiService()
    {
        _http = new HttpClient { BaseAddress = new Uri(AppConfig.BaseUrl) };
        _http.DefaultRequestHeaders.Add("User-Agent", "CineCadiz-Console/1.0");
        _http.Timeout = TimeSpan.FromSeconds(20);
    }

    public Task<Paginated<ContentItem>> GetMoviesAsync(string? q = null, int page = 1)
    {
        var url = $"/api/peliculas?page={page}&limit=25";
        if (!string.IsNullOrEmpty(q)) url += $"&q={Uri.EscapeDataString(q)}";
        return GetAsync<Paginated<ContentItem>>(url);
    }

    public Task<Paginated<SeriesGroup>> GetSeriesAsync(string? q = null, int page = 1)
    {
        var url = $"/api/series-agrupadas?page={page}&limit=25";
        if (!string.IsNullOrEmpty(q)) url += $"&q={Uri.EscapeDataString(q)}";
        return GetAsync<Paginated<SeriesGroup>>(url);
    }

    public Task<List<ContentItem>> GetSeriesEpisodesAsync(string title)
        => GetAsync<List<ContentItem>>($"/api/serie-episodios?titulo={Uri.EscapeDataString(title)}");

    public Task<List<LiveGroup>> GetLiveAsync(string? q = null, string? category = null)
    {
        var url = "/api/live-agrupados";
        var sep = '?';
        if (!string.IsNullOrEmpty(q))        { url += $"?q={Uri.EscapeDataString(q)}";                  sep = '&'; }
        if (!string.IsNullOrEmpty(category)) { url += $"{sep}categoria={Uri.EscapeDataString(category)}"; }
        return GetAsync<List<LiveGroup>>(url);
    }

    public Task<List<string>> GetLiveCategoriesAsync()
        => GetAsync<List<string>>("/api/live-categorias");

    public Task<List<ContentItem>> GetTrendingAsync()
        => GetAsync<List<ContentItem>>("/api/trending");

    public async Task RecordWatchAsync(int contentId)
    {
        try
        {
            await _http.PostAsJsonAsync("/api/watch",
                new { session_key = AppConfig.SessionKey, contenido_id = contentId });
        }
        catch { /* non-critical */ }
    }

    public async Task<string?> ReportLiveDownAsync(int channelId, string url)
    {
        try
        {
            var resp = await _http.PostAsJsonAsync(
                $"/api/live/{channelId}/report-down", new { url });
            if (!resp.IsSuccessStatusCode) return null;
            var doc = await resp.Content.ReadFromJsonAsync<JsonElement>(Opts);
            return doc.TryGetProperty("next_url", out var v) ? v.GetString() : null;
        }
        catch { return null; }
    }

    async Task<T> GetAsync<T>(string url)
    {
        var resp = await _http.GetAsync(url);
        resp.EnsureSuccessStatusCode();
        return (await resp.Content.ReadFromJsonAsync<T>(Opts))!;
    }
}
