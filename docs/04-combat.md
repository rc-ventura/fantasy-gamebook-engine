# 04 — Módulo `combate` (ciclo de vida)

## Responsabilidade
Orquestrar o **sub-loop de combate**: abrir um combate, resolver rodadas (usando o motor
`regras`), aplicar dano à ficha e aos inimigos, persistir o estado e encerrar com um
resultado. É o "modo de luta" separado da narrativa.

## Interface exposta (contrato)

```
iniciar_combate(inimigos: {nome,habilidade,energia}[], fuga_permitida: bool) -> Combate
    # cria combate_id, persiste estado inicial

resolver_rodada(combate_id, usar_sorte: bool) -> {
    fa_heroi, fa_inimigo, quem_acertou,
    dano_aplicado, energia_heroi, energia_inimigo,
    sorte_usada?: { rolagem, sucesso },
    fim: bool, vencedor?: "heroi"|"inimigo"
}
    # lê ficha + combate, chama regras.resolver_rodada (+ modificador de sorte se usar_sorte),
    # atualiza energias, persiste. Se herói chega a 0 -> marca derrota.

escapar(combate_id) -> { dano_sofrido: 2, energia_heroi, fim: true }
    # só se fuga_permitida

encerrar_combate(combate_id) -> ResultadoFinal {
    vencedor, energia_final_heroi, sorte_gasta, rodadas, drops?: str[]
}
    # vitória: grava energia na ficha; derrota: ficha.vivo=false
```

## Dependências (só interfaces)
- `regras` (01) para a matemática da rodada.
- `storage` (03) para ler/gravar `Combate` e `Ficha`.
- `dominio` (02) para os tipos.

## Plugabilidade
Não é plugável em si, mas isola o combate de modo que ele possa ser invocado por qualquer
harness — inclusive como sub-agente no Claude Code (recebe contexto, roda, devolve
`ResultadoFinal`).

## Nota sobre interação com o jogador
A decisão "testar sorte ou não" a cada rodada vem do **harness** (que fala com o jogador).
Este módulo é stateless quanto à UI: recebe `usar_sorte` já decidido e devolve o resultado.

## Critérios de pronto
- Combate em andamento sobrevive a reinício (estado persistido por `combate_id`).
- Morte em combate propaga corretamente `vivo: false`.
- Testável com `storage` em memória e `regras` com seed fixa.
