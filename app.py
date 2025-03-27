from nicegui import ui
import os
import signal
import json
from bot import start_browser
import multiprocessing
from urllib.parse import urlparse
import hashlib
from utilities.utils import update_progress

LOG_FILE = "progress.json"


class App:
    def __init__(self):
        self.archive_url = ""
        self.years_included = ""
        self.base_url = ""
        self.params = {}
        self.domain_hash = None
        self.create_running_dialog()
        self.oldest_date = ""
        self.earliest_date = ""
        self.primary_keywords = ""
        self.secondary_keywords = ""
        self.selector = None
        self.bot_id = ""

    def kill_bot(self):
        update_progress(self.domain_hash, "failed")
        try:
            os.kill(int(self.bot_id), signal.SIGKILL)
            ui.notification(
                message="Bot killed", position="top", type="positive", close_button=True
            )
        except ProcessLookupError as e:
            self.show_validation_notif(f"Process Killed - {e}")
        except Exception as e:
            self.show_validation_notif(f"Bot Killed Error - {e}")

    def get_domain_hash(self):
        domain = urlparse(self.base_url).netloc
        return hashlib.sha1(str(domain).encode()).hexdigest()
        # log_file = hashlib.sha1(str(domain).encode()).hexdigest()

    def add_url_to_logger(self) -> bool:
        if not os.path.exists(LOG_FILE):
            os.mknod(LOG_FILE)
        with open(LOG_FILE, "r+") as f:
            json_str = f.read()
            if json_str:
                json_data = json.loads(json_str)
            else:
                json_data = {}
            if (json_data.get(self.domain_hash)) and (
                json_data[self.domain_hash]["progress"] == "running"
            ):
                return False
            json_data[self.domain_hash] = {"progress": "running"}
            json_data[self.domain_hash].update(self.params)
            f.seek(0)
            f.write(json.dumps(json_data))
            f.truncate()
        ui.notification(
            message=f"Started job for {self.params['base_url']}",
            position="top",
            type="positive",
            close_button=True,
        )
        return True

    def start_bot(self):
        print(self.params, self.domain_hash)
        is_validated = self.parse_inputs()
        self.update_domain_hash()
        if is_validated:
            if self.add_url_to_logger():
                p = multiprocessing.Process(
                    target=start_browser,
                    args=(self.params, self.domain_hash, self.selector),
                )
                p.start()
                update_progress(self.domain_hash, p.pid, "pid")
            else:
                ui.notification(
                    "Archive is currently running", type="info", position="top"
                )

    def show_validation_notif(self, message: str):
        ui.notification(
            message=message, position="top", type="negative", close_button=True
        )
        return None

    def parse_inputs(self):
        self.params["archive_url"] = self.archive_url
        self.params["base_url"] = self.base_url
        self.params["oldest_date"] = self.oldest_date
        self.params["earliest_date"] = self.earliest_date
        self.params["primary_keywords"] = self.primary_keywords.split(";")
        self.params["secondary_keywords"] = self.secondary_keywords.split(";")
        for x in self.params:
            if x not in [
                "primary_keywords",
                "secondary_keywords",
                "oldest_date",
                "earliest_date",
            ]:
                if not self.params[x]:
                    self.show_validation_notif(f"Field is required: {x}")
                    return False
        return True

    def get_input(
        self,
        label: str,
        key: str,
        validation: dict | None = None,
        placeholder: str | None = None,
        width: str = "w-5/6",
    ):
        return (
            ui.input(placeholder=placeholder, label=label, validation=validation)
            .classes(width)
            .bind_value(self, key)
        )

    def update_domain_hash(self):
        self.domain_hash = self.get_domain_hash()

    @ui.refreshable
    def log_ui(self):
        log_file = f"./Logs/{self.domain_hash}.log"
        if os.path.exists(log_file):
            try:
                with ui.card().classes("w-full"):
                    if self.domain_hash:
                        with open(log_file, "r") as f:
                            log_content = f.readlines()
                            log_content.reverse()
                            log_content = "\n".join(log_content)
                    else:
                        log_content = ""
                    ui.label(f"Log File of {self.base_url}").classes(
                        "text-lg font-bold"
                    )
                    ui.separator()
                    log_display = ui.log().classes("w-full h-64")
                    log_display.push(log_content)
            except Exception as e:
                ui.notification(
                    message=e, position="top", close_button=True, type="negative"
                )

    def refresh_log(self) -> None:
        self.log_ui.refresh()

    def create_running_dialog(self):
        with ui.dialog() as self.running_dialog, ui.card():
            with open(LOG_FILE, "r") as f:
                json_content = json.loads(f.read())
            ui.json_editor({"content": {"json": json_content}})
            ui.button("Close", on_click=self.running_dialog.close)

    def show_all_running_dialog(self):
        self.running_dialog.clear()
        with self.running_dialog, ui.card():
            with open(LOG_FILE, "r") as f:
                json_content = json.loads(f.read())
            ui.json_editor({"content": {"json": json_content}})
            ui.button("Close", on_click=self.running_dialog.close)
        self.running_dialog.open()

    def main_page_ui(self):
        with ui.header().classes("text-h4 flex flex-col items-center"):
            ui.label("Archive Scraper Bot")

        with ui.element("div").classes("bg-grey-3 w-full"):
            with ui.column(align_items="center").classes(
                "w-full content-center gap-5 p-2"
            ):
                validation = {"Valid url is required": lambda value: "http" in value}
                self.get_input("Archive Url", "archive_url", validation=validation)
                self.get_input("Base Url", "base_url")
                self.get_input("Next Page/Button Selector", "selector")
                self.get_input(
                    "Primary Keywords", "primary_keywords", placeholder="Arrest;Bodycam"
                ).props("""hint='seperate multiple by ";"' autogrow""")
                self.get_input(
                    "Secondary Keywords",
                    "secondary_keywords",
                    placeholder="Mother;Father",
                ).props("""hint='seperate multiple by ";"' autogrow""")
                with ui.row().classes("w-5/6"):
                    self.get_input(
                        "Date to start from",
                        "earliest_date",
                        placeholder="January 12th 2025",
                        width="w-2/5",
                    )
                    self.get_input(
                        "Date to end at",
                        "oldest_date",
                        placeholder="January 12th 2024",
                        width="w-2/5",
                    )
                with ui.row().classes("w-5/6"):
                    ui.button("Start bot").props("outline").on_click(
                        lambda x: self.start_bot()
                    )
                    ui.button("Show all running").props("outline").on_click(
                        lambda x: self.show_all_running_dialog()
                    )

        with ui.expansion(text="View Logs").classes("w-full bg-grey-2 pa-5"):
            self.get_input(
                "Show logs of", "base_url", placeholder="https://alachuachronicle.com/"
            ).on_value_change(lambda x: self.update_domain_hash())
            self.get_input("Archive Bot ID", "bot_id")
            self.log_ui()
            ui.button(
                "Refresh Log", on_click=lambda: ui.timer(2, lambda: self.refresh_log())
            )
            ui.button("Stop", on_click=lambda: self.kill_bot())


@ui.page("/")
def main():
    the_app = App()
    the_app.main_page_ui()


ui.run(reload=True, port=80)