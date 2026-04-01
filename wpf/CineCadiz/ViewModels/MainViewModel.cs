using System.Windows;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using CineCadiz.Services;

namespace CineCadiz.ViewModels
{
    public partial class MainViewModel : ObservableObject
    {
        [ObservableProperty] private object _currentView;
        [ObservableProperty] private int _selectedNavIndex = 0;
        [ObservableProperty] private string _searchText = string.Empty;

        private readonly HomeViewModel _homeVm;
        private readonly MoviesViewModel _moviesVm;
        private readonly SeriesViewModel _seriesVm;
        private readonly LiveViewModel _liveVm;

        private object? _previousView;

        public PlayerViewModel Player => PlayerViewModel.Instance;

        public MainViewModel()
        {
            _homeVm   = new HomeViewModel();
            _moviesVm = new MoviesViewModel();
            _seriesVm = new SeriesViewModel();
            _liveVm   = new LiveViewModel();

            _currentView = _homeVm;

            NavigationService.Instance.Navigated += vm =>
                Application.Current.Dispatcher.Invoke(() =>
                {
                    _previousView = CurrentView;
                    CurrentView = vm;
                });

            NavigationService.Instance.BackRequested += () =>
                Application.Current.Dispatcher.Invoke(() =>
                {
                    if (_previousView != null)
                    {
                        CurrentView = _previousView;
                        _previousView = null;
                    }
                });

            _homeVm.LoadAsync();

            AppConfig.RefreshRequested += () =>
                Application.Current.Dispatcher.Invoke(() =>
                {
                    _ = _homeVm.LoadAsync();
                    _moviesVm.ForceReload();
                    _seriesVm.ForceReload();
                    _liveVm.ForceReload();
                });
        }

        [RelayCommand]
        private void NavigateHome()
        {
            SelectedNavIndex = 0;
            CurrentView = _homeVm;
        }

        [RelayCommand]
        private void NavigateMovies()
        {
            SelectedNavIndex = 1;
            CurrentView = _moviesVm;
            _moviesVm.EnsureLoaded();
        }

        [RelayCommand]
        private void NavigateSeries()
        {
            SelectedNavIndex = 2;
            CurrentView = _seriesVm;
            _seriesVm.EnsureLoaded();
        }

        [RelayCommand]
        private void NavigateLive()
        {
            SelectedNavIndex = 3;
            CurrentView = _liveVm;
            _liveVm.EnsureLoaded();
        }

        [RelayCommand]
        private void NavigateSettings()
        {
            SelectedNavIndex = 4;
            NavigationService.Instance.NavigateTo(new SettingsViewModel());
        }

        [RelayCommand]
        private void Search()
        {
            if (string.IsNullOrWhiteSpace(SearchText)) return;

            if (SelectedNavIndex == 1)
            {
                _moviesVm.SearchQuery = SearchText;
                _ = _moviesVm.SearchCommand.ExecuteAsync(null);
            }
            else if (SelectedNavIndex == 2)
            {
                _seriesVm.SearchQuery = SearchText;
                _ = _seriesVm.SearchCommand.ExecuteAsync(null);
            }
            else if (SelectedNavIndex == 3)
            {
                _liveVm.SearchQuery = SearchText;
                _ = _liveVm.ApplyFilterCommand.ExecuteAsync(null);
            }
        }
    }
}
