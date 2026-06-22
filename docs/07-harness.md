# 07 — Módulo `harness` (o mestre / narrador) ⭐

## Responsabilidade
Ser o **mestre**: conversar com o jogador, narrar, propor escolhas, ler o módulo de aventura
e chamar o MCP pra tudo que é numérico ou de estado. É a fronteira plugável nº 3:
Claude Code (Fase 1) ↔ PydanticAI/FastAPI (Fase 2), reusando o mesmo MCP.

## Interface exposta (contrato de comportamento do mestre)
Não é uma API de código, é um **contrato de comportamento** (vive no SKILL.md / system prompt):

```
ABERTURA DE SESSÃO:
  ler_ficha + ler_mundo + ler_eventos + ler_resumo  ANTES de narrar.
  sem personagem vivo -> oferecer criar_personagem.
  com personagem -> retomar do ponto exato (nunca recomeçar do zero).

TURNO NORMAL:
  narrar 2–4 parágrafos, 2ª pessoa, tom do módulo de aventura;
  terminar com opções numeradas; aceitar texto livre;
  toda mudança de estado -> via MCP;
  NUNCA rolar dado em texto -> sempre rolar_dado / testar_sorte.

ENCONTRO DE COMBATE:
  delegar ao sub-agente de combate (passar herói, inimigos, fuga_permitida);
  receber ResultadoFinal; narrar vitória ou morte.

CONTROLE DE CONTEXTO:
  a cada N turnos compactar resumo (atualizar_resumo);
  fatos duros migram pra mundo/eventos (estruturado), não só prosa.

FINS:
  morte -> arquivar cemitério, game over;
  flag de vitória do módulo -> epílogo + hall da fama.
```

## Sub-componentes (Fase 1, Claude Code)
- `SKILL.md` do **mestre** (tom + formato do turno).
- `SKILL.md` do **sub-agente de combate** (enxuto, só regras de combate).
- `CLAUDE.md` (regra de abertura de sessão).

## Dependências (só contrato)
- Contrato de ferramentas do `mcp` (05).
- Contrato `ModuloAventura` (06).

## Plugabilidade ⭐
- **Fase 1:** Claude Code consome o MCP + skills.
- **Fase 2:** Agent do PydanticAI com **saída estruturada** — define um tipo `Cena`
  ({ narrativa, escolhas[], efeitos[] }) que o frontend renderiza. Mesmo MCP, mesmo módulo de aventura.

## Critérios de pronto
- Uma sessão joga abertura → exploração → combate → fim sem o mestre inventar números.
- Trocar o harness não exige mudar MCP nem módulo de aventura.
