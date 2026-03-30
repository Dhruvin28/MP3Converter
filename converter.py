import sys
import os
import yt_dlp


def get_output_path():
    """Return the output directory, creating it if needed."""
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def download_mp3(url: str, output_dir: str | None = None, progress_hooks: list | None = None) -> list[str]:
    """Download a YouTube video or playlist and convert to MP3.

    Automatically detects playlists. Playlist tracks are saved into a
    subfolder named after the playlist, with filenames prefixed by track number.

    Args:
        url: YouTube video or playlist URL.
        output_dir: Base directory to save MP3 files. Defaults to ./downloads.
        progress_hooks: Optional list of yt-dlp progress hook callables.

    Returns:
        List of paths to downloaded MP3 files.
    """
    if output_dir is None:
        output_dir = get_output_path()

    is_playlist = "playlist" in url or "&list=" in url

    if is_playlist:
        outtmpl = os.path.join(
            output_dir, "%(playlist_title)s", "%(playlist_index)03d - %(title)s.%(ext)s"
        )
    else:
        outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }
        ],
        "outtmpl": outtmpl,
        "noplaylist": not is_playlist,
        "ignoreerrors": True,
        "progress_hooks": progress_hooks or [],
    }

    downloaded = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            return downloaded

        entries = info.get("entries", [info])
        for entry in entries:
            if entry is None:
                continue
            filename = ydl.prepare_filename(entry)
            mp3_path = os.path.splitext(filename)[0] + ".mp3"
            downloaded.append(mp3_path)

    print(f"\nDownloaded {len(downloaded)} track(s)")
    for path in downloaded:
        print(f"  {path}")
    return downloaded


def main():
    if len(sys.argv) < 2:
        print("Usage: python converter.py <youtube_url> [youtube_url2 ...]")
        print("  Supports single videos and playlist URLs.")
        sys.exit(1)

    urls = sys.argv[1:]
    for url in urls:
        print(f"\nProcessing: {url}")
        try:
            download_mp3(url)
        except Exception as e:
            print(f"Error processing {url}: {e}")


if __name__ == "__main__":
    main()
