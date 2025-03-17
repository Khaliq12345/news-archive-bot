import os
import re
import concurrent.futures
from datetime import datetime
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, Page
from selectolax.parser import HTMLParser
from dotenv import load_dotenv
from loguru import logger
from dateparser import parse
from pydantic import BaseModel
from google import genai
from google.genai import types
import json_repair

from utilities import utils
from model.model import DetailPage, Multi_ListingPage_Article

load_dotenv()

DATE_NOW = datetime.now().strftime("%Y-%m-%d")
API_KEY = os.getenv("OPENAI_KEYS")
GEMINI_KEY = os.getenv("GEMINI_AI")
client = genai.Client(api_key=GEMINI_KEY)
TIMEOUT = 100000
LOG_FILE_NAME = f"Log_{DATE_NOW}.txt"


def model_parser(
    prompt: str, model: BaseModel, content: str
):  # "Extract the article detail info from the text"
    final_chunk = "".join(
        chunk.text
        for chunk in client.models.generate_content_stream(
            model="gemini-2.0-flash",
            contents=[prompt, content],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=model,
            ),
        )
    )
    json_data = json_repair.loads(final_chunk)
    return model(**json_data)


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

        html_text = utils.html_to_md(soup)
        if utils.html_is_validated(html_text, primary_keywords, secondary_keywords):
            return model_parser(
                prompt="Extract the article detail info from the text",
                model=DetailPage,
                content=html_text,
            )
        return None
    except Exception as e:
        logger.error(f"Error extracting detail page info: {e}")
        return None


def get_articles_info(
    logger,
    domain_hash: str,
    base_url: str,
    articles: Multi_ListingPage_Article,
    primary_keywords: list[str] = [],
    secondary_keywords: list[str] = [],
    oldest_date: str | None = None,
    earliest_date: str | None = "1 minute ago",
) -> dict:
    """Retrieve information from a list of articles."""
    earliest_date = earliest_date or "1 minute ago"
    to_continue = True
    parsed_articles = []

    for article in articles.data:
        article_url = urljoin(base_url, article.url)
        if utils.check_url_in_file(f"./Cache/{domain_hash}.txt", article_url):
            logger.info(f"Article already parsed: {article_url}")
            continue

        item = get_detail_page_info(
            logger,
            article_url,
            primary_keywords,
            secondary_keywords,
        )
        if item:
            utils.write_to_file(f"./Cache/{domain_hash}.txt", f"{article_url}\n")
            if item.date and parse(item.date):
                if (oldest_date and parse(item.date) >= parse(oldest_date)) and (
                    parse(item.date) <= parse(earliest_date)
                ):
                    parsed_articles.append(item)
                    utils.save_data(item, article_url, base_url)
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

            actual_url = page.url
            if actual_url == previous_url:
                logger.info(
                    f"Page {page_num} redirected to same URL as previous page: {actual_url}. Stopping pagination."
                )
                break

            previous_url = actual_url
            soup = HTMLParser(page.content())
            articles: Multi_ListingPage_Article = model_parser(
                prompt="Extract the articles info in the listing",
                model=Multi_ListingPage_Article,
                content=utils.html_to_md(soup),
            )

            if not articles.data:
                logger.info(
                    f"No articles found on page {page_num}. Stopping pagination."
                )
                break

            articles_infos = get_articles_info(
                logger,
                domain_hash,
                base_url,
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


def start_browser(params: dict, domain_hash: str) -> None:
    """Initialize the browser and start the scraping process."""
    try:
        logger.info(f"Started the background task: {params}")
        log_file = f"./Logs/{domain_hash}.log"
        logger.add(log_file, mode="w")

        with sync_playwright() as p:
            browser = p.firefox.launch()
            page = browser.new_page()
            outputs = number_pagination(
                page=page, domain_hash=domain_hash, logger=logger, **params
            )

            logger.info(f"Total saved: {len(outputs)}")
            utils.update_progress(domain_hash, "success")
            logger.success("Success")
    except BaseException as e:
        utils.update_progress(domain_hash, "failed")
        logger.exception(e)
        logger.error("Failed")
    finally:
        browser.close()


if __name__ == "__main__":
    params = {
        "archive_url": "https://www.fox35orlando.com/tag/crime-publicsafety?page=1",
        "base_url": "https://www.fox35orlando.com/",
        "oldest_date": "November 01, 2024",
        "earliest_date": "",
        "primary_keywords": "",
        "secondary_keywords": [],
    }
    start_browser(params, "dfbcb7ae3c1dfe10e4db")
