"""
╔══════════════════════════════════════════════════╗
║            Sistema de Tickets Discord            ║
║            Mantido por Knox Dev                  ║
║            discord.py 2.7+ • Python 3.10+        ║
╚══════════════════════════════════════════════════╝
"""

from __future__ import annotations

import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils.config import BOT_NAME, DEVELOPER_NAME
from utils.emojis import mark_emojis_ready, start_background_sync, sync_application_emojis

load_dotenv()

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError(
        "TOKEN não encontrado no .env — copie .env.example para .env e configure o token."
    )

# ── Logs ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger("ticket_bot")

# ── Intents ────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# ── Bot ────────────────────────────────────────────────────────
bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
    case_insensitive=True,
)

COGS = ["cogs.setup", "cogs.tickets"]
_emojis_initialized = False
_startup_lock = asyncio.Lock()


@bot.event
async def on_ready() -> None:
    """Finaliza a inicialização e sincroniza recursos do aplicativo."""
    global _emojis_initialized

    async with _startup_lock:
        if not _emojis_initialized:
            try:
                emoji_map = await sync_application_emojis(bot, TOKEN)
                LOGGER.info("%s emojis disponíveis para uso.", len(emoji_map))
            except Exception as exc:
                # O bot continua online mesmo se o CDN/API estiver temporariamente
                # indisponível; nesse caso usa os IDs de origem como fallback.
                LOGGER.exception("Falha na sincronização inicial de emojis: %s", exc)
            finally:
                # Mesmo com fallback, as views podem ser registradas imediatamente.
                mark_emojis_ready()
                # A rotina em segundo plano tenta novamente sem exigir reinício.
                start_background_sync(bot, TOKEN)

            try:
                synced = await bot.tree.sync()
                LOGGER.info("%s comando(s) slash sincronizado(s).", len(synced))
            except Exception as exc:
                LOGGER.exception("Falha ao sincronizar comandos slash: %s", exc)

            _emojis_initialized = True

    print("=" * 58)
    print(f"  {BOT_NAME}")
    print(f"  Usuário  : {bot.user}")
    print(f"  ID       : {bot.user.id if bot.user else 'indisponível'}")
    print(f"  Servidores: {len(bot.guilds)}")
    print(f"  Dev      : {DEVELOPER_NAME}")
    print("=" * 58)


async def main() -> None:
    """Carrega as extensões e inicia o cliente Discord."""
    async with bot:
        for cog in COGS:
            try:
                await bot.load_extension(cog)
                LOGGER.info("Extensão carregada: %s", cog)
            except Exception as exc:
                LOGGER.exception("Falha ao carregar %s: %s", cog, exc)
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
