"""Sincronização automática dos emojis pertencentes ao aplicativo Discord.

Os IDs em ``EMOJI_SOURCES`` apontam para os emojis de origem fornecidos pelo
Knox Dev. O bot copia os arquivos pelo CDN oficial do Discord para a própria
aplicação e mantém um mapa em memória com os IDs novos. Assim, os comandos
sempre consultam o ID atual sem depender de reinicialização para atualizar o
mapa depois de uma sincronização.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import aiohttp
import discord

LOGGER = logging.getLogger("ticket_bot.emojis")
API_BASE = "https://discord.com/api/v10"
SYNC_INTERVAL_SECONDS = 300

# Nome -> ID do emoji de origem. Todos foram fornecidos pelo Knox Dev.
EMOJI_SOURCES: dict[str, int] = {
    "Hammer": 1513729240699502714,
    "Logs": 1517892797749923961,
    "Moderation": 1513729443661746378,
    "Setup": 1518064603223822466,
    "TbotBug": 1518063885855358996,
    "Tick": 1513732705504854237,
    "Warning": 1517892973482868960,
    "antinuke": 1513728862176149516,
    "apply": 1517892619005329579,
    "automod": 1513729764773462058,
    "backk": 1514497444556312599,
    "claim": 1518064508948447242,
    "close": 1518063747950841866,
    "currency": 1514603922944294922,
    "customize": 1518065679041957989,
    "delete": 1518064106723217418,
    "giveaway": 1513731529279406222,
    "home": 1514491720258293831,
    "idle": 1514493041593942051,
    "level": 1514604359663616061,
    "mikon_owner": 1514498484810809404,
    "module": 1514491499457544314,
    "music": 1513730122715238451,
    "next": 1514493258527412244,
    "pause": 1514497665981874299,
    "premium": 1514498380468846622,
    "question_mark": 1518064034862076007,
    "report": 1518042472683540592,
    "settings": 1517893029157933168,
    "setup": 1518064880769568828,
    "stop": 1514497792775553115,
    "success": 1518137986095644703,
    "t_latency": 1517564528043495675,
    "ticket": 1513730006910500977,
    "ticket_reopen": 1518064251405733898,
    "users": 1517893134887944204,
    "view": 1518064705854373969,
    "warn": 1518063335923257386,
    "wickk": 1518137821355966494,
    "wifi": 1513732038446940430,
}

# Começa apontando para os emojis de origem. Após a sincronização, cada valor
# é substituído pelo ID do emoji pertencente à própria aplicação.
_current_ids: dict[str, int] = dict(EMOJI_SOURCES)
_sync_lock = asyncio.Lock()
_ready_event = asyncio.Event()
_background_task: asyncio.Task[None] | None = None


def emoji(name: str) -> str:
    """Retorna a menção do emoji usando sempre o ID mais recente conhecido."""
    emoji_id = _current_ids.get(name) or EMOJI_SOURCES.get(name)
    if not emoji_id:
        return "❔"
    return f"<:{name}:{emoji_id}>"


async def wait_until_emojis_ready() -> None:
    """Aguarda a primeira tentativa de sincronização antes de montar views."""
    await _ready_event.wait()


def mark_emojis_ready() -> None:
    """Libera as views mesmo quando a primeira sincronização usa o fallback."""
    _ready_event.set()


async def _request_json(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, Any] | None = None,
    attempts: int = 4,
) -> tuple[int, Any]:
    """Executa uma requisição respeitando respostas 429 do Discord."""
    last_data: Any = None
    for attempt in range(attempts):
        async with session.request(method, url, headers=headers, json=json) as response:
            if response.status == 204:
                return response.status, None
            try:
                last_data = await response.json(content_type=None)
            except Exception:
                last_data = await response.text()

            if response.status != 429:
                return response.status, last_data

            retry_after = 1.5
            if isinstance(last_data, dict):
                try:
                    retry_after = float(last_data.get("retry_after", retry_after))
                except (TypeError, ValueError):
                    pass
            LOGGER.warning("Limite de requisições atingido; nova tentativa em %.2fs.", retry_after)
            await asyncio.sleep(retry_after + 0.25)

    return 429, last_data


async def _download_source_emoji(
    session: aiohttp.ClientSession,
    source_id: int,
) -> tuple[bytes, str]:
    """Baixa a imagem original diretamente do CDN oficial do Discord."""
    url = f"https://cdn.discordapp.com/emojis/{source_id}.png?size=128&quality=lossless"
    async with session.get(url) as response:
        if response.status != 200:
            raise RuntimeError(f"CDN retornou HTTP {response.status} para o emoji {source_id}")
        content_type = response.headers.get("Content-Type", "image/png").split(";", 1)[0]
        return await response.read(), content_type


async def sync_application_emojis(bot: discord.Client, token: str) -> dict[str, int]:
    """Cria emojis ausentes no aplicativo e atualiza o mapa local de IDs.

    A sincronização é idempotente: emojis que já existem com o mesmo nome não
    são recriados. Se alguém apagar um emoji da aplicação, a próxima rodada o
    cria novamente automaticamente.
    """
    if not bot.user:
        raise RuntimeError("O usuário do bot ainda não está disponível para sincronizar emojis.")

    async with _sync_lock:
        app_id = bot.application_id or bot.user.id
        headers = {
            "Authorization": f"Bot {token}",
            "User-Agent": "KnoxDev-TicketBot/1.0",
        }
        timeout = aiohttp.ClientTimeout(total=45)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            list_url = f"{API_BASE}/applications/{app_id}/emojis"
            status, data = await _request_json(session, "GET", list_url, headers=headers)
            if status != 200 or not isinstance(data, dict):
                raise RuntimeError(f"Falha ao listar emojis do aplicativo: HTTP {status} - {data}")

            existing = {
                str(item.get("name")).lower(): int(item["id"])
                for item in data.get("items", [])
                if item.get("name") and item.get("id")
            }

            created = 0
            for name, source_id in EMOJI_SOURCES.items():
                lookup_name = name.lower()
                if lookup_name in existing:
                    _current_ids[name] = existing[lookup_name]
                    continue

                try:
                    image_bytes, mime_type = await _download_source_emoji(session, source_id)
                    encoded = base64.b64encode(image_bytes).decode("ascii")
                    payload = {
                        "name": name,
                        "image": f"data:{mime_type};base64,{encoded}",
                    }
                    status, created_data = await _request_json(
                        session,
                        "POST",
                        list_url,
                        headers=headers,
                        json=payload,
                    )
                    if status in (200, 201) and isinstance(created_data, dict) and created_data.get("id"):
                        new_id = int(created_data["id"])
                        _current_ids[name] = new_id
                        existing[lookup_name] = new_id
                        created += 1
                        LOGGER.info("Emoji '%s' adicionado ao aplicativo com ID %s.", name, new_id)
                    else:
                        LOGGER.error("Não foi possível criar '%s': HTTP %s - %s", name, status, created_data)
                except Exception as exc:
                    LOGGER.exception("Falha ao sincronizar o emoji '%s': %s", name, exc)

            # Atualiza também nomes existentes que possam ter recebido novo ID
            # manualmente no Developer Portal entre duas sincronizações.
            status, refreshed = await _request_json(session, "GET", list_url, headers=headers)
            if status == 200 and isinstance(refreshed, dict):
                for item in refreshed.get("items", []):
                    item_name = item.get("name")
                    item_id = item.get("id")
                    if item_name and item_id:
                        source_name = next(
                            (name for name in EMOJI_SOURCES if name.lower() == str(item_name).lower()),
                            None,
                        )
                        if source_name:
                            _current_ids[source_name] = int(item_id)

        _ready_event.set()
        LOGGER.info(
            "Sincronização de emojis concluída: %s criados, %s disponíveis.",
            created,
            len(_current_ids),
        )
        return dict(_current_ids)


async def _background_sync(bot: discord.Client, token: str) -> None:
    """Mantém os emojis sincronizados enquanto o processo estiver online."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
        try:
            await sync_application_emojis(bot, token)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.exception("Sincronização automática de emojis falhou: %s", exc)


def start_background_sync(bot: discord.Client, token: str) -> None:
    """Inicia apenas uma tarefa de sincronização periódica por processo."""
    global _background_task
    if _background_task and not _background_task.done():
        return
    _background_task = asyncio.create_task(_background_sync(bot, token), name="emoji-auto-sync")
