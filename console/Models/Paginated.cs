namespace CineCadizConsole.Models;

record Paginated<T>(
    List<T> Items,
    int Total,
    int Page,
    int Pages,
    int PerPage);
