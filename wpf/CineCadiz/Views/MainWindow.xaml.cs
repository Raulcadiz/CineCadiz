using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using CineCadiz.ViewModels;

namespace CineCadiz.Views
{
    public partial class MainWindow : Window
    {
        public MainWindow()
        {
            InitializeComponent();
        }

        // ── Window chrome commands ────────────────────────────────────
        private void OnClose(object sender, ExecutedRoutedEventArgs e)    => SystemCommands.CloseWindow(this);
        private void OnMinimize(object sender, ExecutedRoutedEventArgs e) => SystemCommands.MinimizeWindow(this);
        private void OnMaximize(object sender, ExecutedRoutedEventArgs e) => SystemCommands.MaximizeWindow(this);
        private void OnRestore(object sender, ExecutedRoutedEventArgs e)  => SystemCommands.RestoreWindow(this);

        private void MaxRestoreButton_Click(object sender, RoutedEventArgs e)
        {
            if (WindowState == WindowState.Maximized)
                SystemCommands.RestoreWindow(this);
            else
                SystemCommands.MaximizeWindow(this);
        }

        private void Window_StateChanged(object sender, System.EventArgs e)
        {
            // Swap the icon on the maximize/restore button
            if (MaxIcon != null)
                MaxIcon.Kind = WindowState == WindowState.Maximized
                    ? MaterialDesignThemes.Wpf.PackIconKind.WindowRestore
                    : MaterialDesignThemes.Wpf.PackIconKind.WindowMaximize;
        }

        // ── Global keyboard shortcuts for the player ──────────────────
        private void Window_KeyDown(object sender, KeyEventArgs e)
        {
            var player = PlayerViewModel.Instance;
            if (!player.IsVisible) return;

            player.ShowControls();

            switch (e.Key)
            {
                case Key.Escape: player.CloseCommand.Execute(null);         e.Handled = true; break;
                case Key.Space:  player.TogglePlayPauseCommand.Execute(null); e.Handled = true; break;
                case Key.Right:  player.SeekForwardCommand.Execute(null);   e.Handled = true; break;
                case Key.Left:   player.SeekBackwardCommand.Execute(null);  e.Handled = true; break;
                case Key.Up:     player.SetVolume(player.Volume + 5);       e.Handled = true; break;
                case Key.Down:   player.SetVolume(player.Volume - 5);       e.Handled = true; break;
                case Key.M:      player.ToggleMuteCommand.Execute(null);    e.Handled = true; break;
            }
        }
    }
}
