import csv
import html as html_parser
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


@dataclass
class MatchOdd:
    date: str
    time: str
    competition: str
    home: str
    away: str
    home_back: str
    home_lay: str
    draw_back: str
    draw_lay: str
    away_back: str
    away_lay: str
    over25_back: str = "N/A"
    over25_lay: str = "N/A"
    score01_back: str = "N/A"
    score01_lay: str = "N/A"


PRICE_PATTERN = re.compile(r"^\d+(?:\.\d+)?$")


class BetfairScraper:
    """Scrapes the Betfair Exchange football pre-match grid."""

    BASE_URL = "https://www.betfair.com/exchange/plus/pt/futebol-apostas-1/today"
    TOMORROW_URL = "https://www.betfair.com/exchange/plus/pt/futebol-apostas-1/tomorrow"
    NEXT_DAY_URL = "https://www.betfair.com/exchange/plus/pt/futebol-apostas-1/future"

    def __init__(self, headless: bool = True, wait_seconds: int = 25, next_day: bool = False, tomorrow: bool = False):
        options = Options()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        self.wait_seconds = wait_seconds
        self.next_day = next_day
        self.tomorrow = tomorrow

        # Calculate the date based on which endpoint is being accessed
        if tomorrow:
            self.target_date = (datetime.now() + timedelta(days=1)).strftime("%d-%m-%Y")
        elif next_day:
            self.target_date = (datetime.now() + timedelta(days=2)).strftime("%d-%m-%Y")
        else:
            self.target_date = datetime.now().strftime("%d-%m-%Y")

    def close(self):
        self.driver.quit()

    def scrape(self, max_pages: int = 8) -> List[MatchOdd]:
        """Main method to scrape Betfair football matches across multiple pages."""
        all_matches = []
        page = 1

        while page <= max_pages:
            # Construct page URL
            if self.tomorrow:
                base_url = self.TOMORROW_URL
            elif self.next_day:
                base_url = self.NEXT_DAY_URL
            else:
                base_url = self.BASE_URL

            if page == 1:
                url = base_url
            else:
                url = f"{base_url}/{page}"

            print(f"\n[Page {page}] Loading {url}...")

            self.driver.set_page_load_timeout(self.wait_seconds + 10)
            self.driver.get(url)

            # Wait for table to load
            try:
                WebDriverWait(self.driver, self.wait_seconds).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.coupon-table")))
            except TimeoutException:
                print(f"[Page {page}] Timeout waiting for table - no more pages")
                break

            import time as sleep_time

            sleep_time.sleep(3)

            # Scroll to bottom to load all lazy-loaded events
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            iterations = 0
            while iterations < 100:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                sleep_time.sleep(0.2)
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                iterations += 1

            # Extract matches and collect URLs for additional markets
            matches = self.extract_matches_from_dom()

            # If no matches found, we've reached the end
            if not matches:
                print(f"[Page {page}] No matches found - end of pagination")
                break

            print(f"[Page {page}] Found {len(matches)} matches")

            # Collect all URLs first (before navigating away)
            match_urls = []
            rows = self.driver.find_elements(By.CSS_SELECTOR, "tr[ng-repeat-start]")
            for row in rows:
                try:
                    link = row.find_element(By.CSS_SELECTOR, "a.mod-link")
                    href = link.get_attribute("href")
                    # Construct the correct URL
                    if href.startswith("pt"):
                        match_url = "https://www.betfair.bet.br/exchange/plus/" + href
                    else:
                        match_url = href
                    match_urls.append(match_url)
                except:
                    match_urls.append(None)

            # Process each match's additional markets
            for i, match_url in enumerate(match_urls):
                if i < len(matches) and match_url:
                    try:
                        over25_back, over25_lay, score01_back, score01_lay = self.get_additional_markets(match_url)
                        matches[i].over25_back = over25_back
                        matches[i].over25_lay = over25_lay
                        matches[i].score01_back = score01_back
                        matches[i].score01_lay = score01_lay
                    except Exception:
                        pass

            all_matches.extend(matches)
            page += 1

        return all_matches

    def fetch_and_extract_matches(self) -> List[MatchOdd]:
        """Navigate to page and extract matches directly from DOM using Selenium."""
        if self.tomorrow:
            url = self.TOMORROW_URL
        elif self.next_day:
            url = self.NEXT_DAY_URL
        else:
            url = self.BASE_URL

        self.driver.set_page_load_timeout(self.wait_seconds + 10)
        self.driver.get(url)

        # Wait for table to load
        try:
            WebDriverWait(self.driver, self.wait_seconds).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.coupon-table")))
        except TimeoutException:
            pass

        import time as sleep_time

        sleep_time.sleep(3)

        # Scroll to bottom to load all lazy-loaded events
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        iterations = 0
        while iterations < 100:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            sleep_time.sleep(0.2)
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            iterations += 1

        # Extract matches and collect URLs for additional markets
        matches = self.extract_matches_from_dom()

        # Collect all URLs first (before navigating away)
        match_urls = []
        rows = self.driver.find_elements(By.CSS_SELECTOR, "tr[ng-repeat-start]")
        for row in rows:
            try:
                link = row.find_element(By.CSS_SELECTOR, "a.mod-link")
                href = link.get_attribute("href")
                # Construct the correct URL
                if href.startswith("pt"):
                    match_url = "https://www.betfair.bet.br/exchange/plus/" + href
                else:
                    match_url = href
                match_urls.append(match_url)
            except:
                match_urls.append(None)

        # Now process each match's additional markets
        for i, match_url in enumerate(match_urls):
            if i < len(matches) and match_url:
                try:
                    # Get additional markets
                    over25_back, over25_lay, score01_back, score01_lay = self.get_additional_markets(match_url)

                    # Update match with additional data
                    matches[i].over25_back = over25_back
                    matches[i].over25_lay = over25_lay
                    matches[i].score01_back = score01_back
                    matches[i].score01_lay = score01_lay
                except Exception:
                    pass

        return matches

    def extract_matches_from_dom(self) -> List[MatchOdd]:
        """Extract match data directly from the live DOM using Selenium."""
        matches = []

        # Find all event rows in the DOM
        rows = self.driver.find_elements(By.CSS_SELECTOR, "tr[ng-repeat-start]")

        for i, row in enumerate(rows):
            try:
                # Get teams from ul.runners li.name
                team_elements = row.find_elements(By.CSS_SELECTOR, "ul.runners li.name")
                if len(team_elements) < 2:
                    continue
                home = team_elements[0].text.strip()
                away = team_elements[1].text.strip()

                if not home or not away:
                    continue

                # Get time: try different selectors
                hour = "N/A"
                try:
                    # Try start-date for scheduled matches
                    date_elem = row.find_element(By.CSS_SELECTOR, ".bf-livescores-start-date span")
                    date_text = date_elem.text.strip()
                    # Extract time from "Hoje às HH:MM" format
                    if "às" in date_text:
                        hour = date_text.split("às")[-1].strip()
                    else:
                        hour = date_text
                except:
                    # For live matches, check if there's elapsed time
                    try:
                        hour = "vivo"
                    except:
                        hour = "N/A"

                # Get competition
                link = row.find_element(By.CSS_SELECTOR, "a.mod-link")
                competition_name = self._format_competition(link.get_attribute("data-competition-or-venue-name") or "")

                # Get prices from runners
                runner_elements = row.find_elements(By.CSS_SELECTOR, "div.coupon-runner")
                if len(runner_elements) < 3:
                    continue

                prices = []
                for runner in runner_elements[:3]:
                    try:
                        # Back price
                        back_elem = runner.find_element(By.CSS_SELECTOR, "ours-price-button[type='back']")
                        back = self._extract_price_value_from_element(back_elem)

                        # Lay price
                        lay_elem = runner.find_element(By.CSS_SELECTOR, "ours-price-button[type='lay']")
                        lay = self._extract_price_value_from_element(lay_elem)

                        prices.append((back, lay))
                    except:
                        prices.append(("N/A", "N/A"))

                if len(prices) < 3:
                    continue

                match = MatchOdd(
                    date=self.target_date,
                    time=hour,
                    competition=competition_name,
                    home=home,
                    away=away,
                    home_back=prices[0][0],
                    home_lay=prices[0][1],
                    draw_back=prices[1][0],
                    draw_lay=prices[1][1],
                    away_back=prices[2][0],
                    away_lay=prices[2][1],
                )
                matches.append(match)

            except Exception:
                continue

        return matches

    @staticmethod
    def _split_date_time(value: str) -> tuple[str, str]:
        parts = value.split()
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        return " ".join(parts[:-1]), parts[-1]

    @staticmethod
    def _format_competition(value: str) -> str:
        if not value:
            return ""
        cleaned = html_parser.unescape(value)
        cleaned = cleaned.replace("-", " ")
        return cleaned.title()

    @staticmethod
    def _extract_price_value_from_element(element) -> str:
        """Extract price from a Selenium WebElement."""
        try:
            text = element.text.strip()
            if not text:
                return "N/A"

            # Handle text with newlines (e.g., "1.02\nR$92")
            # Split by newline and get the first non-empty line
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            if lines:
                first_line = lines[0]
                if PRICE_PATTERN.match(first_line):
                    return first_line

            # Alternative: look in child elements or attributes
            labels = element.find_elements(By.TAG_NAME, "label")
            for label in labels:
                text = label.text.strip()
                if PRICE_PATTERN.match(text):
                    return text
        except:
            pass
        return "N/A"

    def get_additional_markets(self, match_url: str) -> tuple[str, str, str, str]:
        """Extract Over 2.5 and 0-1 correct score from match detail page."""
        over25_back = "N/A"
        over25_lay = "N/A"
        score01_back = "N/A"
        score01_lay = "N/A"

        try:
            import time as sleep_time

            self.driver.get(match_url)
            sleep_time.sleep(4)

            # Scroll to load markets - more iterations
            for _ in range(8):
                self.driver.execute_script("window.scrollBy(0, 500)")
                sleep_time.sleep(0.5)

            # Find all h3 elements with runner names
            h3s = self.driver.find_elements(By.TAG_NAME, "h3")

            for h3 in h3s:
                text = h3.text.strip()

                # Look for Over 2.5
                if "Mais de 2,5" in text and over25_back == "N/A":
                    try:
                        # Get the parent tr (table row)
                        tr = h3.find_element(By.XPATH, "./ancestor::tr")

                        # Find all price buttons in the row
                        all_buttons = tr.find_elements(By.CSS_SELECTOR, "ours-price-button")

                        # Get first back and lay buttons
                        back_count = 0
                        lay_count = 0
                        for btn in all_buttons:
                            btn_type = btn.get_attribute("type")
                            if btn_type == "back" and back_count == 0:
                                over25_back = self._extract_price_value_from_element(btn)
                                back_count += 1
                            elif btn_type == "lay" and lay_count == 0:
                                over25_lay = self._extract_price_value_from_element(btn)
                                lay_count += 1

                            if back_count > 0 and lay_count > 0:
                                break
                    except:
                        pass

                # Look for 0-1 score (format: "0 - 1")
                if score01_back == "N/A" and "0 - 1" in text:
                    try:
                        tr = h3.find_element(By.XPATH, "./ancestor::tr")
                        all_buttons = tr.find_elements(By.CSS_SELECTOR, "ours-price-button")

                        back_count = 0
                        lay_count = 0
                        for btn in all_buttons:
                            btn_type = btn.get_attribute("type")
                            if btn_type == "back" and back_count == 0:
                                score01_back = self._extract_price_value_from_element(btn)
                                back_count += 1
                            elif btn_type == "lay" and lay_count == 0:
                                score01_lay = self._extract_price_value_from_element(btn)
                                lay_count += 1

                            if back_count > 0 and lay_count > 0:
                                break
                    except:
                        pass
        except:
            pass

        return over25_back, over25_lay, score01_back, score01_lay


def save_matches_to_csv(matches: List[MatchOdd], path: Path | str = "betfair_matches.csv") -> None:
    if not matches:
        return

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(matches[0]).keys())

    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for match in matches:
            writer.writerow(asdict(match))


def main():
    import sys

    tomorrow = "--tomorrow" in sys.argv or "-t" in sys.argv
    next_day = "--next-day" in sys.argv or "-n" in sys.argv
    scraper = BetfairScraper(tomorrow=tomorrow, next_day=next_day)
    try:
        matches = scraper.scrape()
        for idx, match in enumerate(matches, start=1):
            print(f"{idx}. {asdict(match)}")

        # Create data folder if it doesn't exist
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)

        # Generate filename with date
        if tomorrow:
            date_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            filename = data_dir / f"betfair_matches_amanha_{date_str}.csv"
        elif next_day:
            date_str = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
            filename = data_dir / f"betfair_matches_futuro_{date_str}.csv"
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")
            filename = data_dir / f"betfair_matches_{date_str}.csv"

        save_matches_to_csv(matches, filename)
        if matches:
            print(f"Saved {len(matches)} matches to {filename}")
        else:
            print("Nenhum jogo encontrado; nenhum arquivo foi gerado.")
    finally:
        scraper.close()


if __name__ == "__main__":
    main()
