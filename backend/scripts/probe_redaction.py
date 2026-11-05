"""Conservative provider explanation redaction for the manual synthetic probes."""

import json
import re
from urllib.parse import quote, quote_plus

from google.genai import types

from app.drafts.schemas import Extraction

# Preserve diagnostic prose instead of replacing every provider explanation with
# an HTTP-status template. Unrecognized prose is suppressed as a whole line.
WORDS = frozenset(
    """
a all allow allowed also an and any api argument arguments array arrays as at
attribute attributes available be because between boolean both bound bounds but
by call can cannot character characters check code collection complexity config
configuration constrained contains content count current decoding defined depth
did dimension disabled do does each empty enabled enum enumerated enumeration
error exceeds expected field fields find finite for format found from generate
generation given greater has have in include included incompatible integer
internal invalid is it item items json key keys keyword keywords larger length
less limit limited limits list long many max maximum min minimum missing model
models must name named nesting no non not number numeric object objects of on
one only optional or output parameter parameters pass payload permitted please
primitive project properties property quota received reference references request
requested required resource response retry returned schema schemas see server
service serving set should size smaller specified states string strings structure
structured supported syntax than that the their there this to token tokens too
total type types undefined unexpected union unknown unrecognized unsupported use
used using valid validation value values version was which with without work
works you your authentication credentials denied exhausted permission rate
v1beta generatecontentrequest listmodels support instead deprecated mutually
exclusive either sent match exceeded compile equal single expired renew billing
enable tier free user location country access region new projects null true false
responseformat mimetype complex generatecontent methods operation operations
endpoint endpoints interactions legacy reported leaked another $
root node nodes child children nested levels recursive recursion circular refs
definitions unresolved prohibited reserved may compile compiled compilation
""".split()
)


def identifiers() -> set[str]:
    names = set(types.GenerateContentConfig.model_fields)
    names.update(types.Schema.model_fields)
    names.update(
        "".join([s.split("_")[0], *[p.title() for p in s.split("_")[1:]]])
        for s in tuple(names)
    )

    def walk(node):
        if isinstance(node, dict):
            names.update(node)
            for key, value in node.items():
                if key in {"properties", "$defs"}:
                    names.update(value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(Extraction.model_json_schema())
    names.update(
        {
            "generation_config",
            "generationConfig",
            "systemInstruction",
            "system_instruction",
            "GenerateContentRequest",
            "GenerationConfig",
            "GenerateContentConfig",
        }
    )
    return names


def explanation(text: str, *, secret: str, excluded: list[str], model: str) -> str:
    """Never pass str(exception) or an entire error body here."""
    if not isinstance(text, str):
        return ""
    # Known input/output strings are removed before free-text handling. Include
    # their JSON/URL encodings, since providers may quote escaped request content.
    for value in [secret, *excluded]:
        if value:
            for encoded in {
                value,
                quote(value, safe=""),
                quote_plus(value),
                json.dumps(value)[1:-1],
            }:
                text = text.replace(encoded, "[redacted]")
    text = re.sub(r"https?://[^\s<>\"']+", "[redacted URL]", text)
    text = re.sub(
        r"(?im)(?:authorization|x-goog-api-key)\s*[:=][^\r\n]*",
        "[redacted header]",
        text,
    )
    text = re.sub(r"(?i)\bBearer\s+\S+", "[redacted credential]", text)
    text = re.sub(
        r"\bAIza[A-Za-z0-9_-]{15,}|\bsk-[A-Za-z0-9_-]{15,}",
        "[redacted credential]",
        text,
    )
    text = re.sub(r"\b\d{7,}\b", "[redacted number]", text)
    known = {name.lower() for name in identifiers()} | WORDS
    known.update({"redacted", "url", "header", "credential", "number"})
    # A configured model may be mentioned by the provider; never allow a URL/key.
    if (
        re.fullmatch(r"(?:models/)?gemini-[A-Za-z0-9._-]{1,100}", model)
        and secret not in model
    ):
        text = text.replace(model, "model")
    safe = []
    for line in text.splitlines()[:20]:
        # A body embedded in the message is not a diagnostic explanation.
        if line.lstrip().startswith(("{", "[")):
            safe.append("[redacted]")
            continue
        line = re.sub(r"\{.*", "[redacted]", line)
        tokens = re.findall(r"[A-Za-z_$][A-Za-z0-9_$-]*", line)
        if all(token.lower() in known for token in tokens):
            safe.append(line)
        else:
            safe.append("[redacted non-diagnostic explanation]")
    return "\n".join(safe)[:1200]
