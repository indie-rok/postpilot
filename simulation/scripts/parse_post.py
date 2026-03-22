"""Parse a Reddit-style markdown post into title + body plain text."""

import re
import argparse


def parse_markdown_post(markdown: str) -> dict[str, str]:
    """Extract title and body from a Reddit-style markdown post.

    Title: First bold line (**text**) that looks like a post title.
    Body: Everything after the title, with markdown formatting stripped.

    Returns:
        {"title": str, "body": str}
    """
    lines = markdown.strip().split("\n")

    title = ""
    title_line_idx = -1

    for i, line in enumerate(lines):
        stripped = line.strip()
        match = re.match(r"^\*\*(.+)\*\*$", stripped)
        if match and len(match.group(1)) > 20:
            title = match.group(1)
            title_line_idx = i
            break

    body_lines = lines[title_line_idx + 1 :] if title_line_idx >= 0 else lines
    body = "\n".join(body_lines)
    body = _strip_markdown(body)

    return {"title": title, "body": body.strip()}


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting, keep plain text."""
    text = re.sub(r"^---+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^[-*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def main():
    parser = argparse.ArgumentParser(description="Parse markdown post to plain text")
    parser.add_argument("input", help="Path to markdown file")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    args = parser.parse_args()

    with open(args.input, "r") as f:
        content = f.read()

    result = parse_markdown_post(content)
    output_text = f"{result['title']}\n\n{result['body']}"

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_text)
        print(f"Written to {args.output}")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
