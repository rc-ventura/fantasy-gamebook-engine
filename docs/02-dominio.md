# 02 — Módulo `dominio` (contratos de dados)

## Responsabilidade
Definir os **modelos de dados compartilhados** entre módulos. É a "linguagem comum":
qualquer módulo que troca dados usa estes contratos. Sem lógica, só estrutura + validação.

## Interface exposta (contrato)

```
Atributo  = { inicial: int, atual: int }   # invariante: 0 <= atual <= inicial

Ficha = {
    nome: str,
    habilidade: Atributo, energia: Atributo, sorte: Atributo,
    inventario: str[], ouro: int, provisoes: int,
    condicoes: str[], vivo: bool
}

Mundo = {
    local_atual: str, locais_visitados: str[],
    npcs_conhecidos: { nome: str, estado: str }[],
    flags: { [chave: str]: bool }, turno: int
}

Evento = { turno: int, tipo: str, dados: object, timestamp: str }

Combate = {
    combate_id: str,
    inimigos: { nome, habilidade, energia }[],
    rodada: int, fuga_permitida: bool, encerrado: bool,
    vencedor?: "heroi" | "inimigo"
}

RegistroArquivo = {   # cemitério / hall da fama
    nome, turnos, desfecho: "morte"|"vitoria",
    local, causa?, inventario_final: str[]
}
```

## Dependências
Nenhuma. É a base da pirâmide.

## Plugabilidade
Não plugável, mas **versionável**: mudanças no schema devem ser retrocompatíveis ou ter
migração. O schema da `Ficha` foi desenhado pra virar tabela no Postgres quase 1:1.

## Critérios de pronto
- Validação dos invariantes (ex.: `atual <= inicial`) centralizada aqui.
- Serialização/desserialização redonda (objeto → JSON → objeto idêntico).
