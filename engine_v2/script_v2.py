"""
Enhanced Script Parser for Hindi Podcasts v2

Supports:
- Standard Male:/Female: labels (compatible with existing format)
- Inline mood annotations: Male [excited]:, Female [serious]:
- Better Hindi sentence splitting (। ! ?)
- Turn merging (consecutive same-speaker short turns)
- Duplicate phrase detection
"""
import re
from typing import List, Dict, Optional, Tuple

# ── Data model ────────────────────────────────────────────────────
class ScriptTurn:
    """A single speaker turn in the script."""
    def __init__(self, role: str, text: str,
                 style: Optional[str] = None,
                 turn_index: int = 0):
        self.role = role.lower()  # 'male' or 'female'
        self.text = text.strip()
        self.style = style        # Optional express-as style override
        self.turn_index = turn_index

    def __repr__(self):
        s = f"[{self.turn_index}] {self.role.upper()}"
        if self.style:
            s += f" [{self.style}]"
        s += f": {self.text[:50]}..."
        return s


# ── Pattern constants ─────────────────────────────────────────────
LABEL_RE = re.compile(
    r'(?P<label>(?:male|female|पुरुष|महिला)\s*)\s*'
    r'(?:\[(?P<style>[^\]]+)\])?\s*:',
    re.IGNORECASE
)

# Sentence boundaries for Hindi
SENTENCE_SPLIT = re.compile(
    r'(?<=[।.!?])\s*'
)

# Short text threshold for merging
SHORT_TEXT_WORDS = 5


def parse_script_v2(raw_text: str) -> List[ScriptTurn]:
    """
    Parse script with support for inline style annotations.

    Input formats:
      Male: नमस्ते!
      Female [excited]: वाओ!
      पुरुष: क्या हुआ?
      महिला [serious]: देखिए...

    Returns list of ScriptTurn objects.
    """
    lines = raw_text.strip().split('\n')
    turns = []
    current_role = None
    current_text_parts = []
    turn_index = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if this line starts with a label
        match = LABEL_RE.match(line)
        if match:
            # Flush any accumulated text for previous role
            if current_role and current_text_parts:
                text = ' '.join(current_text_parts).strip()
                if text:
                    turns.append(ScriptTurn(
                        role=current_role,
                        text=text,
                        turn_index=turn_index
                    ))
                    turn_index += 1
                current_text_parts = []

            # Extract label and style
            label_raw = match.group('label').strip().rstrip(':').lower()
            style_raw = match.group('style')
            current_role = 'male' if label_raw in ('male', 'पुरुष') else 'female'

            # Get the text after the label
            after_label = line[match.end():].strip()

            # Check if the style annotation should apply to this turn
            if style_raw:
                style = style_raw.strip().lower()
            else:
                style = None

            # If there's text on the same line as the label, add it
            if after_label:
                # But first, if we have a pending turn with the same role+style, merge
                if turns and turns[-1].role == current_role and turns[-1].style == style:
                    turns[-1].text += ' ' + after_label
                else:
                    turns.append(ScriptTurn(
                        role=current_role,
                        text=after_label,
                        style=style,
                        turn_index=turn_index
                    ))
                    turn_index += 1
            # else wait for next lines

        else:
            # Continuation of previous role's text
            if current_role:
                current_text_parts.append(line)

    # Flush remaining text
    if current_role and current_text_parts:
        text = ' '.join(current_text_parts).strip()
        if text:
            turns.append(ScriptTurn(
                role=current_role,
                text=text,
                turn_index=turn_index
            ))

    return turns


def merge_short_turns(turns: List[ScriptTurn], max_words: int = SHORT_TEXT_WORDS) -> List[ScriptTurn]:
    """
    Merge consecutive same-speaker short turns into one.
    Also merges 'acknowledgment' short texts with preceding turn.
    """
    if not turns:
        return []

    merged = [turns[0]]

    for turn in turns[1:]:
        prev = merged[-1]
        word_count = len(turn.text.split())

        # Merge if same role AND (text is short OR same role continues)
        if turn.role == prev.role:
            # Merge with previous speaker's text
            prev.text += ' ' + turn.text
        elif word_count <= max_words and prev.text.endswith(('?', '।', '.')):
            # Short acknowledgment like "हाँ", "बिल्कुल", "राइट?" after a question
            # Merge with previous speaker (they're finishing the thought)
            prev.text += ' ' + turn.text
        else:
            merged.append(turn)

    return merged


def detect_duplicates(turns: List[ScriptTurn]) -> List[int]:
    """Return indices of duplicate text turns."""
    seen = {}
    dup_indices = []
    for i, turn in enumerate(turns):
        normalized = turn.text.strip().lower()
        if normalized in seen and len(normalized.split()) > 2:
            dup_indices.append(i)
        else:
            seen[normalized] = i
    return dup_indices


def apply_default_styles(turns: List[ScriptTurn]) -> List[ScriptTurn]:
    """
    Auto-detect best express-as style for each turn based on content,
    but only if no explicit style was provided.
    """
    from .emotion_v2 import detect_emotion_v2, EMOTION_TO_STYLE

    for turn in turns:
        if turn.style is None:
            emotion = detect_emotion_v2(turn.text)
            # Map strongest emotion to style
            best_emotion = max(emotion, key=emotion.get)
            score = emotion[best_emotion]
            if score >= 1.5:
                turn.style = EMOTION_TO_STYLE.get(best_emotion, None)

    return turns


def split_turns_by_sentence(turns: List[ScriptTurn]) -> List[ScriptTurn]:
    """
    Split each turn by sentence boundary for finer-grained emotion control.
    Returns new list with one ScriptTurn per sentence.
    """
    result = []
    idx = 0
    for turn in turns:
        sents = [s.strip() for s in SENTENCE_SPLIT.split(turn.text) if s.strip()]
        for sent in sents:
            result.append(ScriptTurn(
                role=turn.role,
                text=sent,
                style=turn.style,
                turn_index=idx
            ))
            idx += 1
    return result
