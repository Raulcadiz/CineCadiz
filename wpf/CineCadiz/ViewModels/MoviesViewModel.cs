using System.Collections.ObjectModel;
using System.Threading.Tasks;
using System.Windows;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using CineCadiz.Models;
using CineCadiz.Services;

namespace CineCadiz.ViewModels
{
    public partial class MoviesViewModel : ObservableObject
    {
        [ObservableProperty] private ObservableCollection<ContentItem> _movies = new();
        [ObservableProperty] private bool _isLoading;
        [ObservableProperty] private string _searchQuery = string.Empty;
        [ObservableProperty] private int _currentPage = 1;
        [ObservableProperty] private int _totalPages = 1;
        [ObservableProperty] private bool _hasPrevious;
        [ObservableProperty] private bool _hasNext;
        [ObservableProperty] private bool _hasError;
        [ObservableProperty] private string _errorMessage = string.Empty;

        private bool _loaded;
        private int _lastPage = 1;
        private string _lastQuery = string.Empty;

        public void EnsureLoaded()
        {
            if (!_loaded)
            {
                _loaded = true;
                _ = LoadAsync();
            }
        }

        public void ForceReload()
        {
            _loaded = false;
            SearchQuery = string.Empty;
            EnsureLoaded();
        }

        private async Task LoadAsync(int page = 1, string query = "")
        {
            IsLoading = true;
            HasError = false;
            _lastPage = page;
            _lastQuery = query;
            try
            {
                var result = await ApiService.Instance.GetMoviesAsync(page, 25, query);
                Application.Current.Dispatcher.Invoke(() =>
                {
                    Movies.Clear();
                    foreach (var item in result.Items)
                        Movies.Add(item);

                    CurrentPage = result.Page;
                    TotalPages = result.Pages > 0 ? result.Pages : 1;
                    HasPrevious = CurrentPage > 1;
                    HasNext = CurrentPage < TotalPages;
                });
            }
            catch (Exception ex)
            {
                HasError = true;
                ErrorMessage = $"Error al cargar películas: {ex.Message}";
            }
            finally
            {
                IsLoading = false;
            }
        }

        [RelayCommand]
        public async Task Refresh() => await LoadAsync(_lastPage, _lastQuery);

        [RelayCommand]
        public async Task Search()
        {
            CurrentPage = 1;
            await LoadAsync(1, SearchQuery);
        }

        [RelayCommand]
        private async Task PreviousPage()
        {
            if (CurrentPage > 1)
                await LoadAsync(CurrentPage - 1, SearchQuery);
        }

        [RelayCommand]
        private async Task NextPage()
        {
            if (CurrentPage < TotalPages)
                await LoadAsync(CurrentPage + 1, SearchQuery);
        }

        [RelayCommand]
        private void PlayMovie(ContentItem? item)
        {
            if (item == null) return;
            PlayerViewModel.Instance.Play(item);
        }
    }
}
