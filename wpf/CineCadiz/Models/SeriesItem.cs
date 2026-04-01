using System.Collections.Generic;

namespace CineCadiz.Models
{
    public class SeriesItem
    {
        public int      Id           { get; set; }
        public string   Title        { get; set; } = string.Empty;
        public string   Image        { get; set; } = string.Empty;
        public int?     Year         { get; set; }   // nullable
        public List<string> Genres   { get; set; } = new();
        public int      SeasonCount  { get; set; }
        public int      EpisodeCount { get; set; }
        public string   GroupTitle   { get; set; } = string.Empty;
        public string   AddedAt      { get; set; } = string.Empty;

        public string YearDisplay   => Year.HasValue ? Year.ToString()! : string.Empty;
        public string GenresDisplay => Genres.Count > 0 ? string.Join(" · ", Genres) : string.Empty;
    }
}
