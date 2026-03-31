using CineCadizConsole.Models;
using CineCadizConsole.Services;
using Spectre.Console;

namespace CineCadizConsole.UI;

static class LiveUI
{
    const int ActAll    = -1;
    const int ActSearch = -2;
    const int ActClear  = -3;
    const int ActBack   = -4;

    public static async Task RunAsync(ApiService api, PlayerService player)
    {
        while (true)
        {
            Console.Clear();
            List<string> cats = [];
            await AnsiConsole.Status()
                .StartAsync("Cargando categorias...", async _ =>
                    cats = await api.GetLiveCategoriesAsync());

            // Índice -1 = "Todos", 0..N = categorías, ActBack = volver
            var catIndices = new[] { ActAll }
                .Concat(Enumerable.Range(0, cats.Count))
                .Append(ActBack)
                .ToList();

            var selCat = AnsiConsole.Prompt(
                new SelectionPrompt<int>()
                    .Title("[bold]LIVE[/] — Categoria")
                    .HighlightStyle("bold red")
                    .PageSize(20)
                    .UseConverter(i => i switch
                    {
                        ActAll  => "[dim]── Todos los canales ──[/]",
                        ActBack => "← Volver",
                        _       => Markup.Escape(cats[i]),
                    })
                    .AddChoices(catIndices));

            if (selCat == ActBack) return;

            string? category = selCat == ActAll ? null : cats[selCat];
            await BrowseChannelsAsync(api, player, category);
        }
    }

    static async Task BrowseChannelsAsync(ApiService api, PlayerService player, string? category)
    {
        string? query = null;

        while (true)
        {
            Console.Clear();
            List<LiveGroup> channels = [];
            string? error = null;

            await AnsiConsole.Status().StartAsync("Cargando canales...", async _ =>
            {
                try   { channels = await api.GetLiveAsync(query, category); }
                catch (Exception ex) { error = ex.Message; }
            });

            if (error is not null)
            {
                AnsiConsole.MarkupLine($"[red]Error: {Markup.Escape(error)}[/]");
                Console.ReadKey(intercept: true);
                return;
            }

            if (channels.Count == 0)
            {
                AnsiConsole.MarkupLine("[yellow]No hay canales disponibles.[/]");
                Console.ReadKey(intercept: true);
                return;
            }

            var catLabel = category is null ? "Todos" : Markup.Escape(category);
            var title    = $"[bold]LIVE[/] — {catLabel} [dim]({channels.Count})[/]";
            if (query is not null) title += $" [yellow]\"{Markup.Escape(query)}\"[/]";

            var indices = Enumerable.Range(0, channels.Count).ToList();
            indices.Add(ActSearch);
            if (query is not null) indices.Add(ActClear);
            indices.Add(ActBack);

            var sel = AnsiConsole.Prompt(
                new SelectionPrompt<int>()
                    .Title(title)
                    .HighlightStyle("bold red")
                    .PageSize(20)
                    .UseConverter(i => i switch
                    {
                        ActSearch => "[yellow]Buscar canal...[/]",
                        ActClear  => "[dim]Quitar busqueda[/]",
                        ActBack   => "← Volver",
                        _         => FormatChannel(channels[i]),
                    })
                    .AddChoices(indices));

            switch (sel)
            {
                case ActBack:   return;
                case ActSearch: query = AnsiConsole.Ask<string>("Buscar canal: "); break;
                case ActClear:  query = null; break;
                default:
                    await PlayWithFailoverAsync(channels[sel], api, player);
                    break;
            }
        }
    }

    static async Task PlayWithFailoverAsync(LiveGroup group, ApiService api, PlayerService player)
    {
        var urlsToTry = BuildUrlList(group);

        foreach (var (url, channelId) in urlsToTry)
        {
            AnsiConsole.MarkupLine(
                $"  [dim]▶[/] {Markup.Escape(group.Title)} [grey]{Markup.Escape(url.Length > 60 ? url[..60] + "..." : url)}[/]");

            var ok = await player.PlayAsync(url, group.Title, isLive: true);
            if (ok) return; // usuario cerró mpv limpiamente

            // Mpv falló → reportar y probar siguiente
            AnsiConsole.MarkupLine("[yellow]  Canal no disponible, probando alternativa...[/]");
            if (channelId.HasValue)
                await api.ReportLiveDownAsync(channelId.Value, url);
        }

        AnsiConsole.MarkupLine("[red]Sin más alternativas para este canal.[/]");
        Console.ReadKey(intercept: true);
    }

    /// <summary>
    /// Construye la lista ordenada de URLs a intentar para un grupo live.
    /// Prioridad: streamUrl del grupo → liveurls de cada canal interno (rotando desde activeIndex).
    /// </summary>
    static List<(string Url, int? ChannelId)> BuildUrlList(LiveGroup group)
    {
        List<(string Url, int? ChannelId)> result = [];

        if (!string.IsNullOrEmpty(group.StreamUrl))
            result.Add((group.StreamUrl, group.Id));

        if (group.Channels is null) return result;

        foreach (var ch in group.Channels)
        {
            if (ch.LiveUrls?.Count > 0)
            {
                var active = ch.ActiveUrlIndex ?? 0;
                for (int i = 0; i < ch.LiveUrls.Count; i++)
                {
                    var idx = (active + i) % ch.LiveUrls.Count;
                    var u   = ch.LiveUrls[idx];
                    if (!string.IsNullOrEmpty(u) && !result.Any(r => r.Url == u))
                        result.Add((u, ch.Id));
                }
            }
            else if (!string.IsNullOrEmpty(ch.StreamUrl) && !result.Any(r => r.Url == ch.StreamUrl))
            {
                result.Add((ch.StreamUrl, ch.Id));
            }
        }

        return result;
    }

    static string FormatChannel(LiveGroup c)
    {
        var cat   = !string.IsNullOrEmpty(c.GroupTitle) ? $" [grey]{Markup.Escape(c.GroupTitle)}[/]" : "";
        var count = c.ChannelCount > 1 ? $" [dim]({c.ChannelCount} señales)[/]" : "";
        return $"{Markup.Escape(c.Title)}{cat}{count}";
    }
}
