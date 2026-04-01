using System.Windows;
using LibVLCSharp.Shared;

namespace CineCadiz
{
    public partial class App : Application
    {
        protected override void OnStartup(StartupEventArgs e)
        {
            Core.Initialize();
            Services.RemoteService.Instance.Start();
            base.OnStartup(e);
        }

        protected override void OnExit(ExitEventArgs e)
        {
            Services.RemoteService.Instance.Stop();
            var player = ViewModels.PlayerViewModel.Instance;
            try
            {
                player.MediaPlayer.Stop();
                player.MediaPlayer.Dispose();
                player.LibVLC.Dispose();
            }
            catch { }
            base.OnExit(e);
        }
    }
}
