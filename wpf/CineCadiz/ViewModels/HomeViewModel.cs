using System.Collections.ObjectModel;
using System.Threading.Tasks;
using System.Windows;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using CineCadiz.Models;
using CineCadiz.Services;

namespace CineCadiz.ViewModels
{
    public partial class HomeViewModel : ObservableObject
    {
        [ObservableProperty] private ObservableCollection<ProgressEntry> _continueWatching = new();
        [ObservableProperty] private ObservableCollection<ContentItem> _trending = new();
        [ObservableProperty] private bool _isLoading;
        [ObservableProperty] private bool _hasError;
        [ObservableProperty] private string _errorMessage = string.Empty;

        public bool HasContinueWatching => ContinueWatching.Count > 0;

        partial void OnContinueWatchingChanged(ObservableCollection<ProgressEntry> value)
            => OnPropertyChanged(nameof(HasContinueWatching));

        public async Task LoadAsync()
        {
            IsLoading = true;
            try
            {
                var recent = ProgressService.Instance.GetRecentlyWatched(10);
                Application.Current.Dispatcher.Invoke(() =>
                {
                    ContinueWatching.Clear();
                    foreach (var item in recent)
                        ContinueWatching.Add(item);
                });

                var trending = await ApiService.Instance.GetTrendingAsync();
                Application.Current.Dispatcher.Invoke(() =>
                {
                    Trending.Clear();
                    foreach (var item in trending)
                        Trending.Add(item);
                });
            }
            catch (Exception ex)
            {
                HasError = true;
                ErrorMessage = $"No se pudo conectar al servidor: {ex.Message}";
            }
            finally
            {
                IsLoading = false;
            }
        }

        [RelayCommand]
        private void PlayContinue(ProgressEntry? entry)
        {
            if (entry == null) return;
            var item = new ContentItem
            {
                Id = entry.Id,
                Title = entry.Title,
                Type = entry.Type,
                StreamUrl = entry.StreamUrl,
                Image = entry.Image,
                Season = entry.Season,
                Episode = entry.Episode
            };
            PlayerViewModel.Instance.Play(item);
        }

        [RelayCommand]
        private void PlayItem(ContentItem? item)
        {
            if (item == null) return;
            PlayerViewModel.Instance.Play(item);
        }
    }
}
