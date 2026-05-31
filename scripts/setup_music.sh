#!/bin/bash
# setup_music.sh - Download free CC0 background music for podcast production
# Runs automatically in Codespaces postCreateCommand
# Uses free, public domain / CC0 tracks from the internet

set -e

MUSIC_DIR="$HOME/podcast_music"
mkdir -p "$MUSIC_DIR"

echo "🎵 Setting up background music..."

# Download free CC0/public domain ambient tracks
# These are from freesound.org and similar CC0 sources

# Track 1: Soft Ambient Pad (short) from freesound CC0
echo "   Downloading ambient track 1..."
curl -sL "https://github.com/01visheshchaturvedi-oss/podcast_auto/releases/download/v1.0/music_ambient.mp3" \
  -o "$MUSIC_DIR/ambient.mp3" 2>/dev/null || echo "   ⚠️  Could not download (no release yet)"

# If downloads failed, generate ambient drone ourselves
if [ ! -f "$MUSIC_DIR/ambient.mp3" ]; then
    echo "   Generating ambient drone via Python..."
    python3 -c "
import numpy as np, struct

sr = 44100
dur = 300  # 5 min
t = np.arange(sr * dur) / sr

# Warm ambient pad
drone = 0.008 * np.sin(2*np.pi*55*t)      # A2
drone += 0.004 * np.sin(2*np.pi*82*t)      # E3
drone += 0.003 * np.sin(2*np.pi*110*t)     # A3
drone += 0.002 * np.random.randn(len(t)) * 0.3  # noise pad
drone = drone / np.max(np.abs(drone))
drone_int16 = (drone * 18000).astype(np.int16)

with open('$MUSIC_DIR/ambient.raw', 'wb') as f:
    f.write(drone_int16.tobytes())
" 2>/dev/null

    # Convert raw to MP3
    ffmpeg -y -f s16le -ar 44100 -ac 1 -i "$MUSIC_DIR/ambient.raw" \
           -codec:a libmp3lame -b:a 128k "$MUSIC_DIR/ambient.mp3" 2>/dev/null
    rm -f "$MUSIC_DIR/ambient.raw"
fi

echo "   ✅ Background music ready: $MUSIC_DIR/ambient.mp3"
echo ""
echo "   Use with: python podcast_agent_v2.py --script transcribe.txt --music $MUSIC_DIR/ambient.mp3"
echo "   (Or copy your own music file and pass --music path/to/your/music.wav)"
