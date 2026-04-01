using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using CineCadiz.Models;
using CineCadiz.Services;

namespace CineCadiz.ViewModels
{
    public partial class SeriesDetailViewModel : ObservableObject
    {
        public SeriesItem Series { get; }

        [ObservableProperty] private ObservableCollection<int> _seasons = new();
        [ObservableProperty] private int _selectedSeason = 1;
        [ObservableProperty] private ObservableCollection<ContentItem> _episodes = new();
        [ObservableProperty] private bool _isLoading;

        private List<ContentItem> _allEpisodes = new();

        public SeriesDetailViewModel(SeriesItem series)
        {
            Series = series;
        }

        public async Task LoadEpisodesAsync()
        {
            IsLoading = true;
            try
            {
                _allEpisodes = await ApiService.Instance.GetSeriesEpisodesAsync(Series.Title);

                Application.Current.Dispatcher.Invoke(() =>
                {
                    var seasonNums = _allEpisodes
                        .Where(e => e.Season.HasValue)
                        .Select(e => e.Season!.Value)
                        .Distinct()
                        .OrderBy(s => s)
                        .ToList();

                    Seasons.Clear();
                    foreach (var s in seasonNums)
                        Seasons.Add(s);

                    SelectedSeason = seasonNums.Contains(1) ? 1 : (seasonNums.Count > 0 ? seasonNums[0] : 1);
                    FilterEpisodes();
                });
            }
            catch { }
            finally
            {
                IsLoading = false;
            }
        }

        partial void OnSelectedSeasonChanged(int value) => FilterEpisodes();

        private void FilterEpisodes()
        {
            Episodes.Clear();
            var filtered = _allEpisodes
                .Where(e => e.Season == SelectedSeason)
                .OrderBy(e => e.Episode);

            foreach (var ep in filtered)
                Episodes.Add(ep);
        }

        [RelayCommand]
        private void PlayEpisode(ContentItem? episode)
        {
            if (episode == null) return;
            PlayerViewModel.Instance.Play(episode);
        }

        [RelayCommand]
        private void GoBack()
        {
            NavigationService.Instance.NavigateTo(new SeriesViewModel());
        }
    }
}
