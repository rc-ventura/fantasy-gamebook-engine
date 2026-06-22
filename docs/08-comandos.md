# 08 — Módulo `comandos` (comandos de sistema)

## Responsabilidade
Ações do jogador **fora do fluxo narrativo**: consultar ficha, inventário, mapa, salvar.
Lêem (e às vezes escrevem) estado via MCP e imprimem um resultado formatado, sem alterar
a história. Equivalente digital da Folha de Aventura do livro.

## Interface exposta (contrato)
Cada comando: `trigger -> lê/escreve MCP -> imprime formatado -> retorna ao fluxo`.

```
/stats     -> ler_ficha     -> imprime Habilidade/Energia/Sorte (atual/inicial),
                               provisões, ouro, inventário, condições.
                               disponível inclusive durante combate.
/mochila   -> ler_ficha     -> detalha inventário; permite usar item (atualizar_ficha).
/mapa      -> ler_mundo     -> locais_visitados + local_atual.
/salvar    -> salvar_progresso(nome) -> confirma checkpoint.
```

## Dependências (só interface)
- Contrato de ferramentas do `mcp` (05), principalmente as de leitura.

## Plugabilidade
- **Adicionar comando** = registrar novo trigger que segue o mesmo padrão; não toca em
  regras nem em narrativa.
- Na Fase 2, viram componentes de UI (painel de ficha, modal de inventário) sobre os mesmos
  dados — o "comando" vira botão.

## Critérios de pronto
- `/stats` reflete sempre o estado real do MCP (nunca um valor narrado).
- Comandos não alteram a narrativa nem o turno (exceto usar item, que é mudança de estado explícita).
- Padrão uniforme: fácil somar `/mapa`, `/diario`, etc.
