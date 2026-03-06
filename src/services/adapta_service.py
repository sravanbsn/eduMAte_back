import asyncio
import logging
import re
from typing import Dict, List, Optional

import httpx
import spacy
from bs4 import BeautifulSoup
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Try to load the English language model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    logger.warning(
        "Spacy model 'en_core_web_sm' not found. Will be limited functionality or requires manual download via: python -m spacy download en_core_web_sm"
    )
    nlp = spacy.blank(
        "en"
    )  # Fallback to blank if not found to avoid hard crashes during tests


class AdaptaEngine:
    """
    NLP Engine utilizing SpaCy to detect jargon, LangChain to simplify concepts,
    and string manipulation to format text into 'Bionic Reading'.
    """

    def __init__(self):
        self.llm = ChatOpenAI(temperature=0.3, model="gpt-4o-mini")

        self.analogy_prompt = """You are an expert pedagogical aid for students with learning differences.
The user will provide a list of complex jargon terms and the sentence context they appeared in.
Your job is to generate a simple, 'Plain Language' analogy or brief, highly accessible definition for each term.
Ensure vocabulary is kept to a middle-school reading level.

Context:
{context}

Jargon Terms:
{jargon_terms}

Output exactly one simple explanation per jargon term, formatted as:
Term 1: Explanation
Term 2: Explanation
"""

    def get_cognitive_formatting(self, profile: Optional[str]) -> Dict:
        """
        Create a payload of specific UI formatting rules based on the student's Cognitive Profile.
        """
        if not profile:
            return {"theme": "standard", "font": "sans-serif"}
            
        profile_lower = profile.lower()
        if "adhd" in profile_lower:
            return {"read_mask": True, "highlight_active_line": True, "bionic_reading": True, "font": "sans-serif", "colors": "high-contrast"}
        elif "dyslexia" in profile_lower:
            return {"font": "OpenDyslexic", "letter_spacing": "1.5", "line_height": "2.0", "background_color": "#FDF5E6", "text_align": "left"}
        elif "autism" in profile_lower:
            return {"reduce_motion": True, "background_color": "#E8E8E8", "font_color": "#333333", "hide_images": True, "simplify_layout": True}
        
        return {"theme": "standard", "font": "sans-serif"}


    def identify_jargon(self, text: str) -> List[str]:
        """
        Extracts complex vocabulary using spaCy POS tagging and length heuristics.

        Inputs:
            - text (str): The learning material text.
        Output:
            - List[str]: A list of identified complex jargon terms.
        EduMate Module: AdaptaLearn
        """
        doc = nlp(text)
        jargon = []
        for token in doc:
            # Simple heuristic: Look for long nouns/adjectives
            if token.pos_ in ["NOUN", "ADJ"] and len(token.text) > 8:
                jargon.append(token.text)
        return list(set(jargon))  # return unique

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_analogies(
        self, jargon_list: List[str], context: str
    ) -> Dict[str, str]:
        """
        Given a list of complex terms and their original context, generate plain-language definitions/analogies via LLM.

        Inputs:
            - jargon_list (List[str]): Extracted target words.
            - context (str): The sentence context they appeared in to guide the AI.
        Output:
            - Dict[str, str]: Mapping of term to its simplified analogy.
        EduMate Module: AdaptaLearn
        """
        if not jargon_list:
            return {}

        prompt = ChatPromptTemplate.from_messages([("system", self.analogy_prompt)])

        chain = prompt | self.llm
        try:
            response = await chain.ainvoke(
                {"context": context, "jargon_terms": "\n".join(jargon_list)}
            )

            # Simple parser for the expected output format "Term: Explanation"
            analogies = {}
            for line in response.content.split("\n"):
                if ":" in line:
                    parts = line.split(":", 1)
                    analogies[parts[0].strip()] = parts[1].strip()
            return analogies

        except Exception as e:
            logger.error(f"Error generating analogies: {e}")
            raise  # Let tenacity handle retries

    def swap_jargon(self, text: str, analogies: Dict[str, str]) -> str:
        """
        Swap complex jargon for simpler analogies inline instantly.
        """
        swapped_text = text
        for jargon, analogy in analogies.items():
            # Replace jargon with the analogy in brackets so it's clear
            swapped_text = re.sub(
                rf"\b{re.escape(jargon)}\b",
                f"{jargon} [{analogy}]",
                swapped_text,
                flags=re.IGNORECASE
            )
        return swapped_text

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_tts_audio(self, text: str, reading_speed: float) -> str:
        """
        Mock orchestration of a text-to-speech AI generation.
        """
        async with httpx.AsyncClient() as client:
            await asyncio.sleep(0.5)  # Simulate API latency
            logger.info(
                f"Generated TTS for {len(text)} chars at speed {reading_speed}x"
            )
            return f"https://cdn.skillswarm.edu/mock_audio/tts_{hash(text)}_{reading_speed}.mp3"

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def parse_syllabus_tasks(self, syllabus_text: str) -> List[Dict[str, str]]:
        """
        Parse raw syllabus and return structured Task Blocks finding topics and deadlines.
        """
        parser_prompt = """You are an Executive Functioning task parser.
Extract the key topics and immediate deadlines from the syllabus text and return a list of manageable JSON blocks.

Format instructions:
Return a JSON array of objects. Each object must have:
"topic": short string name of the topic or assignment
"deadline": date and time string or null if none
"description": sentence describing what to do

Syllabus Text:
{text}
"""
        prompt = ChatPromptTemplate.from_messages([("system", parser_prompt)])

        chain = prompt | self.llm | JsonOutputParser()
        try:
            parsed = await chain.ainvoke({"text": syllabus_text})
            if isinstance(parsed, dict):
                parsed = [parsed]
            return parsed
        except Exception as e:
            logger.error(f"Error parsing syllabus tasks: {e}")
            raise


def apply_bionic_formatting(text: str) -> str:
    """
    Parses a string and wraps key syllables (typically the first vowel cluster) of every word in <b> tags
    to assist ADHD/Dyslexic readers by serving as artificial fixation points instantly.
    """

    def bionic_word(word):
        # Strip trailing punctuation for calculation
        stripped_word = re.sub(r"[^\w\s]", "", word)
        length = len(stripped_word)

        if length <= 2:
            return f"<b>{word}</b>"

        match = re.search(r"[a-zA-Z0-9]", word)
        if match:
            start_idx = match.start()
            # Bionic fix: simulate key syllable by targeting up to the first vowel + 1 consonant
            vowel_search = re.search(r"[aeiouyAEIOUY]", word[start_idx:])
            if vowel_search:
                fixation_len = vowel_search.end()
            else:
                fixation_len = 2
                
            if fixation_len >= length and length > 3:
                fixation_len = length // 2

            bold_part = word[: start_idx + fixation_len]
            rest = word[start_idx + fixation_len :]
            return f"<b>{bold_part}</b>{rest}"
        return word  # Failsafe for pure punctuation

    words = text.split(" ")
    bionic_words = [bionic_word(w) for w in words]
    return " ".join(bionic_words)


def scrub_html_content(html_string: str) -> str:
    """
    Removes semantic 'clutter' elements (nav, aside, scripts, styles) from an HTML payload,
    extracting only the core readable text to reduce sensory overload.

    Inputs:
        - html_string (str): The raw webpage payload.
        Output:
        - str: Cleaned plaintext document string.
    EduMate Module: AdaptaLearn / General
    """
    soup = BeautifulSoup(html_string, "html.parser")

    # Remove Peripheral UI Clutter specifically reducing sensory overload
    for element in soup(["script", "style", "nav", "aside", "header", "footer", "button", "iframe", "form", "svg", "canvas", "noscript"]):
        element.decompose()
        
    # Overload sensory visual scrubbing (ads, banners, sidebars, popups)
    for cl in ["ad", "banner", "sidebar", "menu", "popup", "modal", "cookie"]:
        for element in soup.find_all(attrs={"class": re.compile(cl, re.I)}):
            element.decompose()
        for element in soup.find_all(attrs={"id": re.compile(cl, re.I)}):
            element.decompose()

    # Get text and clean up whitespace
    text = soup.get_text(separator=" ")
    cleaned_text = " ".join(text.split())

    return cleaned_text
