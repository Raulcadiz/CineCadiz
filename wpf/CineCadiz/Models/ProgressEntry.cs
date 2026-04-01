using System;

namespace CineCadiz.Models
{
    public class ProgressEntry
    {
        public int Id { get; set; }
        public string Title { get; set; } = string.Empty;
        public string Type { get; set; } = string.Empty;
        public string StreamUrl { get; set; } = string.Empty;
        public int Season { get; set; }
        public int Episode { get; set; }
        public double Position { get; set; }
        public double Duration { get; set; }
        public DateTime LastWatched { get; set; }
        public string Image { get; set; } = string.Empty;

        public double ProgressFraction => Duration > 0 ? Math.Clamp(Position / Duration, 0, 1) : 0;
        public string EpisodeLabel => Season > 0 ? $"T{Season:D2}E{Episode:D2}" : string.Empty;
    }
}
