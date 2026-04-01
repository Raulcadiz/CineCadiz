using System;
using System.Windows;
using System.Windows.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using LibVLCSharp.Shared;
using CineCadiz.Models;
using CineCadiz.Services;

namespace CineCadiz.ViewModels
{
    public partial class PlayerViewModel : ObservableObject
    {
        private static readonly PlayerViewModel _instance = new();
        public static PlayerViewModel Instance => _instance;

        public LibVLC LibVLC { get; } = new LibVLC("--no-video-title-show");
        public MediaPlayer MediaPlayer { get; }

        [ObservableProperty] private bool _isVisible;
        [ObservableProperty] private bool _isControlsVisible = true;
        [ObservableProperty] private string _title = string.Empty;
        [ObservableProperty] private bool _isLive;
        [ObservableProperty] private bool _isPlaying;
        [ObservableProperty] private long _currentPosition;
        [ObservableProperty] private long _totalDuration;
        [ObservableProperty] private int _volume = 80;
        [ObservableProperty] private bool _isMuted;
        [ObservableProperty] private bool _isLoading;

        private ContentItem? _currentItem;
        private readonly DispatcherTimer _hideControlsTimer;
        private readonly DispatcherTimer _progressTimer;
        private readonly DispatcherTimer _saveTimer;

        private PlayerViewModel()
        {
            MediaPlayer = new MediaPlayer(LibVLC);

            MediaPlayer.Playing += (s, e) =>
            {
                Application.Current.Dispatcher.Invoke(() =>
                {
                    IsPlaying = true;
                    IsLoading = false;
                });
            };

            MediaPlayer.Paused += (s, e) =>
            {
                Application.Current.Dispatcher.Invoke(() => IsPlaying = false);
            };

            MediaPlayer.Stopped += (s, e) =>
            {
                Application.Current.Dispatcher.Invoke(() =>
                {
                    IsPlaying = false;
                    IsLoading = false;
                });
            };

            MediaPlayer.EndReached += (s, e) =>
            {
                Application.Current.Dispatcher.Invoke(() =>
                {
                    SaveProgress();
                    IsPlaying = false;
                });
            };

            _hideControlsTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(5) };
            _hideControlsTimer.Tick += (s, e) =>
            {
                _hideControlsTimer.Stop();
                IsControlsVisible = false;
            };

            _progressTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(500) };
            _progressTimer.Tick += (s, e) =>
            {
                if (MediaPlayer.IsPlaying)
                {
                    CurrentPosition = MediaPlayer.Time;
                    TotalDuration = MediaPlayer.Length;
                }
            };

            _saveTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(10) };
            _saveTimer.Tick += (s, e) => SaveProgress();
        }

        public void Play(ContentItem item)
        {
            _currentItem = item;
            Title = item.Title;
            IsLive = item.Type == "live";
            IsLoading = true;
            IsVisible = true;
            IsControlsVisible = true;

            var url = item.StreamUrl;
            if (string.IsNullOrEmpty(url) && item.LiveUrls?.Count > 0)
                url = item.LiveUrls[item.ActiveUrlIndex];

            var mediaOptions = IsLive
                ? new[] { "network-caching=2000", "live-caching=2000" }
                : Array.Empty<string>();

            using var media = new Media(LibVLC, new Uri(url), mediaOptions);
            MediaPlayer.Play(media);
            MediaPlayer.Volume = Volume;

            if (!IsLive)
            {
                var savedPos = ProgressService.Instance.GetPositionMs(item.Id);
                if (savedPos > 5000)
                {
                    MediaPlayer.Playing += SeekToSavedPosition;
                }
            }

            _progressTimer.Start();
            _saveTimer.Start();
            ResetControlsTimer();

            _ = ApiService.Instance.PostWatchAsync(item.Id);
        }

        private void SeekToSavedPosition(object? sender, EventArgs e)
        {
            MediaPlayer.Playing -= SeekToSavedPosition;
            if (_currentItem != null)
            {
                var pos = ProgressService.Instance.GetPositionMs(_currentItem.Id);
                if (pos > 0)
                    System.Threading.Tasks.Task.Delay(500).ContinueWith(_ =>
                        Application.Current.Dispatcher.Invoke(() => MediaPlayer.Time = pos));
            }
        }

        private void SaveProgress()
        {
            if (_currentItem == null || IsLive) return;
            if (MediaPlayer.Length > 0)
                ProgressService.Instance.Record(_currentItem, MediaPlayer.Time, MediaPlayer.Length);
        }

        [RelayCommand]
        private void TogglePlayPause()
        {
            if (MediaPlayer.IsPlaying)
                MediaPlayer.Pause();
            else
                MediaPlayer.Play();
        }

        [RelayCommand]
        private void SeekForward()
        {
            if (!IsLive)
                MediaPlayer.Time = Math.Min(MediaPlayer.Time + 10000, MediaPlayer.Length);
        }

        [RelayCommand]
        private void SeekBackward()
        {
            if (!IsLive)
                MediaPlayer.Time = Math.Max(MediaPlayer.Time - 10000, 0);
        }

        [RelayCommand]
        private void Close()
        {
            SaveProgress();
            _progressTimer.Stop();
            _saveTimer.Stop();
            MediaPlayer.Stop();
            IsVisible = false;
            IsPlaying = false;
            _currentItem = null;
        }

        [RelayCommand]
        private void ToggleMute()
        {
            IsMuted = !IsMuted;
            MediaPlayer.Mute = IsMuted;
        }

        public void SetPosition(double fraction)
        {
            if (!IsLive && TotalDuration > 0)
                MediaPlayer.Time = (long)(fraction * TotalDuration);
        }

        public void SetVolume(int vol)
        {
            Volume = Math.Clamp(vol, 0, 100);
            MediaPlayer.Volume = Volume;
        }

        public void SeekSeconds(int seconds)
        {
            if (!IsLive)
                MediaPlayer.Time = Math.Clamp(MediaPlayer.Time + (seconds * 1000L), 0, MediaPlayer.Length);
        }

        public void ShowControls()
        {
            IsControlsVisible = true;
            ResetControlsTimer();
        }

        private void ResetControlsTimer()
        {
            _hideControlsTimer.Stop();
            _hideControlsTimer.Start();
        }
    }
}
