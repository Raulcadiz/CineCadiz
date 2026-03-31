using CineCadizConsole.Models;
using CineCadizConsole.Services;
using Spectre.Console;

namespace CineCadizConsole.UI;

static class HomeUI
{
    // Índices de acción negativos para no colisionar con índices de items
    const int ActNovedades = -1;
    const int ActVolver    = -2;

    public static async Task RunAsync(ApiService api, PlayerService player, ProgressService progress)
    {
        var recent = progress.GetRecent();

        if (recent.Count > 0)
        {
            Console.Clear();
            AnsiConsole.MarkupLine("[bold yellow]▶ Continuar viendo[/]");
            AnsiConsole.WriteLine();

            // Construimos lista de índices: 0..N = recent items, -1 = novedades, -2 = volver
            var indices = Enumerable.Range(0, Math.Min(10, recent.Count))
                .Append(ActNovedades)
                .Append(ActVolver)
                .ToList();

            var sel = AnsiConsole.Prompt(
                new SelectionPrompt<int>()
                    .HighlightStyle("bold yellow")
                    .PageSize(15)
                    .UseConverter(i => i switch
                    {
                        ActNovedades => "[dim]── Ver novedades ──[/]",
                        ActVolver    => "← Volver",
                        _            => FormatEntry(recent[i]),
                    })
                    .AddChoices(indices));

            if (sel == ActVolver) return;

            if (sel != ActNovedades)
            {
                var entry = recent[sel];
                await player.PlayAsync(entry.StreamUrl, entry.Title, entry.Type == "live");
                return;
            }
        }

        await ShowTrendingAsync(api, player, progress);
    }

    static async Task ShowTrendingAsync(ApiService api, PlayerService player, ProgressService progress)
    {
        Console.Clear();
        List<ContentItem> trending = [];
        await AnsiConsole.Status()
            .StartAsync("Cargando novedades...", async _ =>
                trending = await api.GetTrendingAsync());

        if (trending.Count == 0)
        {
            AnsiConsole.MarkupLine("[red]Sin contenido disponible.[/]");
            Console.ReadKey(intercept: true);
            return;
        }

        var items = trending.Take(20).ToList();
        // -1 = volver
        var indices = Enumerable.Range(0, items.Count).Append(-1).ToList();

        var sel = AnsiConsole.Prompt(
            new SelectionPrompt<int>()
                .Title("[bold]Novedades[/]")
                .HighlightStyle("bold red")
                .PageSize(20)
                .UseConverter(i => i == -1
                    ? "← Volver"
                    : $"{Markup.Escape(items[i].Title)} [dim]({items[i].Year})[/] [grey]{items[i].Type}[/]")
                .AddChoices(indices));

        if (sel == -1) return;

        var chosen = items[sel];
        await api.RecordWatchAsync(chosen.Id);
        progress.Record(chosen);
        await player.PlayAsync(chosen.StreamUrl, chosen.Title, chosen.Type == "live");
    }

    static string FormatEntry(ProgressEntry r)
    {
        var when = r.LastWatched.ToString("dd/MM HH:mm");
        var ep   = r.Season.HasValue ? $" [dim]T{r.Season:D2}E{r.Episode ?? 1:D2}[/]" : "";
        return $"{Markup.Escape(r.Title)}{ep} [grey]{when}[/]";
    }
}
