# 06 — Módulo `modulo-aventura` (conteúdo plugável) ⭐

## Responsabilidade
Conter o **lore estático** de uma aventura: a estrutura que o mestre usa pra improvisar.
É a fronteira plugável nº 2: trocar de aventura = trocar este artefato, sem tocar no motor.
Na Fase 1 é um `SKILL.md`; na Fase 2, um registro de dados / arquivo de módulo.

## Interface exposta (contrato `ModuloAventura`)

```
ModuloAventura = {
    metadados: { nome, descricao, tom },
    abertura: str,                      # situação/gancho inicial
    zonas: [{
        id, nome, descricao, atmosfera,
        dificuldade: int                # escala de inimigos
    }],
    bestiario: [{
        nome, habilidade, energia, comportamento, drops?: str[]
    }],
    condicao_vitoria: { descricao, flag: str },   # flag setada no Mundo ao vencer
    regras_especiais?: str[]            # ex.: armadilhas, subornos
}
```

O mestre (harness) lê este contrato e **gera** o conteúdo de cada cena dentro dele.
O motor (`mcp`) não conhece o módulo de aventura — só a ficha/mundo/eventos.

## Dependências
Nenhuma de código. Referencia conceitualmente os tipos de inimigo (compatíveis com `combate`).

## Plugabilidade ⭐
- **Módulo de estreia:** `Ignarok` — Montanha Cinzenta, arquimago Malachar, 5–7 zonas
  progressivas, vitória = derrotar Malachar e escapar. Conteúdo **original** (inspirado no
  clássico, sem nomes/puzzles/textos do livro original — questão de copyright).
- Novos módulos = novos arquivos com o mesmo contrato. Mesmo motor, aventuras infinitas.

## Critérios de pronto
- O mestre consegue conduzir uma aventura completa (abertura → zonas → vitória) só com este artefato.
- Inimigos do bestiário plugam direto em `iniciar_combate`.
- Condição de vitória é uma flag verificável no `Mundo`.
