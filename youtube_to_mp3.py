"""YouTube動画をMP3に変換する。

使い方:
    python youtube_to_mp3.py <YouTube URL> [出力ディレクトリ]

例:
    python youtube_to_mp3.py "https://youtu.be/hm-0M7m_ImY"
    python youtube_to_mp3.py "https://youtu.be/hm-0M7m_ImY" ./music

事前準備:
    pip install yt-dlp
    ffmpegをインストール (macOS: brew install ffmpeg)
"""

import shutil
import sys
from pathlib import Path

import yt_dlp


def convert_to_mp3(url: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpegが見つかりません。先にffmpegをインストールしてください。")

    downloaded: dict[str, Path] = {}

    def hook(d: dict) -> None:
        if d.get("status") == "finished":
            downloaded["path"] = Path(d["filename"])

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ],
        "progress_hooks": [hook],
        "quiet": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    title = info.get("title", "audio")
    mp3_path = output_dir / f"{title}.mp3"
    if not mp3_path.exists() and "path" in downloaded:
        mp3_path = downloaded["path"].with_suffix(".mp3")

    return mp3_path


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    url = sys.argv[1]
    output_dir = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("./output")

    try:
        mp3_path = convert_to_mp3(url, output_dir)
    except Exception as exc:
        print(f"変換に失敗しました: {exc}", file=sys.stderr)
        return 1

    print(f"\n変換完了: {mp3_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
