from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urljoin, urlparse


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class WebNavigator:
    def __init__(self) -> None:
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"
            )
        }

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        try:
            import httpx
        except ModuleNotFoundError:
            return []
        async with httpx.AsyncClient(timeout=10, headers=self._headers) as client:
            response = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
            )
            response.raise_for_status()
        return self._parse_search_results(response.text, limit)

    async def fetch_page(self, url: str) -> str:
        try:
            import httpx
        except ModuleNotFoundError:
            return "Remote page fetch is unavailable because httpx is not installed in this runtime."
        async with httpx.AsyncClient(
            timeout=10, headers=self._headers, follow_redirects=True
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
        return self._extract_text(response.text, str(response.url))

    def _parse_search_results(self, html: str, limit: int) -> list[SearchResult]:
        try:
            from bs4 import BeautifulSoup
        except ModuleNotFoundError:
            return []
        soup = BeautifulSoup(html, "html.parser")
        results: list[SearchResult] = []
        for anchor in soup.select("a.result__a"):
            title = anchor.get_text(" ", strip=True)
            href = anchor.get("href", "").strip()
            if not href:
                continue
            snippet_node = anchor.find_parent("div", class_="result").select_one(
                ".result__snippet"
            ) if anchor.find_parent("div", class_="result") else None
            snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
            results.append(SearchResult(title=title, url=href, snippet=snippet))
            if len(results) >= limit:
                break
        return results

    def _extract_text(self, html: str, base_url: str) -> str:
        try:
            from bs4 import BeautifulSoup
        except ModuleNotFoundError:
            cleaned = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
            title = urlparse(base_url).netloc
            return f"{title}\n{cleaned[:1200]}"
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else urlparse(base_url).netloc
        paragraphs = []
        for node in soup.select("article p, main p, p"):
            text = node.get_text(" ", strip=True)
            if len(text) >= 40:
                paragraphs.append(text)
            if len(paragraphs) == 6:
                break
        content = "\n\n".join(paragraphs) if paragraphs else soup.get_text(" ", strip=True)
        cleaned = re.sub(r"\s+", " ", content).strip()
        return f"{title}\n{cleaned[:1200]}"
