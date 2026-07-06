"""Centralized data normalization utilities."""


def norm_email(email: str | None) -> str:
    """Strip and lowercase email addresses for comparison."""
    return email.strip().lower() if email else ""


def norm_phone_digits(phone: str | None) -> str:
    """Extract digits only from a phone number."""
    return "".join(filter(str.isdigit, phone)) if phone else ""


def safe_append_description(description: str | None, tag: str, content: str) -> str:
    """Append a tagged section to a description only if the tag isn't present."""
    if not description:
        description = ""
    if tag in description:
        return description
    return f"{description.rstrip()}\n\n{tag}\n{content}".strip()
