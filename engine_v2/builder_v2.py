"""
Podcast Builder v2 - Orchestration Layer

Assembles the full podcast:
1. Parse script with emotion annotations
2. Merge short turns and detect duplicates
3. Synthesize each turn with appropriate emotion/style
4. Crossfade between speakers
5. Master audio (EQ, compressor, limiting)
6. Optionally mix background music with ducking
7. Export as 256kbps AAC (matching reference quality)
"""
import asyncio
import os
import re
import subprocess
import sys
import time
from typing import List, Optional, Tuple, Dict

from pydub import AudioSegment
from pydub.silence import detect_silence

from .script_v2 import (
    parse_script_v2, merge_short_turns, ScriptTurn,
    apply_default_styles, detect_duplicates, split_turns_by_sentence,
)
from .tts_v2 import EmotionalTTSv2, silence, MODES
from .audio_v2 import (
    master_podcast_v2, mix_background_music, overlap_crossfade,
    analyze_loudness, _find_ffmpeg,
)
from .emotion_v2 import detect_emotion_v2


class PodcastBuilderV2:
    """
    Main podcast assembly orchestrator.

    Usage:
        builder = PodcastBuilderV2(mode='4', output_dir='podcast_output')
        result = await builder.build('transcribe.txt')
    """

    def __init__(self, mode: str = '4', output_dir: str = 'podcast_output',
                 cache_voices: bool = True,
                 use_express_as: bool = True,
                 background_music: Optional[str] = None,
                 music_volume: float = -20.0,
                 high_quality: bool = True,
                 export_bitrate: str = '256k',
                 split_sentences: bool = True):
        """
        Args:
            mode: Speed preset (1=fast, 2=slow, 3=normal, 4=expressive)
            output_dir: Output directory
            cache_voices: Cache identical phrases
            use_express_as: Try Microsoft express-as SSML styles
            background_music: Path to background music file (or None)
            music_volume: Background music volume in dB (negative = quieter)
            high_quality: Use enhanced mastering chain
            export_bitrate: Export bitrate (e.g. '256k', '192k')
            split_sentences: Split each turn by sentence for finer emotion
        """
        self.mode = mode
        self.output_dir = output_dir
        self.use_express_as = use_express_as
        self.high_quality = high_quality
        self.export_bitrate = export_bitrate
        self.split_sentences = split_sentences

        self.tts = EmotionalTTSv2(
            mode=mode,
            output_dir=os.path.join(output_dir, '_temp'),
            use_express_as=use_express_as,
            cache_voices=cache_voices,
        )

        self.background_music = background_music
        self.music_volume = music_volume

        self.stats = {
            'total_turns': 0,
            'synthesized': 0,
            'express_as_used': 0,
            'native_params_used': 0,
            'bare_used': 0,
            'gtts_used': 0,
            'failed': 0,
            'duplicate_skipped': 0,
            'merged': 0,
            'duration_s': 0,
        }

    async def build(self, script_path: str,
                    output_name: Optional[str] = None) -> Dict:
        """
        Full build pipeline: parse → synthesize → assemble → master → export.

        Args:
            script_path: Path to script file (.txt)
            output_name: Output filename (without extension).

        Returns:
            Dict with result info.
        """
        start_time = time.time()

        if not output_name:
            script_base = os.path.splitext(os.path.basename(script_path))[0]
            bit = "HQ" if self.high_quality else "STD"
            mus = "_wmusic" if self.background_music else ""
            output_name = f"{time.strftime('%d-%m-%y')}_{script_base}_{bit}{mus}"

        output_path = os.path.join(self.output_dir, f"{output_name}.m4a")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        print(f"📖 Loading script: {script_path}")

        # ═══════════ STEP 1: Parse ═══════════
        raw_text = self._load_script(script_path)
        turns = parse_script_v2(raw_text)
        print(f"   Parsed {len(turns)} turns")

        # ═══════════ STEP 2: Optimise ════════
        # Detect duplicates
        dup_indices = detect_duplicates(turns)
        print(f"   Found {len(dup_indices)} duplicate turns")

        # Merge short consecutive same-speaker turns
        merged = merge_short_turns(turns)
        merged_count = len(turns) - len(merged)
        print(f"   Merged ~{merged_count} short turns → {len(merged)} turns")

        # Apply default emotion styles (if no explicit style)
        styled = apply_default_styles(merged)

        # Optionally split by sentence
        if self.split_sentences:
            styled = split_turns_by_sentence(styled)
            print(f"   Split into {len(styled)} sentence-level turns")

        # Remove duplicates
        dup_indices_final = detect_duplicates(styled)
        filtered = []
        for i, turn in enumerate(styled):
            if i not in dup_indices_final:
                filtered.append(turn)
            else:
                self.stats['duplicate_skipped'] += 1
        turns = filtered

        self.stats['total_turns'] = len(turns)
        print(f"   Total to synthesize: {len(turns)} turns")
        print()

        # ═══════════ STEP 3: Synthesize ══════
        print(f"🎤 Synthesizing {len(turns)} turns...")
        clips: List[Tuple[Optional[AudioSegment], str, str]] = []

        batch_size = 8
        for batch_start in range(0, len(turns), batch_size):
            batch = turns[batch_start:batch_start + batch_size]
            batch_tasks = []

            for turn in batch:
                batch_tasks.append(self._synthesize_turn(turn))

            results = await asyncio.gather(*batch_tasks)

            for (clip, info, role), turn in zip(results, batch):
                if clip:
                    clips.append((clip, role, info.get('method', '?')))
                else:
                    print(f"   ⚠️  Failed turn {turn.turn_index}: '{turn.text[:40]}...'")
                    clips.append((None, turn.role, 'failed'))
                    self.stats['failed'] += 1

            # Progress
            done = min(batch_start + batch_size, len(turns))
            print(f"   Progress: {done}/{len(turns)} turns ({done * 100 // len(turns)}%)")

        print()

        # ═══════════ STEP 4: Assemble ════════
        print("🔊 Assembling podcast...")
        podcast = AudioSegment.empty()
        current_role = None

        for idx, (clip, role, method) in enumerate(clips):
            if clip is None:
                # Add silence for failed turns
                podcast += silence(2000)
                continue

            # Count stats
            if method == 'express-as':
                self.stats['express_as_used'] += 1
            elif method == 'native':
                self.stats['native_params_used'] += 1
            elif method == 'bare':
                self.stats['bare_used'] += 1
            elif method == 'gtts':
                self.stats['gtts_used'] += 1

            self.stats['synthesized'] += 1

            # Role-based crossfade
            if current_role and role != current_role:
                # Speaker change → use overlap crossfade
                seg_gap = 300  # ms natural pause on speaker change
                podcast += silence(seg_gap)
                podcast += clip
            elif current_role:
                # Same speaker → shorter gap
                podcast += silence(200)
                podcast += clip
            else:
                # First clip
                podcast = clip

            current_role = role

        podcasts_dur = len(podcast) / 1000 / 60
        print(f"   Raw duration: {podcasts_dur:.1f} min")
        print()

        # ═══════════ STEP 5: Master ══════════
        if self.high_quality:
            print("🎛️  Mastering (broadcast chain)...")
            podcast = master_podcast_v2(podcast, target_loudness=-16.0)
        else:
            print("🎛️  Normalizing...")
            podcast = podcast.normalize()

        # ═══════════ STEP 5b: Background Music ══════════
        if self.background_music and os.path.exists(self.background_music):
            print(f"🎵 Mixing background music: {self.background_music}")
            podcast = mix_background_music(
                podcast,
                music_path=self.background_music,
                volume_db=self.music_volume
            )
        elif self.background_music:
            print(f"⚠️  Background music file not found: {self.background_music}")
            print(f"   Generating ambient drone instead...")
            podcast = mix_background_music(podcast, music_path=None)

        # ═══════════ STEP 6: Export ═════════════════════
        print(f"💾 Exporting to {output_path}...")

        # Determine export format
        if output_path.endswith('.m4a'):
            ffmpeg = _find_ffmpeg()
            if ffmpeg:
                # Export as WAV first, then encode with ffmpeg
                temp_wav = output_path.replace('.m4a', '_temp.wav')
                try:
                    podcast.export(temp_wav, format='wav')
                    subprocess.run(
                        [ffmpeg, '-y', '-i', temp_wav,
                         '-c:a', 'aac', '-b:a', self.export_bitrate,
                         '-movflags', '+faststart',
                         output_path],
                        capture_output=True, timeout=120
                    )
                    if os.path.exists(temp_wav):
                        os.remove(temp_wav)
                except Exception as e:
                    print(f"   FFmpeg export failed: {e}, trying direct...")
                    podcast.export(output_path, format='mp4')
            else:
                podcast.export(output_path, format='mp4')
        else:
            podcast.export(output_path, format='mp3',
                          parameters=["-q:a", "0", "-b:a", self.export_bitrate])

        elapsed = time.time() - start_time
        self.stats['duration_s'] = int(elapsed)

        # Verify output
        output_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0

        # ═══════════ Report ═══════════
        print()
        print("=" * 55)
        print(f"📊 BUILD REPORT — {output_name}")
        print("=" * 55)
        print(f"  Turns synthesized: {self.stats['synthesized']}/{self.stats['total_turns']}")
        print(f"    - express-as SSML:  {self.stats['express_as_used']}")
        print(f"    - native params:    {self.stats['native_params_used']}")
        print(f"    - bare edge-tts:    {self.stats['bare_used']}")
        print(f"    - gTTS fallback:    {self.stats['gtts_used']}")
        print(f"    - failed:           {self.stats['failed']}")
        print(f"  Duplicates skipped:  {self.stats['duplicate_skipped']}")
        print(f"  Podcast duration:    {podcasts_dur:.1f} min")
        print(f"  Output size:         {output_size / 1024 / 1024:.1f} MB")
        print(f"  Export bitrate:      {self.export_bitrate}")
        print(f"  Build time:          {elapsed:.1f}s")
        print("=" * 55)

        # Recommend next step
        if self.stats['express_as_used'] == 0 and self.use_express_as:
            print()
            print("💡 Note: express-as styles were NOT used. This means")
            print("   Microsoft's emotion styles may not be supported by")
            print("   Hindi voices, or SSML caused issues. Audio still")
            print("   uses native rate/pitch/volume emotion parameters.")
            print()
            print("   To test express-as: python podcast_agent_v2.py --test-express")

        elif self.stats['express_as_used'] > 0:
            print()
            print(f"🎭 express-as styles worked! Used on {self.stats['express_as_used']} turns.")

        return {
            'status': 'completed',
            'output_path': output_path,
            'duration_min': podcasts_dur,
            'size_mb': output_size / 1024 / 1024,
            'stats': self.stats,
        }

    def _load_script(self, path: str) -> str:
        """Load script file content."""
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    async def _synthesize_turn(self, turn: ScriptTurn) -> Tuple[Optional[AudioSegment], Dict, str]:
        """Synthesize a single turn with emotion-aware TTS."""
        clip, info = await self.tts.synthesize_turn(
            text=turn.text,
            role=turn.role,
            style=turn.style,
        )
        return clip, info, turn.role
