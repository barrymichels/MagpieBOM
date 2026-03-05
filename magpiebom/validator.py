# magpiebom/validator.py
import base64
import json
import re
import time
from pathlib import Path

from openai import OpenAI

from magpiebom.tracer import Tracer

VALIDATION_PROMPT = """Does this image show the individual electronic component "{part_number}" or a very similar variant from the same product family?

Description: "{description}"

Accept ONLY if the image shows the component BY ITSELF (a single part, possibly on a white/neutral background, or a close-up product photo). Accept even if the exact variant differs slightly (e.g. different pin count, package size, or suffix).

Reject if the image shows:
- A PCB or circuit board with multiple components soldered on it
- An assembled product, module, or device containing multiple parts
- A logo, banner, advertisement, or promotional graphic
- A placeholder, icon, or completely different component type
- A screenshot of a website or software

Reply with ONLY this JSON, nothing else:
{{"match": true, "reason": "..."}} or {{"match": false, "reason": "..."}}"""

DESCRIPTION_EXTRACTION_PROMPT = """You are analyzing a web page about electronic component "{part_number}".

Extract a concise technical description of this component from the text signals below. The description should include: component type, key specs (pin count, pitch, voltage, package, etc.), and nothing else.

If the page text is mostly marketing, store boilerplate, or doesn't contain enough info to describe the component, return an empty description.

Page title: {title}
Meta description: {meta_description}
Meta keywords: {meta_keywords}
URL path: {url_path}
Page text:
{paragraphs}

Reply with ONLY this JSON: {{"description": "..."}} or {{"description": ""}} if no real description can be extracted."""

AGGREGATED_EXTRACTION_PROMPT = """You are analyzing multiple web sources about electronic component "{part_number}".

Write ONE short sentence (under 15 words) describing what this component is. Include: component type, pin count or key differentiator, and package/form factor. Do NOT list detailed specs like voltage, current, temperature, dimensions, or materials.

Example good descriptions:
- "8-pin 2.54mm dual-row female header connector, through-hole"
- "5V linear voltage regulator, TO-220 package"
- "100uF 25V aluminum electrolytic capacitor, radial"

Ignore marketing text and store boilerplate. If no sources describe the component, return empty.

{sources_text}

Reply with ONLY this JSON: {{"description": "..."}} or {{"description": ""}} if no real description can be extracted."""


def extract_description_from_sources(
    client: OpenAI, model: str, part_number: str,
    sources: list[dict], tracer: Tracer | None = None,
) -> str:
    """Extract a description from multiple text signal sources in a single LLM call.

    Each source dict should have: title, meta_description, meta_keywords,
    url_path, url_category, paragraphs.
    Returns the extracted description string, or "" if extraction fails.
    """
    if not sources:
        return ""

    # Build a combined context block from all sources
    parts = []
    for i, src in enumerate(sources, 1):
        lines = [f"--- Source {i} ---"]
        if src.get("title"):
            lines.append(f"Title: {src['title']}")
        if src.get("url_category"):
            lines.append(f"Category: {src['url_category']}")
        if src.get("meta_description"):
            lines.append(f"Description: {src['meta_description']}")
        if src.get("meta_keywords"):
            lines.append(f"Keywords: {src['meta_keywords']}")
        if src.get("url_path"):
            lines.append(f"URL path: {src['url_path']}")
        paragraphs = src.get("paragraphs", [])
        if paragraphs:
            lines.append("Text: " + " ".join(paragraphs))
        parts.append("\n".join(lines))

    sources_text = "\n\n".join(parts)
    prompt = AGGREGATED_EXTRACTION_PROMPT.format(
        part_number=part_number,
        sources_text=sources_text,
    )

    try:
        start = time.monotonic()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0,
        )
        duration_ms = (time.monotonic() - start) * 1000
        content = response.choices[0].message.content.strip()
        if tracer:
            tokens_dict = None
            if response.usage:
                tokens_dict = {"prompt": response.usage.prompt_tokens, "completion": response.usage.completion_tokens}
            tracer.llm(purpose="extract_description_from_sources", prompt=prompt, response=content, tokens=tokens_dict, duration_ms=duration_ms)
        return _parse_description_response(content)
    except Exception as e:
        if tracer:
            tracer.error("LLM aggregated description extraction failed", exception=e)
        return ""


def extract_description(
    client: OpenAI, model: str, part_number: str,
    text_signals: dict, tracer: Tracer | None = None,
) -> str:
    """Extract a concise technical description from page text signals using LLM.

    Returns the extracted description string, or "" if extraction fails.
    """
    paragraphs_text = "\n".join(text_signals.get("paragraphs", []))
    prompt = DESCRIPTION_EXTRACTION_PROMPT.format(
        part_number=part_number,
        title=text_signals.get("title", ""),
        meta_description=text_signals.get("meta_description", ""),
        meta_keywords=text_signals.get("meta_keywords", ""),
        url_path=text_signals.get("url_path", ""),
        paragraphs=paragraphs_text or "(none)",
    )

    try:
        start = time.monotonic()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0,
        )
        duration_ms = (time.monotonic() - start) * 1000
        content = response.choices[0].message.content.strip()
        if tracer:
            tokens_dict = None
            if response.usage:
                tokens_dict = {"prompt": response.usage.prompt_tokens, "completion": response.usage.completion_tokens}
            tracer.llm(purpose="extract_description", prompt=prompt, response=content, tokens=tokens_dict, duration_ms=duration_ms)
        return _parse_description_response(content)
    except Exception as e:
        if tracer:
            tracer.error("LLM description extraction failed", exception=e)
        return ""


def _parse_description_response(content: str) -> str:
    """Parse LLM description extraction response. Returns description or ""."""
    # Strategy 1: Parse as JSON {"description": "..."}
    try:
        data = json.loads(content)
        return str(data.get("description", "")).strip()
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Strategy 2: Find {"description": "..."} anywhere in text
    match = re.search(r'\{\s*"description"\s*:\s*"([^"]*)"\s*\}', content)
    if match:
        return match.group(1).strip()

    # Strategy 3: Truncated JSON — extract text after "description": " even without closing
    match = re.search(r'"description"\s*:\s*"(.+)', content, re.DOTALL)
    if match:
        text = match.group(1).rstrip().rstrip('"').rstrip('}').strip()
        if text:
            return text

    return ""


def get_model_name(client: OpenAI) -> str:
    """Auto-detect the first available model from the local LLM server."""
    models = client.models.list()
    return models.data[0].id


def validate_image(
    client: OpenAI,
    model: str,
    image_path: str,
    part_number: str,
    description: str,
    tracer: Tracer | None = None,
) -> dict:
    """Send an image to the LLM for validation. Returns {"match": bool, "reason": str}."""
    image_data = base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")
    ext = Path(image_path).suffix.lstrip(".")
    mime_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                 "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/jpeg")

    prompt = VALIDATION_PROMPT.format(part_number=part_number, description=description)

    try:
        start = time.monotonic()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}"
                            },
                        },
                    ],
                }
            ],
            max_tokens=200,
            temperature=0,
        )
        duration_ms = (time.monotonic() - start) * 1000
        content = response.choices[0].message.content.strip()
        if tracer:
            tokens_dict = None
            if response.usage:
                tokens_dict = {"prompt": response.usage.prompt_tokens, "completion": response.usage.completion_tokens}
            tracer.llm(purpose="validate_image", prompt=prompt, response=content, tokens=tokens_dict, duration_ms=duration_ms)
        result = _parse_response(content)
        if response.usage:
            result["prompt_tokens"] = response.usage.prompt_tokens
            result["completion_tokens"] = response.usage.completion_tokens
        return result
    except Exception as e:
        if tracer:
            tracer.error("LLM validation failed", exception=e)
        return {"match": False, "reason": "LLM request failed"}


def _parse_response(content: str) -> dict:
    """Parse the LLM JSON response. Extracts JSON from verbose responses."""
    # Strategy 1: Try parsing the whole content as JSON
    try:
        data = json.loads(content)
        return _normalize(data)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Extract from markdown code fences
    if "```" in content:
        try:
            block = content.split("```")[1]
            if block.startswith("json"):
                block = block[4:]
            data = json.loads(block.strip())
            return _normalize(data)
        except (json.JSONDecodeError, IndexError, ValueError):
            pass

    # Strategy 3: Find JSON object anywhere in the text
    match = re.search(r'\{[^{}]*"match"\s*:\s*(true|false)[^{}]*\}', content, re.IGNORECASE)
    if match:
        try:
            data = json.loads(match.group())
            return _normalize(data)
        except (json.JSONDecodeError, ValueError):
            pass

    return {"match": False, "reason": f"Could not parse LLM response: {content[:100]}"}


def _normalize(data: dict) -> dict:
    """Normalize a parsed LLM response dict."""
    return {
        "match": bool(data.get("match", False)),
        "reason": str(data.get("reason", "")),
    }
