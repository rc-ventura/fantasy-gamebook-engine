# 01 — Módulo `regras` (motor puro)

## Responsabilidade
Resolver toda a matemática do jogo de forma **determinística e pura**: rolagem de dados,
geração de atributos, teste de sorte e a resolução de uma rodada de combate. Sem I/O,
sem estado, sem conhecer IA nem storage. É a peça que vai **intacta** pra Fase 2.

## Interface exposta (contrato)
Funções puras; o gerador aleatório é **injetável** (pra testes determinísticos).

```
rolar_dado(notacao: str, rng) -> { rolagens: int[], total: int }
    # notacao: "NdM", "NdM+K", "NdM-K"  (ex.: "2d6+6")

gerar_atributos(rng) -> {
    habilidade: { inicial, atual },   # 1d6+6
    energia:    { inicial, atual },   # 2d6+12
    sorte:      { inicial, atual },   # 1d6+6
}

testar_sorte(sorte_atual: int, rng) -> {
    rolagem: int, sucesso: bool, sorte_depois: int   # sorte_depois = sorte_atual - 1
}

resolver_rodada(habilidade_heroi: int, habilidade_inimigo: int, rng) -> {
    fa_heroi: int, fa_inimigo: int,
    quem_acertou: "heroi" | "inimigo" | "empate",
    dano_base: int   # 2 no perdedor; 0 em empate
}

aplicar_modificador_sorte(quem_acertou, dano_base, sucesso_sorte: bool) -> dano_final: int
    # venceu+sucesso -> 4 ; venceu+falha -> 1
    # perdeu+sucesso -> 1 ; perdeu+falha -> 3
```

## Dependências
- Apenas tipos do módulo 02 (`dominio`), e idealmente nem isso — pode retornar dicts simples.
- **Nenhuma** dependência de storage, MCP ou IA.

## Plugabilidade
Não é plugável (é o núcleo estável). Mas o **rng injetável** permite trocar a fonte de
aleatoriedade (ex.: seed fixa em testes, RNG criptográfico em produção).

## Critérios de pronto
- Testável 100% isoladamente, sem IA e sem disco.
- Com seed fixa, resultados reproduzíveis.
- Testes cobrem: parsing de notação inválida, faixas dos atributos, decremento da sorte
  sempre em 1, empate sem dano, e os 4 casos do modificador de sorte.
