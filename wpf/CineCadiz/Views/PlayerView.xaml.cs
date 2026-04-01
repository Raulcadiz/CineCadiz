using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using CineCadiz.ViewModels;

namespace CineCadiz.Views
{
    public partial class PlayerView : UserControl
    {
        private DateTime _lastClickTime = DateTime.MinValue;

        public PlayerView()
        {
            InitializeComponent();
            Loaded += PlayerView_Loaded;
        }

        private void PlayerView_Loaded(object sender, RoutedEventArgs e)
        {
            VideoViewControl.MediaPlayer = PlayerViewModel.Instance.MediaPlayer;

            if (ProgressSlider != null)
            {
                ProgressSlider.AddHandler(Slider.PreviewMouseLeftButtonUpEvent,
                    new MouseButtonEventHandler(ProgressSlider_MouseUp), true);
            }
        }

        private void ProgressSlider_MouseUp(object sender, MouseButtonEventArgs e)
        {
            if (sender is Slider slider)
                PlayerViewModel.Instance.SetPosition(slider.Value);
        }

        private void UserControl_MouseMove(object sender, MouseEventArgs e)
        {
            PlayerViewModel.Instance.ShowControls();
        }

        /// <summary>
        /// Single click → show controls.
        /// Double-click (within 400 ms) → toggle fullscreen.
        /// </summary>
        private void ClickCatcher_MouseDown(object sender, MouseButtonEventArgs e)
        {
            var now   = DateTime.UtcNow;
            var delta = (now - _lastClickTime).TotalMilliseconds;

            if (delta < 400)
            {
                // Double-click → fullscreen
                PlayerViewModel.Instance.ToggleFullscreenCommand.Execute(null);
                _lastClickTime = DateTime.MinValue; // reset so triple-click doesn't re-trigger
            }
            else
            {
                PlayerViewModel.Instance.ShowControls();
                _lastClickTime = now;
            }
        }
    }
}
