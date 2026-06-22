# 00 — Índice e Mapa de Módulos

Decomposição modular do sistema de livro-jogo com IA. Cada módulo tem spec própria,
expõe um **contrato (interface)** e depende **só de interfaces** de outros módulos —
nunca de implementações concretas. É isso que torna tudo plugável.

## Módulos

| # | Módulo | Responsabilidade | Plugável? |
|---|--------|------------------|-----------|
| 01 | `regras` | Motor de regras puro (dado, sorte, combate) | — (estável) |
| 02 | `dominio` | Contratos de dados (Ficha, Mundo, Evento, Combate) | — (estável) |
| 03 | `storage` | Persistência atrás de interface abstrata | ✅ JSON ↔ Postgres |
| 04 | `combate` | Ciclo de vida do combate (estado + rodadas) | — |
| 05 | `mcp` | Servidor MCP: expõe ferramentas ao harness | — (contrato estável) |
| 06 | `modulo-aventura` | Conteúdo/lore plugável (zonas, NPCs, vitória) | ✅ Ignarok ↔ outros |
| 07 | `harness` | O mestre/narrador que consome o MCP | ✅ Claude Code ↔ PydanticAI |
| 08 | `comandos` | Comandos de sistema (/stats, /mochila, ...) | ✅ adicionar novos |

## Grafo de dependências (só aponta pra interfaces)

```
07 harness ───────► 05 mcp ◄──────── 08 comandos
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   01 regras     04 combate     03 storage (interface)
        │             │             ▲
        └──────►──────┘             │ implementa
                  │                 │
                  ▼                 │
            02 dominio ◄────────────┘  (contratos de dados compartilhados)

06 modulo-aventura ──(lore consumido pelo)──► 07 harness
```

Regra de ouro da modularidade: setas só apontam pra **interfaces**. `mcp` conhece a
*interface* `StorageBackend`, não a implementação JSON. `harness` conhece o *contrato de
ferramentas* do MCP, não o código por trás.

## As 3 fronteiras plugáveis que importam
1. **`StorageBackend`** (módulo 03) — troca persistência sem tocar no resto.
2. **`ModuloAventura`** (módulo 06) — troca a aventura sem tocar no motor.
3. **Harness** (módulo 07) — troca quem narra (terminal → web) reusando o MCP.

## Template de cada spec
Responsabilidade · Interface exposta (contrato) · Dependências · Plugabilidade ·
Critérios de pronto.
