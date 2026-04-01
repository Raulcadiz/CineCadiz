using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using CineCadiz.Models;

namespace CineCadiz.Services
{
    public class ProgressService
    {
        private static readonly ProgressService _instance = new();
        public static ProgressService Instance => _instance;

        private List<ProgressEntry> _entries = new();
        private readonly JsonSerializerOptions _jsonOptions = new() { WriteIndented = true };

        private ProgressService()
        {
            Load();
        }

        private void Load()
        {
            try
            {
                if (File.Exists(AppConfig.ProgressFile))
                {
                    var json = File.ReadAllText(AppConfig.ProgressFile);
                    _entries = JsonSerializer.Deserialize<List<ProgressEntry>>(json) ?? new();
                }
            }
            catch
            {
                _entries = new();
            }
        }

        private void Save()
        {
            try
            {
                Directory.CreateDirectory(AppConfig.DataFolder);
                var json = JsonSerializer.Serialize(_entries, _jsonOptions);
                File.WriteAllText(AppConfig.ProgressFile, json);
            }
            catch { }
        }

        public void Record(ContentItem item, double position, double duration)
        {
            var existing = _entries.FirstOrDefault(e => e.Id == item.Id);
            if (existing != null)
            {
                existing.Position = position;
                existing.Duration = duration;
                existing.LastWatched = DateTime.Now;
                existing.StreamUrl = item.StreamUrl;
                existing.Season = item.Season ?? 0;
                existing.Episode = item.Episode ?? 0;
            }
            else
            {
                _entries.Insert(0, new ProgressEntry
                {
                    Id = item.Id,
                    Title = item.Title,
                    Type = item.Type,
                    StreamUrl = item.StreamUrl,
                    Season = item.Season ?? 0,
                    Episode = item.Episode ?? 0,
                    Position = position,
                    Duration = duration,
                    LastWatched = DateTime.Now,
                    Image = item.Image
                });
            }

            // Keep only last 50 entries
            if (_entries.Count > 50)
                _entries = _entries.Take(50).ToList();

            Save();
        }

        public double GetPosition(int contentId)
        {
            var entry = _entries.FirstOrDefault(e => e.Id == contentId);
            if (entry == null || entry.Duration <= 0) return 0.0;
            return entry.Position / entry.Duration;
        }

        public long GetPositionMs(int contentId)
        {
            var entry = _entries.FirstOrDefault(e => e.Id == contentId);
            return entry != null ? (long)entry.Position : 0L;
        }

        public void ClearAll()
        {
            _entries.Clear();
            Save();
        }

        public List<ProgressEntry> GetRecentlyWatched(int count = 10)
        {
            return _entries
                .Where(e => e.Type != "live" && e.Duration > 0)
                .OrderByDescending(e => e.LastWatched)
                .Take(count)
                .ToList();
        }
    }
}
