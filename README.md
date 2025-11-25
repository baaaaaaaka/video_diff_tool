# Video Diff Tool

A cross-platform GUI tool for comparing videos side-by-side with difference visualization. Supports real-time preview with MPV and encoding with FFmpeg.

## Features

- **Video Comparison**: Compare two videos side-by-side with automatic difference visualization
- **Real-time Preview**: Preview comparisons using MPV player
- **FFmpeg Encoding**: Encode comparison videos with hardware-accelerated HEVC
- **Optional Third Video**: Add a third video to the bottom-right quadrant
- **Drag & Drop**: Easy video file selection with drag and drop support
- **Customizable Titles**: Add custom overlay titles to each video
- **Cross-platform**: Works on macOS and Windows
- **Persistent Settings**: All preferences are saved automatically

## Output Layout

```
+------------+------------+
|  Video 1   |  Video 2   |
| (Candidate)| (Baseline) |
+------------+------------+
|    Diff    |  Video 3   |
|   Blend    | (Optional) |
+------------+------------+
```

## Requirements

### System Requirements
- Python 3.10 or higher
- MPV player (for preview)
- FFmpeg (for encoding)

### Python Dependencies
```bash
pip install -r requirements.txt
```

## Installation

### 1. Install Python dependencies
```bash
cd video_diff_tool
pip install -r requirements.txt
```

### 2. Install MPV

**macOS:**
```bash
brew install mpv
```

**Windows:**
- Download from https://mpv.io/installation/
- Or use Chocolatey: `choco install mpv`
- Or use Scoop: `scoop install mpv`

### 3. Install FFmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
- Download from https://ffmpeg.org/download.html
- Or use Chocolatey: `choco install ffmpeg`
- Or use Scoop: `scoop install ffmpeg`

## Usage

### Launch the application
```bash
python main.py
```

### Basic Workflow

1. **Add Videos**: Drag and drop video files into the Left and Right video zones, or click "Browse..."
2. **Set Titles**: Enter custom titles for each video (optional)
3. **Preview**: Click "Preview with MPV" to see the comparison in real-time
4. **Encode**: Click "Encode with FFmpeg" to create an encoded comparison video

### Enable Third Video

1. Check "Enable Third Video (Bottom Right)"
2. Add a video to the third video zone
3. The third video will appear in the bottom-right quadrant

### Encoding Options

- **Resolution**: 2160p (default), 1080p, 720p, or custom
- **FPS**: 60 fps (default), configurable
- **Encoder**: Auto-selects best available (VideoToolbox, NVENC, AMF, QSV, or CPU)
- **Quality**: QP 17 (default), configurable
- **GOP**: 30 (default), configurable

### Settings

Access settings via **File → Settings** to configure:
- MPV/FFmpeg binary paths
- Font file for overlays
- Default video titles
- Default encoding parameters

## Encoding Details

### Default Encoding Settings
- **Codec**: HEVC (H.265)
- **Pixel Format**: YUV444P (CPU), YUV420P (HW)
- **Resolution**: 3840×2160 (2160p)
- **Frame Rate**: 60 fps
- **Quality**: QP 17
- **GOP Size**: 30

### Hardware Encoders Supported
- **macOS**: VideoToolbox (hevc_videotoolbox)
- **NVIDIA**: NVENC (hevc_nvenc)
- **AMD**: AMF (hevc_amf)
- **Intel**: QuickSync (hevc_qsv)

### Video Scaling
- Input videos are scaled to fit 1/2 of output resolution
- Aspect ratio is preserved with letterboxing/pillarboxing

## Troubleshooting

### "MPV not found"
- Ensure MPV is installed and in your PATH
- Or manually set the path in Settings

### "FFmpeg not found"
- Ensure FFmpeg is installed and in your PATH
- Or manually set the path in Settings

### "Font not found"
- The tool auto-detects system fonts
- If detection fails, manually select a .ttf or .otf font in Settings

### "Frame count mismatch"
- All input videos must have the same number of frames
- Use videos from the same source/render for best results

## License

MIT License

