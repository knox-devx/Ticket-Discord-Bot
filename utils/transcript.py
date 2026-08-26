"""Gerador de transcripts HTML para tickets.

Mantido e adaptado por Knox Dev.
"""

from __future__ import annotations

import datetime
import html
import io

import discord

from utils.config import BOT_NAME, DEVELOPER_NAME


async def generate_transcript(channel: discord.TextChannel) -> discord.File:
    """Gera um arquivo HTML com todo o histórico disponível do canal."""
    messages: list[discord.Message] = []
    async for message in channel.history(limit=None, oldest_first=True):
        messages.append(message)

    html_content = _build_html(channel, messages)
    buffer = io.BytesIO(html_content.encode("utf-8"))
    return discord.File(buffer, filename=f"transcript-{channel.name}.html")


def _build_html(channel: discord.TextChannel, messages: list[discord.Message]) -> str:
    """Monta o HTML do transcript com conteúdo escapado por segurança."""
    rows = ""
    for message in messages:
        if message.author.bot and not message.embeds and not message.content:
            continue

        timestamp = message.created_at.strftime("%d/%m/%Y %H:%M:%S UTC")
        avatar = html.escape(str(message.author.display_avatar.url), quote=True)
        author = html.escape(message.author.display_name)
        content = html.escape(message.content or "").replace("\n", "<br>")

        attachments = ""
        for attachment in message.attachments:
            url = html.escape(attachment.url, quote=True)
            filename = html.escape(attachment.filename)
            attachments += f'<a href="{url}" target="_blank" rel="noreferrer">[Anexo: {filename}]</a> '

        embed_parts: list[str] = []
        for embed in message.embeds:
            parts: list[str] = []
            if embed.title:
                parts.append(f"<strong>{html.escape(embed.title)}</strong>")
            if embed.description:
                parts.append(html.escape(embed.description).replace("\n", "<br>"))
            embed_parts.append(
                f'<span class="embed-note">[Embed: {" — ".join(parts) if parts else "sem conteúdo"}]</span>'
            )

        embed_note = " ".join(embed_parts)
        if embed_note and content:
            embed_note += " "

        rows += f"""
        <div class="message">
          <img class="avatar" src="{avatar}" alt="Avatar"/>
          <div class="body">
            <span class="author">{author}</span>
            <span class="ts">{timestamp}</span>
            <p>{embed_note}{content}{attachments}</p>
          </div>
        </div>"""

    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    safe_bot_name = html.escape(BOT_NAME)
    safe_developer = html.escape(DEVELOPER_NAME)
    safe_channel = html.escape(channel.name)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Transcript • #{safe_channel}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #1e1f22; color: #dbdee1; font-family: 'Segoe UI', sans-serif; padding: 32px; }}
  header {{ margin-bottom: 24px; border-bottom: 1px solid #3f4147; padding-bottom: 16px; }}
  header h1 {{ color: #fff; font-size: 1.4rem; }}
  header p {{ color: #888; font-size: 0.85rem; margin-top: 4px; }}
  .brand {{ color: #5865f2; font-weight: 600; }}
  .message {{ display: flex; gap: 14px; margin-bottom: 20px; }}
  .avatar {{ width: 40px; height: 40px; border-radius: 50%; flex-shrink: 0; }}
  .body {{ flex: 1; }}
  .author {{ font-weight: 700; color: #fff; margin-right: 8px; }}
  .ts {{ font-size: 0.72rem; color: #72767d; }}
  p {{ margin-top: 4px; line-height: 1.5; word-break: break-word; }}
  .embed-note {{ color: #5865f2; font-style: italic; }}
  a {{ color: #00b0f4; }}
  footer {{ margin-top: 32px; border-top: 1px solid #3f4147; padding-top: 12px; font-size: 0.78rem; color: #777; }}
</style>
</head>
<body>
<header>
  <h1>Transcript — <span style="color:#5865f2">#{safe_channel}</span></h1>
  <p>Gerado em {generated} &nbsp;•&nbsp; <span class="brand">{safe_bot_name}</span> &nbsp;•&nbsp; mantido por {safe_developer}</p>
</header>
{rows}
<footer>{safe_bot_name} • Mantido por {safe_developer} • {generated}</footer>
</body>
</html>"""
