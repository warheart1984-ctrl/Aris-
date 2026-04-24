from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import ast
import operator
import re
from urllib.parse import urlparse

from .web import WebNavigator

_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


@dataclass(frozen=True, slots=True)
class ToolResult:
    name: str
    content: str


class ToolRouter:
    def __init__(self) -> None:
        self.navigator = WebNavigator()

    async def run(
        self, query: str, *, enable_remote_fetch: bool, mode: str
    ) -> list[ToolResult]:
        results: list[ToolResult] = []
        normalized = query.lower()
        if any(word in normalized for word in ("time", "date", "today", "clock")):
            now = datetime.now().strftime("%A, %B %d, %Y %I:%M %p")
            results.append(ToolResult(name="clock", content=f"Current local time: {now}"))
        math_result = self._maybe_calculate(query)
        if math_result is not None:
            results.append(ToolResult(name="calculator", content=math_result))
        if enable_remote_fetch:
            if self._should_search(query, mode):
                search_results = await self.navigator.search(query, limit=3)
                if search_results:
                    formatted = "\n".join(
                        f"- {item.title} | {item.url} | {item.snippet}"
                        for item in search_results
                    )
                    results.append(
                        ToolResult(name="web_search", content=f"Search results:\n{formatted}")
                    )
                    if mode == "deep":
                        for item in search_results[:2]:
                            try:
                                page_text = await self.navigator.fetch_page(item.url)
                            except Exception:
                                continue
                            results.append(
                                ToolResult(
                                    name="web_page",
                                    content=f"{item.url}\n{page_text[:900]}",
                                )
                            )
            fetch_results = await self._fetch_urls(query)
            results.extend(fetch_results)
        return results

    def _maybe_calculate(self, query: str) -> str | None:
        if not re.search(r"\d", query):
            return None
        if not any(symbol in query for symbol in "+-*/%^()"):
            return None
        expression = query.replace("^", "**")
        try:
            value = self._safe_eval(ast.parse(expression, mode="eval").body)
        except Exception:
            return None
        return f"Calculated result: {value}"

    def _safe_eval(self, node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
            left = self._safe_eval(node.left)
            right = self._safe_eval(node.right)
            return _ALLOWED_OPERATORS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
            operand = self._safe_eval(node.operand)
            return _ALLOWED_OPERATORS[type(node.op)](operand)
        raise ValueError("Unsupported expression.")

    async def _fetch_urls(self, query: str) -> list[ToolResult]:
        urls = []
        for token in query.split():
            if token.startswith(("http://", "https://")):
                urls.append(token.strip(".,);]"))
        unique_urls = []
        seen = set()
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            unique_urls.append(url)
        results: list[ToolResult] = []
        try:
            import httpx
        except ModuleNotFoundError:
            if unique_urls:
                return [
                    ToolResult(
                        name="url_fetch_unavailable",
                        content="Remote URL fetch is unavailable because httpx is not installed in this runtime.",
                    )
                ]
            return results
        async with httpx.AsyncClient(timeout=8) as client:
            for url in unique_urls[:2]:
                try:
                    response = await client.get(url, follow_redirects=True)
                    response.raise_for_status()
                    text = re.sub(r"\s+", " ", response.text)
                    host = urlparse(str(response.url)).netloc or urlparse(url).netloc
                    results.append(
                        ToolResult(
                            name="url_fetch",
                            content=f"{host}: {text[:320]}",
                        )
                    )
                except Exception:
                    continue
        return results

    def _should_search(self, query: str, mode: str) -> bool:
        normalized = query.lower()
        triggers = (
            "search",
            "look up",
            "find",
            "latest",
            "current",
            "news",
            "today",
            "who is",
            "what is",
            "when did",
            "where is",
        )
        return mode == "deep" or any(trigger in normalized for trigger in triggers)
