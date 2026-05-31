"""
Enhanced Emotion Detection v2 for Hindi Podcasts

Provides:
- Same keyword-based detection as v1 (backwards compatible)
- Emotion-to-style mapping for Microsoft express-as styles
- Inline mood annotation parsing
- Sentence-level emotion scoring
"""
import re
from typing import Dict, List, Optional, Tuple
from enum import Enum

# ── Emotion types ─────────────────────────────────────────────────
class EmotionType(str, Enum):
    EXCITEMENT = 'excitement'
    QUESTION = 'question'
    EMPHASIS = 'emphasis'
    SERIOUS = 'serious'
    TRANSITION = 'transition'
    AFFIRMATION = 'affirmation'
    QUIZ = 'quiz'
    NEUTRAL = 'neutral'
    SAD = 'sad'
    ANGRY = 'angry'
    HOPEFUL = 'hopeful'
    EMPATHETIC = 'empathetic'


class VoiceStyle(str, Enum):
    """Microsoft mstts:express-as style names."""
    CHEERFUL = 'cheerful'
    SAD = 'sad'
    ANGRY = 'angry'
    EXCITED = 'excited'
    FRIENDLY = 'friendly'
    HOPEFUL = 'hopeful'
    SERIOUS = 'serious'
    EMPATHETIC = 'empathetic'
    NEWSCAST = 'newscast'
    NARRATION_RELAXED = 'narration-relaxed'
    NEUTRAL = 'neutral'


# ── Emotion → Express-As Style Mapping ────────────────────────────
EMOTION_TO_STYLE = {
    EmotionType.EXCITEMENT: VoiceStyle.EXCITED,
    EmotionType.QUESTION: VoiceStyle.FRIENDLY,
    EmotionType.EMPHASIS: VoiceStyle.SERIOUS,
    EmotionType.SERIOUS: VoiceStyle.SERIOUS,
    EmotionType.TRANSITION: VoiceStyle.FRIENDLY,
    EmotionType.AFFIRMATION: VoiceStyle.FRIENDLY,
    EmotionType.QUIZ: VoiceStyle.CHEERFUL,
    EmotionType.NEUTRAL: VoiceStyle.NEUTRAL,
    EmotionType.SAD: VoiceStyle.SAD,
    EmotionType.ANGRY: VoiceStyle.ANGRY,
    EmotionType.HOPEFUL: VoiceStyle.HOPEFUL,
    EmotionType.EMPATHETIC: VoiceStyle.EMPATHETIC,
}

# ── Inline style annotations ──────────────────────────────────────
STYLE_ALIASES = {
    'excited': VoiceStyle.EXCITED,
    'excitement': VoiceStyle.EXCITED,
    'happy': VoiceStyle.CHEERFUL,
    'cheerful': VoiceStyle.CHEERFUL,
    'sad': VoiceStyle.SAD,
    'angry': VoiceStyle.ANGRY,
    'angry': VoiceStyle.ANGRY,
    'serious': VoiceStyle.SERIOUS,
    'important': VoiceStyle.SERIOUS,
    'emphatic': VoiceStyle.SERIOUS,
    'friendly': VoiceStyle.FRIENDLY,
    'warm': VoiceStyle.FRIENDLY,
    'hopeful': VoiceStyle.HOPEFUL,
    'optimistic': VoiceStyle.HOPEFUL,
    'empathetic': VoiceStyle.EMPATHETIC,
    'caring': VoiceStyle.EMPATHETIC,
    'tender': VoiceStyle.EMPATHETIC,
    'neutral': VoiceStyle.NEUTRAL,
    'normal': VoiceStyle.NEUTRAL,
    'newscast': VoiceStyle.NEWSCAST,
    'news': VoiceStyle.NEWSCAST,
    'relaxed': VoiceStyle.NARRATION_RELAXED,
    'narration': VoiceStyle.NARRATION_RELAXED,
}

# ── Keyword patterns (from v1, enhanced) ──────────────────────────
EXCITED_PATTERNS = [
    r'\bवाओ\b', r'\bवाह\b', r'\bग्रेट\b', r'\bब्रिलियंट\b',
    r'\bपरफेक्ट\b', r'\bएक्सैक्टली\b', r'\bएग्जैक्टली\b',
    r'\bहिस्टोरिक\b', r'\bमैसिव\b', r'\bह्यूज\b',
    r'\bक्या बात\b', r'\bबहुत ही\b', r'\bबेहद\b',
    r'\bज़बरदस्त\b', r'\bशानदार\b', r'\bगज़ब\b',
    r'\bसक्सेसफुली\b', r'\bलैंडमार्क\b',
    r'\bअब्सोलुटली\b', r'\bबिल्कुल सही\b',
    r'\bवाओ\b', r'\bदैट्स\b.*\bबिग\b',
    r'\bमजेदार\b', r'\bकमाल\b',
]

QUESTION_PATTERNS = [
    r'\?', r'\bक्या\b', r'\bक्यों\b', r'\bकैसे\b', r'\bकहाँ\b',
    r'\bकब\b', r'\bकौन\b', r'\bकितना\b', r'\bकितने\b',
    r'\bहै ना\b', r'\bराइट\?\b', r'\bहै न\b',
    r'\bसमझे\b', r'\bसमझिए\b', r'\bपता है\b',
    r'\bकंफ्यूजन\b', r'\bका मतलब\b',
]

EMPHASIS_PATTERNS = [
    r'\bसबसे बड़ा\b', r'\bसबसे ज़रूरी\b', r'\bमेन\b',
    r'\bक्रूशियल\b', r'\bइंपॉर्टेंट\b', r'\bजरूरी\b',
    r'\bध्यान दें\b', r'\bयाद रखें\b', r'\bगौर करें\b',
    r'\bबिल्कुल\b', r'\bबेसिक\b', r'\bक्लियर\b',
    r'\bमिनिमम\b', r'\bकम से कम\b',
    r'\bगारंटी\b', r'\bसॉलिड\b', r'\bस्ट्रांग\b',
    r'\bज़ीरो\b', r'\bएकदम\b',
    r'\bलैंडमार्क\b', r'\bरिफॉर्म\b',
]

SERIOUS_PATTERNS = [
    r'\bदेखिए\b', r'\bअसल में\b',
    r'\bएक्चुअली\b', r'\bटेक्निकल\b',
    r'\bकॉम्प्लेक्स\b', r'\bएनालिसिस\b', r'\bडीप डाइव\b',
    r'\bगहराई\b', r'\bगहन\b', r'\bडिटेल्ड\b',
    r'\bलॉजिक\b', r'\bफंडा\b', r'\bकॉन्सेप्ट\b',
    r'\bफैक्ट\b', r'\bडाटा\b', r'\bएनालिसिस\b',
    r'\bरिवीजन\b', r'\bमैकेनिज्म\b',
]

TRANSITION_PATTERNS = [
    r'\bचलिए\b', r'\bतो\b', r'\bअब\b', r'\bवैसे\b',
    r'\bहालांकि\b', r'\bलेकिन\b', r'\bपर\b',
    r'\bहाँ\b', r'\bहां\b', r'\bजी हां\b',
    r'\bवेलकम\b', r'\bआपका स्वागत\b',
    r'\bइसके अलावा\b', r'\bसाथ ही\b',
]

AFFIRMATION_PATTERNS = [
    r'^(हाँ|हां|हम|हूं|जी|हम्म|अच्छा)$',
    r'\bमेक सेंस\b', r'\bमेक्स सेंस\b',
    r'\bटोटल सेंस\b',
]

QUIZ_PATTERNS = [
    r'\bसवाल\b', r'\bक्विज\b', r'\bटेस्ट\b',
    r'\bकितना याद\b', r'\bसेल्फ असेसमेंट\b',
    r'\bरैपिड फायर\b', r'\bमेंटल चेक\b',
    r'\bबताइए\b', r'\bजवाब\b', r'\bउत्तर\b',
]

SAD_PATTERNS = [
    r'\bदुख\b', r'\bअफसोस\b', r'\bबुरा\b',
    r'\bनुकसान\b', r'\bदुर्घटना\b', r'\bमौत\b',
    r'\bहार\b', r'\bविफल\b',
]

ANGRY_PATTERNS = [
    r'\bगुस्सा\b', r'\bनाराज\b', r'\bफ्रस्ट्रेशन\b',
    r'\bअन्याय\b', r'\bभ्रष्टाचार\b',
]

HOPEFUL_PATTERNS = [
    r'\bउम्मीद\b', r'\bभरोसा\b', r'\bविश्वास\b',
    r'\bसुधार\b', r'\bबेहतर\b', r'\bबदलाव\b',
    r'\bचमत्कार\b', r'\bभविष्य\b',
]


def detect_emotion_v2(text: str) -> Dict[str, float]:
    """
    Enhanced emotion detection with additional emotion types.
    Returns scores for all emotion types.
    """
    scores = {
        'excitement': 0.0,
        'question': 0.0,
        'emphasis': 0.0,
        'serious': 0.0,
        'transition': 0.0,
        'affirmation': 0.0,
        'quiz': 0.0,
        'sad': 0.0,
        'angry': 0.0,
        'hopeful': 0.0,
        'neutral': 1.0,  # Default baseline
    }

    words = len(text.split())
    if words == 0:
        return scores

    lower = text.lower()

    # Check each pattern category
    for pattern in EXCITED_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['excitement'] += 1.0
            scores['neutral'] -= 0.2

    for pattern in QUESTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['question'] += 1.0
            scores['neutral'] -= 0.2

    for pattern in EMPHASIS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['emphasis'] += 1.0
            scores['neutral'] -= 0.2

    for pattern in SERIOUS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['serious'] += 1.0
            scores['neutral'] -= 0.15

    for pattern in TRANSITION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['transition'] += 0.5
            scores['neutral'] -= 0.1

    for pattern in AFFIRMATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['affirmation'] += 1.0
            scores['neutral'] -= 0.2

    for pattern in QUIZ_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['quiz'] += 1.5
            scores['neutral'] -= 0.3

    for pattern in SAD_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['sad'] += 1.0
            scores['neutral'] -= 0.3

    for pattern in ANGRY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['angry'] += 1.0
            scores['neutral'] -= 0.3

    for pattern in HOPEFUL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['hopeful'] += 1.0
            scores['neutral'] -= 0.2

    # Cap at 3.0
    for key in scores:
        scores[key] = max(0.0, min(scores[key], 3.0))

    # Short texts stay neutral-ish
    if words <= 3:
        for key in scores:
            if key != 'neutral':
                scores[key] = min(scores[key], 1.0)
        scores['neutral'] = max(scores['neutral'], 0.7)

    return scores


def get_voice_style(emotion_scores: Dict[str, float]) -> Tuple[Optional[str], float]:
    """
    Map emotion scores to Microsoft express-as style.
    Returns (style_name, confidence) where confidence is 0-1.
    """
    if not emotion_scores:
        return None, 0.0

    # Find dominant emotion
    dominant = max(emotion_scores, key=emotion_scores.get)
    score = emotion_scores[dominant]

    # Only use express-as if score is significant (≥1.5) and not neutral
    if score < 1.5 or dominant == 'neutral':
        return None, 0.0

    style = EMOTION_TO_STYLE.get(EmotionType(dominant))
    if style:
        return style, min(score / 3.0, 1.0)

    return None, 0.0


def get_native_params(emotion_scores: Dict[str, float], role: str, text: str) -> Dict[str, str]:
    """
    Convert emotion scores to edge-tts native rate/pitch/volume params.
    Used as fallback when express-as is not available.
    Backwards-compatible with v1's get_ssml_params.
    """
    params = {
        'pitch': '+0Hz',
        'rate': '+0%',
        'volume': '+0%',
    }

    # ── Excitement → higher pitch, faster, louder ──
    if emotion_scores['excitement'] >= 2:
        params['pitch'] = '+60Hz'
        params['rate'] = '+18%'
        params['volume'] = '+50%'
    elif emotion_scores['excitement'] >= 1:
        params['pitch'] = '+30Hz'
        params['rate'] = '+10%'
        params['volume'] = '+25%'

    # ── Question → rising pitch ──
    if emotion_scores['question'] >= 1:
        if params['pitch'] == '+0Hz':
            params['pitch'] = '+40Hz'
        params['rate'] = '+5%' if params['rate'] == '+0%' else '+8%'

    # ── Emphasis → slower, louder ──
    if emotion_scores['emphasis'] >= 2:
        params['pitch'] = '+20Hz'
        params['rate'] = '-8%'
        params['volume'] = '+40%'
    elif emotion_scores['emphasis'] >= 1:
        if params['rate'] == '+0%':
            params['rate'] = '-5%'
        params['volume'] = '+25%'

    # ── Serious → slower, lower pitch ──
    if emotion_scores['serious'] >= 2:
        params['pitch'] = '-30Hz'
        params['rate'] = '-12%'
        params['volume'] = '+12%'
    elif emotion_scores['serious'] >= 1:
        if params['pitch'] == '+0Hz':
            params['pitch'] = '-15Hz'
        params['rate'] = '-8%'

    # ── Quiz → energetic, faster ──
    if emotion_scores['quiz'] >= 1:
        params['pitch'] = '+40Hz' if params['pitch'] == '+0Hz' else '+45Hz'
        params['rate'] = '+15%'

    # ── Affirmation → gentle ──
    if emotion_scores['affirmation'] >= 1:
        if params['pitch'] == '+0Hz':
            params['pitch'] = '-5Hz'
        params['volume'] = '+12%'

    # ── Sad → slower, lower, quieter ──
    if emotion_scores['sad'] >= 1:
        params['pitch'] = '-40Hz'
        params['rate'] = '-15%'
        params['volume'] = '-15%'

    # ── Angry → faster, louder, lower pitch ──
    if emotion_scores['angry'] >= 1:
        params['pitch'] = '-20Hz'
        params['rate'] = '+15%'
        params['volume'] = '+50%'

    # ── Hopeful → warm, moderate pitch ──
    if emotion_scores['hopeful'] >= 1:
        params['pitch'] = '+15Hz'
        params['volume'] = '+15%'

    # Override: very short texts stay natural
    words = len(text.split())
    if words <= 3 and emotion_scores['excitement'] < 2:
        if params['rate'] not in ('+0%', '+5%'):
            params['rate'] = '+3%'

    return params


def get_express_as_style_from_annotation(style_str: Optional[str]) -> Optional[str]:
    """Convert inline style annotation to Microsoft express-as style name."""
    if not style_str:
        return None
    style_lower = style_str.strip().lower()
    mapped = STYLE_ALIASES.get(style_lower)
    return mapped.value if mapped else None
