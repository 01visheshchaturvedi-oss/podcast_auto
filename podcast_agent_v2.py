#!/usr/bin/env python3
"""
Aakashvani v2 🎙️ — Emotion-Aware Hindi Podcast Generator

Enhanced version with:
  • Microsoft express-as SSML styles (emotional voices)
  • Background music mixing with ducking
  • Broadcast-quality mastering (-16 LUFS)
  • Inline mood annotations [excited] [serious] [cheerful]
  • Voice caching for faster rebuilds
  • Overlap-based crossfades

Usage:
  # Basic (mode 4 = expressive)
  python podcast_agent_v2.py --script transcribe.txt

  # High quality with background music
  python podcast_agent_v2.py --script transcribe.txt --name "My_Podcast" --music bg.wav

  # Test express-as compatibility
  python podcast_agent_v2.py --test-express

  # Fast revision mode
  python podcast_agent_v2.py --script transcribe.txt --mode 1 --quick

  # Analyze reference audio
  python podcast_agent_v2.py --analyze reference.m4a

All free, no paid APIs. Uses edge-tts (free) + gTTS (fallback).
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine_v2 import (
    PodcastBuilderV2,
    detect_emotion_v2, get_voice_style,
    analyze_loudness, _find_ffmpeg,
    FEMALE_VOICE, MALE_VOICE, EXPRESS_AS_STYLES, VoiceStyle,
)
from engine_v2.emotion_v2 import get_express_as_style_from_annotation, STYLE_ALIASES

from pydub import AudioSegment


async def test_express_as():
    """Test if Microsoft express-as styles work with Hindi voices."""
    print("=" * 60)
    print("🧪 Testing Microsoft express-as SSML with Hindi voices")
    print("=" * 60)
    print()
    print(f"Female: {FEMALE_VOICE}")
    print(f"Male:   {MALE_VOICE}")
    print()

    test_phrase = "नमस्ते, आप कैसे हैं?"

    for voice_name, role in [(FEMALE_VOICE, 'female'), (MALE_VOICE, 'male')]:
        print(f"📢 Testing {role.upper()} ({voice_name}):")
        print()

        for style in EXPRESS_AS_STYLES:
            try:
                ssml = f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
 xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="hi-IN">
 <voice name="{voice_name}">
  <mstts:express-as style="{style}">
   {test_phrase}
  </mstts:express-as>
 </voice>
</speak>'''

                ssml_path = f"_test_{role}_{style}.xml"
                out_path = f"_test_{role}_{style}.mp3"

                with open(ssml_path, 'w', encoding='utf-8') as f:
                    f.write(ssml)

                rc = subprocess.run(
                    [sys.executable, '-m', 'edge_tts',
                     '--write-media', out_path,
                     '--custom-ssml', ssml_path],
                    capture_output=True, text=True, timeout=30
                )

                success = rc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 500

                if success:
                    try:
                        seg = AudioSegment.from_mp3(out_path)
                        dur_ms = len(seg)
                    except:
                        dur_ms = -1
                    size_kb = os.path.getsize(out_path) // 1024
                    print(f"   ✅ {style:20s}  {size_kb}KB  {dur_ms}ms")
                else:
                    err = rc.stderr[:60] if rc.stderr else "unknown error"
                    print(f"   ❌ {style:20s}  {err}")

                # Cleanup
                for p in [ssml_path, out_path]:
                    try:
                        os.remove(p)
                    except:
                        pass

            except Exception as e:
                print(f"   ❌ {style:20s}  exception: {e}")

        print()

    print()
    print("Note: If most styles show ✅, express-as works with Hindi voices!")
    print("If they show ❌, audio will use native rate/pitch/volume params")
    print("which still provide emotion but with less variety.")
    print()


async def analyze(audio_path: str):
    """Analyze a reference audio file."""
    if not os.path.exists(audio_path):
        print(f"❌ File not found: {audio_path}")
        return

    print("=" * 60)
    print(f"📊 Audio Analysis: {os.path.basename(audio_path)}")
    print("=" * 60)

    ffmpeg = _find_ffmpeg()
    if ffmpeg:
        ffprobe = ffmpeg.replace('ffmpeg', 'ffprobe')
        r = subprocess.run(
            [ffprobe, '-v', 'quiet', '-print_format', 'json',
             '-show_format', '-show_streams', audio_path],
            capture_output=True, text=True, timeout=30
        )
        try:
            data = json.loads(r.stdout)
            streams = data.get('streams', [])
            fmt = data.get('format', {})

            for stream in streams:
                if stream['codec_type'] == 'audio':
                    print(f"\n  Format: {stream['codec_name'].upper()} ({stream.get('codec_long_name','?')})")
                    print(f"  Sample Rate: {stream['sample_rate']} Hz")
                    print(f"  Channels: {stream['channels']} ({stream.get('channel_layout','?')})")
                    print(f"  Duration: {float(fmt.get('duration',0))/60:.1f} min")

            # Loudness
            print(f"\n  ⏳ Analyzing loudness...")
            audio = AudioSegment.from_file(audio_path)
            info = analyze_loudness(audio)
            if 'integrated' in info:
                print(f"  Integrated: {info['integrated']:.1f} LUFS")
            if 'lra' in info:
                print(f"  LRA: {info['lra']:.1f} LU")
            if 'peak' in info:
                print(f"  Peak: {info['peak']:.1f} dB")
            if 'rms' in info:
                print(f"  Duration: {len(audio)/1000/60:.1f} min ({len(audio)//1000}s)")

        except Exception as e:
            print(f"  Analysis error: {e}")

    print("=" * 60)


async def interactive_mode():
    """Interactive mode: enter Hindi text and get instant podcast."""
    print("=" * 60)
    print("🎙️  Aakashvani v2 - Interactive Mode")
    print("   Type Hindi podcast script (or paste)")
    print("   Format: Male:, Female:, Male [excited]:, etc.")
    print("   Press Ctrl+D (or Ctrl+Z on Windows) when done")
    print("=" * 60)
    print()

    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except (EOFError, KeyboardInterrupt):
        pass

    if not lines:
        print("No input provided.")
        return

    # Write to temp file
    temp_path = "_interactive_script.txt"
    with open(temp_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    builder = PodcastBuilderV2(
        mode='4',
        output_dir='.',
        use_express_as=True,
        cache_voices=True,
    )
    result = await builder.build(temp_path, output_name=f"interactive_{int(time.time())}")

    try:
        os.remove(temp_path)
    except:
        pass

    if os.path.exists(result['output_path']):
        print(f"\n🎯 Output: {result['output_path']}")


def main():
    parser = argparse.ArgumentParser(
        description='Aakashvani v2 — Emotion-Aware Hindi Podcast Generator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python podcast_agent_v2.py --script transcribe.txt
  python podcast_agent_v2.py --script transcribe.txt --mode 4 --music bg_music.wav
  python podcast_agent_v2.py --script transcribe.txt --name "My_Podcast" --quick
  python podcast_agent_v2.py --test-express
  python podcast_agent_v2.py --analyze reference.m4a
  python podcast_agent_v2.py --interactive
        """
    )
    parser.add_argument('--script', '-s', type=str,
                        help='Path to script text file')
    parser.add_argument('--name', '-n', type=str, default=None,
                        help='Output filename (without extension)')
    parser.add_argument('--mode', '-m', type=str, default='4',
                        choices=['1', '2', '3', '4'],
                        help='Speed preset: 1=Revision, 2=Learn, 3=Normal, 4=Expressive (default)')
    parser.add_argument('--music', type=str, default=None,
                        help='Background music file path (WAV/MP3)')
    parser.add_argument('--music-volume', type=float, default=-20.0,
                        help='Background music volume in dB (default: -20)')
    parser.add_argument('--quick', '-q', action='store_true',
                        help='Skip background music, use basic mastering')
    parser.add_argument('--no-express', action='store_true',
                        help='Disable express-as SSML styles')
    parser.add_argument('--no-cache', action='store_true',
                        help='Disable voice caching')
    parser.add_argument('--output-dir', '-o', type=str, default='podcast_output',
                        help='Output directory (default: podcast_output)')
    parser.add_argument('--bitrate', type=str, default='256k',
                        help='Export bitrate (default: 256k)')
    parser.add_argument('--test-express', action='store_true',
                        help='Test express-as SSML compatibility with Hindi voices')
    parser.add_argument('--analyze', type=str,
                        help='Analyze an audio file (LUFS, format, etc.)')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='Interactive mode: type/paste script, get podcast')
    parser.add_argument('--no-split', action='store_true',
                        help='Disable sentence-level splitting')

    args = parser.parse_args()

    if args.test_express:
        asyncio.run(test_express_as())
        return

    if args.analyze:
        asyncio.run(analyze(args.analyze))
        return

    if args.interactive:
        asyncio.run(interactive_mode())
        return

    if not args.script:
        parser.print_help()
        print()
        print("❌ Provide --script or use --interactive or --test-express or --analyze")
        sys.exit(1)

    if not os.path.exists(args.script):
        print(f"❌ Script file not found: {args.script}")
        sys.exit(1)

    # Welcome
    print()
    print("╔══════════════════════════════════════════════╗")
    MODE_LABELS = {"1": "Revision (fast)", "2": "Learn (slow)",
                   "3": "Natural", "4": "Expressive (recommended)"}
    print(f"║   🎙️  Aakashvani v2 — {MODE_LABELS.get(args.mode, 'Custom')}")
    print("╚══════════════════════════════════════════════╝")
    print()

    print(f"📄 Script:     {args.script}")
    print(f"🎯 Mode:       {args.mode} ({MODE_LABELS.get(args.mode, 'Custom')})")
    print(f"🎭 express-as: {'ON' if not args.no_express else 'OFF'}")
    print(f"🎵 Background: {args.music or 'None (ambient drone)'}")
    print(f"💾 Export:     {args.bitrate}")
    print()

    builder = PodcastBuilderV2(
        mode=args.mode,
        output_dir=args.output_dir,
        cache_voices=not args.no_cache,
        use_express_as=not args.no_express,
        background_music=args.music if not args.quick else None,
        music_volume=args.music_volume,
        high_quality=not args.quick,
        export_bitrate=args.bitrate,
        split_sentences=not args.no_split,
    )

    result = asyncio.run(builder.build(args.script, output_name=args.name))

    if result.get('status') == 'completed':
        print(f"\n✅ Done! → {result['output_path']}")
    else:
        print(f"\n❌ Build failed.")


if __name__ == '__main__':
    main()
