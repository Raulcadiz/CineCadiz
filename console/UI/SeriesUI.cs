using CineCadizConsole.Models;
using CineCadizConsole.Services;
using Spectre.Console;

namespace CineCadizConsole.UI;

static class SeriesUI
{
    const int ActSearch = -1;
    const int ActClear  = -2;
    const int ActPrev   = -3;
    const int ActNext   = -4;
    const int ActBack   = -5;

    public static async Task RunAsync(ApiService api, PlayerService player, ProgressService progress)
    {
        string? query = null;
        int page = 1;

        while (true)
        {
            Console.Clear();
            Paginated<SeriesGroup>? result = null;
            string? error = null;

            await AnsiConsole.Status().StartAsync("Cargando series...", async _ =>
            {
                try   { result = await api.GetSeriesAsync(query, page); }
                catch (Exception ex) { error = ex.Message; }
            });

            if (error is not null || result is null)
            {
                AnsiConsole.MarkupLine($"[red]Error al cargar: {Markup.Escape(error ?? "sin respuesta")}[/]");
                Console.ReadKey(intercept: true);
                return;
            }

            if (result.Items.Count == 0)
            {
                AnsiConsole.MarkupLine("[yellow]No se encontraron series.[/]");
                Console.ReadKey(intercept: true);
                if (query is not null) { query = null; page = 1; continue; }
                return;
            }

            var header = query is null
                ? $"[bold]SERIES[/] [dim]pag {page}/{result.Pages} — {result.Total} total[/]"
                : $"[bold]SERIES[/] [yellow]\"{Markup.Escape(query)}\"[/] [dim]— {result.Total} resultado(s)[/]";

            var indices = Enumerable.Range(0, result.Items.Count).ToList();
            if (page > 1)            indices.Add(ActPrev);
            if (page < result.Pages) indices.Add(ActNext);
            indices.Add(ActSearch);
            if (query is not null)   indices.Add(ActClear);
            indices.Add(ActBack);

            var sel = AnsiConsole.Prompt(
                new SelectionPrompt<int>()
                    .Title(header)
                    .HighlightStyle("bold red")
                    .PageSize(20)
                    .UseConverter(i => i switch
                    {
                        ActSearch => "[yellow]Buscar...[/]",
                        ActClear  => "[dim]Quitar busqueda[/]",
                        ActPrev   => "« Pagina anterior",
                        ActNext   => "Pagina siguiente »",
                        ActBack   => "← Volver",
                        _         => FormatSeries(result.Items[i]),
                    })
                    .AddChoices(indices));

            switch (sel)
            {
                case ActBack:   return;
                case ActSearch: query = AnsiConsole.Ask<string>("Buscar: "); page = 1; break;
                case ActClear:  query = null; page = 1; break;
                case ActPrev:   page--; break;
                case ActNext:   page++; break;
                default:
                    await ShowEpisodesAsync(result.Items[sel], api, player, progress);
                    break;
            }
        }
    }

    static async Task ShowEpisodesAsync(
        SeriesGroup series, ApiService api, PlayerService player, ProgressService progress)
    {
        Console.Clear();
        List<ContentItem>? episodes = null;
        string? error = null;

        await AnsiConsole.Status()
            .StartAsync($"Cargando '{Markup.Escape(series.Title)}'...", async _ =>
            {
                try   { episodes = await api.GetSeriesEpisodesAsync(series.Title); }
                catch (Exception ex) { error = ex.Message; }
            });

        if (error is not null || episodes is null || episodes.Count == 0)
        {
            AnsiConsole.MarkupLine("[red]No se encontraron episodios.[/]");
            Console.ReadKey(intercept: true);
            return;
        }

        var seasons = episodes
            .GroupBy(e => e.Season ?? 1)
            .OrderBy(g => g.Key)
            .ToList();

        int season;
        if (seasons.Count == 1)
        {
            season = seasons[0].Key;
        }
        else
        {
            // Selector de temporada
            var sIndices = Enumerable.Range(0, seasons.Count).Append(-1).ToList();
            var selS = AnsiConsole.Prompt(
                new SelectionPrompt<int>()
                    .Title($"[bold]{Markup.Escape(series.Title)}[/] — Temporadas")
                    .HighlightStyle("bold red")
                    .PageSize(20)
                    .UseConverter(i => i == -1
                        ? "← Volver"
                        : $"Temporada {seasons[i].Key:D2} [dim]({seasons[i].Count()} episodios)[/]")
                    .AddChoices(sIndices));
            if (selS == -1) return;
            season = seasons[selS].Key;
        }

        var eps = seasons.First(g => g.Key == season)
            .OrderBy(e => e.Episode ?? 0)
            .ToList();

        // Selector de episodio
        var eIndices = Enumerable.Range(0, eps.Count).Append(-1).ToList();
        var selE = AnsiConsole.Prompt(
            new SelectionPrompt<int>()
                .Title($"[bold]{Markup.Escape(series.Title)}[/] T{season:D2} — Episodios")
                .HighlightStyle("bold red")
                .PageSize(20)
                .UseConverter(i => i == -1
                    ? "← Volver"
                    : $"E{eps[i].Episode ?? 0:D2}  {Markup.Escape(eps[i].Title)}")
                .AddChoices(eIndices));

        if (selE == -1) return;

        var chosen = eps[selE];
        await api.RecordWatchAsync(chosen.Id);
        progress.Record(chosen);
        await player.PlayAsync(
            chosen.StreamUrl,
            $"{series.Title} T{season:D2}E{chosen.Episode ?? 1:D2}");
    }

    static string FormatSeries(SeriesGroup s)
    {
        var year   = s.Year.HasValue ? $" [dim]({s.Year})[/]" : "";
        var info   = $" [grey]{s.SeasonCount}T {s.EpisodeCount}ep[/]";
        var genres = s.GenresDisplay.Length > 0 ? $" [grey]{Markup.Escape(s.GenresDisplay)}[/]" : "";
        return $"{Markup.Escape(s.Title)}{year}{info}{genres}";
    }
}
