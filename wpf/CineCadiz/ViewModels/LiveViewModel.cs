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
    public partial class LiveViewModel : ObservableObject
    {
        [ObservableProperty] private ObservableCollection<LiveGroup>    _channels      = new();
        [ObservableProperty] private ObservableCollection<string>       _categories    = new();
        [ObservableProperty] private ObservableCollection<LiveListInfo> _lists         = new();
        [ObservableProperty] private string        _selectedCategory = "Todos";
        [ObservableProperty] private string        _searchQuery      = string.Empty;
        [ObservableProperty] private bool          _isLoading;
        [ObservableProperty] private LiveListInfo? _selectedList;

        private bool _loaded;
        private bool _initializing;

        partial void OnSelectedListChanged(LiveListInfo? value)
        {
            if (_initializing || value == null) return;
            if (value.IsCustom)
            {
                // Custom M3U list: no server categories
                Application.Current.Dispatcher.Invoke(() =>
                {
                    Categories.Clear();
                    Categories.Add("Todos");
                    SelectedCategory = "Todos";
                });
            }
            else
            {
                _ = LoadCategoriesAsync();
            }
            _ = ApplyFilterAsync();
        }

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

        private async Task LoadAsync()
        {
            _initializing = true;
            IsLoading = true;
            try
            {
                var listas = await ApiService.Instance.GetLiveListasAsync();

                // Append custom M3U lists from local config
                var customUrls = AppConfig.CustomM3uUrls;
                var customLists = customUrls
                    .Select((url, i) => new LiveListInfo
                    {
                        Id       = -(i + 1),
                        Nombre   = ExtractM3uName(url),
                        IsCustom = true,
                        M3uUrl   = url
                    })
                    .ToList();

                Application.Current.Dispatcher.Invoke(() =>
                {
                    Lists.Clear();
                    foreach (var l in listas)      Lists.Add(l);
                    foreach (var l in customLists) Lists.Add(l);

                    SelectedList = listas.FirstOrDefault(l => l.IsDefault)
                                ?? listas.FirstOrDefault()
                                ?? Lists.FirstOrDefault();
                });
            }
            catch { }
            finally { _initializing = false; }

            await LoadCategoriesAsync();
            await ApplyFilterAsync();
            IsLoading = false;
        }

        private async Task LoadCategoriesAsync()
        {
            if (SelectedList?.IsCustom == true) return; // M3U lists have no backend categories
            try
            {
                var cats = await ApiService.Instance.GetLiveCategoriasAsync(SelectedList?.Id);
                Application.Current.Dispatcher.Invoke(() =>
                {
                    Categories.Clear();
                    Categories.Add("Todos");
                    foreach (var c in cats) Categories.Add(c);
                    SelectedCategory = "Todos";
                });
            }
            catch { }
        }

        [RelayCommand]
        public async Task ApplyFilter() => await ApplyFilterAsync();

        private async Task ApplyFilterAsync()
        {
            IsLoading = true;
            try
            {
                List<LiveGroup> groups;

                if (SelectedList?.IsCustom == true && !string.IsNullOrEmpty(SelectedList.M3uUrl))
                {
                    // Parse M3U playlist
                    groups = await ApiService.Instance.GetLiveFromM3uAsync(SelectedList.M3uUrl);

                    // Apply client-side search filter
                    if (!string.IsNullOrWhiteSpace(SearchQuery))
                    {
                        var q = SearchQuery.ToLowerInvariant();
                        groups = groups.Where(g => g.Title.ToLowerInvariant().Contains(q)).ToList();
                    }
                }
                else
                {
                    var cat = SelectedCategory == "Todos" ? "" : SelectedCategory;
                    groups  = await ApiService.Instance.GetLiveGroupsAsync(SearchQuery, cat, SelectedList?.Id);
                }

                Application.Current.Dispatcher.Invoke(() =>
                {
                    Channels.Clear();
                    foreach (var g in groups) Channels.Add(g);
                });
            }
            catch { }
            finally { IsLoading = false; }
        }

        [RelayCommand]
        private void SelectCategory(string? category)
        {
            if (category == null) return;
            SelectedCategory = category;
            _ = ApplyFilterAsync();
        }

        [RelayCommand]
        private async Task SelectList(LiveListInfo? lista)
        {
            if (lista == null) return;
            SelectedList = lista;
            if (!lista.IsCustom)
                await LoadCategoriesAsync();
            await ApplyFilterAsync();
        }

        [RelayCommand]
        private void PlayChannel(LiveGroup? group)
        {
            if (group == null) return;

            ContentItem item;
            if (group.Channels?.Count > 0)
            {
                item = group.Channels[0];
            }
            else
            {
                item = new ContentItem
                {
                    Id         = group.Id,
                    Title      = group.Title,
                    Type       = "live",
                    StreamUrl  = group.StreamUrl,
                    Image      = group.Image,
                    GroupTitle = group.GroupTitle,
                    LiveUrls   = group.Channels?.Select(c => c.StreamUrl).ToList() ?? new()
                };
            }
            item.Type = "live";
            PlayerViewModel.Instance.Play(item);
        }

        // ── Helpers ────────────────────────────────────────────────
        private static string ExtractM3uName(string url)
        {
            try
            {
                var uri  = new System.Uri(url);
                var host = uri.Host;
                var path = uri.AbsolutePath;
                // Use filename without extension, or host
                var fileName = System.IO.Path.GetFileNameWithoutExtension(path);
                return string.IsNullOrWhiteSpace(fileName) ? host : fileName;
            }
            catch
            {
                return url.Length > 40 ? url[..40] + "…" : url;
            }
        }
    }
}
