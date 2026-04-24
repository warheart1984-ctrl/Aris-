"""Result normalization for `generate_code` contractor requests."""

from __future__ import annotations

from forge.schemas import ContractorResult, GeneratedFile
from forge.utils.bounded_output import bound_text


guidance = (
    "Generate code artifacts only. Do not explain your work outside the JSON payload. "
    "When possible, return complete files that satisfy the requested goal."
)

response_schema = """{
  "files": [
    {
      "path": "relative/path.ext",
      "content": "full file contents"
    }
  ]
}"""


def normalize_result(
    parsed: object,
    *,
    max_output_chars: int,
    context: dict[str, object] | None = None,
) -> ContractorResult | None:
    if not isinstance(parsed, dict):
        return None
    raw_files = parsed.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        return None

    files: list[GeneratedFile] = []
    for item in raw_files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip().replace("\\", "/")
        content = item.get("content")
        if not path or not isinstance(content, str):
            continue
        files.append(
            GeneratedFile(
                path=path,
                content=bound_text(content, max_output_chars),
            )
        )
    if not files:
        return None
    return ContractorResult(files=files)
