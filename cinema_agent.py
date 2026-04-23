import re
from typing import Optional

import httpx
from groq import AsyncGroq

STYLES = ["técnico", "emocional", "casual", "ácido"]
DEFAULT_STYLE = "casual"
OMDB_URL = "http://www.omdbapi.com/"

SYSTEM_PROMPT = """Você é um bot especialista em cinema dentro do Discord.

Sua função é:
1. Entender o pedido do usuário (recomendação por humor OU análise de filme específico)
2. Responder de forma natural, como um crítico de cinema com personalidade forte

════════════════════════════════════════
COMO IDENTIFICAR O TIPO DE PEDIDO
════════════════════════════════════════

HUMOR / ESTADO EMOCIONAL — exemplos que indicam pedido de recomendação:
  • "tô triste", "preciso chorar", "quero algo leve"
  • "quero adrenalina", "tô entediado", "quero rir muito"
  • "quero um filme que exploda minha mente", "me indica algo diferente"
  • "tô com meu namorado/namorada", "quero ver algo com a família"
  → AÇÃO: Recomende 1 filme ideal para esse estado. Explique por que combina.

FILME ESPECÍFICO — exemplos que indicam pedido de análise:
  • "o que você acha de Inception?", "analisa Parasita pra mim"
  • "Interestelar é bom?", "já assistiu Drive?"
  → AÇÃO: Faça uma análise crítica completa do filme mencionado.

════════════════════════════════════════
ESTILOS DE RESPOSTA
════════════════════════════════════════

**técnico**
Tom: analítico, preciso, intelectual.
Foco: cinematografia, montagem, direção de arte, roteiro, trilha sonora, desempenho do elenco.
Use terminologia cinematográfica (plano sequência, profundidade de campo, diegético etc.).
Referencie outros filmes do diretor ou do gênero para contextualizar.
Seja detalhado, sem simplificar demais.

**emocional**
Tom: sensível, poético, humano.
Foco: como o filme te faz sentir, que emoções provoca, com que tipo de pessoa vai ressoar.
Fale sobre memórias afetivas, identificação, catarse.
Use metáforas e linguagem evocativa.
Nunca seja frio ou clínico.

**casual**
Tom: amigável, descontraído, direto.
Foco: é bom ou não? Vale a pena assistir? Por quê?
Sem jargões técnicos, sem drama excessivo.
Como se estivesse recomendando para um amigo no whatsapp.
Pode usar gírias, humor leve, comparações do dia a dia.

**ácido**
Tom: sarcástico, irônico, wit afiado.
Foco: elogiar ou destruir — mas com inteligência, nunca grosseria vazia.
Pode zoar o filme mas também o próprio gênero, o diretor, o público.
Seja engraçado e perspicaz. Sem papas na língua.
Mesmo nos elogios, adicione uma pitada de ironia.

════════════════════════════════════════
FORMATO OBRIGATÓRIO DA RESPOSTA
════════════════════════════════════════

Use exatamente este template, sem pular seções:

🎬 Filme: [Nome do Filme em Português (Ano)]
🔍 Título Original: [Título original em inglês ou idioma nativo]

🧠 Análise:
[Parágrafo(s) de análise — envolvente, no estilo escolhido]

⭐ Nota: [X.X / 10]

✅ Pontos fortes:
- [ponto 1]
- [ponto 2]
- [ponto 3 se aplicável]

❌ Pontos fracos:
- [ponto 1]
- [ponto 2]

👥 Indicado para:
[Descreva o perfil do espectador que vai curtir. Seja específico.]

════════════════════════════════════════
REGRAS IMPORTANTES
════════════════════════════════════════

• Adapte rigidamente o tom ao estilo escolhido — não misture estilos
• Nunca repita os mesmos filmes clássicos óbvios (evite sempre Poderoso Chefão, Cidadão Kane etc.)
• Varie entre décadas, países e gêneros nas recomendações
• Seja natural — nada de linguagem robótica ou respostas genéricas
• Para recomendações por humor, escolha filmes que realmente se encaixem, não os mais famosos
• Responda sempre em português do Brasil
• Mantenha a análise densa mas legível — parágrafos curtos, sem textão
"""


class CinemaAgent:
    def __init__(self, api_key: str, omdb_key: str):
        self.client = AsyncGroq(api_key=api_key)
        self.omdb_key = omdb_key

    async def _get_imdb_rating(self, title: str, year: Optional[str] = None) -> Optional[str]:
        try:
            params = {"t": title, "apikey": self.omdb_key}
            if year:
                params["y"] = year
            async with httpx.AsyncClient(timeout=5) as http:
                r = await http.get(OMDB_URL, params=params)
                data = r.json()
                print(f"[OMDB] título='{title}' ano={year} → {data.get('imdbRating')} (Response={data.get('Response')})")
                if data.get("Response") == "True" and data.get("imdbRating") not in (None, "N/A"):
                    return data["imdbRating"]
        except Exception as e:
            print(f"[OMDB] erro: {e}")
        return None

    async def analyze(self, user_message: str, style: str = DEFAULT_STYLE) -> str:
        if style not in STYLES:
            style = DEFAULT_STYLE

        response = await self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=1024,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Estilo de resposta: **{style}**\n\n{user_message}"},
            ],
        )

        text = response.choices[0].message.content

        # Extrai ano da linha 🎬 Filme
        year_match = re.search(r"🎬 Filme:.*?\((\d{4})\)", text)
        year = year_match.group(1) if year_match else None

        # Usa título original (inglês) para busca no OMDB
        orig_match = re.search(r"🔍 Título Original:\s*\[?([^\[\]\n]+?)\]?\s*(?:\n|$)", text)
        title = orig_match.group(1).strip() if orig_match else None

        # Fallback: usa título em português se não encontrar original
        if not title:
            fb = re.search(r"🎬 Filme:\s*\[?([^\(\[\n\]]+?)\s*(?:\((\d{4})\))?\]?(?:\n|$)", text)
            title = fb.group(1).strip() if fb else None

        print(f"[OMDB] buscando título='{title}' ano={year}")
        if title:
            imdb_rating = await self._get_imdb_rating(title, year)
            if imdb_rating:
                text = re.sub(
                    r"⭐ Nota:.*",
                    f"⭐ Nota: {imdb_rating}/10 (IMDB)",
                    text,
                )
                # Remove a linha do título original da resposta final
                text = re.sub(r"🔍 Título Original:.*\n?", "", text)

        return text
