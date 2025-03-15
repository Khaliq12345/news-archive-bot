from selectolax.parser import HTMLParser
import html2text
from model.model import DetailPage
import json
from datetime import datetime
import pandas as pd
from utilities import gsheet_utils
import os


def html_is_validated(
    html: str, primary_keywords: list[str], secondary_keywords: list[str]
) -> bool:
    primary_passed = False
    try:
        if primary_keywords:
            for keyword in primary_keywords:
                if keyword.lower() in html.lower():
                    primary_passed = True
                    break
        else:
            return True
        if secondary_keywords:
            for keyword in secondary_keywords:
                if keyword.lower() in html.lower():
                    return True
        else:
            if primary_passed:
                return True
        return False
    except Exception as e:
        print(f"Error: {e} | HTML Not Validated")
        return False


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


def save_data(item: DetailPage, article_url: str, base_url: str) -> None:
    """Save item data and article URL to a Google Sheet."""
    item_json = json.loads(item.model_dump_json())
    item_json.update(
        {"article_url": article_url, "date_found": datetime.now().isoformat()}
    )

    df = pd.DataFrame(item_json, index=[0]).astype("object").replace(pd.NaT, None)
    row_data = df.iloc[0].tolist()
    gsheet_utils.add_row(base_url, row_data)


def update_progress(domain_hash: str, status: str) -> None:
    """Update the progress status in a JSON file."""
    with open("progress.json", "r+") as f:
        content = f.read()
        json_data = json.loads(content) if content else {}
        json_data.setdefault(domain_hash, {})["progress"] = status
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
