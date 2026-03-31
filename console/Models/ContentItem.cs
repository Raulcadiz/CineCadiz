namespace CineCadizConsole.Models;

record ContentItem(
    int Id,
    string Title,
    string Type,
    string StreamUrl,
    string? Image,
    string? Description,
    int? Year,
    List<string>? Genres,
    string? GroupTitle,
    int? Season,
    int? Episode,
    bool Active,
    string? AddedAt,
    List<string>? LiveUrls,
    int? ActiveUrlIndex)
{
    public string GenresDisplay => Genres?.Count > 0 ? string.Join(", ", Genres) : "";
    public string EpisodeLabel  => Season.HasValue ? $"T{Season:D2}E{Episode ?? 1:D2}" : "";
}
