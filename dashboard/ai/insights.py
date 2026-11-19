"""Leituras assertivas dos gráficos — uma única chamada ao Gemini por recorte de filtros.

O Python calcula os FATOS (participações, rankings, comparações já formatados em
pt-BR) e o modelo só escolhe o que importa e redige. Assim ele não precisa fazer
contas (onde LLMs erram) e não tem espaço para "talvez", "parece", etc.

Se a IA falhar, as leituras caem para os próprios fatos calculados — o painel
nunca fica com um card vazio. Falhas não entram no cache.
"""

import json
from functools import lru_cache

from ai.gemini_client import IAIndisponivel, perguntar

PROMPT_TEMPLATE = """Você é analista-chefe de dados educacionais e escreve para secretários de educação.
Recorte analisado: {contexto}

Abaixo, FATOS já calculados e verificados para cada gráfico do painel (chave: lista de fatos).
{fatos}

Tarefa: devolva um JSON com exatamente estas chaves:
- "resumo": lista com 3 frases — os 3 achados mais relevantes do recorte inteiro, do mais para o menos importante.
- {chaves}: para cada chave, UMA leitura do gráfico correspondente.

Formato de cada frase/leitura (markdown):
**<manchete de até 10 palavras, com o número-chave>** <uma frase curta com a consequência, contraste ou o que merece atenção>.

Regras inegociáveis:
- Use SOMENTE números que aparecem nos fatos, copiados exatamente como estão. Nunca calcule, arredonde ou invente.
- Priorize contrastes e extremos (maior x menor, acima x abaixo da média do Brasil, concentração) sobre
  volumes óbvios. A segunda frase diz por que isso importa para quem planeja a rede de ensino.
- Seja afirmativo e específico. Proibido: "parece", "pode indicar", "possivelmente", "talvez", "os dados mostram",
  "observa-se", "é importante notar", "vale destacar", "em resumo".
- A manchete é uma afirmação, não um rótulo: nunca comece copiando o nome do fato
  (errado: "**Estados com mais matrículas: SP 10,1 mi**"; certo: "**SP concentra 21,3% das matrículas do país**").
- Nada de descrever o gráfico ("o gráfico mostra..."): diga o achado.
- Máximo de 35 palavras por leitura. Português do Brasil.
"""


def _fallback(fatos: dict[str, list[str]]) -> dict:
    leituras = {chave: (f"**{itens[0]}**" + (f" {itens[1]}" if len(itens) > 1 else "")) for chave, itens in fatos.items() if itens}
    resumo = [f"**{itens[0]}**" for itens in fatos.values() if itens][:3]
    return {"resumo": resumo, **leituras, "_origem": "calculado"}


@lru_cache(maxsize=256)
def _gerar_cacheado(contexto: str, fatos_json: str) -> str:
    fatos = json.loads(fatos_json)
    texto_fatos = "\n".join(f'"{chave}": ' + json.dumps(itens, ensure_ascii=False) for chave, itens in fatos.items())
    prompt = PROMPT_TEMPLATE.format(
        contexto=contexto, fatos=texto_fatos, chaves=", ".join(f'"{c}"' for c in fatos)
    )
    bruto = perguntar(prompt, temperatura=0.2, json=True)
    dados = json.loads(bruto)  # JSON inválido levanta erro e não é cacheado
    if not isinstance(dados, dict) or not isinstance(dados.get("resumo"), list):
        raise ValueError("Resposta da IA fora do formato esperado.")
    return bruto


def gerar_leituras(contexto: str, fatos: dict[str, list[str]]) -> dict:
    """Retorna {"resumo": [..3 frases..], <chave_do_grafico>: "texto", "_origem": "ia"|"calculado"}."""
    fatos = {chave: itens for chave, itens in fatos.items() if itens}
    if not fatos:
        return {"resumo": [], "_origem": "calculado"}
    try:
        dados = json.loads(_gerar_cacheado(contexto, json.dumps(fatos, ensure_ascii=False, sort_keys=True)))
    except (IAIndisponivel, ValueError) as exc:
        print(f"[AVISO] Leituras da IA indisponíveis, usando fatos calculados: {exc!r}", flush=True)
        return _fallback(fatos)

    base = _fallback(fatos)
    saida = {"_origem": "ia", "resumo": [str(f) for f in dados.get("resumo", [])][:3] or base["resumo"]}
    for chave in fatos:
        valor = dados.get(chave)
        saida[chave] = str(valor).strip() if isinstance(valor, str) and valor.strip() else base[chave]
    return saida
