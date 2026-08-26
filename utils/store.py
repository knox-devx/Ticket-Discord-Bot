"""Persistência simples em JSON para configurações e tickets.

Mantido e adaptado por Knox Dev.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
CONFIGS_FILE = DATA_DIR / "configs.json"
TICKETS_FILE = DATA_DIR / "tickets.json"


def _ensure() -> None:
    """Garante que a pasta de dados exista antes de ler ou salvar arquivos."""
    DATA_DIR.mkdir(exist_ok=True)


# ── Configurações dos servidores ───────────────────────────────

def _load_configs() -> dict:
    _ensure()
    if not CONFIGS_FILE.exists():
        return {}
    try:
        return json.loads(CONFIGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_configs(data: dict) -> None:
    _ensure()
    CONFIGS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def get_config(guild_id: int) -> dict | None:
    return _load_configs().get(str(guild_id))


def set_config(guild_id: int, config: dict) -> None:
    configs = _load_configs()
    configs[str(guild_id)] = config
    _save_configs(configs)


# ── Registros de tickets ───────────────────────────────────────

def _load_tickets() -> dict:
    _ensure()
    if not TICKETS_FILE.exists():
        return {}
    try:
        return json.loads(TICKETS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_tickets(data: dict) -> None:
    _ensure()
    TICKETS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def get_ticket(channel_id: int) -> dict | None:
    return _load_tickets().get(str(channel_id))


def get_user_open_count(guild_id: int, user_id: int) -> int:
    tickets = _load_tickets()
    return sum(
        1
        for ticket in tickets.values()
        if ticket["guild_id"] == str(guild_id)
        and ticket["author_id"] == str(user_id)
        and ticket["status"] == "open"
    )


def next_ticket_number(guild_id: int) -> int:
    tickets = _load_tickets()
    numbers = [
        ticket.get("number", 0)
        for ticket in tickets.values()
        if ticket["guild_id"] == str(guild_id)
    ]
    return (max(numbers) if numbers else 0) + 1


def create_ticket(channel_id: int, data: dict) -> None:
    tickets = _load_tickets()
    tickets[str(channel_id)] = {
        **data,
        "status": "open",
        "created_at": time.time(),
    }
    _save_tickets(tickets)


def update_ticket(channel_id: int, updates: dict) -> None:
    tickets = _load_tickets()
    key = str(channel_id)
    if key in tickets:
        tickets[key].update(updates)
        _save_tickets(tickets)


def delete_ticket(channel_id: int) -> None:
    tickets = _load_tickets()
    tickets.pop(str(channel_id), None)
    _save_tickets(tickets)
