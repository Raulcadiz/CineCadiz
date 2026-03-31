namespace CineCadizConsole.Models;

record SeriesGroup(
    int Id,
    string Title,
    string? Image,
    int? Year,
    List<string>? Genres,
    int SeasonCount,
    int EpisodeCount,
    string? GroupTitle,
    string? AddedAt)
{
    public string GenresDisplay => Genres?.Count > 0 ? string.Join(", ", Genres) : "";
}
