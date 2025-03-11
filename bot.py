from playwright.sync_api import sync_playwright, Page
import hrequests
from selectolax.parser import HTMLParser, Node
import openai
from urllib.parse import urljoin
from utilities import utils
from model.model import DetailPage
from datetime import datetime
import os
from loguru import logger
from dateparser import parse
import json
import pandas as pd
from utilities import gsheet_utils
from dotenv import load_dotenv

load_dotenv()

DATE_NOW = datetime.now().strftime("%Y-%m-%d")

API_KEY = os.getenv("OPENAI_KEYS")
client = openai.OpenAI(api_key=API_KEY)
TIMEOUT = 100000
LOG_FILE_NAME = f"Log_{DATE_NOW}.txt"


def save_data(item: DetailPage, article_url: str, base_url: str) -> None:
    """Save item data and article URL to a Google Sheet instead of CSV."""
    # Convert item to JSON and add article_url
    item_json = json.loads(item.model_dump_json())
    item_json["article_url"] = article_url
    item_json["date_found"] = datetime.now().isoformat()

    # Convert to DataFrame (single row)
    df = pd.DataFrame(item_json, index=[0])
    df.to_csv("test.csv", index=False)
    df = df.astype("object")
    df = df.replace(pd.NaT, None)
    row_data = df.iloc[0].tolist()
    gsheet_utils.add_row(base_url, row_data)


def update_progress(domain_hash: str, status):
    with open("progress.json", "r+") as f:
        json_str = f.read()
        if json_str:
            json_data = json.loads(json_str)
            if not json_data.get(domain_hash):
                json_data[domain_hash] = {}
        else:
            json_data = {}
            json_data[domain_hash] = {}
        json_data[domain_hash]["progress"] = status
        f.seek(0)
        f.write(json.dumps(json_data))
        f.truncate()


def check_url_in_file(filename: str, url: str) -> bool:
    if not os.path.exists(filename):
        os.mknod(filename)
    with open(filename, "r") as file:
        content = file.read()
        if url.lower() in content.lower():
            return True
    return False


def write_to_file(filename: str, data: str):
    if not os.path.exists(filename):
        os.mknod(filename)
    with open(filename, "a") as f:
        f.write(data)


def get_detail_page_info(
    logger,
    url: str,
    article_selector: str,
    primary_keywords: list[str] = [],
    secondary_keywords: list[str] = [],
) -> DetailPage:
    try:
        response = hrequests.get(url)
        logger.info(f"Url: {url} | {response.status_code}")
        soup = HTMLParser(response.text)
        html_text = ""
        htmls = soup.css(article_selector)
        for html in htmls:
            html_text += f" {html.html}"
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

            detail_info = completion.choices[0].message.parsed
            return detail_info
        return None
    except Exception as e:
        logger.info(e)
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
    earliest_date = earliest_date if earliest_date else "1 minute ago"
    to_continue = True
    parsed_articles = []
    # states = []
    for x in articles:
        article_url = x.css_first("a").attrs["href"]
        article_url = urljoin(base_url, article_url)
        if check_url_in_file(f"./Cache/{domain_hash}.txt", article_url):
            logger.info(f"Article already parsed: {article_url}")
        else:
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
                    print(
                        f"Current: {parse(item.date)} | Oldest: {oldest_date} | Earliest: {parse(earliest_date)}"
                    )
                    if (oldest_date is not None) and (earliest_date is not None):
                        if (parse(item.date) >= parse(oldest_date)) and (
                            parse(item.date) <= parse(earliest_date)
                        ):
                            parsed_articles.append(item)
                            save_data(item, article_url, base_url)
                        else:
                            logger.info(f"Has reached the stop date {item.date}")
                            to_continue = False
                            break
                    else:
                        parsed_articles.append(item)
                        save_data(item, article_url, base_url)
                else:
                    break

    result = {"articles": parsed_articles, "to_continue": to_continue}
    return result


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
):
    logger.info("Page loading")
    page.goto(archive_url, timeout=TIMEOUT, wait_until="load")
    logger.info("Waiting for the news data")
    page.wait_for_selector(listing_page_selector, timeout=TIMEOUT)
    all_articles = []
    soup = HTMLParser(page.content())
    page_num = 1
    while page.is_visible(next_page_selector):
        logger.info(f"Page {page_num}")
        try:
            soup = HTMLParser(page.content())
            articles = soup.css(listing_page_selector)
            articles_infos = get_articles_info(
                logger,
                domain_hash,
                base_url,
                detail_page_selector,
                articles,
                primary_keywords=primary_keywords,
                secondary_keywords=secondary_keywords,
                oldest_date=oldest_date,
                earliest_date=earliest_date,
            )
            all_articles.extend(articles_infos.get("articles"))
            logger.info(f"All articles: {len(all_articles)}")
            if not articles_infos.get("to_continue"):
                break
            page.click(next_page_selector, timeout=TIMEOUT)
            page.wait_for_load_state("load", timeout=TIMEOUT)
        except Exception as e:
            logger.exception(e)(f"Error: {e}")
            break
        page_num += 1
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
):
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
        articles_to_parse = []
        temp_article_urls = []
        for article in articles:
            article_url = article.css_first("a").attrs["href"]
            if article_url in all_article_urls:
                pass
            else:
                # parse the article
                temp_article_urls.append(article_url)
                articles_to_parse.append(article)
        if len(temp_article_urls) == 0:
            break
        articles_infos = get_articles_info(
            logger,
            domain_hash,
            base_url,
            detail_page_selector,
            articles,
            primary_keywords=primary_keywords,
            secondary_keywords=secondary_keywords,
            oldest_date=oldest_date,
            earliest_date=earliest_date,
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
):
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
        articles_to_parse = []
        for article in articles:
            article_url = article.css_first("a").attrs["href"]
            if article_url in all_article_urls:
                pass
            else:
                temp_article_urls.append(article_url)
                articles_to_parse.append(article)
        if len(temp_article_urls) == 0:
            break

        articles_infos = get_articles_info(
            logger,
            domain_hash,
            base_url,
            detail_page_selector,
            articles,
            primary_keywords=primary_keywords,
            secondary_keywords=secondary_keywords,
            oldest_date=oldest_date,
            earliest_date=earliest_date,
        )
        all_articles.extend(articles_infos.get("articles"))
        all_article_urls.extend(temp_article_urls)
        logger.info(f"Found {len(all_article_urls)} articles")
        page.keyboard.press("End")
        if not articles_infos.get("to_continue"):
            break
    return all_articles


def start_browser(params: dict, domain_hash: str):
    try:
        logger.info(f"Started the background task: {params}")
        log_file = f"./Logs/{domain_hash}.log"
        logger.add(log_file, mode="w")
        p = sync_playwright().start()
        logger.info("Automated initiated")
        browser = p.firefox.launch(headless=True)
        logger.info("Browser created")
        page = browser.new_page()
        logger.info("Page created")
        if params.get("pagination_type") == "numbered":
            del params["pagination_type"]
            outputs = number_pagination(
                page=page, domain_hash=domain_hash, logger=logger, **params
            )
        elif params.get("pagination_type") == "load_more":
            del params["pagination_type"]
            outputs = load_more_pagination(
                page=page, domain_hash=domain_hash, logger=logger, **params
            )
        elif params.get("pagination_type") == "infinite_scroll":
            del params["pagination_type"]
            outputs = infinite_scroll_pagination(
                page=page, domain_hash=domain_hash, logger=logger, **params
            )

        print("Total saved", len(outputs))
        update_progress(domain_hash, "success")
        logger.success("Success")
    except Exception as e:
        update_progress(domain_hash, "failed")
        logger.exception(e)
        logger.success("Failed")
    finally:
        browser.close()


if __name__ == "__main__":
    params = {
        "archive_url": "https://nebraska.tv/news/crime",
        "base_url": "https://nebraska.tv/",
        "next_page_selector": "",
        "listing_page_selector": "#js-Section-List .index-module_teaser__fbfM",
        "detail_page_selector": ".index-module_storyContainer__aWnP",
        "oldest_date": "January 01, 2025",
        "earliest_date": "",
        "primary_keywords": ["crime"],
        "secondary_keywords": [],
        "pagination_type": "numbered",
    }
    start_browser(params, "dfbcb7ae3c1dfe10e4db")
