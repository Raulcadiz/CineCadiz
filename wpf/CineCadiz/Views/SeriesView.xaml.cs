using System.Windows.Controls;
using System.Windows.Input;
using CineCadiz.Models;
using CineCadiz.ViewModels;

namespace CineCadiz.Views
{
    public partial class SeriesView : UserControl
    {
        public SeriesView()
        {
            InitializeComponent();
        }

        private void SeriesCard_Click(object sender, MouseButtonEventArgs e)
        {
            if (sender is System.Windows.Controls.Border b && b.Tag is SeriesItem item
                && DataContext is SeriesViewModel vm)
                vm.OpenSeriesCommand.Execute(item);
        }
    }
}
