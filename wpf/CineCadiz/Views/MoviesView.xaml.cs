using System.Windows.Controls;
using System.Windows.Input;
using CineCadiz.Models;
using CineCadiz.ViewModels;

namespace CineCadiz.Views
{
    public partial class MoviesView : UserControl
    {
        public MoviesView()
        {
            InitializeComponent();
        }

        private void MovieCard_Click(object sender, MouseButtonEventArgs e)
        {
            if (sender is System.Windows.Controls.Border b && b.Tag is ContentItem item
                && DataContext is MoviesViewModel vm)
                vm.PlayMovieCommand.Execute(item);
        }
    }
}
