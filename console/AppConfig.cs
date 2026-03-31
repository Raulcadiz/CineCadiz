namespace CineCadizConsole;

static class AppConfig
{
    public const string BaseUrl = "https://cinecadiz.servegame.com";

    static readonly string DataDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "CineCadiz");

    public static string ProgressFile => Path.Combine(DataDir, "progress.json");
    static string SessionFile         => Path.Combine(DataDir, "session.txt");

    public static string MpvPath { get; } = ResolveMpvPath();

    static string ResolveMpvPath()
    {
        // 1. Carpeta ./mpv/ junto al exe (bundled)
        var local = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "mpv", "mpv.exe");
        if (File.Exists(local)) return local;

        // 2. mpv.exe en el PATH del sistema (instalado con winget/choco)
        var inPath = Environment
            .GetEnvironmentVariable("PATH")?
            .Split(Path.PathSeparator)
            .Select(dir => Path.Combine(dir, "mpv.exe"))
            .FirstOrDefault(File.Exists);
        if (inPath is not null) return inPath;

        // Devuelve la ruta local aunque no exista (para que el mensaje de error sea claro)
        return local;
    }

    static string? _sessionKey;
    public static string SessionKey => _sessionKey ??= LoadOrCreateSession();

    static string LoadOrCreateSession()
    {
        Directory.CreateDirectory(DataDir);
        if (File.Exists(SessionFile))
            return File.ReadAllText(SessionFile).Trim();
        var key = Guid.NewGuid().ToString("N");
        File.WriteAllText(SessionFile, key);
        return key;
    }
}
