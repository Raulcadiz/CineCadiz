using System.Text.Json;
using CineCadizConsole.Models;

namespace CineCadizConsole.Services;

record ProgressEntry(
    int Id,
    string Title,
    string Type,
    string StreamUrl,
    int? Season,
    int? Episode,
    DateTime LastWatched);

class ProgressService
{
    static readonly JsonSerializerOptions Opts = new() { WriteIndented = true };
    List<ProgressEntry> _entries = [];

    public ProgressService() => Load();

    public void Record(ContentItem item)
    {
        _entries.RemoveAll(e => e.Id == item.Id);
        _entries.Insert(0, new ProgressEntry(
            item.Id, item.Title, item.Type, item.StreamUrl,
            item.Season, item.Episode, DateTime.Now));
        if (_entries.Count > 50)
            _entries = [.. _entries.Take(50)];
        Save();
    }

    public IReadOnlyList<ProgressEntry> GetRecent() => _entries.AsReadOnly();

    void Load()
    {
        try
        {
            if (!File.Exists(AppConfig.ProgressFile)) return;
            _entries = JsonSerializer.Deserialize<List<ProgressEntry>>(
                File.ReadAllText(AppConfig.ProgressFile), Opts) ?? [];
        }
        catch { _entries = []; }
    }

    void Save()
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(AppConfig.ProgressFile)!);
            File.WriteAllText(AppConfig.ProgressFile,
                JsonSerializer.Serialize(_entries, Opts));
        }
        catch { }
    }
}
