using CineCadizConsole.Models;
using CineCadizConsole.Services;
using Spectre.Console;

namespace CineCadizConsole.UI;

static class MoviesUI
{
    // Acciones (índices negativos para no colisionar con índices de películas 0..N)
    const int ActSearch    = -1;
    const int ActClear     = -2;
    const int ActPrev      = -3;
    const int ActNext      = -4;
    const int ActBack      = -5;

    public static async Task RunAsync(ApiService api, PlayerService player, ProgressService progress)
    {
        string? query = null;
        int page = 1;

        while (true)
        {
            Console.Clear();
            Paginated<ContentItem>? result = null;
            string? error = null;

            await AnsiConsole.Status().StartAsync("Cargando películas...", async _ =>
            {
                try   { result = await api.GetMoviesAsync(query, page); }
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
                AnsiConsole.MarkupLine("[yellow]No se encontraron películas.[/]");
                Console.ReadKey(intercept: true);
                if (query is not null) { query = null; page = 1; continue; }
                return;
            }

            var header = query is null
                ? $"[bold]PELICULAS[/] [dim]pag {page}/{result.Pages} — {result.Total} total[/]"
                : $"[bold]PELICULAS[/] [yellow]\"{Markup.Escape(query)}\"[/] [dim]— {result.Total} resultado(s)[/]";

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
                        _         => FormatMovie(result.Items[i]),
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
                    var movie = result.Items[sel];
                    await api.RecordWatchAsync(movie.Id);
                    progress.Record(movie);
                    await player.PlayAsync(movie.StreamUrl, movie.Title);
                    break;
            }
        }
    }

    static string FormatMovie(ContentItem m)
    {
        var year   = m.Year.HasValue ? $" [dim]({m.Year})[/]" : "";
        var genres = m.GenresDisplay.Length > 0 ? $" [grey]{Markup.Escape(m.GenresDisplay)}[/]" : "";
        return $"{Markup.Escape(m.Title)}{year}{genres}";
    }
}
