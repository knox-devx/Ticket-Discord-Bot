from __future__ import annotations

import re

import discord
from discord import app_commands
from discord.ext import commands

from utils.config import BOT_NAME, BRAND_FULL, DEVELOPER_NAME
from utils.emojis import emoji, wait_until_emojis_ready
from utils.store import (
    create_ticket,
    delete_ticket,
    get_config,
    get_ticket,
    get_user_open_count,
    next_ticket_number,
    update_ticket,
)
from utils.transcript import generate_transcript

DEFAULT_CATEGORIES = ["Suporte Geral", "Resgatar Sorteio", "Reportar Bug", "Outro"]
CATEGORY_EMOJIS = {
    "Suporte Geral": "question_mark",
    "Resgatar Sorteio": "giveaway",
    "Reportar Bug": "TbotBug",
    "Outro": "customize",
}


def _safe_channel_name(text: str) -> str:
    """Converte nomes para um formato aceito em canais do Discord."""
    text = text.lower().strip().replace(" ", "-")
    text = re.sub(r"[^a-z0-9-]", "", text)
    return text[:60] or "usuario"


def build_panel_embed(guild: discord.Guild, config: dict) -> discord.Embed:
    """Monta o painel de abertura de tickets."""
    categories = config.get("active_categories", DEFAULT_CATEGORIES)
    lines = []
    for category in categories:
        name = CATEGORY_EMOJIS.get(category, "ticket")
        lines.append(f"{emoji(name)} **{category}**")

    embed = discord.Embed(
        title=config.get("panel_title", "Central de Suporte"),
        description=(
            f"{config.get('panel_description', 'Escolha uma categoria para abrir um ticket.')}\n\n"
            + "\n".join(lines)
        ),
        color=discord.Color.blurple(),
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text=BRAND_FULL)
    return embed


async def send_log(guild: discord.Guild, config: dict, title: str, description: str) -> None:
    """Envia um evento para o canal de logs, quando configurado."""
    log_id = config.get("log_channel_id")
    if not log_id:
        return
    channel = guild.get_channel(int(log_id))
    if not isinstance(channel, discord.TextChannel):
        return
    embed = discord.Embed(title=title, description=description, color=discord.Color.dark_embed())
    embed.set_footer(text=BRAND_FULL)
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


async def open_ticket(interaction: discord.Interaction, category: str) -> None:
    """Cria o canal privado e registra o ticket."""
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return

    config = get_config(interaction.guild.id)
    if not config:
        await interaction.response.send_message(
            f"{emoji('warn')} O sistema ainda não foi configurado.",
            ephemeral=True,
        )
        return

    limit = int(config.get("ticket_limit", 3))
    if get_user_open_count(interaction.guild.id, interaction.user.id) >= limit:
        await interaction.response.send_message(
            f"{emoji('warn')} Você já atingiu o limite de **{limit}** tickets abertos.",
            ephemeral=True,
        )
        return

    ticket_category = interaction.guild.get_channel(int(config["ticket_category_id"]))
    support_role = interaction.guild.get_role(int(config["support_role_id"]))
    if not isinstance(ticket_category, discord.CategoryChannel) or not support_role:
        await interaction.response.send_message(
            f"{emoji('warn')} A configuração do servidor está incompleta.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    number = next_ticket_number(interaction.guild.id)
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
        ),
        support_role: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_messages=True,
        ),
        interaction.guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            read_message_history=True,
        ),
    }

    channel = await interaction.guild.create_text_channel(
        name=f"ticket-{number:04d}-{_safe_channel_name(interaction.user.display_name)}",
        category=ticket_category,
        overwrites=overwrites,
        topic=f"Ticket #{number:04d} | Autor: {interaction.user.id} | Categoria: {category}",
        reason=f"Ticket aberto por {interaction.user}",
    )

    create_ticket(
        channel.id,
        {
            "guild_id": str(interaction.guild.id),
            "author_id": str(interaction.user.id),
            "number": number,
            "category": category,
            "claimed_by": None,
        },
    )

    form_instruction = str(config.get("forms", {}).get(category, "")).strip()
    extra_instruction = (
        f"\n\n**Instruções deste atendimento:**\n{form_instruction}"
        if form_instruction
        else ""
    )
    embed = discord.Embed(
        title=f"{emoji('ticket')} Ticket #{number:04d}",
        description=(
            f"Olá {interaction.user.mention}! Seu ticket foi criado.\n\n"
            f"**Categoria:** {category}\n"
            f"**Equipe:** {support_role.mention}\n\n"
            "Explique com detalhes o que você precisa."
            f"{extra_instruction}"
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=BRAND_FULL)
    await channel.send(
        content=f"{interaction.user.mention} {support_role.mention}",
        embed=embed,
        view=TicketControlView(),
        allowed_mentions=discord.AllowedMentions(users=True, roles=True),
    )

    await send_log(
        interaction.guild,
        config,
        f"{emoji('ticket')} Ticket aberto",
        f"{interaction.user.mention} abriu {channel.mention} em **{category}**.",
    )
    await interaction.followup.send(
        f"{emoji('success')} Ticket criado: {channel.mention}",
        ephemeral=True,
    )


async def close_ticket(interaction: discord.Interaction) -> None:
    """Fecha o ticket atual removendo o acesso do autor."""
    if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
        return
    ticket = get_ticket(interaction.channel.id)
    if not ticket:
        await interaction.response.send_message(
            f"{emoji('warn')} Este canal não é um ticket.",
            ephemeral=True,
        )
        return

    author = interaction.guild.get_member(int(ticket["author_id"]))
    if author:
        await interaction.channel.set_permissions(author, view_channel=False)

    update_ticket(interaction.channel.id, {"status": "closed"})
    await interaction.response.send_message(
        f"{emoji('close')} Ticket fechado por {interaction.user.mention}.",
        view=ClosedTicketView(),
    )

    config = get_config(interaction.guild.id) or {}
    await send_log(
        interaction.guild,
        config,
        f"{emoji('close')} Ticket fechado",
        f"{interaction.channel.mention} foi fechado por {interaction.user.mention}.",
    )


class CategorySelect(discord.ui.Select):
    def __init__(self, categories: list[str]) -> None:
        options = [
            discord.SelectOption(
                label=category[:100],
                value=category,
                emoji=emoji(CATEGORY_EMOJIS.get(category, "ticket")),
            )
            for category in categories[:10]
        ]
        super().__init__(
            placeholder="Selecione uma categoria para abrir o ticket…",
            options=options,
            custom_id="tickets:category_select",
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await open_ticket(interaction, self.values[0])


class TicketPanelView(discord.ui.View):
    """View persistente do painel público."""

    def __init__(self, categories: list[str] | None = None) -> None:
        super().__init__(timeout=None)
        self.add_item(CategorySelect(categories or DEFAULT_CATEGORIES))


class TicketControlView(discord.ui.View):
    """Controles persistentes exibidos dentro de tickets abertos."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Assumir",
        style=discord.ButtonStyle.primary,
        emoji=emoji("claim"),
        custom_id="tickets:claim",
    )
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            return
        ticket = get_ticket(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("Este canal não é um ticket.", ephemeral=True)
            return
        update_ticket(interaction.channel.id, {"claimed_by": str(interaction.user.id)})
        button.disabled = True
        button.label = f"Assumido por {interaction.user.display_name}"[:80]
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"{emoji('claim')} Ticket assumido por {interaction.user.mention}."
        )

    @discord.ui.button(
        label="Fechar",
        style=discord.ButtonStyle.danger,
        emoji=emoji("close"),
        custom_id="tickets:close",
    )
    async def close(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await close_ticket(interaction)


class ClosedTicketView(discord.ui.View):
    """Controles persistentes exibidos após o fechamento."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Reabrir",
        style=discord.ButtonStyle.success,
        emoji=emoji("ticket_reopen"),
        custom_id="tickets:reopen",
    )
    async def reopen(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return
        ticket = get_ticket(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("Este canal não é um ticket.", ephemeral=True)
            return
        author = interaction.guild.get_member(int(ticket["author_id"]))
        if author:
            await interaction.channel.set_permissions(
                author,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )
        update_ticket(interaction.channel.id, {"status": "open"})
        await interaction.response.send_message(
            f"{emoji('ticket_reopen')} Ticket reaberto por {interaction.user.mention}.",
            view=TicketControlView(),
        )

    @discord.ui.button(
        label="Excluir",
        style=discord.ButtonStyle.danger,
        emoji=emoji("delete"),
        custom_id="tickets:delete",
    )
    async def delete(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return
        ticket = get_ticket(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("Este canal não é um ticket.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        author = interaction.guild.get_member(int(ticket["author_id"]))
        try:
            transcript = await generate_transcript(interaction.channel)
            if author:
                await author.send(
                    f"{emoji('Logs')} Transcript do seu ticket em **{interaction.guild.name}**:",
                    file=transcript,
                )
        except (discord.HTTPException, discord.Forbidden):
            pass

        config = get_config(interaction.guild.id) or {}
        await send_log(
            interaction.guild,
            config,
            f"{emoji('delete')} Ticket excluído",
            f"`#{interaction.channel.name}` foi excluído por {interaction.user.mention}.",
        )
        delete_ticket(interaction.channel.id)
        await interaction.channel.delete(reason=f"Ticket excluído por {interaction.user}")


class TicketsCog(commands.Cog):
    """Comandos e views do sistema de tickets."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._views_registered = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._views_registered:
            return
        await wait_until_emojis_ready()
        # As views são registradas uma única vez para sobreviver a reconexões.
        self.bot.add_view(TicketPanelView())
        self.bot.add_view(TicketControlView())
        self.bot.add_view(ClosedTicketView())
        self._views_registered = True

    @app_commands.command(name="close", description="Feche o ticket atual")
    async def close_cmd(self, interaction: discord.Interaction) -> None:
        await close_ticket(interaction)

    @app_commands.command(name="add", description="Adicione um membro ao ticket")
    @app_commands.describe(membro="Membro que receberá acesso")
    async def add_member(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        if not isinstance(interaction.channel, discord.TextChannel) or not get_ticket(interaction.channel.id):
            await interaction.response.send_message("Este canal não é um ticket.", ephemeral=True)
            return
        await interaction.channel.set_permissions(
            membro,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
        )
        await interaction.response.send_message(
            f"{emoji('users')} {membro.mention} foi adicionado ao ticket."
        )

    @app_commands.command(name="remove", description="Remova um membro do ticket")
    @app_commands.describe(membro="Membro que perderá o acesso")
    async def remove_member(self, interaction: discord.Interaction, membro: discord.Member) -> None:
        if not isinstance(interaction.channel, discord.TextChannel) or not get_ticket(interaction.channel.id):
            await interaction.response.send_message("Este canal não é um ticket.", ephemeral=True)
            return
        await interaction.channel.set_permissions(membro, overwrite=None)
        await interaction.response.send_message(
            f"{emoji('users')} {membro.mention} foi removido do ticket."
        )

    @app_commands.command(name="transcript", description="Gere um transcript HTML do ticket")
    async def transcript_cmd(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.channel, discord.TextChannel) or not get_ticket(interaction.channel.id):
            await interaction.response.send_message("Este canal não é um ticket.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        transcript = await generate_transcript(interaction.channel)
        await interaction.followup.send(
            f"{emoji('Logs')} Transcript gerado.",
            file=transcript,
            ephemeral=True,
        )

    @app_commands.command(name="ticketinfo", description="Veja informações do ticket atual")
    async def ticket_info(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            return
        ticket = get_ticket(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("Este canal não é um ticket.", ephemeral=True)
            return

        author = interaction.guild.get_member(int(ticket["author_id"])) if interaction.guild else None
        claimed = ticket.get("claimed_by")
        claimer = interaction.guild.get_member(int(claimed)) if interaction.guild and claimed else None
        embed = discord.Embed(
            title=f"{emoji('view')} Ticket #{int(ticket.get('number', 0)):04d}",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Autor", value=author.mention if author else ticket["author_id"], inline=False)
        embed.add_field(name="Categoria", value=ticket.get("category", "Desconhecida"), inline=True)
        embed.add_field(name="Status", value=ticket.get("status", "open"), inline=True)
        embed.add_field(name="Assumido por", value=claimer.mention if claimer else "Ninguém", inline=False)
        embed.set_footer(text=BRAND_FULL)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="setform", description="Defina uma instrução personalizada para uma categoria")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(categoria="Categoria", instrucoes="Texto mostrado quando o ticket for aberto")
    async def setform(self, interaction: discord.Interaction, categoria: str, instrucoes: str) -> None:
        """Salva instruções personalizadas que aparecem ao abrir a categoria."""
        config = get_config(interaction.guild.id) or {}
        forms = config.setdefault("forms", {})
        forms[categoria] = instrucoes[:1500]
        from utils.store import set_config
        set_config(interaction.guild.id, config)
        await interaction.response.send_message(
            f"{emoji('success')} Instruções de **{categoria}** salvas.",
            ephemeral=True,
        )

    @app_commands.command(name="help", description=f"Veja os comandos e recursos do {BOT_NAME}")
    async def help_cmd(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title=f"{emoji('question_mark')} {BOT_NAME} — Ajuda",
            description=(
                "**Usuários**\n"
                "`/help` — mostra esta ajuda\n\n"
                "**Tickets**\n"
                "`/close` — fecha o ticket\n"
                "`/add` — adiciona um membro\n"
                "`/remove` — remove um membro\n"
                "`/transcript` — gera transcript HTML\n"
                "`/ticketinfo` — mostra detalhes\n\n"
                "**Administração**\n"
                "`/setup` — configura o sistema\n"
                "`/panel2` — reenvia o painel\n"
                "`/setupinfo` — mostra a configuração\n"
                "`/setform` — salva instruções por categoria"
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Recursos",
            value=(
                "• Painel persistente\n"
                "• Claim / fechar / reabrir / excluir\n"
                "• Logs e transcripts\n"
                "• Limite por usuário\n"
                "• Emojis sincronizados automaticamente\n"
                "• Nome configurável no `.env`"
            ),
            inline=False,
        )
        embed.set_footer(text=f"Mantido e adaptado por {DEVELOPER_NAME}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TicketsCog(bot))
