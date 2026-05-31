"""
Aakashvani - Emotional Hindi Podcast Generator Engine
"""
from .podcast_builder import PodcastBuilder, parse_script, MODES
from .tts_engine import EmotionalTTSEngine, FEMALE_VOICE, MALE_VOICE
from .emotion_ssml import detect_emotion, get_ssml_params, wrap_in_ssml
from .audio_effects import master_podcast, broadcast_compressor, parametric_eq

__all__ = [
    'PodcastBuilder', 'parse_script', 'MODES',
    'EmotionalTTSEngine', 'FEMALE_VOICE', 'MALE_VOICE',
    'detect_emotion', 'get_ssml_params', 'wrap_in_ssml',
    'master_podcast', 'broadcast_compressor', 'parametric_eq',
]
