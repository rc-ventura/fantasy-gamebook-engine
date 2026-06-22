# 05 — Módulo `mcp` (servidor / contrato de ferramentas)

## Responsabilidade
Expor o motor de regras + estado como **ferramentas MCP** consumíveis por qualquer harness.
É a fachada que o narrador (IA) usa. Não contém regra de jogo própria — só orquestra
`regras`, `combate` e `storage`. É o que garante "a IA nunca rola dado em texto".

## Interface exposta (contrato de ferramentas MCP)

```
# Dados / sorte
rolar_dado(notacao) -> { rolagens, total }
testar_sorte() -> { rolagem, sucesso, sorte_depois }

# Ficha
criar_personagem(nome) -> Ficha
ler_ficha() -> Ficha
atualizar_ficha(mudancas) -> Ficha       # valida invariantes via dominio

# Mundo / eventos
ler_mundo() -> Mundo
registrar_evento(tipo, dados) -> None
ler_eventos() -> Evento[]
ler_resumo() -> str
atualizar_resumo(texto) -> None

# Combate (delega ao módulo 04)
iniciar_combate(inimigos, fuga_permitida) -> Combate
resolver_rodada_combate(combate_id, usar_sorte) -> ResultadoRodada
escapar_combate(combate_id) -> ResultadoFuga
encerrar_combate(combate_id) -> ResultadoFinal

# Fins / sessão
arquivar_personagem(destino) -> None
salvar_progresso(slot?) / carregar_progresso(slot?)
```

## Dependências (só interfaces)
- `regras` (01), `combate` (04), `storage` (03 — recebe a implementação por injeção), `dominio` (02).

## Plugabilidade
O **contrato de ferramentas é estável**: é a fronteira plugável nº 3 vista do outro lado.
Qualquer harness (Claude Code agora, PydanticAI depois) fala o mesmo MCP sem mudanças.
A implementação de `storage` é injetada na inicialização do servidor (JSON ou Postgres).

## Critérios de pronto
- Servidor sobe e lista todas as ferramentas.
- Cada ferramenta valida entrada e nunca deixa estado inconsistente.
- Trocar `JSONStorage` por outra impl. não exige mudança em nenhuma ferramenta.
