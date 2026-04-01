using System;
using CommunityToolkit.Mvvm.ComponentModel;

namespace CineCadiz.Services
{
    public class NavigationService
    {
        private static readonly NavigationService _instance = new();
        public static NavigationService Instance => _instance;

        private NavigationService() { }

        public event Action<object>? Navigated;
        public event Action? BackRequested;

        public void NavigateTo(object viewModel) => Navigated?.Invoke(viewModel);
        public void GoBack()                     => BackRequested?.Invoke();
    }
}
