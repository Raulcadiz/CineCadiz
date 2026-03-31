namespace CineCadizConsole.Models;

record LiveGroup(
    int Id,
    string Title,
    string StreamUrl,
    string? Image,
    List<string>? Genres,
    string? GroupTitle,
    int ChannelCount,
    List<ContentItem>? Channels);
