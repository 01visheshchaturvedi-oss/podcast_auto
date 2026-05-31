"""
Podcast Builder - Assembles multi-speaker podcast with smart transitions
Handles:
- Script parsing (Male:/Female: labels)
- Multi-threaded TTS generation
- Smart crossfades between speakers
- Broadcast-quality mastering chain
- High-bitrate output
"""

import asyncio
import os
import re
import time
from pydub import AudioSegment
from pydub.effects import normalize

from .tts_engine import EmotionalTTSEngine, silence, MODES
from .emotion_ssml import detect_emotion, get_ssml_params, analyze_script_for_emotions
from .audio_effects import master_podcast


def parse_script(raw_text):
    """
    Parse Male:/Female: prefixed text into script turns.
    Handles both line-separated and same-line formats.
    """
    parts = re.split(r'((?:male|female|पुरुष|महिला)\s*:)', raw_text, flags=re.IGNORECASE)

    script = []
    i = 1
    while i < len(parts) - 1:
        label = parts[i].strip().rstrip(':').lower()
        text = parts[i + 1].strip() if i + 1 < len(parts) else ""
        # Clean up trailing role label accidentally included
        text = re.split(r'(?:male|female|पुरुष|महिला)\s*:', text, flags=re.IGNORECASE)[0].strip()
        role = "male" if label in ("male", "पुरुष") else "female"
        if text:
            script.append({"role": role, "text": text})
        i += 2

    return script


def parse_plain_notes(raw_text):
    """
    Convert plain notes to alternating speaker script with intro/outro.
    """
    sents = [s.strip() for s in re.split(r'(?<=[।.!?])\s+', raw_text) if s.strip()]

    if not sents:
        return []

    script = [
        {"role": "male", "text": "नमस्ते! आज के करंट अफेयर्स रिवीजन में आपका स्वागत है।"}
    ]

    # Alternate speakers every 2-3 sentences
    role_idx = 0
    chunk_size = 2
    i = 0
    while i < len(sents):
        chunk = " ".join(sents[i:i+chunk_size])
        role = "female" if (role_idx % 2 == 0) else "male"
        script.append({"role": role, "text": chunk})
        role_idx += 1
        i += chunk_size
        # Vary chunk size slightly for natural feel
        chunk_size = 3 if chunk_size == 2 else 2

    script.append({"role": "male", "text": "यह था आज का रिवीजन। धन्यवाद! आपका दिन शुभ हो।"})

    return script


def split_sentences(text):
    """Split text into sentences."""
    text = re.sub(r'([।.!?])\s*', r'\1\n', text)
    return [s.strip() for s in text.split('\n') if s.strip()]


class PodcastBuilder:
    """
    Full podcast assembly pipeline.
    """

    def __init__(self, mode="3", output_dir="podcast_output"):
        self.mode = mode
        self.output_dir = output_dir
        self.tts = EmotionalTTSEngine(mode=mode, output_dir=output_dir)
        os.makedirs(output_dir, exist_ok=True)

    def clean_text(self, text):
        """Clean text for display."""
        text = re.sub(r'<[^>]+>', '', text)
        return re.sub(r'\s+', ' ', text).strip()

    def summary_text(self, text, max_len=50):
        """Truncated clean text for display."""
        clean = self.clean_text(text)
        return clean[:max_len] + "..." if len(clean) > max_len else clean

    async def build(self, raw_text, fmt="1", name="podcast", use_mastering=True):
        """
        Build podcast from raw script text.

        Args:
            raw_text: Input script with Male:/Female: labels or plain notes
            fmt: "1" for labeled, "2" for plain notes
            name: Output filename (without extension)
            use_mastering: Apply broadcast mastering chain

        Returns:
            Path to output audio file, or None on failure
        """
        start_time = time.time()

        # ── Parse ──────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("   🎙️  EMOTIONAL HINDI PODCAST GENERATOR")
        print("=" * 60)

        if fmt == "1":
            raw_script = parse_script(raw_text)
        else:
            raw_script = parse_plain_notes(raw_text)

        if not raw_script:
            print("❌ No valid script content parsed!")
            return None

        # ── Analyze for emotions ──────────────────────────────
        print(f"\n📊 Analyzing {len(raw_script)} speaker turns for emotion...")
        script = analyze_script_for_emotions(raw_script)

        print(f"\n📋 Script Preview:")
        for i, turn in enumerate(script):
            emoji = "👩" if turn['role'] == 'female' else '👨'
            emotion_str = ", ".join(
                f"{k}:{v}" for k, v in turn.get('emotion', {}).items() if v > 0
            ) or "neutral"
            print(f"   {emoji} [{turn['role'].upper()}] {self.summary_text(turn['text'], 55)}")
            if emotion_str:
                print(f"        → {emotion_str}")

        # ── Generate TTS ──────────────────────────────────────
        print(f"\n🎤 Generating {len(script)} turns with emotional SSML...\n")

        clips = []  # List of (role, AudioSegment, params)
        for i, turn in enumerate(script):
            role = turn['role']
            text = turn['text']
            emoji = "👩" if role == 'female' else '👨'

            print(f"  {emoji} [{i+1}/{len(script)}] ({role.upper()}) {self.summary_text(text)}...")

            clip, params = await self.tts.synthesize_turn(turn, i)

            if clip is None:
                print(f"    ⚠️  Skipping empty segment #{i+1}")
                continue

            clips.append((role, clip, params))
            print(f"    ✅ {len(clip)/1000:.1f}s")

            # Throttle to avoid edge-tts rate limiting (Microsoft servers)
            await asyncio.sleep(1.5)

        if not clips:
            print("❌ No audio generated!")
            return None

        # ── Assemble with transitions ─────────────────────────
        print(f"\n🔗 Assembling {len(clips)} audio segments...")

        final = clips[0][1]
        for i in range(1, len(clips)):
            prev_role = clips[i-1][0]
            curr_role = clips[i][0]
            curr_clip = clips[i][1]

            if prev_role != curr_role:
                # Speaker switch: gap + crossfade
                gap = silence(500)
                faded_end = final.fade_out(80)
                faded_curr = curr_clip.fade_in(80)
                final = faded_end + gap + faded_curr
            else:
                # Same speaker continues
                final = final + silence(300) + curr_clip

        # ── Mastering ─────────────────────────────────────────
        print(f"\n🎚️  Post-processing ({len(final)/1000:.1f}s raw)...")

        if use_mastering:
            final = master_podcast(final)
        else:
            final = normalize(final)

        # ── Export ────────────────────────────────────────────
        out_path = os.path.join(self.output_dir, f"{name}.mp3")

        # Convert to stereo 44.1kHz for broadcast quality if needed
        import subprocess, tempfile
        if final.channels == 1:
            print("  🎛️  Upmixing mono → stereo...")
            final = final.set_channels(2)
        if final.frame_rate < 44100:
            print(f"  🎛️  Upsampling {final.frame_rate}Hz → 44100Hz...")
            final = final.set_frame_rate(44100)

        # Export with explicit CBR 256k parameters
        # Using -b:a 256k (not -q:a) for guaranteed bitrate
        final.export(out_path, format="mp3",
                     parameters=["-b:a", "256k", "-ar", "44100", "-ac", "2"])

        elapsed = time.time() - start_time
        duration_min = len(final) / 60000

        print(f"\n✅ Done! 🎉")
        print(f"   📁 Output: {out_path}")
        print(f"   ⏱️  Duration: {len(final)/1000:.1f}s ({duration_min:.1f} min)")
        print(f"   📦 Size: {os.path.getsize(out_path)/1024/1024:.1f} MB")
        print(f"   ⚡ Generated in {elapsed:.1f}s ({(len(final)/1000)/elapsed:.1f}x realtime)")

        return out_path
