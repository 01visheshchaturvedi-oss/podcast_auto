#!/usr/bin/env python3
"""
🎙️  Aakashvani - Emotional Hindi Podcast Generator
===================================================
Automation agent that generates male+female conversation podcasts
with human-like emotion using free resources only.

Features:
- Emotion-aware SSML prosody (pitch, rate, volume per sentence)
- Male/Female Hindi voices from Microsoft Edge TTS (free)
- Broadcast-quality audio mastering (EQ, compression, stereo widen)
- Smart transitions between speakers
- High-bitrate output (256kbps MP3)

Usage:
  python podcast_agent.py                           # Interactive mode
  python podcast_agent.py --script script.txt       # From file
  python podcast_agent.py --text "Male:...."        # Inline text
  python podcast_agent.py --help                    # Full options
"""

import asyncio
import os
import sys
import argparse

# Add current directory so 'engine' package is found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.podcast_builder import PodcastBuilder, parse_script, MODES
from engine.tts_engine import EmotionalTTSEngine
from engine.emotion_ssml import detect_emotion, get_ssml_params


def get_script_input(args):
    """Get script text from file, inline text, or stdin."""
    if args.script:
        with open(args.script, 'r', encoding='utf-8') as f:
            return f.read().strip(), "file"

    if args.text:
        return args.text.strip(), "inline"

    return None, None


def interactive_input():
    """Interactive input mode with user-friendly prompts."""
    print("\n" + "=" * 60)
    print("   🎙️  AAKASHVANI - Emotional Hindi Podcast Generator")
    print("=" * 60)
    print()
    print("⚡ Select Mode:")
    for k, v in MODES.items():
        print(f"   {k} → {v['label']}")
    mode = input("\n   Choice (1/2/3/4) [default: 3]: ").strip() or "3"
    if mode not in MODES:
        mode = "3"
    print(f"   ✅ {MODES[mode]['label']}\n")

    print("📋 Input Format:")
    print("   1 → With Male:/Female: labels (you control who speaks)")
    print("   2 → Plain notes (auto alternate voices)")
    fmt = input("\n   Choice (1/2) [default: 1]: ").strip() or "1"

    print("\n📝 Paste your script below.")
    print("   → Labels: Male: / Female: (or पुरुष: / महिला:)")
    print("   → Press Enter on a blank line when done.\n")
    lines = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            break
        if line.strip() == "" and lines:
            break
        if line.strip():
            lines.append(line.strip())

    raw = "\n".join(lines).strip()
    if not raw:
        print("❌ No input received!")
        return None, None, None

    name = input("\n💾 Output filename (no extension) [default: podcast]: ").strip() or "podcast"
    mastering = input("\n🎚️  Apply broadcast mastering? (Y/n) [default: Y]: ").strip().lower() != 'n'

    return raw, fmt, mode, name, mastering


def main():
    parser = argparse.ArgumentParser(
        description="🎙️ Aakashvani - Emotional Hindi Podcast Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python podcast_agent.py --script transcribe.txt
  python podcast_agent.py --text "Male: नमस्ते|Female: आज का विषय"
  python podcast_agent.py --text "Male:..." --mode 4 --no-mastering
        """
    )
    parser.add_argument('--script', type=str, help='Input script file with Male:/Female: labels')
    parser.add_argument('--text', type=str, help='Inline script text')
    parser.add_argument('--format', type=str, choices=['1', '2'], default='1',
                        help='1=labeled 2=plain (default: 1)')
    parser.add_argument('--mode', type=str, choices=['1', '2', '3', '4'], default='3',
                        help='Speed mode (default: 3=natural)')
    parser.add_argument('--name', type=str, default='podcast',
                        help='Output filename (default: podcast)')
    parser.add_argument('--no-mastering', action='store_true',
                        help='Skip broadcast mastering chain')
    parser.add_argument('--quick-test', type=str,
                        help='Quick test with short text (for testing)')
    parser.add_argument('--preview', action='store_true',
                        help='Show emotion analysis without generating audio')
    parser.add_argument('--sample-text', type=str,
                        help='Path to sample text file for demo/test')

    args = parser.parse_args()

    # ── Quick test mode ────────────────────────────────────────
    if args.quick_test:
        raw = args.quick_test
        fmt = args.format

        # Auto-detect format
        if not any(label in raw for label in ['Male:', 'Female:', 'male:', 'female:', 'पुरुष:', 'महिला:']):
            fmt = '2'

        print(f"\n⚡ Quick Test Mode")
        print(f"   Text: {raw[:80]}...")
        print(f"   Format: {'Labeled' if fmt == '1' else 'Plain'}")
        print(f"   Mode: {MODES[args.mode]['label']}")

        # Show emotion analysis
        print("\n📊 Emotion Analysis:")
        from engine.podcast_builder import parse_script
        if fmt == '1':
            script = parse_script(raw)
        else:
            script = [{"role": "male" if i % 2 == 0 else "female", "text": s}
                      for i, s in enumerate(raw.replace('\n', ' ').split('.')) if s.strip()]

        for turn in script:
            emotion = detect_emotion(turn['text'])
            params = get_ssml_params(emotion, turn['role'], turn['text'])
            active = {k: v for k, v in emotion.items() if v > 0}
            print(f"   [{turn['role'].upper()}] {turn['text'][:50]}...")
            print(f"       Emotion: {active or 'neutral'}")
            print(f"       SSML: pitch={params['pitch']}, rate={params['rate']}, vol={params['volume']}")

        if args.preview:
            return

        # Generate audio
        builder = PodcastBuilder(mode=args.mode)
        out = asyncio.run(builder.build(raw, fmt=fmt, name=args.name or "test",
                                        use_mastering=not args.no_mastering))
        if out:
            print(f"\n🎉 Generated: {out}")
        return

    # ── File / inline mode ─────────────────────────────────────
    raw, source = get_script_input(args)
    if raw:
        fmt = args.format
        if not any(label in raw for label in ['Male:', 'Female:', 'male:', 'female:', 'पुरुष:', 'महिला:']):
            fmt = '2'

        builder = PodcastBuilder(mode=args.mode)
        out = asyncio.run(builder.build(raw, fmt=fmt, name=args.name or "podcast",
                                        use_mastering=not args.no_mastering))
        if out:
            print(f"\n🎉 Generated: {out}")
        return

    # ── Interactive mode ──────────────────────────────────────
    result = interactive_input()
    if result is None or result[0] is None:
        return

    raw, fmt, mode, name, mastering = result
    builder = PodcastBuilder(mode=mode)
    out = asyncio.run(builder.build(raw, fmt=fmt, name=name,
                                    use_mastering=mastering))
    if out:
        print(f"\n🎉 Generated: {out}")

    # ── Sample/demo text ──────────────────────────────────────
    if args.sample_text:
        try:
            with open(args.sample_text, 'r', encoding='utf-8') as f:
                raw = f.read()
            builder = PodcastBuilder(mode=args.mode)
            out = asyncio.run(builder.build(raw, fmt='1', name=args.name or "demo",
                                            use_mastering=not args.no_mastering))
            if out:
                print(f"\n🎉 Generated: {out}")
        except FileNotFoundError:
            print(f"❌ Sample text file not found: {args.sample_text}")


if __name__ == "__main__":
    main()
