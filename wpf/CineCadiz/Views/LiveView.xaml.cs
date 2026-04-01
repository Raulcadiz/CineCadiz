using System.Windows.Controls;
using System.Windows.Input;
using CineCadiz.Models;
using CineCadiz.ViewModels;

namespace CineCadiz.Views
{
    public partial class LiveView : UserControl
    {
        public LiveView()
        {
            InitializeComponent();
        }

        private void Channel_Click(object sender, MouseButtonEventArgs e)
        {
            if (sender is Border b && b.Tag is LiveGroup group && DataContext is LiveViewModel vm)
                vm.PlayChannelCommand.Execute(group);
        }
    }
}
