"""
TTS Engine v2 for Hindi Emotion-Aware Podcasts

Key improvements over v1:
1. Tries mstts:express-as SSML for emotional lines (WITHOUT prosody to avoid elongation)
2. Falls back to native edge-tts rate/pitch/volume params
3. Falls back to gTTS
4. Voice caching to avoid re-generating identical phrases
5. OS-detect for Windows/Linux timeout handling
6. Rate limiting to avoid Microsoft throttling
"""
import asyncio
import os
import platform
import re
import subprocess
import sys
import uuid
import hashlib
from typing import Dict, Optional, Tuple, List

from pydub import AudioSegment

from .emotion_v2 import (
    detect_emotion_v2, get_voice_style, get_native_params,
    get_express_as_style_from_annotation,
)

# ── Voice constants ───────────────────────────────────────────────
FEMALE_VOICE = "hi-IN-SwaraNeural"
MALE_VOICE = "hi-IN-MadhurNeural"

# All express-as styles supported by Microsoft TTS
EXPRESS_AS_STYLES = [
    'cheerful', 'sad', 'angry', 'excited', 'friendly',
    'hopeful', 'serious', 'empathetic', 'newscast',
    'narration-relaxed', 'neutral',
]

# Speed presets (backwards-compatible with v1)
MODES = {
    "1": {"label": "Revision (थोड़ा तेज़)", "female": "+15%", "male": "+5%"},
    "2": {"label": "Learn    (थोड़ा धीमा)", "female": "-10%", "male": "-15%"},
    "3": {"label": "Natural  (सामान्य)",      "female": "+0%",  "male": "+0%"},
    "4": {"label": "Expressive (भावनात्मक)",   "female": "+5%",  "male": "+0%"},
}


def _compat_volume(db_val: str) -> str:
    """Convert SSML dB volume to edge-tts percentage format."""
    if db_val.endswith('dB'):
        try:
            db = float(db_val.replace('dB', ''))
            pct = round(db * 12.5)
            return f"{'+' if pct >= 0 else ''}{pct}%"
        except ValueError:
            pass
    return db_val


def silence(ms: int) -> AudioSegment:
    return AudioSegment.silent(duration=ms)


class EmotionalTTSv2:
    """
    Enhanced TTS Engine with:
    - express-as style SSML support
    - Voice caching
    - Multi-fallback chain
    - OS-detect timeout handling
    - Rate limiting
    """

    # Rate-limit state (class-level to span synthesize calls)
    _call_count = 0
    _last_call_time = 0.0
    _BATCH_SIZE = 12
    _BATCH_DELAY = 2.0
    _RESET_DELAY = 8.0

    # Voice cache (shared across instances)
    _voice_cache: Dict[str, str] = {}

    def __init__(self, mode='3', output_dir='podcast_output',
                 use_express_as=True, cache_voices=True):
        self.mode = mode
        self.rate_config = MODES.get(mode, MODES["3"])
        self.output_dir = output_dir
        self.use_express_as = use_express_as
        self.cache_voices = cache_voices
        os.makedirs(output_dir, exist_ok=True)

    def get_voice(self, role: str) -> str:
        return FEMALE_VOICE if role == "female" else MALE_VOICE

    def get_base_rate(self, role: str) -> str:
        return self.rate_config["female"] if role == "female" else self.rate_config["male"]

    def _cache_key(self, text: str, voice: str, style: Optional[str],
                   rate: str, pitch: str, volume: str) -> str:
        """Generate a unique cache key for a TTS request."""
        raw = f"{text}|{voice}|{style}|{rate}|{pitch}|{volume}"
        return hashlib.md5(raw.encode()).hexdigest()

    async def _rate_limit_delay(self):
        """Enforce inter-call delay + batch reset to avoid Microsoft throttling."""
        EmotionalTTSv2._call_count += 1
        now = asyncio.get_event_loop().time()

        if EmotionalTTSv2._last_call_time > 0:
            elapsed = now - EmotionalTTSv2._last_call_time
            needed = EmotionalTTSv2._BATCH_DELAY - elapsed
            if needed > 0:
                await asyncio.sleep(needed)

        if EmotionalTTSv2._call_count % EmotionalTTSv2._BATCH_SIZE == 0:
            await asyncio.sleep(EmotionalTTSv2._RESET_DELAY)

        EmotionalTTSv2._last_call_time = asyncio.get_event_loop().time()
        return EmotionalTTSv2._call_count

    # ── SSML generation with express-as ───────────────────────────
    def _build_express_ssml(self, text: str, voice: str, style: str) -> str:
        """
        Build SSML with mstts:express-as style.
        NO prosody tags — only express-as style to avoid elongation.
        """
        text_clean = (text
                      .replace('&', '&amp;')
                      .replace('<', '&lt;')
                      .replace('>', '&gt;'))

        return f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
 xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="hi-IN">
 <voice name="{voice}">
  <mstts:express-as style="{style}">
   {text_clean}
  </mstts:express-as>
 </voice>
</speak>'''

    # ── Edge-tts subprocess runners ──────────────────────────────
    async def _run_edge_tts(self, text: str, voice: str, out_path: str,
                            timeout: int = 20,
                            rate: str = '+0%', pitch: str = '+0Hz',
                            volume: str = '+0%',
                            use_ssml: bool = False,
                            style: Optional[str] = None) -> bool:
        """Run edge-tts CLI with either native params or SSML input."""
        OS = platform.system()
        loop = asyncio.get_event_loop()

        if use_ssml and style:
            # ── SSML mode with express-as ──
            ssml = self._build_express_ssml(text, voice, style)
            ssml_path = out_path.replace('.mp3', '.xml')
            with open(ssml_path, 'w', encoding='utf-8') as f:
                f.write(ssml)

            cmd = [sys.executable, '-m', 'edge_tts',
                   '--write-media', out_path,
                   '--custom-ssml', ssml_path]
        else:
            # ── Native param mode ──
            cmd = [sys.executable, '-m', 'edge_tts',
                   '--text', text,
                   '--voice', voice,
                   '--write-media', out_path]
            if rate != '+0%':
                cmd.extend(['--rate', rate])
            if pitch != '+0Hz':
                cmd.extend(['--pitch', pitch])
            if volume != '+0%':
                cmd.extend(['--volume', volume])

        try:
            if OS == 'Windows':
                rc = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        cmd, timeout=timeout,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    ).returncode
                )
            else:
                rc = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        cmd, timeout=timeout,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    ).returncode
                )

            # Clean up SSML temp file
            if use_ssml and style:
                try:
                    os.remove(ssml_path)
                except:
                    pass

            return rc == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 500

        except (subprocess.TimeoutExpired, Exception):
            if use_ssml and style:
                try:
                    os.remove(ssml_path)
                except:
                    pass
            return False

    async def _synthesize_gtts(self, text: str, voice: str, out_path: str) -> bool:
        """gTTS fallback."""
        try:
            from gtts import gTTS
        except ImportError:
            return False

        lang = 'hi' if 'hi-' in voice else 'en'
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: gTTS(text=text, lang=lang, slow=False).save(out_path)
            )
            return os.path.exists(out_path) and os.path.getsize(out_path) > 500
        except Exception:
            return False

    # ── Main synthesize method ────────────────────────────────────
    async def synthesize(self, text: str, role: str,
                         style: Optional[str] = None,
                         use_express: bool = True) -> Tuple[Optional[str], Dict]:
        """
        Synthesize text with the best available method.

        Strategy (tried in order):
        1. edge-tts with mstts:express-as SSML (if style provided AND use_express=True)
        2. edge-tts with native rate/pitch/volume params
        3. edge-tts bare (no params)
        4. gTTS fallback

        Returns (path_to_mp3, info_dict) or (None, info_dict) on failure.
        """
        voice = self.get_voice(role)
        base_rate = self.get_base_rate(role)

        # Detect emotion for param fallback
        emotion_scores = detect_emotion_v2(text)
        native_params = get_native_params(emotion_scores, role, text)

        # Combine base rate with emotion rate
        combined_rate = native_params['rate']
        if base_rate and base_rate != '+0%':
            try:
                emo_pct = int(combined_rate.replace('%', '').replace('+', '').replace('-', ''))
                base_pct = int(base_rate.replace('%', '').replace('+', '').replace('-', ''))
                emo_sign = -1 if '-' in native_params['rate'] and native_params['rate'] != '+0%' else 1
                base_sign = -1 if '-' in base_rate else 1
                combined = emo_sign * emo_pct + base_sign * base_pct
                sign = '+' if combined >= 0 else ''
                combined_rate = f"{sign}{combined}%"
            except ValueError:
                pass

        # Resolve style
        effective_style = None
        if style:
            effective_style = get_express_as_style_from_annotation(style)
        if not effective_style and use_express:
            auto_style, confidence = get_voice_style(emotion_scores)
            if auto_style and confidence >= 0.5:
                effective_style = auto_style

        # Check cache
        ckey = self._cache_key(text, voice, effective_style,
                               combined_rate, native_params['pitch'],
                               _compat_volume(native_params['volume']))
        if self.cache_voices and ckey in EmotionalTTSv2._voice_cache:
            cached = EmotionalTTSv2._voice_cache[ckey]
            if os.path.exists(cached):
                return cached, {'method': 'cache', 'style': effective_style}

        # Generate unique output path
        filename = f"_{uuid.uuid4().hex[:8]}.mp3"
        out_path = os.path.join(self.output_dir, filename)

        # Attempt 1: edge-tts with express-as SSML
        if effective_style and use_express:
            await self._rate_limit_delay()
            success = await self._run_edge_tts(
                text, voice, out_path, timeout=20,
                use_ssml=True, style=effective_style
            )
            if success:
                if self.cache_voices:
                    EmotionalTTSv2._voice_cache[ckey] = out_path
                return out_path, {'method': 'express-as', 'style': effective_style}

        # Attempt 2: edge-tts with native params
        await self._rate_limit_delay()
        success = await self._run_edge_tts(
            text, voice, out_path, timeout=15,
            rate=combined_rate,
            pitch=native_params['pitch'],
            volume=_compat_volume(native_params['volume']),
            use_ssml=False
        )
        if success:
            if self.cache_voices:
                EmotionalTTSv2._voice_cache[ckey] = out_path
            return out_path, {'method': 'native', 'params': native_params}

        # Attempt 3: edge-tts bare
        bare_path = out_path.replace('.mp3', '_bare.mp3')
        await self._rate_limit_delay()
        success = await self._run_edge_tts(
            text, voice, bare_path, timeout=20,
            use_ssml=False
        )
        if success:
            if self.cache_voices:
                EmotionalTTSv2._voice_cache[ckey] = bare_path
            return bare_path, {'method': 'bare'}

        # Attempt 4: gTTS
        gtts_path = out_path.replace('.mp3', '_gtts.mp3')
        await self._rate_limit_delay()
        success = await self._synthesize_gtts(text, voice, gtts_path)
        if success:
            if self.cache_voices:
                EmotionalTTSv2._voice_cache[ckey] = gtts_path
            return gtts_path, {'method': 'gtts'}

        return None, {'method': 'failed'}

    async def synthesize_turn(self, text: str, role: str,
                              style: Optional[str] = None) -> Tuple[Optional[AudioSegment], Dict]:
        """
        Synthesize a full turn, with per-sentence fallback.
        Returns (AudioSegment, info) or (None, info).
        """
        result_path, info = await self.synthesize(text, role, style)

        if result_path:
            try:
                clip = AudioSegment.from_mp3(result_path)
                # Clean up temp file
                try:
                    os.remove(result_path)
                except:
                    pass
                return clip, info
            except Exception:
                pass

        # Per-sentence fallback
        sents = [s.strip() for s in re.split(r'(?<=[।.!?])\s*', text) if s.strip()]
        if len(sents) <= 1:
            return None, info

        clips = []
        for sent in sents:
            p, i = await self.synthesize(sent, role, None, use_express=False)
            if p:
                try:
                    clip = AudioSegment.from_mp3(p)
                    clips.append(clip)
                    try:
                        os.remove(p)
                    except:
                        pass
                except:
                    pass

        if not clips:
            return None, info

        combined = AudioSegment.empty()
        for i, clip in enumerate(clips):
            if i > 0:
                combined += silence(200)
            combined += clip

        return combined, {'method': 'multi-sentence', 'count': len(clips)}
