import os
import json
import re
import concurrent.futures
from datetime import datetime
from urllib.parse import urljoin

import pandas as pd
from playwright.sync_api import sync_playwright, Page
from selectolax.parser import HTMLParser, Node
from dotenv import load_dotenv
from loguru import logger
from dateparser import parse
import openai

from utilities import utils, gsheet_utils
from model.model import DetailPage

load_dotenv()

DATE_NOW = datetime.now().strftime("%Y-%m-%d")
API_KEY = os.getenv("OPENAI_KEYS")
client = openai.OpenAI(api_key=API_KEY)
TIMEOUT = 100000
LOG_FILE_NAME = f"Log_{DATE_NOW}.txt"


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


def load_detail_page_html(detail_page_url: str) -> HTMLParser | None:
    """Load and parse HTML content from a detail page URL."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(detail_page_url, timeout=50000)
            return HTMLParser(page.content())
    except Exception as e:
        logger.error(f"Error loading page {detail_page_url}: {e}")
        return None


def increment_to_page_url(url: str, num: int) -> str:
    """Modify a pagination URL to point to a specific page number."""
    if re.search(r"[?&](page|pagenum|pg|p)=\d+", url):
        return re.sub(r"([?&])(page|pagenum|pg|p)=\d+", rf"\1\2={num}", url)
    elif re.search(r"/page/\d+", url):
        return re.sub(r"/page/\d+", f"/page/{num}", url)
    return url


def get_detail_page_info(
    logger,
    url: str,
    article_selector: str,
    primary_keywords: list[str] = [],
    secondary_keywords: list[str] = [],
) -> DetailPage | None:
    """Extract detailed information from a detail page."""
    try:
        logger.info(f"Fetching URL: {url}")
        with concurrent.futures.ThreadPoolExecutor() as pool:
            soup = pool.submit(load_detail_page_html, url).result()
        if not soup:
            return None

        html_text = " ".join(html.html for html in soup.css(article_selector))
        if utils.html_is_validated(html_text, primary_keywords, secondary_keywords):
            completion = client.beta.chat.completions.parse(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "Extract the article detail info from the text",
                    },
                    {"role": "user", "content": html_text},
                ],
                response_format=DetailPage,
            )
            return completion.choices[0].message.parsed
        return None
    except Exception as e:
        logger.error(f"Error extracting detail page info: {e}")
        return None


def get_articles_info(
    logger,
    domain_hash: str,
    base_url: str,
    detail_page_selector: str,
    articles: list[Node],
    primary_keywords: list[str] = [],
    secondary_keywords: list[str] = [],
    oldest_date: str | None = None,
    earliest_date: str | None = "1 minute ago",
) -> dict:
    """Retrieve information from a list of articles."""
    earliest_date = earliest_date or "1 minute ago"
    to_continue = True
    parsed_articles = []

    for article in articles:
        article_url = urljoin(base_url, article.css_first("a").attrs["href"])
        if check_url_in_file(f"./Cache/{domain_hash}.txt", article_url):
            logger.info(f"Article already parsed: {article_url}")
            continue

        item = get_detail_page_info(
            logger,
            article_url,
            detail_page_selector,
            primary_keywords,
            secondary_keywords,
        )
        if item:
            write_to_file(f"./Cache/{domain_hash}.txt", f"{article_url}\n")
            if item.date and parse(item.date):
                if (oldest_date and parse(item.date) >= parse(oldest_date)) and (
                    parse(item.date) <= parse(earliest_date)
                ):
                    parsed_articles.append(item)
                    save_data(item, article_url, base_url)
                else:
                    logger.info(f"Reached stop date {item.date}")
                    to_continue = False
                    break
            else:
                break

    return {"articles": parsed_articles, "to_continue": to_continue}


def number_pagination(
    page: Page,
    domain_hash: str,
    archive_url: str,
    base_url: str,
    next_page_selector: str,
    listing_page_selector: str,
    detail_page_selector: str,
    oldest_date: str,
    earliest_date: str,
    primary_keywords: list[str],
    secondary_keywords: list[str],
    logger,
) -> list:
    """Handle pagination by page numbers."""
    logger.info("Starting pagination process")
    all_articles = []
    page_num = 1
    current_url = archive_url
    previous_url = None

    while True:
        logger.info(f"Processing page {page_num} - URL: {current_url}")
        try:
            page.goto(current_url, timeout=TIMEOUT, wait_until="load")
            logger.info("Waiting for the news data")
            page.wait_for_selector(listing_page_selector, timeout=TIMEOUT)

            actual_url = page.url
            if actual_url == previous_url:
                logger.info(
                    f"Page {page_num} redirected to same URL as previous page: {actual_url}. Stopping pagination."
                )
                break

            previous_url = actual_url
            soup = HTMLParser(page.content())
            articles = soup.css(listing_page_selector)

            if not articles:
                logger.info(
                    f"No articles found on page {page_num}. Stopping pagination."
                )
                break

            articles_infos = get_articles_info(
                logger,
                domain_hash,
                base_url,
                detail_page_selector,
                articles,
                primary_keywords,
                secondary_keywords,
                oldest_date,
                earliest_date,
            )

            all_articles.extend(articles_infos.get("articles"))
            logger.info(f"All articles: {len(all_articles)}")

            if not articles_infos.get("to_continue"):
                logger.info(
                    "Found article older than the cut-off date. Stopping pagination."
                )
                break

            page_num += 1
            current_url = increment_to_page_url(archive_url, page_num)
            page.wait_for_timeout(2000)

        except Exception as e:
            logger.exception(f"Error on page {page_num}: {e}")
            break

    return all_articles


def load_more_pagination(
    page: Page,
    domain_hash: str,
    archive_url: str,
    base_url: str,
    next_page_selector: str,
    listing_page_selector: str,
    detail_page_selector: str,
    oldest_date: str,
    earliest_date: str,
    primary_keywords: list[str],
    secondary_keywords: list[str],
    logger,
) -> list:
    """Handle pagination by clicking 'load more' buttons."""
    logger.info("Page loading")
    page.goto(archive_url, timeout=TIMEOUT, wait_until="load")
    logger.info("Waiting for the news data")
    page.wait_for_selector(listing_page_selector, timeout=TIMEOUT)
    all_articles = []
    all_article_urls = []

    while page.is_visible(next_page_selector):
        page.click(next_page_selector)
        page.wait_for_timeout(3000)
        soup = HTMLParser(page.content())
        articles = soup.css(listing_page_selector)
        temp_article_urls = []

        for article in articles:
            article_url = article.css_first("a").attrs["href"]
            if article_url not in all_article_urls:
                temp_article_urls.append(article_url)

        if not temp_article_urls:
            break

        articles_infos = get_articles_info(
            logger,
            domain_hash,
            base_url,
            detail_page_selector,
            articles,
            primary_keywords,
            secondary_keywords,
            oldest_date,
            earliest_date,
        )
        all_articles.extend(articles_infos.get("articles"))
        all_article_urls.extend(temp_article_urls)
        logger.info(f"Found {len(all_article_urls)} articles")

        if not articles_infos.get("to_continue"):
            break

    return all_articles


def infinite_scroll_pagination(
    page: Page,
    domain_hash: str,
    archive_url: str,
    base_url: str,
    next_page_selector: str,
    listing_page_selector: str,
    detail_page_selector: str,
    oldest_date: str,
    earliest_date: str,
    primary_keywords: list[str],
    secondary_keywords: list[str],
    logger,
) -> list:
    """Handle pagination by infinite scrolling."""
    logger.info("Page loading")
    page.goto(archive_url, timeout=TIMEOUT, wait_until="load")
    logger.info("Waiting for the news data")
    page.wait_for_selector(listing_page_selector, timeout=TIMEOUT)
    all_article_urls = []
    all_articles = []

    while True:
        page.wait_for_timeout(3000)
        page.mouse.dblclick(0, 0)
        page.wait_for_timeout(1000)
        soup = HTMLParser(page.content())
        articles = soup.css(listing_page_selector)
        temp_article_urls = []

        for article in articles:
            article_url = article.css_first("a").attrs["href"]
            if article_url not in all_article_urls:
                temp_article_urls.append(article_url)

        if not temp_article_urls:
            break

        articles_infos = get_articles_info(
            logger,
            domain_hash,
            base_url,
            detail_page_selector,
            articles,
            primary_keywords,
            secondary_keywords,
            oldest_date,
            earliest_date,
        )
        all_articles.extend(articles_infos.get("articles"))
        all_article_urls.extend(temp_article_urls)
        logger.info(f"Found {len(all_article_urls)} articles")
        page.keyboard.press("End")

        if not articles_infos.get("to_continue"):
            logger.info(
                "Found article older than the cut-off date. Stopping pagination."
            )
            break

    return all_articles


def start_browser(params: dict, domain_hash: str) -> None:
    """Initialize the browser and start the scraping process."""
    try:
        logger.info(f"Started the background task: {params}")
        log_file = f"./Logs/{domain_hash}.log"
        logger.add(log_file, mode="w")

        with sync_playwright() as p:
            browser = p.firefox.launch()
            page = browser.new_page()

            pagination_type = params.pop("pagination_type", None)
            if pagination_type == "numbered":
                outputs = number_pagination(
                    page=page, domain_hash=domain_hash, logger=logger, **params
                )
            elif pagination_type == "load_more":
                outputs = load_more_pagination(
                    page=page, domain_hash=domain_hash, logger=logger, **params
                )
            elif pagination_type == "infinite_scroll":
                outputs = infinite_scroll_pagination(
                    page=page, domain_hash=domain_hash, logger=logger, **params
                )

            logger.info(f"Total saved: {len(outputs)}")
            update_progress(domain_hash, "success")
            logger.success("Success")
    except Exception as e:
        update_progress(domain_hash, "failed")
        logger.exception(e)
        logger.error("Failed")
    finally:
        browser.close()


if __name__ == "__main__":
    params = {
        "archive_url": "https://navarrepress.com/archive/crime/page/1/",
        "base_url": "https://navarrepress.com/",
        "next_page_selector": "",
        "listing_page_selector": 'div[class="uk-grid tm-grid-expand uk-grid-row-small uk-margin-large"]',
        "detail_page_selector": 'div[class="uk-container uk-container-xlarge"]',
        "oldest_date": "November 01, 2024",
        "earliest_date": "",
        "primary_keywords": "",
        "secondary_keywords": [],
        "pagination_type": "numbered",
    }
    start_browser(params, "dfbcb7ae3c1dfe10e4db")
