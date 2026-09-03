"""Build French anatomy names from Wikipedia language links and Wikidata labels.

The generated mapping is committed with the application. Production therefore
uses sourced French names without making live requests to Wikipedia.
"""

from __future__ import annotations

import json
import os
import pprint
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from scripts.build_wikidata_latin_terms import collect_terms  # noqa: E402
from sourced_latin_terms import SOURCED_LATIN_SOURCES  # noqa: E402


EN_WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "RadiusAnatomyQBank/1.0 (https://github.com/zefyoe/mcq-quiz)"
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "sourced_french_terms.py")
SSL_CONTEXT = ssl.create_default_context(cafile="/etc/ssl/cert.pem")


def api_request(endpoint: str, parameters: dict) -> dict:
    payload = urllib.parse.urlencode(parameters).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=60, context=SSL_CONTEXT) as response:
        return json.load(response)


def request_with_retries(endpoint: str, parameters: dict) -> dict:
    for attempt in range(3):
        try:
            return api_request(endpoint, parameters)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("Unreachable")


def french_wikipedia_titles(
    english_titles: set[str],
) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    results = {}
    entity_ids = {}
    ordered = sorted(english_titles, key=str.casefold)
    for offset in range(0, len(ordered), 40):
        batch = ordered[offset:offset + 40]
        payload = request_with_retries(EN_WIKIPEDIA_API, {
            "action": "query",
            "format": "json",
            "redirects": "1",
            "prop": "langlinks|pageprops",
            "ppprop": "wikibase_item",
            "lllang": "fr",
            "lllimit": "max",
            "titles": "|".join(batch),
        })
        query = payload.get("query", {})
        aliases = {title.casefold(): title.casefold() for title in batch}
        display_titles = {title.casefold(): title for title in batch}
        for item in query.get("normalized", []):
            aliases[item["from"].casefold()] = item["to"].casefold()
            display_titles[item["to"].casefold()] = item["to"]
        for item in query.get("redirects", []):
            aliases[item["from"].casefold()] = item["to"].casefold()
            display_titles[item["to"].casefold()] = item["to"]
        pages = {
            page["title"].casefold(): page
            for page in query.get("pages", {}).values()
            if "missing" not in page
        }
        for requested in batch:
            resolved = requested.casefold()
            for _ in range(5):
                next_title = aliases.get(resolved, resolved)
                if next_title == resolved:
                    break
                resolved = next_title
            page = pages.get(resolved)
            entity_id = (page or {}).get("pageprops", {}).get("wikibase_item")
            if entity_id:
                entity_ids[requested.casefold()] = entity_id
            langlinks = page.get("langlinks", []) if page else []
            if not langlinks:
                continue
            french_title = langlinks[0]["*"]
            source = "https://fr.wikipedia.org/wiki/" + urllib.parse.quote(
                french_title.replace(" ", "_")
            )
            results[requested.casefold()] = (french_title, source)
        print(
            f"Wikipedia checked {min(offset + len(batch), len(ordered))}/{len(ordered)}",
            flush=True,
        )
        time.sleep(0.1)
    return results, entity_ids


def french_wikidata_labels(entity_ids: set[str]) -> dict[str, tuple[str, str]]:
    results = {}
    ordered = sorted(entity_ids)
    for offset in range(0, len(ordered), 50):
        batch = ordered[offset:offset + 50]
        payload = request_with_retries(WIKIDATA_API, {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(batch),
            "props": "labels|sitelinks",
            "languages": "fr",
            "sitefilter": "frwiki",
        })
        for entity_id, entity in payload.get("entities", {}).items():
            sitelink = entity.get("sitelinks", {}).get("frwiki", {})
            label = entity.get("labels", {}).get("fr", {}).get("value")
            french_title = sitelink.get("title") or label
            if not french_title:
                continue
            source = (
                "https://fr.wikipedia.org/wiki/"
                + urllib.parse.quote(french_title.replace(" ", "_"))
                if sitelink.get("title")
                else f"https://www.wikidata.org/wiki/{entity_id}"
            )
            results[entity_id] = (french_title, source)
    return results


def clean_french_title(title: str) -> str:
    title = title.replace("_", " ").strip()
    title = re.sub(r"\s*\([^)]*(?:anatomie|biologie|humain|médecine|muscle|os)\)\s*$", "", title, flags=re.I)
    return title[:1].upper() + title[1:] if title else title


def add_side(french_term: str, side: str | None) -> str:
    if not side:
        return french_term
    if side == "left":
        adjective = "gauche"
    else:
        feminine_starts = (
            "artère ", "veine ", "glande ", "fissure ", "fosse ", "face ",
            "branche ", "tête ", "queue ", "lame ", "membrane ", "zone ",
            "cavité ", "bourse ", "capsule ", "cochlée ", "moelle ", "trompe ",
            "épine ", "crête ", "suture ", "racine ", "partie ", "paroi ",
            "aile ", "articulation ", "scissure ", "loge ",
        )
        adjective = "droite" if french_term.casefold().startswith(feminine_starts) else "droit"
    return f"{french_term} {adjective}"


def main() -> None:
    original_terms = collect_terms()
    wikipedia_sources = {}
    wikidata_sources = {}
    for original, source in SOURCED_LATIN_SOURCES.items():
        if "wikipedia.org/wiki/" in source:
            title = urllib.parse.unquote(source.rsplit("/wiki/", 1)[1]).replace("_", " ")
            wikipedia_sources[original] = title
        elif match := re.search(r"/(Q\d+)$", source):
            wikidata_sources[original] = match.group(1)

    canonical_titles = {
        canonical[:1].upper() + canonical[1:]
        for _, canonical in original_terms.values()
    }
    source_titles = set(wikipedia_sources.values())
    title_results, title_entities = french_wikipedia_titles(
        source_titles | canonical_titles
    )
    entity_results = french_wikidata_labels(
        set(wikidata_sources.values()) | set(title_entities.values())
    )

    mapped = {}
    sources = {}
    for original, (side, canonical) in sorted(original_terms.items()):
        match = None
        if original in wikipedia_sources:
            source_key = wikipedia_sources[original].casefold()
            match = title_results.get(source_key)
            if not match and source_key in title_entities:
                match = entity_results.get(title_entities[source_key])
        elif original in wikidata_sources:
            match = entity_results.get(wikidata_sources[original])
        if not match:
            match = title_results.get(canonical.casefold())
        if not match and canonical.casefold() in title_entities:
            match = entity_results.get(title_entities[canonical.casefold()])
        if not match:
            continue
        french_term, source = match
        mapped[original] = add_side(clean_french_title(french_term), side)
        sources[original] = source

    header = (
        "# Generated by scripts/build_wikidata_french_terms.py.\n"
        "# French anatomy names come from French Wikipedia language links or\n"
        "# Wikidata French labels. Every value retains its verification source.\n\n"
    )
    with open(OUTPUT_PATH, "w", encoding="utf-8") as output:
        output.write(header)
        output.write("SOURCED_FRENCH_TERMS = ")
        output.write(pprint.pformat(mapped, width=120, sort_dicts=True))
        output.write("\n\nSOURCED_FRENCH_SOURCES = ")
        output.write(pprint.pformat(sources, width=120, sort_dicts=True))
        output.write("\n")

    print(f"Wrote {len(mapped)}/{len(original_terms)} sourced French terms to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
