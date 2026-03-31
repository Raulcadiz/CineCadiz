using System.Diagnostics;

namespace CineCadizConsole.Services;

class PlayerService
{
    public bool IsAvailable => File.Exists(AppConfig.MpvPath);

    /// <summary>
    /// Lanza mpv con la URL dada. Devuelve true si mpv cerró limpiamente (código 0).
    /// </summary>
    public async Task<bool> PlayAsync(string url, string title, bool isLive = false)
    {
        var args = BuildArgs(url, title, isLive);
        var psi  = new ProcessStartInfo
        {
            FileName        = AppConfig.MpvPath,
            Arguments       = args,
            UseShellExecute = false,
            CreateNoWindow  = false,
        };
        using var p = Process.Start(psi);
        if (p is null) return false;
        await p.WaitForExitAsync();
        return p.ExitCode == 0;
    }

    static string BuildArgs(string url, string title, bool isLive)
    {
        var safe  = title.Replace("\"", "'");
        var parts = new List<string>
        {
            $"--title=\"{safe}\"",
            "--force-window=yes",
        };
        if (isLive)
        {
            parts.Add("--no-resume-playback");
            parts.Add("--cache=yes");
            parts.Add("--demuxer-max-bytes=50M");
            parts.Add("--stream-lavf-o=reconnect_streamed=1");
        }
        parts.Add($"\"{url}\"");
        return string.Join(" ", parts);
    }
}
