"""Prompts da IA do DevRecap.

Define a persona do assistente (SYSTEM_INSTRUCTION), as chaves de resposta
esperadas (RESPONSE_KEYS, espelhando os campos de AIInsights) e a montagem do
prompt do usuário a partir dos dados do dia (build_user_prompt).

Sem dependências externas — apenas stdlib.
"""
from __future__ import annotations

from devrecap.core.logging_setup import get_logger
from devrecap.core.models import DayActivity, RepoActivity

logger = get_logger(__name__)


# Limite de caracteres do trecho de referência de estilo embutido no prompt.
_STYLE_REFERENCE_LIMIT = 2000

# Guia de tamanho do post (curto por padrão — o João achou o texto grande demais).
_LENGTH_GUIDE = {
    "curto": "MUITO curto: 2 a 4 frases, no máximo ~60 palavras. Direto ao ponto, sem enrolação.",
    "medio": "curto: 5 a 7 frases, ~110 palavras.",
    "longo": "moderado: ~180 a 220 palavras — ainda casual, sem encher linguiça.",
}


# --------------------------------------------------------------------------- #
# Persona / instrução de sistema
# --------------------------------------------------------------------------- #
SYSTEM_INSTRUCTION = """\
Você é o assistente pessoal de desenvolvimento do João, um desenvolvedor.
Seu trabalho tem dois objetivos:

1. RESUMIR o que o João fez no dia a partir dos dados reais de commits, diffs,
   pull requests, issues e estatísticas que ele te fornece.
2. ESCREVER um post de LinkedIn autêntico, em primeira pessoa, contando o
   progresso real do dia.

Princípios obrigatórios:

- NUNCA invente fatos. Use SOMENTE o que está nos dados fornecidos. Se algo não
  aparece nos commits/diffs/PRs/issues, não afirme que aconteceu. Não exagere
  números, não atribua impacto que os dados não sustentam, não cite tecnologias
  que não estão presentes.
- Se o dia foi pequeno (poucos commits, trabalho incremental), trate isso com
  honestidade — progresso pequeno também é progresso. Não infle.
- Escreva em primeira pessoa ("eu fiz", "aprendi", "resolvi"), como o João
  falando.
- Tom autêntico e direto. ZERO jargão corporativo vazio (nada de "sinergia",
  "disruptivo", "game changer", "alavancar", frases motivacionais genéricas).
- Escreva CURTO. Um bom post aqui tem poucas frases — não encha linguiça, não
  repita a mesma ideia com outras palavras. Respeite o tamanho pedido no prompt.
- Soe HUMANO e casual, como um dev contando o dia pra um amigo — NÃO como um
  comunicado de empresa, um relatório ou um texto de coach/motivacional.
- O foco do post é aprendizado real e progresso concreto: o que foi construído,
  o problema resolvido, o que se aprendeu no caminho.
- Seja específico sobre o trabalho técnico, mas acessível — o post é para o
  LinkedIn, não um changelog. Também mantenha o "summary" enxuto (2-3 frases).
- Respeite o idioma e o tom que forem pedidos no prompt do usuário.
- Quando houver um exemplo de estilo de escrita do João, use-o como REFERÊNCIA
  de voz e ritmo — NÃO copie o texto literalmente.

Você responde SEMPRE e SOMENTE com um objeto JSON válido, sem nenhum texto
fora do JSON e sem blocos de markdown."""


# --------------------------------------------------------------------------- #
# Chaves esperadas na resposta da IA (espelham AIInsights)
# --------------------------------------------------------------------------- #
RESPONSE_KEYS: list[str] = [
    "summary",
    "technologies",
    "progress",
    "value_added",
    "bullet_highlights",
    "linkedin_post",
    "linkedin_hashtags",
    "photo_keywords",
    "photo_prompt",
]


# --------------------------------------------------------------------------- #
# Serialização dos dados do dia
# --------------------------------------------------------------------------- #
def _format_languages(langs: dict[str, int]) -> str:
    """Formata o mapa de linguagens (extensão -> nº arquivos) de forma compacta."""
    if not langs:
        return "nenhuma"
    ordered = sorted(langs.items(), key=lambda kv: kv[1], reverse=True)
    return ", ".join(f"{ext} ({n})" for ext, n in ordered)


def _format_repo(repo: RepoActivity) -> str:
    """Serializa um RepoActivity em um bloco de texto legível para o prompt."""
    lines: list[str] = []
    lines.append(f"### Repo: {repo.name}")
    lines.append(
        f"- commits: {repo.commit_count} | "
        f"+{repo.insertions} -{repo.deletions} linhas | "
        f"{repo.files_changed} arquivos"
    )
    lines.append(f"- linguagens: {_format_languages(repo.languages)}")

    if repo.is_dirty and repo.uncommitted_files:
        amostra = ", ".join(repo.uncommitted_files[:10])
        lines.append(
            f"- mudanças não commitadas ({len(repo.uncommitted_files)}): {amostra}"
        )
    elif repo.is_dirty:
        lines.append("- há mudanças não commitadas")

    if repo.commits:
        lines.append("- mensagens dos commits:")
        for c in repo.commits:
            subject = c.subject or "(sem mensagem)"
            lines.append(f"  - {subject}")

    if repo.prs:
        lines.append("- pull requests:")
        for pr in repo.prs:
            lines.append(f"  - [{pr.state}] #{pr.number} {pr.title}")

    if repo.issues:
        lines.append("- issues:")
        for iss in repo.issues:
            lines.append(f"  - [{iss.state}] #{iss.number} {iss.title}")

    return "\n".join(lines)


def _serialize_activity(activity: DayActivity) -> str:
    """Serializa o dia inteiro (repos ativos + totais) de forma compacta."""
    repos = activity.active_repos
    blocks: list[str] = []
    blocks.append(f"Data: {activity.day}")
    blocks.append(
        "Totais do dia: "
        f"{activity.total_commits} commits | "
        f"+{activity.total_insertions} -{activity.total_deletions} linhas | "
        f"{activity.total_files_changed} arquivos | "
        f"{len(repos)} repositório(s) com atividade"
    )
    blocks.append(f"Linguagens agregadas: {_format_languages(activity.languages)}")

    if activity.notes:
        blocks.append("Avisos da coleta: " + "; ".join(activity.notes))

    if repos:
        blocks.append("")
        blocks.append("Repositórios:")
        for repo in repos:
            blocks.append("")
            blocks.append(_format_repo(repo))
    else:
        blocks.append("")
        blocks.append("Nenhum repositório com atividade registrada no dia.")

    return "\n".join(blocks)


# --------------------------------------------------------------------------- #
# Montagem do prompt do usuário
# --------------------------------------------------------------------------- #
def build_user_prompt(
    activity: DayActivity,
    *,
    language: str = "pt-BR",
    tone: str = "",
    style_reference: str | None = None,
    post_length: str = "curto",
) -> str:
    """Monta o prompt do usuário com os dados do dia e pede um JSON estruturado.

    Serializa os dados do dia (repos, commits, linguagens, stats), inclui o tom
    desejado e, se houver, um trecho da referência de estilo. Pede explicitamente
    uma resposta SOMENTE em JSON com exatamente as RESPONSE_KEYS. Em qualquer
    falha de serialização, devolve um prompt mínimo seguro (nunca levanta).
    """
    try:
        dados = _serialize_activity(activity)
    except Exception as e:  # noqa: BLE001 — nunca deixar exceção vazar
        logger.exception("Falha ao serializar atividade do dia para o prompt: %s", e)
        dia = getattr(activity, "day", "") or "desconhecido"
        dados = f"Data: {dia}\n(Não foi possível serializar os dados do dia.)"

    tone = (tone or "").strip()
    partes: list[str] = []

    partes.append(
        "Abaixo estão os dados REAIS do meu dia de desenvolvimento. "
        "Use apenas estas informações — não invente nada."
    )
    partes.append("")
    partes.append("=== DADOS DO DIA ===")
    partes.append(dados)
    partes.append("=== FIM DOS DADOS ===")
    partes.append("")

    partes.append(f"Idioma das saídas: {language}.")
    if tone:
        partes.append(f"Tom desejado para o post: {tone}.")
    length = _LENGTH_GUIDE.get((post_length or "curto").strip().lower(), _LENGTH_GUIDE["curto"])
    partes.append(f"TAMANHO do post (linkedin_post): {length}")

    if style_reference and style_reference.strip():
        trecho = style_reference.strip()[:_STYLE_REFERENCE_LIMIT]
        partes.append("")
        partes.append(
            "Referência de ESTILO de escrita do João (use como inspiração de voz "
            "e ritmo, NÃO copie literalmente):"
        )
        partes.append('"""')
        partes.append(trecho)
        partes.append('"""')

    partes.append("")
    partes.append(
        "Responda SOMENTE com um objeto JSON válido (sem markdown, sem cercas de "
        "código, sem texto antes ou depois) contendo EXATAMENTE estas chaves:"
    )
    partes.append("")
    partes.append(
        '- "summary" (string): resumo do que foi feito no dia, em '
        f"{language}."
    )
    partes.append(
        '- "technologies" (lista de strings): tecnologias/linguagens/ferramentas '
        "efetivamente usadas, segundo os dados."
    )
    partes.append(
        '- "progress" (string): avaliação honesta do progresso do dia, em '
        f"{language}."
    )
    partes.append(
        '- "value_added" (string): como o trabalho agregou aos projetos, em '
        f"{language}."
    )
    partes.append(
        '- "bullet_highlights" (lista de strings): o que foi feito, em frases '
        "curtas e orientadas a resultado."
    )
    partes.append(
        '- "linkedin_post" (string): o post pronto pro LinkedIn, CURTO e casual, '
        f"em primeira pessoa, em {language}, RESPEITANDO o tamanho pedido acima."
    )
    partes.append(
        '- "linkedin_hashtags" (lista de strings): hashtags relevantes (com ou '
        "sem o caractere #)."
    )
    partes.append(
        '- "photo_keywords" (lista de strings): palavras-chave para buscar uma '
        "foto que combine com o post."
    )
    partes.append(
        '- "photo_prompt" (string): um prompt EM INGLÊS, descritivo, para gerar '
        "uma imagem que combine com o post (estilo foto/ilustração profissional, "
        "SEM nenhum texto na imagem)."
    )
    partes.append("")
    partes.append(
        f"Todas as saídas em {language}, EXCETO photo_prompt, que deve ser em "
        "inglês."
    )

    return "\n".join(partes)
