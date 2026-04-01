using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using CineCadiz.Models;
using CineCadiz.ViewModels;

namespace CineCadiz.Views
{
    public partial class HomeView : UserControl
    {
        public HomeView()
        {
            InitializeComponent();
        }

        private void ContinueCard_Click(object sender, MouseButtonEventArgs e)
        {
            if (sender is Border b && b.Tag is ProgressEntry entry && DataContext is HomeViewModel vm)
                vm.PlayContinueCommand.Execute(entry);
        }

        private void TrendingCard_Click(object sender, MouseButtonEventArgs e)
        {
            if (sender is Border b && b.Tag is ContentItem item && DataContext is HomeViewModel vm)
                vm.PlayItemCommand.Execute(item);
        }
    }
}
