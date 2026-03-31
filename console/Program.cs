using CineCadizConsole;
using CineCadizConsole.Services;
using CineCadizConsole.UI;
using Spectre.Console;

Console.OutputEncoding = System.Text.Encoding.UTF8;

if (!File.Exists(AppConfig.MpvPath))
{
    AnsiConsole.MarkupLine("[bold red]ERROR:[/] mpv.exe no encontrado en [yellow]./mpv/mpv.exe[/]");
    AnsiConsole.MarkupLine("Ejecuta [italic]./download-mpv.ps1[/] para descargarlo automáticamente.");
    AnsiConsole.MarkupLine("O descárgalo desde [underline]https://mpv.io/installation/[/] y cópialo a la carpeta mpv/");
    Console.ReadKey(intercept: true);
    return;
}

var api      = new ApiService();
var player   = new PlayerService();
var progress = new ProgressService();

while (true)
{
    Console.Clear();
    AnsiConsole.Write(new FigletText("CINE CADIZ").Centered().Color(Color.Red));
    AnsiConsole.Write(new Rule("[dim]cinecadiz.servegame.com[/]").RuleStyle("grey").Centered());
    AnsiConsole.WriteLine();

    var opcion = AnsiConsole.Prompt(
        new SelectionPrompt<string>()
            .HighlightStyle("bold red")
            .AddChoices(
                "▶  Continuar viendo / Novedades",
                "Peliculas",
                "Series",
                "Live",
                "Salir"));

    switch (opcion)
    {
        case "▶  Continuar viendo / Novedades": await HomeUI.RunAsync(api, player, progress);   break;
        case "Peliculas":                        await MoviesUI.RunAsync(api, player, progress); break;
        case "Series":                           await SeriesUI.RunAsync(api, player, progress); break;
        case "Live":                             await LiveUI.RunAsync(api, player);             break;
        case "Salir":                            return;
    }
}
