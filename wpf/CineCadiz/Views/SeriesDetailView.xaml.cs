using System.Windows.Controls;
using System.Windows.Input;
using CineCadiz.Models;
using CineCadiz.ViewModels;

namespace CineCadiz.Views
{
    public partial class SeriesDetailView : UserControl
    {
        public SeriesDetailView()
        {
            InitializeComponent();
        }

        private void SeasonChip_Click(object sender, System.Windows.RoutedEventArgs e)
        {
            if (sender is Button b && b.Tag is int season && DataContext is SeriesDetailViewModel vm)
                vm.SelectedSeason = season;
        }

        private void Episode_Click(object sender, MouseButtonEventArgs e)
        {
            if (sender is Border b && b.Tag is ContentItem ep && DataContext is SeriesDetailViewModel vm)
                vm.PlayEpisodeCommand.Execute(ep);
        }
    }
}
