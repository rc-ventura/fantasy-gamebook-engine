# 03 — Módulo `storage` (persistência plugável) ⭐

## Responsabilidade
Persistir e recuperar todo o estado que sobrevive entre sessões, **atrás de uma interface
abstrata**. É a fronteira plugável nº 1: trocar JSON por Postgres não pode afetar nenhum
outro módulo.

## Interface exposta (contrato) — `StorageBackend`

```
interface StorageBackend:
    # Personagem
    carregar_personagem() -> Ficha | None
    salvar_personagem(ficha: Ficha) -> None

    # Mundo
    carregar_mundo() -> Mundo
    salvar_mundo(mundo: Mundo) -> None

    # Eventos / cronologia (append-only)
    anexar_evento(evento: Evento) -> None
    carregar_eventos() -> Evento[]

    # Resumo narrativo
    carregar_resumo() -> str
    salvar_resumo(texto: str) -> None

    # Combate em andamento
    carregar_combate(combate_id: str) -> Combate | None
    salvar_combate(combate: Combate) -> None
    remover_combate(combate_id: str) -> None

    # Fins de jogo
    arquivar(registro: RegistroArquivo, destino: "cemiterio"|"hall_da_fama") -> None

    # Slots de save (opcional)
    salvar_slot(nome: str) -> None
    carregar_slot(nome: str) -> None
```

Garantia exigida das implementações: **escrita atômica** (não corromper estado se
o processo morrer no meio) e leitura consistente.

## Dependências
- Módulo 02 (`dominio`) para os tipos.

## Plugabilidade ⭐
- **Fase 1 — `JSONStorage`**: um arquivo por entidade em `estado/` (`personagem.json`,
  `mundo.json`, `eventos.json`, `resumo.md`, `combate.json`). Escrita atômica via
  arquivo temporário + rename.
- **Fase 2 — `PostgresStorage`**: mesma interface, tabelas no banco. Nenhum outro módulo muda.
- Implementações adicionais possíveis: SQLite, Redis, memória (pra testes).

## Critérios de pronto
- Os módulos `mcp` e `combate` dependem **só da interface**, nunca de `JSONStorage`.
- Trocar a implementação concreta num único ponto (injeção de dependência) muda todo o backend.
- Teste com implementação em memória prova que o resto funciona sem disco.
