"""
Aakashvani v2 - Enhanced Emotion-Aware Hindi Podcast Generator
Engine package with express-as styles, background music, and improved mastering
"""
from .tts_v2 import EmotionalTTSv2, FEMALE_VOICE, MALE_VOICE, EXPRESS_AS_STYLES
from .emotion_v2 import (
    detect_emotion_v2, get_voice_style, get_native_params,
    EmotionType, VoiceStyle, EMOTION_TO_STYLE
)
from .audio_v2 import (
    _find_ffmpeg, master_podcast_v2, mix_background_music, audio_duck,
    overlap_crossfade, MatchLoudness, analyze_loudness
)
from .builder_v2 import PodcastBuilderV2
from .script_v2 import parse_script_v2, ScriptTurn, merge_short_turns

__all__ = [
    'EmotionalTTSv2', 'FEMALE_VOICE', 'MALE_VOICE', 'EXPRESS_AS_STYLES',
    'detect_emotion_v2', 'get_voice_style', 'get_native_params',
    'EmotionType', 'VoiceStyle', 'EMOTION_TO_STYLE',
    '_find_ffmpeg', 'master_podcast_v2', 'mix_background_music', 'audio_duck',
    'overlap_crossfade', 'MatchLoudness', 'analyze_loudness',
    'PodcastBuilderV2',
    'parse_script_v2', 'ScriptTurn', 'merge_short_turns',
]
