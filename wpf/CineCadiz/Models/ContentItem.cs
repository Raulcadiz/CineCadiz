using System.Collections.Generic;

namespace CineCadiz.Models
{
    public class ContentItem
    {
        public int      Id             { get; set; }
        public string   Title          { get; set; } = string.Empty;
        public string   Type           { get; set; } = string.Empty;
        public string   StreamUrl      { get; set; } = string.Empty;
        public string   Image          { get; set; } = string.Empty;
        public string   Description    { get; set; } = string.Empty;
        public int?     Year           { get; set; }   // nullable — el backend puede devolver null
        public List<string> Genres     { get; set; } = new();
        public string   GroupTitle     { get; set; } = string.Empty;
        public int?     Season         { get; set; }   // nullable
        public int?     Episode        { get; set; }   // nullable
        public bool     Active         { get; set; }
        public string?  AddedAt        { get; set; }
        public List<string> LiveUrls   { get; set; } = new();
        public int      ActiveUrlIndex { get; set; }

        // Helpers UI
        public string YearDisplay    => Year.HasValue ? Year.ToString()! : string.Empty;
        public string EpisodeLabel   => Season.HasValue ? $"T{Season:D2}E{Episode ?? 1:D2}" : string.Empty;
        public string GenresDisplay  => Genres.Count > 0 ? string.Join(" · ", Genres) : string.Empty;
    }
}
