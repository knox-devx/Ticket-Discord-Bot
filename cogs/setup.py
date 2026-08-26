from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from utils.config import BOT_NAME
from utils.emojis import emoji
from utils.store import get_config, set_config

# Configurações padrão do sistema de tickets.
DEFAULT_CATEGORIES = ["Suporte Geral", "Resgatar Sorteio", "Reportar Bug", "Outro"]

CATEGORY_EMOJIS = {
    "Suporte Geral": "question_mark",
    "Resgatar Sorteio": "giveaway",
    "Reportar Bug": "TbotBug",
    "Outro": "customize",
}


class SetupModal(discord.ui.Modal, title="Configuração do painel de tickets"):
    """Modal principal usado pelo /setup para definir o painel."""

    titulo = discord.ui.TextInput(label="Título do painel", default="Central de Suporte", max_length=100)
    descricao = discord.ui.TextInput(
        label="Descrição do painel", default="Escolha uma categoria abaixo para abrir um ticket.",
        style=discord.TextStyle.paragraph, max_length=500,
    )
    limite = discord.ui.TextInput(label="Limite de tickets por usuário", default="3", max_length=2)
    categorias = discord.ui.TextInput(
        label="Categorias (separe com |)",
        default="Suporte Geral | Resgatar Sorteio | Reportar Bug | Outro",
        style=discord.TextStyle.paragraph, max_length=500,
    )

    def __init__(self, bot: commands.Bot, support_role: discord.Role, panel_channel: discord.TextChannel,
                 ticket_category: discord.CategoryChannel, log_channel: discord.TextChannel | None) -> None:
        super().__init__()
        self.bot = bot
        self.support_role = support_role
        self.panel_channel = panel_channel
        self.ticket_category = ticket_category
        self.log_channel = log_channel

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            ticket_limit = max(1, min(10, int(str(self.limite.value).strip())))
        except ValueError:
            ticket_limit = 3

        categories = [item.strip() for item in str(self.categorias.value).split("|") if item.strip()][:10]
        if not categories:
            categories = DEFAULT_CATEGORIES[:]

        previous_config = get_config(interaction.guild.id) or {}
        config = {
            "support_role_id": str(self.support_role.id),
            "panel_channel_id": str(self.panel_channel.id),
            "ticket_category_id": str(self.ticket_category.id),
            "log_channel_id": str(self.log_channel.id) if self.log_channel else None,
            "ticket_limit": ticket_limit,
            "panel_title": str(self.titulo.value),
            "panel_description": str(self.descricao.value),
            "active_categories": categories,
            # Mantém instruções já configuradas pelo /setform.
            "forms": previous_config.get("forms", {}),
        }
        set_config(interaction.guild.id, config)

        # Importação tardia evita dependência circular entre os cogs.
        from cogs.tickets import TicketPanelView, build_panel_embed

        await self.panel_channel.send(embed=build_panel_embed(interaction.guild, config), view=TicketPanelView(categories))
        await interaction.response.send_message(
            f"{emoji('success')} Painel enviado em {self.panel_channel.mention} e configuração salva.", ephemeral=True
        )


class SetupCog(commands.Cog):
    """Comandos administrativos de configuração."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="setup", description=f"Configure o sistema de tickets do {BOT_NAME}")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        cargo_suporte="Cargo que poderá gerenciar tickets",
        canal_painel="Canal onde o painel será enviado",
        categoria_tickets="Categoria onde os canais de ticket serão criados",
        canal_logs="Canal opcional para registrar eventos",
    )
    async def setup(self, interaction: discord.Interaction, cargo_suporte: discord.Role,
                    canal_painel: discord.TextChannel, categoria_tickets: discord.CategoryChannel,
                    canal_logs: discord.TextChannel | None = None) -> None:
        await interaction.response.send_modal(
            SetupModal(self.bot, cargo_suporte, canal_painel, categoria_tickets, canal_logs)
        )

    @app_commands.command(name="panel2", description="Reenvie o painel de tickets configurado")
    @app_commands.default_permissions(administrator=True)
    async def panel2(self, interaction: discord.Interaction) -> None:
        config = get_config(interaction.guild.id)
        if not config:
            await interaction.response.send_message(f"{emoji('warn')} Execute `/setup` primeiro.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(int(config["panel_channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(f"{emoji('warn')} O canal configurado não existe mais.", ephemeral=True)
            return
        from cogs.tickets import TicketPanelView, build_panel_embed
        categories = config.get("active_categories", DEFAULT_CATEGORIES)
        await channel.send(embed=build_panel_embed(interaction.guild, config), view=TicketPanelView(categories))
        await interaction.response.send_message(f"{emoji('success')} Painel reenviado em {channel.mention}.", ephemeral=True)

    @app_commands.command(name="setupinfo", description="Veja a configuração atual do sistema de tickets")
    @app_commands.default_permissions(administrator=True)
    async def setupinfo(self, interaction: discord.Interaction) -> None:
        config = get_config(interaction.guild.id)
        if not config:
            await interaction.response.send_message(f"{emoji('warn')} Nenhuma configuração foi salva ainda.", ephemeral=True)
            return
        role = interaction.guild.get_role(int(config["support_role_id"]))
        panel = interaction.guild.get_channel(int(config["panel_channel_id"]))
        category = interaction.guild.get_channel(int(config["ticket_category_id"]))
        log_channel = interaction.guild.get_channel(int(config["log_channel_id"])) if config.get("log_channel_id") else None
        embed = discord.Embed(title=f"{emoji('settings')} Configuração do {BOT_NAME}", color=discord.Color.blurple())
        embed.add_field(name="Cargo de suporte", value=role.mention if role else "Não encontrado", inline=False)
        embed.add_field(name="Canal do painel", value=panel.mention if panel else "Não encontrado", inline=False)
        embed.add_field(name="Categoria", value=category.name if category else "Não encontrada", inline=False)
        embed.add_field(name="Logs", value=log_channel.mention if log_channel else "Desativado", inline=False)
        embed.add_field(name="Limite", value=str(config.get("ticket_limit", 3)), inline=True)
        embed.add_field(name="Categorias", value="\n".join(f"• {item}" for item in config.get("active_categories", DEFAULT_CATEGORIES)), inline=False)
        embed.set_footer(text=f"{BOT_NAME} • Knox Dev")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupCog(bot))
