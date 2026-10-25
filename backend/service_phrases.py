from __future__ import annotations

import re

from backend.fixtures import ServiceFixture


_TOKEN = re.compile(r"[a-z0-9]+")


def normalize_service_phrase(text: str) -> tuple[str, ...]:
    tokens = tuple(
        "trim" if token == "trimming" else token
        for token in _TOKEN.findall(text.casefold())
    )
    return tuple(
        token
        for index, token in enumerate(tokens)
        if not (
            token == "my"
            and index > 0
            and index + 1 < len(tokens)
            and tokens[index - 1] == "trim"
            and tokens[index + 1] == "beard"
        )
    )


def service_aliases(service: ServiceFixture) -> tuple[str, ...]:
    aliases = [service.name]
    if service.service_id == "haircut":
        aliases.append("hair cut")
    elif service.service_id == "beard-trim":
        aliases.extend(("trim beard", "trim my beard", "beard trimming"))
    elif service.service_id == "haircut-beard":
        aliases.extend(
            (
                "haircut and beard trim",
                "haircut beard trim",
                "haircut and beard",
                "haircut and beard combo",
                "haircut beard combo",
                "haircut with beard trim",
            )
        )
    return tuple(dict.fromkeys(aliases))


def mentioned_service_ids(
    text: str,
    services: tuple[ServiceFixture, ...],
) -> tuple[str, ...]:
    tokens = normalize_service_phrase(text)
    matches: list[tuple[int, int, str]] = []
    for service in services:
        for alias in service_aliases(service):
            alias_tokens = normalize_service_phrase(alias)
            if not alias_tokens:
                continue
            for start in range(len(tokens) - len(alias_tokens) + 1):
                if tokens[start : start + len(alias_tokens)] == alias_tokens:
                    matches.append(
                        (start, start + len(alias_tokens), service.service_id)
                    )

    selected: list[tuple[int, int, str]] = []
    for match in sorted(
        matches,
        key=lambda item: (item[0], -(item[1] - item[0]), item[2]),
    ):
        start, end, _ = match
        if not any(
            start < selected_end and end > selected_start
            for selected_start, selected_end, _ in selected
        ):
            selected.append(match)
    return tuple(dict.fromkeys(service_id for _, _, service_id in selected))
