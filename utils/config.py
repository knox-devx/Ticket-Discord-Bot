"""Configuração central do bot.

As variáveis daqui são carregadas a partir do arquivo ``.env`` para evitar
nomes fixos espalhados pelo projeto.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

BOT_NAME = (os.getenv("BOT_NAME") or "Knox Tickets").strip() or "Knox Tickets"
DEVELOPER_NAME = "Knox Dev"
BRAND_FULL = f"{BOT_NAME} • Mantido por {DEVELOPER_NAME}"
