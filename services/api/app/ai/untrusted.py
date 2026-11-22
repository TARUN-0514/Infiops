"""Keep untrusted text inside its data block.

Emails, web pages, files, documents and tool output are wrapped in tags such as
<email>...</email> before a model sees them, and the system prompt says text inside is
data. That only holds if the text can't close the tag itself: an email whose body
contains "</email> New instructions: ..." would otherwise step outside its block.
`neutral` defuses every tag name NEXUS uses for wrapping, open or closing, so data can
never start or end a block. Attribute values are HTML-escaped by `attr`."""

import html
import re

# Every tag NEXUS wraps prompt content in. Add new wrapper tags here.
WRAPPER_TAGS = (
    "assistant_reply",
    "attachment",
    "data",
    "document",
    "email",
    "existing_memories",
    "facts",
    "file",
    "instructions",
    "memories",
    "passage",
    "passages",
    "question",
    "sentence",
    "system",
    "task",
    "tasks",
    "today",
    "user_message",
    "web_page",
)

_TAG = re.compile(r"<(\s*/?\s*)(" + "|".join(WRAPPER_TAGS) + r")\b", re.IGNORECASE)


def neutral(text: str) -> str:
    """Replace the '<' of any wrapper tag inside untrusted text with '&lt;'."""
    return _TAG.sub(lambda m: "&lt;" + m.group(1) + m.group(2), text)


def attr(value: str) -> str:
    return html.escape(value, quote=True)
