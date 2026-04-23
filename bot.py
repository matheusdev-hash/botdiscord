import os
import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from cinema_agent import CinemaAgent, DEFAULT_STYLE, STYLES
from ratings import save_rating, get_movie_ratings, get_top_movies

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OMDB_API_KEY = os.getenv("OMDB_API_KEY")
RATINGS_CHANNEL = "notas-da-galera"

if not DISCORD_TOKEN or not GROQ_API_KEY:
    raise ValueError("Configure DISCORD_TOKEN e GROQ_API_KEY no arquivo .env")

user_styles: dict[int, str] = {}

STYLE_DISPLAY = {
    "técnico": "🔬 Técnico",
    "emocional": "💙 Emocional",
    "casual": "😎 Casual",
    "ácido": "🔪 Ácido",
    "ação": "💥 Ação",
    "drama": "🎭 Drama",
    "comédia": "😂 Comédia",
    "terror": "👻 Terror",
    "suspense": "🔦 Suspense",
    "romance": "❤️ Romance",
    "ficção científica": "🚀 Ficção Científica",
    "fantasia": "🧙 Fantasia",
    "animação": "🎨 Animação",
    "documentário": "🎥 Documentário",
    "herói": "🦸 Herói",
}

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
cinema = CinemaAgent(GROQ_API_KEY, OMDB_API_KEY)


class RatingModal(discord.ui.Modal, title="Dar minha nota"):
    nota = discord.ui.TextInput(
        label="Sua nota (0 a 10)",
        placeholder="Ex: 8.5",
        min_length=1,
        max_length=4,
    )

    def __init__(self, movie: str):
        super().__init__()
        self.movie = movie

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rating = float(self.nota.value.replace(",", "."))
            if not 0 <= rating <= 10:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "❌ Nota inválida. Use um número entre 0 e 10 (ex: 8.5)",
                ephemeral=True,
            )
            return

        ratings = save_rating(self.movie, interaction.user.id, str(interaction.user.display_name), rating)
        avg = sum(r["rating"] for r in ratings) / len(ratings)
        count = len(ratings)

        await interaction.response.send_message(
            f"✅ Nota **{rating}/10** salva para **{self.movie}**!",
            ephemeral=True,
        )

        channel = discord.utils.get(interaction.guild.text_channels, name=RATINGS_CHANNEL)
        if channel:
            await channel.send(
                f"⭐ **{interaction.user.display_name}** avaliou **{self.movie}**\n"
                f"Nota: **{rating}/10** · "
                f"Média da galera: **{avg:.1f}/10** ({count} avaliação{'ões' if count > 1 else ''})"
            )


class RatingView(discord.ui.View):
    def __init__(self, movie: str):
        super().__init__(timeout=None)
        self.movie = movie

    @discord.ui.button(label="⭐ Dar minha nota", style=discord.ButtonStyle.primary)
    async def rate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RatingModal(self.movie))


@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"⚡ {len(synced)} comando(s) sincronizado(s)")
    except Exception as e:
        print(f"❌ Erro ao sincronizar comandos: {e}")


@bot.tree.command(
    name="cinema",
    description="🎬 Analise um filme ou receba recomendação baseada no seu humor",
)
@app_commands.describe(
    mensagem="Descreva seu humor (ex: 'tô triste') ou cite um filme (ex: 'analisa Oppenheimer')",
    estilo="Estilo do crítico — deixe em branco para usar seu padrão",
)
@app_commands.choices(
    estilo=[
        app_commands.Choice(name="🔬 Técnico — análise profunda e cinematográfica", value="técnico"),
        app_commands.Choice(name="💙 Emocional — foco nos sentimentos e emoções", value="emocional"),
        app_commands.Choice(name="😎 Casual — leve, direto, como um amigo", value="casual"),
        app_commands.Choice(name="🔪 Ácido — crítico, sarcástico e afiado", value="ácido"),
        app_commands.Choice(name="💥 Ação — foco em adrenalina e sequências de ação", value="ação"),
        app_commands.Choice(name="🎭 Drama — foco em personagens e profundidade emocional", value="drama"),
        app_commands.Choice(name="😂 Comédia — foco em humor, timing e leveza", value="comédia"),
        app_commands.Choice(name="👻 Terror — foco em atmosfera, tensão e medo", value="terror"),
        app_commands.Choice(name="🔦 Suspense — foco em tensão, twists e narrativa", value="suspense"),
        app_commands.Choice(name="❤️ Romance — foco em química e emoções do casal", value="romance"),
        app_commands.Choice(name="🚀 Ficção Científica — foco em ideias e world building", value="ficção científica"),
        app_commands.Choice(name="🧙 Fantasia — foco em universo, magia e lore", value="fantasia"),
        app_commands.Choice(name="🎨 Animação — foco em técnica visual e mensagem", value="animação"),
        app_commands.Choice(name="🎥 Documentário — foco em rigor, impacto e ponto de vista", value="documentário"),
        app_commands.Choice(name="🦸 Herói — foco em universo expandido e espetáculo", value="herói"),
    ]
)
async def cinema_command(
    interaction: discord.Interaction,
    mensagem: str,
    estilo: Optional[str] = None,
):
    await interaction.response.defer(thinking=True)

    style = estilo or user_styles.get(interaction.user.id, DEFAULT_STYLE)

    try:
        result = await cinema.analyze(mensagem, style)

        movie_match = re.search(r"🎬 Filme:\s*\[?([^\[\]\n]+?)(?:\s*\(\d{4}\))?\]?(?:\n|$)", result)
        movie_title = movie_match.group(1).strip() if movie_match else "Filme"

        await _send_long_message(interaction, result, movie_title)

    except Exception as e:
        await interaction.followup.send(
            f"❌ Algo deu errado: `{e}`\nTente novamente em alguns segundos.",
            ephemeral=True,
        )


@bot.tree.command(
    name="estilo",
    description="🎭 Define seu estilo padrão de crítica para o /cinema",
)
@app_commands.describe(estilo="Escolha o estilo que será usado por padrão nas suas análises")
@app_commands.choices(
    estilo=[
        app_commands.Choice(name="🔬 Técnico — análise profunda e cinematográfica", value="técnico"),
        app_commands.Choice(name="💙 Emocional — foco nos sentimentos e emoções", value="emocional"),
        app_commands.Choice(name="😎 Casual — leve, direto, como um amigo", value="casual"),
        app_commands.Choice(name="🔪 Ácido — crítico, sarcástico e afiado", value="ácido"),
        app_commands.Choice(name="💥 Ação — foco em adrenalina e sequências de ação", value="ação"),
        app_commands.Choice(name="🎭 Drama — foco em personagens e profundidade emocional", value="drama"),
        app_commands.Choice(name="😂 Comédia — foco em humor, timing e leveza", value="comédia"),
        app_commands.Choice(name="👻 Terror — foco em atmosfera, tensão e medo", value="terror"),
        app_commands.Choice(name="🔦 Suspense — foco em tensão, twists e narrativa", value="suspense"),
        app_commands.Choice(name="❤️ Romance — foco em química e emoções do casal", value="romance"),
        app_commands.Choice(name="🚀 Ficção Científica — foco em ideias e world building", value="ficção científica"),
        app_commands.Choice(name="🧙 Fantasia — foco em universo, magia e lore", value="fantasia"),
        app_commands.Choice(name="🎨 Animação — foco em técnica visual e mensagem", value="animação"),
        app_commands.Choice(name="🎥 Documentário — foco em rigor, impacto e ponto de vista", value="documentário"),
        app_commands.Choice(name="🦸 Herói — foco em universo expandido e espetáculo", value="herói"),
    ]
)
async def estilo_command(
    interaction: discord.Interaction,
    estilo: str,
):
    user_styles[interaction.user.id] = estilo
    await interaction.response.send_message(
        f"✅ Estilo padrão definido como **{STYLE_DISPLAY[estilo]}**!\n"
        f"Agora use `/cinema` sem escolher estilo e este será aplicado automaticamente.",
        ephemeral=True,
    )


@bot.tree.command(
    name="ranking",
    description="🏆 Veja as notas da galera para um filme ou o ranking geral",
)
@app_commands.describe(filme="Nome do filme (opcional — deixe em branco para o ranking geral)")
async def ranking_command(
    interaction: discord.Interaction,
    filme: Optional[str] = None,
):
    if filme:
        ratings, found_title = get_movie_ratings(filme)
        if not ratings:
            await interaction.response.send_message(
                f"Nenhuma avaliação para **{filme}** ainda.", ephemeral=True
            )
            return
        avg = sum(r["rating"] for r in ratings) / len(ratings)
        lines = [f"⭐ **{found_title}** — Média: **{avg:.1f}/10** ({len(ratings)} avaliações)\n"]
        for r in sorted(ratings, key=lambda x: x["rating"], reverse=True):
            lines.append(f"• {r['username']}: **{r['rating']}/10**")
        await interaction.response.send_message("\n".join(lines))
    else:
        top = get_top_movies()
        if not top:
            await interaction.response.send_message(
                "Nenhuma avaliação ainda. Use `/cinema` e dê sua nota!", ephemeral=True
            )
            return
        lines = ["🏆 **Ranking da Galera**\n"]
        for i, m in enumerate(top, 1):
            lines.append(f"{i}. **{m['movie']}** — {m['average']:.1f}/10 ({m['count']} avaliações)")
        await interaction.response.send_message("\n".join(lines))


async def _send_long_message(interaction: discord.Interaction, text: str, movie_title: str = "Filme") -> None:
    view = RatingView(movie_title)

    if len(text) <= 2000:
        await interaction.followup.send(text, view=view)
        return

    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > 1900:
            if current:
                chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)

    await interaction.followup.send(chunks[0])
    for chunk in chunks[1:-1]:
        await interaction.channel.send(chunk)
    await interaction.channel.send(chunks[-1], view=view)


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
