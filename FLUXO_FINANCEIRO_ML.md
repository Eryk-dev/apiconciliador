# Fluxo Financeiro Mercado Livre / Mercado Pago

## Guia Completo para Conciliação Contábil

Este documento detalha como funciona o sistema financeiro do Mercado Livre e Mercado Pago, explicando o ciclo de vida das transações e como os diferentes relatórios se relacionam.

---

## 1. Ciclo de Vida de uma Venda

### 1.1 Fluxo Normal (Venda → Entrega → Liberação)

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   COMPRA    │───▶│   ENVIO     │───▶│   ENTREGA   │───▶│  LIBERAÇÃO  │
│             │    │             │    │             │    │             │
│ Pagamento   │    │ Produto     │    │ Confirmação │    │ Dinheiro    │
│ aprovado    │    │ enviado     │    │ de entrega  │    │ disponível  │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
      │                                                         │
      │                                                         │
      ▼                                                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    RELATÓRIO: DINHEIRO EM CONTA                     │
│                    (Settlement Report)                              │
│                                                                     │
│  Registra IMEDIATAMENTE após pagamento aprovado                     │
│  Status: SETTLEMENT                                                 │
│  Valor ainda RETIDO até liberação                                   │
└─────────────────────────────────────────────────────────────────────┘
      │                                                         │
      │                                                         │
      ▼                                                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    RELATÓRIO: LIBERAÇÕES                            │
│                    (Reserve-Release Report)                         │
│                                                                     │
│  Registra quando dinheiro SAI da retenção                           │
│  DESCRIPTION: "payment" = liberação de venda                        │
│  Detalha: GROSS_AMOUNT, taxas, valor líquido                        │
└─────────────────────────────────────────────────────────────────────┘
      │                                                         │
      │                                                         │
      ▼                                                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    RELATÓRIO: EXTRATO                               │
│                    (Account Statement)                              │
│                                                                     │
│  Registra movimentação REAL na conta                                │
│  "Liberação de dinheiro" = entrada efetiva                          │
│  Este é o valor que REALMENTE entrou na conta                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Prazos de Liberação

| Tipo de Envio | Reputação | Produto | Prazo |
|---------------|-----------|---------|-------|
| Mercado Envios | Com reputação | Novo | 2-8 dias após entrega |
| Mercado Envios | Com reputação | Usado | 6-12 dias após entrega |
| Mercado Envios | Sem reputação | Qualquer | 12 dias após entrega |
| Por conta própria | MercadoLíder | - | 11 dias após aviso |
| Por conta própria | Sem MercadoLíder | - | 28 dias (ou 5 se confirmado) |

### 1.3 Por que existe retenção?

O Mercado Livre retém o dinheiro para:
1. **Proteger contra fraudes** - Garantir fundos para reembolso se necessário
2. **Confirmar entrega** - Assegurar que produto foi recebido
3. **Período de reclamação** - Permitir que comprador reclame se houver problema

---

## 2. Relação Entre os 5 Relatórios

### 2.1 Mapa de Relacionamento

```
┌────────────────────────────────────────────────────────────────────────┐
│                         VENDAS (Collection)                            │
│                                                                        │
│  QUANDO: Momento da venda                                              │
│  O QUE TEM: Dados do pedido, produto, frete cobrado do comprador       │
│  CHAVE: operation_id (op_id)                                           │
│  VALORES IMPORTANTES:                                                  │
│    - transaction_amount = valor do PRODUTO                             │
│    - shipping_cost = frete (pode ser pago pelo comprador ou vendedor)  │
└────────────────────────────────────────────────────────────────────────┘
         │
         │ operation_id = SOURCE_ID
         ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    DINHEIRO EM CONTA (Settlement)                      │
│                                                                        │
│  QUANDO: Pagamento aprovado (mesmo dia ou próximo)                     │
│  O QUE TEM: Transação financeira com taxas calculadas                  │
│  CHAVE: SOURCE_ID                                                      │
│  VALORES IMPORTANTES:                                                  │
│    - TRANSACTION_AMOUNT = valor bruto                                  │
│    - FEE_AMOUNT = soma de TODAS as taxas                               │
│    - SHIPPING_FEE_AMOUNT = taxa de frete (parte da FEE)                │
│    - REAL_AMOUNT = valor líquido (bruto - taxas)                       │
│  TRANSACTION_TYPE:                                                     │
│    - SETTLEMENT = venda aprovada                                       │
│    - REFUND = devolução                                                │
│    - CHARGEBACK = contestação no cartão                                │
│    - DISPUTE = reclamação do comprador                                 │
└────────────────────────────────────────────────────────────────────────┘
         │
         │ SOURCE_ID = SOURCE_ID
         ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      LIBERAÇÕES (Reserve-Release)                      │
│                                                                        │
│  QUANDO: Dinheiro é liberado (após entrega + prazo)                    │
│  O QUE TEM: Detalhamento da liberação com breakdown de valores         │
│  CHAVE: SOURCE_ID                                                      │
│  DESCRIPTION (tipo de movimento):                                      │
│    - "payment" = liberação de venda normal                             │
│    - "refund" = devolução processada                                   │
│    - "chargeback" = contestação                                        │
│    - "shipping" = ajuste de frete                                      │
│    - "payout" = saque                                                  │
│  VALORES IMPORTANTES:                                                  │
│    - GROSS_AMOUNT = valor bruto                                        │
│    - MP_FEE_AMOUNT = taxa do Mercado Pago                              │
│    - FINANCING_FEE_AMOUNT = taxa de parcelamento s/ juros              │
│    - SHIPPING_FEE_AMOUNT = custo de envio                              │
│    - NET_CREDIT_AMOUNT = crédito líquido (entrada)                     │
│    - NET_DEBIT_AMOUNT = débito líquido (saída)                         │
└────────────────────────────────────────────────────────────────────────┘
         │
         │ SOURCE_ID = REFERENCE_ID
         ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         EXTRATO (Account Statement)                    │
│                                                                        │
│  QUANDO: Movimento efetivo na conta                                    │
│  O QUE TEM: Registro contábil real da movimentação                     │
│  CHAVE: REFERENCE_ID                                                   │
│  VALORES:                                                              │
│    - TRANSACTION_NET_AMOUNT = valor líquido movimentado                │
│  TRANSACTION_TYPE (descrição textual):                                 │
│    - "Liberação de dinheiro" = entrada de venda                        │
│    - "Reembolso" = saída por devolução                                 │
│    - "Transferência" = PIX/TED                                         │
│    - etc.                                                              │
│                                                                        │
│  ⚠️ ESTE É O RELATÓRIO "PROVA REAL"                                    │
│     Se está no extrato, REALMENTE movimentou a conta                   │
└────────────────────────────────────────────────────────────────────────┘
         │
         ▲
         │
┌────────────────────────────────────────────────────────────────────────┐
│                       PÓS-VENDA (After Collection)                     │
│                                                                        │
│  QUANDO: Eventos após a venda (reclamações, devoluções)                │
│  O QUE TEM: Detalhes de reclamações e motivos                          │
│  CHAVE: operation_id                                                   │
│  USA PARA: Enriquecer descrição de REFUND/CHARGEBACK/DISPUTE           │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Qual relatório usar para quê?

| Necessidade | Relatório Principal | Relatório Complementar |
|-------------|---------------------|------------------------|
| Saber valor do produto vendido | VENDAS | - |
| Saber taxas cobradas | DINHEIRO EM CONTA | LIBERAÇÕES (detalhado) |
| Saber quando dinheiro liberou | LIBERAÇÕES | EXTRATO (confirmação) |
| Confirmar entrada real | EXTRATO | - |
| Entender motivo de devolução | PÓS-VENDA | DINHEIRO EM CONTA |
| Rastrear origem da receita | Todos (via SOURCE_ID) | - |

---

## 3. Entendendo os Valores

### 3.1 Anatomia de uma Venda

```
EXEMPLO: Venda de R$ 100,00 com frete de R$ 15,00

┌─────────────────────────────────────────────────────────────────┐
│ VENDAS (Collection)                                             │
│   transaction_amount: R$ 100,00 (valor do produto)              │
│   shipping_cost: R$ 15,00 (frete cobrado do comprador)          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ DINHEIRO EM CONTA (Settlement)                                  │
│   TRANSACTION_AMOUNT: R$ 100,00 (valor bruto do produto)        │
│   FEE_AMOUNT: R$ 18,00 (soma de todas as taxas)                 │
│      ├── Comissão ML: R$ 12,00                                  │
│      └── SHIPPING_FEE_AMOUNT: R$ 6,00 (parte do frete paga      │
│                                         pelo vendedor)          │
│   REAL_AMOUNT: R$ 82,00 (100 - 18 = líquido)                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ LIBERAÇÕES (Reserve-Release) - DESCRIPTION: "payment"           │
│   GROSS_AMOUNT: R$ 100,00                                       │
│   MP_FEE_AMOUNT: R$ -12,00 (comissão)                           │
│   FINANCING_FEE_AMOUNT: R$ 0,00 (sem parcelamento s/ juros)     │
│   SHIPPING_FEE_AMOUNT: R$ -6,00 (frete do vendedor)             │
│   NET_CREDIT_AMOUNT: R$ 82,00                                   │
│   NET_DEBIT_AMOUNT: R$ 0,00                                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ EXTRATO (Account Statement)                                     │
│   TRANSACTION_TYPE: "Liberação de dinheiro"                     │
│   TRANSACTION_NET_AMOUNT: R$ 82,00                              │
│   (Este é o valor que REALMENTE entrou na conta)                │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Cálculo das Taxas

```
VALOR LÍQUIDO = VALOR BRUTO - COMISSÃO ML - TAXA PARCELAMENTO - FRETE VENDEDOR

Onde:
- COMISSÃO ML (MP_FEE_AMOUNT): % sobre o valor da venda (varia por categoria)
- TAXA PARCELAMENTO (FINANCING_FEE_AMOUNT): custo de oferecer parcelas s/ juros
- FRETE VENDEDOR (SHIPPING_FEE_AMOUNT): parte do frete que o vendedor paga
```

### 3.3 Sobre o Frete

O frete pode ter diferentes configurações:

| Cenário | shipping_cost (Vendas) | SHIPPING_FEE_AMOUNT (Settlement) |
|---------|------------------------|----------------------------------|
| Frete grátis (vendedor paga tudo) | R$ 0,00 | R$ -15,00 (custo real) |
| Comprador paga frete | R$ 15,00 | R$ 0,00 ou parcial |
| Frete subsidiado ML | Variável | Diferença subsidiada |

**IMPORTANTE**: O `shipping_cost` no relatório de VENDAS é o que o COMPRADOR pagou.
O `SHIPPING_FEE_AMOUNT` no SETTLEMENT é o que foi DESCONTADO do vendedor.

---

## 4. Devoluções e Chargebacks

### 4.1 Tipos de Reversão

```
┌─────────────────────────────────────────────────────────────────┐
│                         REFUND (Devolução)                      │
│                                                                 │
│  INICIADO POR: Vendedor ou Mercado Livre (mediação)             │
│  QUANDO: Comprador reclama e há acordo/decisão                  │
│  IMPACTO FINANCEIRO:                                            │
│    - Valor devolvido ao comprador                               │
│    - Taxas podem ser estornadas (total ou parcialmente)         │
│  NO RELATÓRIO:                                                  │
│    - DINHEIRO EM CONTA: TRANSACTION_TYPE = "REFUND"             │
│    - LIBERAÇÕES: DESCRIPTION = "refund"                         │
│    - EXTRATO: "Reembolso" + ID da operação                      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      CHARGEBACK (Contestação)                   │
│                                                                 │
│  INICIADO POR: Banco/operadora do cartão                        │
│  QUANDO: Comprador não reconhece compra no cartão               │
│  IMPACTO FINANCEIRO:                                            │
│    - Valor FORÇADAMENTE retirado do vendedor                    │
│    - Taxas NÃO são devolvidas                                   │
│    - Pode haver taxa adicional de chargeback                    │
│  NO RELATÓRIO:                                                  │
│    - DINHEIRO EM CONTA: TRANSACTION_TYPE = "CHARGEBACK"         │
│    - LIBERAÇÕES: DESCRIPTION = "chargeback"                     │
│    - EXTRATO: Geralmente "Dinheiro retido" ou similar           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        DISPUTE (Reclamação)                     │
│                                                                 │
│  INICIADO POR: Comprador (via plataforma ML)                    │
│  QUANDO: Problema com produto/entrega                           │
│  IMPACTO FINANCEIRO:                                            │
│    - Dinheiro BLOQUEADO durante mediação                        │
│    - Se resolvido a favor do comprador → REFUND                 │
│    - Se resolvido a favor do vendedor → liberação normal        │
│  NO RELATÓRIO:                                                  │
│    - DINHEIRO EM CONTA: TRANSACTION_TYPE = "DISPUTE"            │
│    - EXTRATO: "Dinheiro retido" (bloqueio)                      │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Fluxo de uma Devolução

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ VENDA    │───▶│ RECLAMA- │───▶│ MEDIAÇÃO │───▶│ RESULTADO│
│ ORIGINAL │    │ ÇÃO      │    │          │    │          │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
     │               │               │               │
     │               │               │               ├── Favor Vendedor
     │               │               │               │   └── Libera normal
     │               │               │               │
     │               │               │               └── Favor Comprador
     │               │               │                   └── REFUND
     ▼               ▼               ▼                        │
┌─────────────────────────────────────────────────────────────┴───┐
│                    NO EXTRATO APARECE:                          │
│                                                                 │
│  1. "Liberação de dinheiro" - R$ 82,00 (venda original)         │
│  2. "Dinheiro retido" - R$ -82,00 (bloqueio por reclamação)     │
│  3. "Reembolso" - R$ -82,00 (se devolvido)                      │
│     OU                                                          │
│  3. Crédito de R$ 82,00 (se desbloqueado a favor do vendedor)   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 Estornos de Taxa em Devoluções

Quando há devolução, o Mercado Livre pode estornar as taxas:

| Tipo de Devolução | Estorno de Taxa |
|-------------------|-----------------|
| Devolução total (culpa do comprador) | 100% das taxas estornadas |
| Devolução total (culpa do vendedor) | Parcial ou nenhum |
| Devolução parcial | Proporcional ao valor |
| Chargeback | Nenhum estorno + taxa extra |

**No relatório de LIBERAÇÕES**, você verá:
- `DESCRIPTION: "refund"` com valores POSITIVOS = estorno de taxas
- `DESCRIPTION: "refund"` com valores NEGATIVOS = devolução ao comprador

---

## 5. Como Detalhar uma "Liberação de Dinheiro"

### 5.1 O Problema

O EXTRATO mostra apenas:
```
"Liberação de dinheiro" - R$ 82,00
```

Mas você precisa saber:
```
Receita: R$ 100,00
Comissão ML: R$ -12,00
Frete: R$ -6,00
Líquido: R$ 82,00
```

### 5.2 A Solução: Cruzamento de Dados

```
PASSO 1: Pegar REFERENCE_ID do EXTRATO
         └── Ex: "12345678901"

PASSO 2: Buscar no LIBERAÇÕES onde SOURCE_ID = "12345678901"
         └── Encontra linha com DESCRIPTION = "payment"

PASSO 3: Extrair valores detalhados:
         ├── GROSS_AMOUNT = R$ 100,00 (receita)
         ├── MP_FEE_AMOUNT = R$ -12,00 (comissão)
         ├── FINANCING_FEE_AMOUNT = R$ 0,00
         ├── SHIPPING_FEE_AMOUNT = R$ -6,00 (frete)
         └── NET_CREDIT_AMOUNT = R$ 82,00 (líquido)

PASSO 4: (Opcional) Buscar no VENDAS para obter:
         ├── Descrição do produto
         ├── Número do pedido ML
         └── Data da venda original
```

### 5.3 Algoritmo de Cruzamento

```python
# Pseudocódigo para cruzamento

para cada linha no EXTRATO:
    reference_id = linha['REFERENCE_ID']
    valor_extrato = linha['TRANSACTION_NET_AMOUNT']
    tipo = linha['TRANSACTION_TYPE']

    se tipo contém "Liberação de dinheiro":
        # Buscar detalhes no LIBERAÇÕES
        liberacao = LIBERACOES[SOURCE_ID == reference_id E DESCRIPTION == "payment"]

        se liberacao existe:
            receita = liberacao['GROSS_AMOUNT']
            comissao = liberacao['MP_FEE_AMOUNT'] + liberacao['FINANCING_FEE_AMOUNT']
            frete = liberacao['SHIPPING_FEE_AMOUNT']

            # Validar: receita + comissao + frete deve = valor_extrato

            gerar_lancamentos([
                (receita, "Receita de Venda"),
                (comissao, "Comissão Marketplace"),
                (frete, "Frete de Envio")
            ])
        senão:
            # Fallback: usar valor total como receita
            gerar_lancamento(valor_extrato, "Liberação de Venda")

    se tipo contém "Reembolso":
        # Buscar detalhes no LIBERAÇÕES
        refund = LIBERACOES[SOURCE_ID == reference_id E DESCRIPTION == "refund"]

        se refund existe:
            # Calcular proporções para detalhar
            ...
```

---

## 6. Cenários Especiais

### 6.1 Venda Parcelada sem Juros

```
Venda: R$ 300,00 em 3x sem juros

DINHEIRO EM CONTA:
  TRANSACTION_AMOUNT: R$ 300,00
  FEE_AMOUNT: R$ 45,00
    ├── Comissão: R$ 30,00 (10%)
    └── FINANCING_FEE: R$ 15,00 (5% de taxa de parcelamento)
  REAL_AMOUNT: R$ 255,00

LIBERAÇÕES (3 parcelas, uma por mês):
  Mês 1: NET_CREDIT_AMOUNT = R$ 85,00
  Mês 2: NET_CREDIT_AMOUNT = R$ 85,00
  Mês 3: NET_CREDIT_AMOUNT = R$ 85,00
```

### 6.2 Devolução Parcial

```
Venda original: R$ 200,00 (2 produtos de R$ 100,00 cada)
Devolução: 1 produto (R$ 100,00)

LIBERAÇÕES terá:
  1. payment (parcial): GROSS = R$ 100,00, NET_CREDIT = R$ 82,00
  2. refund: GROSS = R$ -100,00, NET_DEBIT = R$ 82,00
     + estorno proporcional de taxas
```

### 6.3 Liberação Cancelada

Quando uma venda é liberada mas depois há chargeback:

```
EXTRATO mostra:
  1. "Liberação de dinheiro" - R$ 82,00 (entrada)
  2. "Liberação de dinheiro cancelada" - R$ -82,00 (estorno)
```

### 6.4 PIX Recebido (não é venda ML)

```
EXTRATO:
  TRANSACTION_TYPE: "Transferência Pix recebida de FULANO"
  TRANSACTION_NET_AMOUNT: R$ 500,00

NÃO terá correspondência no LIBERAÇÕES ou DINHEIRO EM CONTA
(porque não é uma venda do Mercado Livre)

Tratamento: Classificar separadamente (pode ser venda externa,
transferência entre contas, etc.)
```

---

## 7. Glossário de Campos

### 7.1 Relatório DINHEIRO EM CONTA (Settlement)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| SOURCE_ID | String | ID único da transação no MP |
| TRANSACTION_TYPE | String | SETTLEMENT, REFUND, CHARGEBACK, DISPUTE, WITHDRAWAL, PAYOUT |
| TRANSACTION_DATE | Date | Data da transação |
| TRANSACTION_AMOUNT | Decimal | Valor bruto |
| FEE_AMOUNT | Decimal | Soma de todas as taxas |
| SHIPPING_FEE_AMOUNT | Decimal | Taxa de frete descontada |
| REAL_AMOUNT | Decimal | Valor líquido |
| MONEY_RELEASE_DATE | Date | Data prevista de liberação |
| EXTERNAL_REFERENCE | String | Referência externa (pedido) |
| SUB_UNIT | String | Origem (ex: "point" = maquininha) |

### 7.2 Relatório LIBERAÇÕES (Reserve-Release)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| SOURCE_ID | String | ID da transação original |
| DATE | Date | Data da liberação |
| DESCRIPTION | String | payment, refund, chargeback, shipping, payout |
| GROSS_AMOUNT | Decimal | Valor bruto |
| MP_FEE_AMOUNT | Decimal | Taxa do Mercado Pago |
| FINANCING_FEE_AMOUNT | Decimal | Taxa de parcelamento s/ juros |
| SHIPPING_FEE_AMOUNT | Decimal | Custo de envio |
| NET_CREDIT_AMOUNT | Decimal | Crédito líquido (entrada) |
| NET_DEBIT_AMOUNT | Decimal | Débito líquido (saída) |

### 7.3 Relatório EXTRATO (Account Statement)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| REFERENCE_ID | String | ID de referência (= SOURCE_ID) |
| TRANSACTION_TYPE | String | Descrição textual da transação |
| TRANSACTION_NET_AMOUNT | Decimal | Valor líquido movimentado |
| RELEASE_DATE | Date | Data do movimento |

### 7.4 Relatório VENDAS (Collection)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| operation_id | String | ID da operação (= SOURCE_ID) |
| order_id | String | ID do pedido no Mercado Livre |
| transaction_amount | Decimal | Valor do produto |
| shipping_cost | Decimal | Frete cobrado do comprador |
| date_created | Date | Data da venda |
| date_released | Date | Data prevista de liberação |
| shipment_status | String | Status do envio |

---

## 8. Regras de Negócio para Classificação

### 8.1 Categorias Contábeis

```
RECEITAS (valores positivos):
├── 1.1.1 MercadoLibre (vendas com order_id)
├── 1.1.2 Loja Própria (vendas sem order_id, não point)
├── 1.1.5 Vendas Diretas/Balcão (sub_unit = "point")
├── 1.3.4 Estornos de Taxas (refund com valores positivos)
└── 1.3.7 Estorno de Frete (bônus de envio)

DESPESAS (valores negativos):
├── 1.2.1 Devoluções e Cancelamentos (refund/chargeback)
├── 2.8.2 Comissões de Marketplace (MP_FEE + FINANCING_FEE)
├── 2.9.4 MercadoEnvios (SHIPPING_FEE)
└── 2.9.10 Logística Reversa (frete de devolução)
```

### 8.2 Regras de Classificação

```
REGRA 1: Origem da Venda
  SE existe order_id no VENDAS → origem = "ML"
  SE sub_unit contém "point" → origem = "BALCÃO"
  SENÃO → origem = "LOJA"

REGRA 2: Tipo de Transação
  SE TRANSACTION_TYPE = "SETTLEMENT" → é venda
  SE TRANSACTION_TYPE = "REFUND" → é devolução
  SE TRANSACTION_TYPE = "CHARGEBACK" → é contestação
  SE TRANSACTION_TYPE = "DISPUTE" → é reclamação (bloqueio)

REGRA 3: Detalhamento de Liberação
  SEMPRE buscar no LIBERAÇÕES para obter breakdown
  Receita = GROSS_AMOUNT ou valor do produto (VENDAS)
  Comissão = MP_FEE_AMOUNT + FINANCING_FEE_AMOUNT
  Frete = SHIPPING_FEE_AMOUNT (quando < 0)

REGRA 4: Validação
  SEMPRE: Receita + Comissão + Frete = Valor do Extrato
  SE não bater → registrar discrepância para revisão
```

---

## 9. Fontes e Referências

- [Documentação Oficial - Relatório de Liberações](https://www.mercadopago.com.br/developers/pt/docs/checkout-api/additional-content/reports/released-money)
- [Campos do Relatório - Dinheiro em Conta](https://www.mercadopago.com.br/developers/pt/docs/checkout-api/additional-content/reports/account-money/report-fields)
- [Central de Vendedores - Como recebo dinheiro](https://vendedores.mercadolivre.com.br/nota/como-recebo-o-dinheiro-das-minhas-vendas-no-mercado-livre)
- [Ajuda ML - Liberação de Dinheiro](https://www.mercadolivre.com.br/ajuda/3143)
- [API de Devoluções](https://developers.mercadolivre.com.br/pt_br/gerenciar-devolucoes)
- [Chargebacks - Documentação](https://www.mercadopago.com.br/developers/en/docs/checkout-pro/chargebacks)

---

## 10. Mapeamento Assertivo para IDs Múltiplos

### 10.1 O Problema dos IDs Múltiplos

Em alguns casos, o mesmo `SOURCE_ID` pode aparecer múltiplas vezes no EXTRATO com diferentes tipos de transação. Isso ocorre principalmente em casos de **reclamações com devolução**.

**Exemplo real:**
```
ID: 131861422575
EXTRATO:
  1. "Débito por dívida Reclamações no Mercado Livre" → R$ -167.90
  2. "Liberação de dinheiro"                          → R$  114.60
  3. "Reembolso Envío cancelado a ..."               → R$   53.30
  SOMA = R$ 0.00 (ciclo completo)
```

### 10.2 Mapeamento EXTRATO → LIBERAÇÕES

Cada tipo de transação do EXTRATO corresponde a um tipo específico no LIBERAÇÕES:

| EXTRATO (TRANSACTION_TYPE) | LIBERAÇÕES (DESCRIPTION) | Detalhamento |
|----------------------------|--------------------------|--------------|
| "Liberação de dinheiro" | `payment` | Receita (GROSS) + Comissão (MP_FEE + FIN_FEE) + Frete (SHIP_FEE) |
| "Débito por dívida Reclamações..." | `mediation` | Valor direto negativo |
| "Reembolso..." | `refund` | Estorno taxa (MP_FEE) + Estorno frete (SHIP_FEE) |
| "Dinheiro retido..." | `reserve_for_dispute` | Bloqueio/desbloqueio por disputa |

### 10.3 Como Funciona o Detalhamento Assertivo

```
PASSO 1: Identificar IDs com múltiplas transações no EXTRATO
         └── Agrupar por REFERENCE_ID e contar ocorrências

PASSO 2: Para cada linha do EXTRATO de um ID múltiplo:
         ├── Determinar o tipo de DESCRIPTION esperado no LIBERAÇÕES
         ├── Buscar o registro específico pelo valor (NET_AMOUNT ≈ valor extrato)
         └── Usar os campos detalhados (GROSS, MP_FEE, SHIP_FEE, etc.)

PASSO 3: Gerar lançamentos detalhados:
         ├── Para "payment": Receita + Comissão + Frete
         ├── Para "refund": Estorno taxa + Estorno frete
         ├── Para "mediation": Valor direto (débito)
         └── Para "reserve_for_dispute": Bloqueio/desbloqueio
```

### 10.4 Exemplo Completo de Detalhamento

**EXTRATO (ID: 131861422575):**
```
"Débito por dívida Reclamações..." → R$ -167.90
"Liberação de dinheiro"            → R$  114.60
"Reembolso Envío cancelado..."     → R$   53.30
```

**LIBERAÇÕES (mesmo ID):**
```
mediation: GROSS=-167.90, NET=-167.90
payment:   GROSS=167.90, MP_FEE=-19.69, FIN_FEE=-8.01, SHIP=-25.60, NET=114.60
refund:    GROSS=0.00, MP_FEE=19.69, FIN_FEE=8.01, SHIP=25.60, NET=53.30
```

**LANÇAMENTOS GERADOS:**
```
Para "Débito por dívida":
  └── Devoluções e Cancelamentos: R$ -167.90

Para "Liberação de dinheiro":
  ├── MercadoLibre (Receita):     R$  167.90
  ├── Comissões de Marketplace:   R$  -27.70
  └── MercadoEnvios (Frete):      R$  -25.60

Para "Reembolso":
  ├── Estorno de Taxa ML:         R$   27.70
  └── Estorno de Frete:           R$   25.60

SOMA TOTAL = R$ 0.00 ✓
```

### 10.5 Regras de Validação

1. **Soma por ID deve bater**: A soma de todos os lançamentos para um ID deve ser igual à soma das linhas do extrato para esse ID

2. **NET_AMOUNT como validador**: O `NET_CREDIT_AMOUNT - NET_DEBIT_AMOUNT` do LIBERAÇÕES deve ser aproximadamente igual ao valor do EXTRATO (tolerância de R$ 0.10)

3. **Fallback**: Se não encontrar correspondência no LIBERAÇÕES, usar o valor direto do extrato com categoria apropriada

---

## 11. Tratamento do Frete (Vendedor vs Comprador)

### 11.1 O Problema

O frete pode ser pago por duas partes diferentes:
- **VENDEDOR paga frete**: É uma despesa real do vendedor (ex: frete grátis)
- **COMPRADOR paga frete**: É apenas um repasse (entra e sai da conta)

### 11.2 Como Identificar Quem Paga

Consultar o campo `Frete (shipping_cost)` no relatório **VENDAS**:

| VENDAS.Frete | Significado | Tratamento |
|--------------|-------------|------------|
| `< 0` (negativo) | **Vendedor** paga frete | Lançar como despesa separada |
| `= 0` | **Comprador** pagou | Excluir da receita (repasse) |

### 11.3 Exemplos Reais

**Caso 1: COMPRADOR paga frete (ID: 131161010175)**
```
VENDAS:
  Produto:      R$  39,03
  Frete:        R$   0,00  ← Comprador pagou

LIBERAÇÕES:
  GROSS_AMOUNT:   R$  46,02  (inclui frete)
  SHIPPING_FEE:   R$  -6,99  (repasse)

LANÇAMENTOS:
  Receita:      R$  39,03  (GROSS + SHIPPING = 46,02 - 6,99)
  Comissão:     R$ -13,14
  Frete:        NÃO LANÇA  (é repasse)
```

**Caso 2: VENDEDOR paga frete (ID: 128484156479)**
```
VENDAS:
  Produto:      R$ 106,01
  Frete:        R$ -16,41  ← Vendedor paga (negativo)

LIBERAÇÕES:
  GROSS_AMOUNT:   R$ 106,01  (só produto)
  SHIPPING_FEE:   R$ -16,41  (despesa)

LANÇAMENTOS:
  Receita:      R$ 106,01  (GROSS, valor cheio)
  Comissão:     R$ -XX,XX
  Frete:        R$ -16,41  ← LANÇA como despesa
```

### 11.4 Implementação no Código

```python
# Consultar VENDAS para saber quem paga frete
frete_vendas = map_vendas[op_id].get('frete_comprador', 0.0)
vendedor_paga_frete = frete_vendas < -0.01  # Negativo = vendedor paga

if vendedor_paga_frete:
    # Vendedor paga: Receita = GROSS, Frete = despesa separada
    receita = gross
    frete_despesa = frete_lib  # Lançar como despesa
else:
    # Comprador pagou: Receita = valor do produto (sem frete)
    receita = gross + frete_lib  # Desconta frete embutido
    frete_despesa = 0.0  # Não lançar (é repasse)
```

### 11.5 Resumo

| Quem Paga | Receita | Frete |
|-----------|---------|-------|
| Comprador | GROSS + SHIPPING_FEE | Não lança |
| Vendedor | GROSS | Lança como despesa |

---

## 12. Separação CONFIRMADOS vs PREVISÃO

### 12.1 Regra Fundamental

O EXTRATO é a **fonte de verdade** para determinar se uma transação foi confirmada:

```
CONFIRMADOS = Transações presentes no EXTRATO (movimentaram a conta)
PREVISÃO    = Transações do DINHEIRO EM CONTA que ainda não estão no EXTRATO
```

### 12.2 Pagamentos de Faturas ML (SETTLEMENT Negativo)

Transações do tipo `SETTLEMENT` com valor **negativo** no relatório DINHEIRO EM CONTA representam pagamentos de faturas/cobranças automáticas do Mercado Livre.

**Identificação:**
- `TRANSACTION_TYPE` = SETTLEMENT
- `REAL_AMOUNT` = valor negativo
- `EXTERNAL_REFERENCE` contém "MELIPAYMENTS-COLLECTIONATTEMPT"

**Tratamento:**

| Presente no EXTRATO? | Destino | Arquivo |
|---------------------|---------|---------|
| Sim | CONFIRMADOS | PAGAMENTO_CONTAS.csv |
| Não | PREVISÃO | IMPORTACAO_CONTA_AZUL_PREVISAO.csv |

### 12.3 Exemplo Real

```
DINHEIRO EM CONTA:
  ID: 130293587397
  TRANSACTION_TYPE: SETTLEMENT
  REAL_AMOUNT: -195.89
  EXTERNAL_REFERENCE: MELIPAYMENTS-COLLECTIONATTEMPT-1541937786...

EXTRATO:
  (não encontrado)

RESULTADO:
  → Vai para PREVISÃO (categoria: 2.1.1 Compra de Mercadorias)
  → NÃO vai para CONFIRMADOS
```

### 12.4 Validação

A soma dos arquivos de saída deve bater com o EXTRATO:

```
CONFIRMADOS + PAGAMENTOS + TRANSFERÊNCIAS = EXTRATO (tolerância: R$ 0.10)
```

Se a diferença for maior, verificar:
1. Transações do DINHEIRO EM CONTA sendo classificadas como CONFIRMADAS indevidamente
2. IDs duplicados ou não mapeados corretamente

---

*Documento criado em: Novembro 2025*
*Versão: 1.4 - Adicionada regra de separação CONFIRMADOS vs PREVISÃO*
