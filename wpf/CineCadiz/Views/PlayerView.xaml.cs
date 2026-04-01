using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using CineCadiz.ViewModels;

namespace CineCadiz.Views
{
    public partial class PlayerView : UserControl
    {
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

        // Clicking the transparent overlay also shows controls
        private void ClickCatcher_MouseDown(object sender, MouseButtonEventArgs e)
        {
            PlayerViewModel.Instance.ShowControls();
        }
    }
}
