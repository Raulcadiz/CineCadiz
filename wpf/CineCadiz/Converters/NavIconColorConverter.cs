using System;
using System.Globalization;
using System.Windows;
using System.Windows.Data;
using System.Windows.Media;

namespace CineCadiz.Converters
{
    public class NavIconColorConverter : IValueConverter
    {
        public static readonly NavIconColorConverter Instance = new();

        private static readonly SolidColorBrush ActiveBrush = new(Color.FromRgb(0xE5, 0x39, 0x35));
        private static readonly SolidColorBrush InactiveBrush = new(Color.FromRgb(0xB0, 0xB0, 0xB0));

        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            if (value is int selectedIndex && parameter is string paramStr
                && int.TryParse(paramStr, out int targetIndex))
            {
                return selectedIndex == targetIndex ? ActiveBrush : InactiveBrush;
            }
            return InactiveBrush;
        }

        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
            => DependencyProperty.UnsetValue;
    }
}
