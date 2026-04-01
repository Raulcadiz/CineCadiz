namespace CineCadiz.Models
{
    public class LiveListInfo
    {
        public int    Id        { get; set; }
        public string Nombre    { get; set; } = string.Empty;
        public bool   IsDefault { get; set; }

        // Custom M3U list (not from backend)
        public bool   IsCustom  { get; set; }
        public string? M3uUrl   { get; set; }
    }
}
