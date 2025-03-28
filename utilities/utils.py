from selectolax.parser import HTMLParser
import html2text
from model.model import DetailPage
import json
from datetime import datetime
import os
from urllib.parse import urlparse
from utilities.table import add_data


def html_is_validated(
    html: str, primary_keywords: list[str], secondary_keywords: list[str]
) -> tuple:
    html = str(html)
    ps = []
    ss = []
    for pk in primary_keywords:
        if pk.lower() in html.lower():
            ps.append(pk)
    for sk in secondary_keywords:
        if sk.lower() in html.lower():
            ss.append(sk)

    return ps, ss


def html_to_md(soup: HTMLParser):
    h = html2text.HTML2Text()
    h.body_width = 0  # Prevent line wrapping
    h.ignore_links = False  # Keep links
    h.inline_links = True  # Use inline links (more compact)

    # Options to remove unnecessary content
    h.ignore_images = True
    h.ignore_emphasis = True
    h.ignore_tables = True
    h.single_line_break = True
    h.unicode_snob = False
    h.wrap_links = False
    h.mark_code = False
    h.pad_tables = False
    h.escape_snob = False
    h.skip_internal_links = True
    h.ignore_anchors = True
    return h.handle(soup.html)


def save_data(
    item: DetailPage,
    article_url: str,
    base_url: str,
    primary_keywords: list[str],
    secondary_keywords: list[str],
) -> None:
    """Save item data and article URL to a Google Sheet."""
    secondary_keywords = ";".join(secondary_keywords)
    primary_keywords = ";".join(primary_keywords)
    add_data(
        table_name=urlparse(base_url).netloc,
        data={
            "Date Scraped": datetime.now().isoformat(),
            "Date Of Article": item.date,
            "News Article": item.title,
            "Link": article_url,
            "Suspect Name": item.suspect_name,
            "Charges": item.charge,
            "Primary Keywords": primary_keywords,
            "Secondary Keywords": secondary_keywords,
        },
    )


def update_progress(domain_hash: str, status: str, key: str = "progress") -> None:
    """Update the progress status in a JSON file."""
    with open("progress.json", "r+") as f:
        content = f.read()
        json_data = json.loads(content) if content else {}
        json_data.setdefault(domain_hash, {})[key] = status
        f.seek(0)
        json.dump(json_data, f)
        f.truncate()


def check_url_in_file(filename: str, url: str) -> bool:
    """Check if a URL is already present in a file."""
    os.mknod(filename) if not os.path.exists(filename) else {}
    with open(filename, "r") as file:
        content = file.read()
        return url.lower() in content.lower()
    return False


def write_to_file(filename: str, data: str) -> None:
    """Append data to a file, creating it if it doesn't exist."""
    os.mknod(filename) if not os.path.exists(filename) else {}
    with open(filename, "a") as f:
        f.write(data)
