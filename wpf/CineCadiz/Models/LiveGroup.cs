using System.Collections.Generic;

namespace CineCadiz.Models
{
    public class LiveGroup
    {
        public int Id { get; set; }
        public string Title { get; set; } = string.Empty;
        public string StreamUrl { get; set; } = string.Empty;
        public string Image { get; set; } = string.Empty;
        public string GroupTitle { get; set; } = string.Empty;
        public int ChannelCount { get; set; }
        public List<ContentItem> Channels { get; set; } = new();
    }
}
