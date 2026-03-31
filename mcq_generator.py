"""
mcq_generator.py
================
Generates Multiple Choice Questions from text using the Anthropic Claude API
(claude-sonnet-4-20250514).  Falls back to a rule-based stub if the key is
missing so the app is still runnable for demo purposes.

Environment variable required:
    ANTHROPIC_API_KEY   – your Anthropic API key
"""

import os
import json
import logging
import textwrap
import time
import re
import random

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  PROMPT BUILDER (Enhanced)
# ─────────────────────────────────────────────

SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert educational assessment designer.
    When given a passage of text you generate high-quality Multiple Choice
    Questions (MCQs) exactly as instructed.

    Rules:
    1. Each question must have exactly 4 options labelled A, B, C, D.
    2. Exactly one option must be correct; the other three are plausible
       distractors that relate to the topic.
    3. Provide a concise explanation (1–3 sentences) for the correct answer.
    4. Return ONLY a JSON array – no markdown fences, no extra text.
    5. JSON schema for each element:
       {
         "chapter": "<chapter name or topic>",
         "question": "<question text>",
         "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
         "correct_answer": "A. ...",
         "difficulty": "Easy|Medium|Hard|Expert",
         "explanation": "..."
       }
""").strip()


def _build_user_prompt(chapter_name: str, text: str, num_mcqs: int, 
                       difficulty: str = "mixed", question_length: str = "medium") -> str:
    """Build prompt with difficulty and length specifications."""
    
    # Truncate very long chapters to ~6 000 words to stay within token limits
    words = text.split()
    if len(words) > 6000:
        text = " ".join(words[:6000]) + " [truncated for length]"

    # Map difficulty to instruction
    difficulty_instruction = {
        "easy": "Make all questions Easy difficulty - basic recall and simple concepts.",
        "medium": "Make all questions Medium difficulty - requires understanding and application.",
        "hard": "Make all questions Hard difficulty - requires analysis and synthesis.",
        "expert": "Make all questions Expert difficulty - complex, multi-step reasoning.",
        "mixed": "Vary difficulty across Easy, Medium, Hard, and Expert levels."
    }.get(difficulty, "Vary difficulty across Easy, Medium, and Hard.")

    # Map question length to instruction
    length_instruction = {
        "short": "Keep questions brief (1-2 sentences, 10-20 words).",
        "medium": "Make questions moderate length (2-3 sentences, 20-40 words).",
        "detailed": "Make questions detailed (3-4 sentences, 40-60 words) with specific context.",
        "comprehensive": "Make questions comprehensive (4-6 sentences, 60-100 words) with thorough context.",
        "in-depth": "Make questions in-depth (6-8 sentences, 100-150 words) exploring complex relationships."
    }.get(question_length, "Make questions moderate length (2-3 sentences).")

    return (
        f"Chapter / Section: {chapter_name}\n\n"
        f"Text:\n{text}\n\n"
        f"Generate exactly {num_mcqs} MCQ(s) from the text above.\n\n"
        f"Difficulty requirement: {difficulty_instruction}\n\n"
        f"Question length requirement: {length_instruction}\n\n"
        f"Return ONLY the JSON array."
    )


# ─────────────────────────────────────────────
#  ANTHROPIC CLAUDE CALL
# ─────────────────────────────────────────────

def _call_claude(chapter_name: str, text: str, num_mcqs: int, 
                 difficulty: str = "mixed", question_length: str = "medium") -> list[dict]:
    """Call Anthropic Claude API and parse the JSON response."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package not installed. Run: pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Add it to your .env file or export it before running."
        )

    client = anthropic.Anthropic(api_key=api_key)

    user_prompt = _build_user_prompt(chapter_name, text, num_mcqs, difficulty, question_length)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )

    raw = response.content[0].text.strip()

    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    mcqs = json.loads(raw)

    # Inject chapter name and ensure correct_answer field exists
    for mcq in mcqs:
        mcq.setdefault("chapter", chapter_name)
        # Ensure we have correct_answer (some models might use "answer")
        if "answer" in mcq and "correct_answer" not in mcq:
            mcq["correct_answer"] = mcq["answer"]
        elif "correct_answer" not in mcq:
            # Default to first option if missing
            mcq["correct_answer"] = mcq["options"][0] if mcq.get("options") else "A. Unknown"

    return mcqs


# ─────────────────────────────────────────────
#  ENHANCED STUB FALLBACK (with difficulty and length)
# ─────────────────────────────────────────────

def _stub_mcqs(chapter_name: str, num_mcqs: int, 
               difficulty: str = "medium", question_length: str = "medium") -> list[dict]:
    """Return placeholder MCQs when no API key is configured."""
    difficulties = ["Easy", "Medium", "Hard", "Expert"]
    
    # Ensure we only generate exactly num_mcqs questions
    mcqs = []
    topics = ["concept", "principle", "application", "analysis", "synthesis", "evaluation"]
    
    # Define option templates for variety
    option_templates = [
        ["This is the correct answer explaining the {topic} of {chapter}", 
         "This is a plausible but incorrect distractor about {topic}",
         "Another alternative that might seem correct about {topic}",
         "This is clearly wrong but related to {topic}"],
        
        ["The correct approach to understanding {topic} in {chapter}",
         "A common misconception about {topic}",
         "An alternative perspective on {topic}",
         "An unrelated concept often confused with {topic}"],
        
        ["{topic} is best defined as this core principle",
         "This is a related but secondary aspect of {topic}",
         "This describes a different concept entirely",
         "This is the opposite of what {topic} represents"]
    ]
    
    for i in range(num_mcqs):
        # Randomly select which option will be correct (0, 1, 2, or 3)
        correct_index = random.randint(0, 3)
        correct_letter = chr(65 + correct_index)  # A, B, C, or D
        
        # Select a random option template
        template_idx = i % len(option_templates)
        template = option_templates[template_idx]
        
        # Generate topic for this question
        topic = random.choice(topics)
        
        # Build options array
        options = []
        for opt_idx in range(4):
            if opt_idx == correct_index:
                # This is the correct answer
                option_text = template[0].format(topic=topic, chapter=chapter_name)
            else:
                # This is a distractor - use the corresponding template
                distractor_idx = opt_idx % len(template)
                option_text = template[distractor_idx].format(topic=topic, chapter=chapter_name)
            
            options.append(f"{chr(65 + opt_idx)}. {option_text}")
        
        # Set difficulty
        if difficulty == "mixed":
            current_difficulty = difficulties[i % 4]
        elif difficulty == "easy":
            current_difficulty = "Easy"
        elif difficulty == "medium":
            current_difficulty = "Medium"
        elif difficulty == "hard":
            current_difficulty = "Hard"
        elif difficulty == "expert":
            current_difficulty = "Expert"
        else:
            current_difficulty = difficulties[i % 3]
        
        # Build question with appropriate length
        question = f"What is the primary {topic} in {chapter_name}?"
        
        mcqs.append({
            "chapter": chapter_name,
            "topic": chapter_name,
            "question": question,
            "options": options,
            "correct_answer": options[correct_index],  # This will be A, B, C, or D
            "difficulty": current_difficulty,
            "explanation": (
                f"This is a {current_difficulty} level question about {chapter_name}. "
                f"The correct answer is {correct_letter} because {options[correct_index][3:]}..."
            ),
        })
    
    return mcqs


# ─────────────────────────────────────────────
#  NEW: GENERATE FROM TEXT (for app.py)
# ─────────────────────────────────────────────

# Add this function to mcq_generator.py (if missing)

def generate_mcqs_from_text(context: str, num_mcqs: int = 10, 
                           difficulty: str = "medium", 
                           question_length: str = "medium") -> list[dict]:
    """
    Generate MCQs directly from text context (used by /generate endpoint)
    This creates a single chapter from the context and generates questions.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    
    # Extract topic from first line or use default
    lines = context.split('\n')
    topic = "Provided Content"
    if lines and lines[0].startswith("Topic:"):
        topic = lines[0].replace("Topic:", "").strip()
        context = '\n'.join(lines[1:])
    elif context:
        # Use first 50 chars as topic
        topic = context[:50] + "..."
    
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set – returning demo stub MCQs.")
        return _stub_mcqs(topic, num_mcqs, difficulty, question_length)
    
    try:
        # Use the same chapter-based approach but with a single chapter
        return generate_mcqs_for_chapter(
            chapter_name=topic,
            text=context,
            num_mcqs=num_mcqs,
            difficulty=difficulty,
            question_length=question_length
        )
    except Exception as e:
        logger.error(f"Error generating MCQs from text: {e}")
        # Fall back to stub on error
        return _stub_mcqs(topic, num_mcqs, difficulty, question_length)


# ─────────────────────────────────────────────
#  PUBLIC API (Updated)
# ─────────────────────────────────────────────

def generate_mcqs_for_chapter(
    chapter_name: str,
    text: str,
    num_mcqs: int,
    difficulty: str = "mixed",
    question_length: str = "medium",
    retries: int = 2,
) -> list[dict]:
    """
    Generate MCQs for a single chapter.
    Falls back to stub if ANTHROPIC_API_KEY is missing.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if not api_key:
        logger.warning(
            "ANTHROPIC_API_KEY not set – returning demo stub MCQs for chapter '%s'.",
            chapter_name,
        )
        return _stub_mcqs(chapter_name, num_mcqs, difficulty, question_length)

    for attempt in range(1, retries + 2):
        try:
            return _call_claude(chapter_name, text, num_mcqs, difficulty, question_length)
        except json.JSONDecodeError as e:
            logger.warning("JSON parse error on attempt %d: %s", attempt, e)
        except Exception as e:
            logger.warning("API error on attempt %d: %s", attempt, e)
            if attempt <= retries:
                time.sleep(2 ** attempt)  # exponential back-off

    # All attempts failed – return stubs so the rest of the pipeline continues
    logger.error(
        "All attempts failed for chapter '%s'; returning stub MCQs.", chapter_name
    )
    return _stub_mcqs(chapter_name, num_mcqs, difficulty, question_length)


def generate_all_mcqs(chapters_with_counts: list[dict], 
                     difficulty: str = "mixed",
                     question_length: str = "medium") -> list[dict]:
    """
    Iterate over all chapters and aggregate MCQs.

    Input: list of dicts with keys: chapter, text, mcq_count
    Output: flat list of MCQ dicts
    """
    all_mcqs: list[dict] = []

    for chapter_info in chapters_with_counts:
        chapter_name = chapter_info["chapter"]
        text = chapter_info["text"]
        num_mcqs = chapter_info.get("mcq_count", 1)

        logger.info(
            "Generating %d MCQ(s) for chapter: %s", num_mcqs, chapter_name
        )

        mcqs = generate_mcqs_for_chapter(
            chapter_name, 
            text, 
            num_mcqs, 
            difficulty=difficulty,
            question_length=question_length
        )
        all_mcqs.extend(mcqs)

    return all_mcqs