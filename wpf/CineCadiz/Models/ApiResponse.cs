using System.Collections.Generic;

namespace CineCadiz.Models
{
    public class ApiResponse<T>
    {
        public List<T> Items { get; set; } = new();
        public int Total { get; set; }
        public int Page { get; set; }
        public int Pages { get; set; }
        public int PerPage { get; set; }
    }
}
