"""
Ghost Protocol — Upload knowledge base to Azure AI Search (Foundry IQ)

Reads all 8 markdown files in /knowledge/, chunks them by section heading,
and uploads the chunks as searchable documents to Azure AI Search.

Usage:
    python knowledge/upload_to_foundry.py

Required environment variables (in .env):
    AZURE_SEARCH_ENDPOINT   — e.g. https://my-search.search.windows.net
    AZURE_SEARCH_KEY        — Admin key for the search resource
    AZURE_SEARCH_INDEX      — Index name (default: ghost-protocol-knowledge)
"""

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchFieldDataType,
)
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError

load_dotenv()

_KNOWLEDGE_DIR = Path(__file__).parent

_KNOWLEDGE_FILES = {
    "world":         "world_overview.md",
    "corporations":  "corporations.md",
    "districts":     "districts.md",
    "crew":          "crew_profiles.md",
    "heists":        "heist_targets.md",
    "factions":      "factions.md",
    "gear":          "items_and_gear.md",
    "rules":         "homebrew_rules.md",
}

_MAX_CHUNK_CHARS = 2000


def _chunk_markdown(text: str) -> list[dict]:
    """Split markdown into sections by ## headings. Returns list of {heading, content}."""
    # Split on lines starting with ##
    sections = re.split(r"\n(?=## )", text)
    chunks = []
    for section in sections:
        lines = section.strip().splitlines()
        if not lines:
            continue
        heading = lines[0].lstrip("#").strip() if lines[0].startswith("#") else "Overview"
        body = "\n".join(lines[1:]).strip()
        # Further split body into chunks if it exceeds the character limit
        while len(body) > _MAX_CHUNK_CHARS:
            chunks.append({"heading": heading, "content": body[:_MAX_CHUNK_CHARS]})
            body = body[_MAX_CHUNK_CHARS:]
        if body:
            chunks.append({"heading": heading, "content": body})
    return chunks


def _create_index(index_client: SearchIndexClient, index_name: str) -> None:
    """Create the Azure AI Search index if it does not already exist."""
    fields = [
        SimpleField(name="id",          type=SearchFieldDataType.String, key=True),
        SimpleField(name="key",         type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="source_file", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="title",   type=SearchFieldDataType.String),
        SearchableField(name="section", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
    ]
    index = SearchIndex(name=index_name, fields=fields)
    try:
        index_client.create_or_update_index(index)
        print(f"  Index '{index_name}' ready.")
    except HttpResponseError as exc:
        print(f"  ERROR creating index: {exc}", file=sys.stderr)
        raise


def _build_documents(key: str, filename: str) -> list[dict]:
    """Read a markdown file and return a list of Azure Search documents."""
    path = _KNOWLEDGE_DIR / filename
    text = path.read_text(encoding="utf-8")
    chunks = _chunk_markdown(text)
    docs = []
    for i, chunk in enumerate(chunks):
        docs.append({
            "id":          f"{key}_{i}",
            "key":         key,
            "title":       key.upper(),
            "section":     chunk["heading"],
            "content":     chunk["content"],
            "source_file": filename,
        })
    return docs


def upload_all(endpoint: str, key: str, index_name: str) -> int:
    """Upload all knowledge files to Azure AI Search. Returns total document count."""
    credential = AzureKeyCredential(key)
    index_client = SearchIndexClient(endpoint=endpoint, credential=credential)
    search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)

    _create_index(index_client, index_name)

    total = 0
    for kb_key, filename in _KNOWLEDGE_FILES.items():
        try:
            docs = _build_documents(kb_key, filename)
            result = search_client.upload_documents(documents=docs)
            succeeded = sum(1 for r in result if r.succeeded)
            total += succeeded
            print(f"  {filename:30s} → {succeeded}/{len(docs)} chunks uploaded")
        except FileNotFoundError:
            print(f"  WARNING: {filename} not found, skipping.", file=sys.stderr)
        except HttpResponseError as exc:
            print(f"  ERROR uploading {filename}: {exc}", file=sys.stderr)

    print(f"\n  Done. {total} total documents in '{index_name}'.")
    return total


def main() -> None:
    endpoint  = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    admin_key = os.getenv("AZURE_SEARCH_KEY", "")
    index     = os.getenv("AZURE_SEARCH_INDEX", "ghost-protocol-knowledge")

    if not endpoint or not admin_key:
        print(
            "ERROR: AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_KEY must be set in .env",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Uploading Ghost Protocol knowledge base to Azure AI Search")
    print(f"  Endpoint : {endpoint}")
    print(f"  Index    : {index}")
    print()
    upload_all(endpoint, admin_key, index)


if __name__ == "__main__":
    main()
