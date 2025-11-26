# Super Conciliador API

**Versão:** 2.0.0
**Porta:** 1909
**Tecnologia:** FastAPI + Python 3.11

---

## Sumário

1. [Visão Geral](#visão-geral)
2. [Arquitetura](#arquitetura)
3. [Instalação e Deploy](#instalação-e-deploy)
4. [Endpoints](#endpoints)
5. [Arquivos de Entrada](#arquivos-de-entrada)
6. [Arquivos de Saída](#arquivos-de-saída)
7. [Plano de Contas - Conta Azul](#plano-de-contas---conta-azul)
8. [Regras de Negócio](#regras-de-negócio)
9. [Mapeamento de Categorias](#mapeamento-de-categorias)
10. [Exemplos de Uso](#exemplos-de-uso)
11. [API V2 - Melhorias](#api-v2---melhorias)

---

## Visão Geral

A **Super Conciliador API** é uma solução de automação contábil que processa relatórios financeiros do **Mercado Livre/Mercado Pago** e gera arquivos formatados para importação no sistema **Conta Azul**.

### Problema Resolvido

Vendedores do Mercado Livre precisam conciliar manualmente centenas de transações mensais, classificando cada uma em categorias contábeis. Este processo manual é:
- Demorado (horas de trabalho)
- Propenso a erros
- Repetitivo

### Solução

A API automatiza todo o processo:
1. Recebe 5-6 relatórios CSV do Mercado Livre
2. Cruza informações entre os relatórios
3. Classifica automaticamente cada transação
4. Gera arquivos prontos para importação no Conta Azul

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                        ENTRADA (CSV)                            │
├─────────────┬─────────────┬─────────────┬─────────────┬─────────┤
│  Dinheiro   │   Vendas    │  Pós-Venda  │ Liberações  │ Extrato │
│ (settlement)│ (collection)│(after_coll) │(reserve-rel)│(account)│
└──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┴────┬────┘
       │             │             │             │           │
       └─────────────┴─────────────┼─────────────┴───────────┘
                                   │
                                   ▼
                    ┌──────────────────────────┐
                    │   PROCESSAMENTO          │
                    │                          │
                    │  • Normalização de IDs   │
                    │  • Cruzamento de dados   │
                    │  • Classificação         │
                    │  • Cálculo de valores    │
                    └────────────┬─────────────┘
                                 │
                                 ▼
       ┌─────────────────────────────────────────────────────┐
       │                    SAÍDA (ZIP)                      │
       ├─────────────┬─────────────┬─────────────┬───────────┤
       │ Confirmados │  Previsão   │ Pagamentos  │Transferên.│
       │ (CSV/XLSX)  │ (CSV/XLSX)  │ (CSV/XLSX)  │(CSV/XLSX) │
       └─────────────┴─────────────┴─────────────┴───────────┘
```

### Tecnologias Utilizadas

| Componente | Tecnologia | Versão |
|------------|------------|--------|
| Framework | FastAPI | >= 0.104.0 |
| Servidor | Uvicorn | >= 0.24.0 |
| Processamento | Pandas | >= 2.0.0 |
| Cálculos | NumPy | >= 1.24.0 |
| Excel | OpenPyXL | >= 3.1.0 |
| Upload | python-multipart | >= 0.0.6 |
| Runtime | Python | 3.11 |

---

## Instalação e Deploy

### Requisitos

- Docker e Docker Compose
- Ou Python 3.11+ com pip

### Deploy com Docker (Recomendado)

```bash
# Clonar repositório
git clone git@github.com:Eryk-dev/apiconciliador.git
cd apiconciliador

# Build e iniciar
docker-compose up -d --build

# Verificar status
docker-compose ps
docker logs conciliador-api
```

### Deploy Manual

```bash
# Instalar dependências
pip install -r requirements.txt

# Iniciar servidor
python api.py
# ou
uvicorn api:app --host 0.0.0.0 --port 1909
```

### Configurações Docker

| Parâmetro | Valor |
|-----------|-------|
| Porta | 1909 |
| Memória Limite | 512MB |
| Memória Reservada | 256MB |
| Timezone | America/Sao_Paulo |
| Health Check | A cada 30s |

---

## Endpoints

### GET `/`

Health check básico.

**Resposta:**
```json
{
    "status": "online",
    "service": "Super Conciliador API",
    "version": "1.0.0"
}
```

### GET `/health`

Health check detalhado com versões das dependências.

**Resposta:**
```json
{
    "status": "healthy",
    "timestamp": "2024-01-15T10:30:00",
    "dependencies": {
        "pandas": "2.1.0",
        "numpy": "1.26.0"
    }
}
```

### POST `/conciliar`

Endpoint principal que processa os relatórios e retorna um ZIP.

**Content-Type:** `multipart/form-data`

**Parâmetros:**

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `dinheiro` | File (CSV) | Sim | Settlement report |
| `vendas` | File (CSV) | Sim | Collection report |
| `pos_venda` | File (CSV) | Sim | After collection report |
| `liberacoes` | File (CSV) | Sim | Reserve-release report |
| `extrato` | File (CSV) | Sim | Account statement report |
| `retirada` | File (CSV) | Não | Withdraw report |
| `centro_custo` | String | Não | Centro de custo (padrão: "NETAIR") |

**Resposta:**
- **Content-Type:** `application/zip`
- **Headers:**
  - `X-Stats-Confirmados`: Quantidade de lançamentos confirmados
  - `X-Stats-Previsao`: Quantidade de lançamentos de previsão
  - `X-Stats-Pagamentos`: Quantidade de pagamentos
  - `X-Stats-Transferencias`: Quantidade de transferências

---

## Arquivos de Entrada

### 1. Dinheiro em Conta (settlement)

Relatório de settlement do Mercado Pago.

**Colunas principais:**
- `SOURCE_ID` - ID da operação
- `TRANSACTION_TYPE` - Tipo (SETTLEMENT, REFUND, CHARGEBACK, etc.)
- `TRANSACTION_DATE` - Data da transação
- `TRANSACTION_AMOUNT` - Valor bruto
- `FEE_AMOUNT` - Taxa total
- `SHIPPING_FEE_AMOUNT` - Taxa de frete
- `REAL_AMOUNT` - Valor líquido
- `MONEY_RELEASE_DATE` - Data de liberação prevista
- `EXTERNAL_REFERENCE` - Referência externa (pedido)
- `SUB_UNIT` - Origem (point = balcão)

### 2. Vendas (collection)

Relatório de vendas/cobranças.

**Colunas principais:**
- `Número da transação do Mercado Pago (operation_id)` - ID da operação
- `Número da venda no Mercado Livre (order_id)` - ID do pedido ML
- `Descrição da operação (reason)` - Descrição
- `Valor do produto (transaction_amount)` - Valor do produto
- `Frete (shipping_cost)` - Custo de frete
- `Status do envio (shipment_status)` - Status de entrega
- `Data da compra (date_created)` - Data da venda
- `Data de liberação do dinheiro (date_released)` - Data de liberação

### 3. Pós-Venda (after_collection)

Relatório de eventos pós-venda.

**Colunas principais:**
- `ID da transação (operation_id)` - ID da operação
- `Motivo detalhado (reason_detail)` - Descrição detalhada

### 4. Liberações (reserve-release)

Relatório de liberações de saldo.

**Colunas principais:**
- `SOURCE_ID` - ID da operação
- `DATE` - Data da liberação
- `DESCRIPTION` - Tipo (payment, refund)
- `GROSS_AMOUNT` - Valor bruto
- `NET_CREDIT_AMOUNT` - Crédito líquido
- `NET_DEBIT_AMOUNT` - Débito líquido
- `MP_FEE_AMOUNT` - Taxa Mercado Pago
- `FINANCING_FEE_AMOUNT` - Taxa de parcelamento
- `SHIPPING_FEE_AMOUNT` - Taxa de frete

### 5. Extrato (account_statement)

Extrato da conta Mercado Pago.

**Observação:** Este arquivo tem 3 linhas de cabeçalho que são ignoradas.

**Colunas principais:**
- `REFERENCE_ID` - ID da operação
- `TRANSACTION_TYPE` - Tipo/descrição da transação
- `TRANSACTION_NET_AMOUNT` - Valor líquido
- `RELEASE_DATE` - Data de lançamento

### 6. Retirada (withdraw) - Opcional

Relatório de saques/retiradas da conta.

---

## Arquivos de Saída

O endpoint `/conciliar` retorna um arquivo ZIP contendo:

### Arquivos Gerados

| Arquivo | Descrição |
|---------|-----------|
| `IMPORTACAO_CONTA_AZUL_CONFIRMADOS.csv` | Lançamentos já realizados (CSV) |
| `IMPORTACAO_CONTA_AZUL_CONFIRMADOS.xlsx` | Lançamentos já realizados (Excel) |
| `IMPORTACAO_CONTA_AZUL_CONFIRMADOS_RESUMO.xlsx` | Lançamentos agrupados por data/categoria |
| `IMPORTACAO_CONTA_AZUL_PREVISAO.csv` | Lançamentos pendentes de liberação (CSV) |
| `IMPORTACAO_CONTA_AZUL_PREVISAO.xlsx` | Lançamentos pendentes de liberação (Excel) |
| `IMPORTACAO_CONTA_AZUL_PREVISAO_RESUMO.xlsx` | Previsões agrupadas por data/categoria |
| `PAGAMENTO_CONTAS.csv` | Pagamentos feitos via MP (CSV) |
| `PAGAMENTO_CONTAS.xlsx` | Pagamentos feitos via MP (Excel) |
| `TRANSFERENCIAS.csv` | PIX e transferências (CSV) |
| `TRANSFERENCIAS.xlsx` | PIX e transferências (Excel) |

### Estrutura dos Arquivos de Saída

Todos os arquivos seguem o formato de importação do Conta Azul:

| Coluna | Descrição |
|--------|-----------|
| Data de Competência | Data do fato gerador |
| Data de Vencimento | Data de vencimento |
| Data de Pagamento | Data do pagamento efetivo |
| Valor | Valor da transação |
| Categoria | Categoria do plano de contas |
| Descrição | Descrição do lançamento |
| Cliente/Fornecedor | "MERCADO LIVRE" |
| CNPJ/CPF Cliente/Fornecedor | "03007331000141" |
| Centro de Custo | Centro de custo configurado |
| Observações | Observações adicionais |

---

## Plano de Contas - Conta Azul

### REGRA FUNDAMENTAL DE VALORES

> **IMPORTANTE:** As categorias de **RECEITA** devem receber apenas **valores POSITIVOS**.
> As categorias de **DESPESA** devem receber apenas **valores NEGATIVOS**.

---

### Categorias de Receita (Valores POSITIVOS)

#### 1.1 RECEITA DE VENDAS

| Código | Categoria |
|--------|-----------|
| 1.1.1 | MercadoLibre |
| 1.1.2 | Loja Própria (E-commerce) |
| 1.1.3 | Vendas B2B (Atacado) |
| 1.1.4 | Marketplace (Outros - Shopee, Amazon, Magalu) |
| 1.1.5 | Vendas Diretas/Balcão |
| 1.1.6 | Serviços (Instalação, Consultoria) |

#### 1.3 OUTRAS RECEITAS OPERACIONAIS

| Código | Categoria |
|--------|-----------|
| 1.3.1 | Receita de Frete Cobrado |
| 1.3.2 | Juros Recebidos |
| 1.3.3 | Rendimento de Aplicações |
| 1.3.4 | Descontos e Estornos de Taxas e Tarifas |
| 1.3.5 | Receitas Intercompany |
| 1.3.6 | Reversão de Provisões |
| 1.3.7 | Estorno de Frete sobre Vendas |

#### 1.4 RECEITAS NÃO OPERACIONAIS

| Código | Categoria |
|--------|-----------|
| 1.4.1 | Venda de Ativo Imobilizado |
| 1.4.2 | Outras Receitas Eventuais |

---

### Categorias de Despesa (Valores NEGATIVOS)

#### 1.2 DEDUÇÕES DA RECEITA BRUTA

| Código | Categoria |
|--------|-----------|
| 1.2.1 | Devoluções e Cancelamentos |
| 1.2.2 | Descontos Comerciais |
| 1.2.3 | Abatimentos |

#### 2.1 CUSTO DE PRODUTOS

| Código | Categoria |
|--------|-----------|
| 2.1.1 | Compra de Mercadorias |
| 2.1.2 | Frete sobre Compras (Entrada) |
| 2.1.3 | Seguro de Transporte - Entrada |
| 2.1.4 | Embalagens |
| 2.1.5 | Material de Empacotamento |
| 2.1.6 | Custo de Mercadoria Vendida |

#### 2.2 IMPOSTOS SOBRE VENDAS

| Código | Categoria |
|--------|-----------|
| 2.2.1 | ICMS |
| 2.2.2 | ICMS-ST (Substituição Tributária) |
| 2.2.3 | DIFAL (Diferencial de Alíquota) |
| 2.2.4 | PIS |
| 2.2.5 | COFINS |
| 2.2.6 | ISS (Serviços) |
| 2.2.7 | Simples Nacional |

#### 2.3 IMPOSTOS DIVERSOS

| Código | Categoria |
|--------|-----------|
| 2.3.1 | IPTU |
| 2.3.2 | IPVA e Licenciamento |

#### 2.4 DESPESAS COM PESSOAL

| Código | Categoria |
|--------|-----------|
| 2.4.1 | Salários e Ordenados (CLT) |
| 2.4.2 | Pró-Labore (Sócios) |
| 2.4.3 | Prestadores de Serviço (PJ) |
| 2.4.4 | Horas Extras |
| 2.4.5 | Férias e 13º Salário |
| 2.4.6 | Aviso Prévio e Rescisões |
| 2.4.7 | FGTS |
| 2.4.8 | INSS Patronal |
| 2.4.9 | Rateio de Funcionários Compartilhados |
| 2.4.10 | Vale Transporte (VT) |
| 2.4.11 | Plano de Saúde |
| 2.4.12 | Seguro de Vida |
| 2.4.13 | Treinamentos e Capacitação |
| 2.4.14 | Uniformes e EPIs |
| 2.4.15 | INSS |

#### 2.5 DESPESAS ADMINISTRATIVAS

| Código | Categoria |
|--------|-----------|
| 2.5.1 | Aluguel |
| 2.5.2 | Condomínio |
| 2.5.3 | Energia Elétrica |
| 2.5.4 | Água e Esgoto |
| 2.5.5 | Telefone e Internet |
| 2.5.6 | Correios (Administrativo) |
| 2.5.7 | Material de Escritório |
| 2.5.8 | Material de Limpeza |
| 2.5.9 | Manutenção e Reparos |
| 2.5.10 | Segurança e Vigilância |
| 2.5.11 | Seguros |
| 2.5.12 | Depreciação |

#### 2.6 TECNOLOGIA E SISTEMAS

| Código | Categoria |
|--------|-----------|
| 2.6.1 | Software e Licenças |
| 2.6.2 | ERP |
| 2.6.3 | Software de Automação |
| 2.6.4 | Banco de Dados (Supabase) |
| 2.6.5 | APIs e Integrações |
| 2.6.6 | Hospedagem de Sites |
| 2.6.7 | Cloud Computing |
| 2.6.8 | Desenvolvimento de Software |
| 2.6.9 | Domínios e SSL |
| 2.6.10 | Manutenção de Sistemas |

#### 2.7 MARKETING E PUBLICIDADE

| Código | Categoria |
|--------|-----------|
| 2.7.1 | Google Ads |
| 2.7.2 | Meta Ads |
| 2.7.3 | Marketing em Marketplace |
| 2.7.4 | Anúncios MercadoLibre |
| 2.7.5 | SEO e Conteúdo |
| 2.7.6 | Design e Criação |
| 2.7.7 | Fotografia de Produtos |
| 2.7.8 | Agência de Marketing |
| 2.7.9 | Brindes e Materiais Promocionais |
| 2.7.10 | Tiktok ADS |

#### 2.8 DESPESAS COMERCIAIS

| Código | Categoria |
|--------|-----------|
| 2.8.1 | Comissões de Vendedores |
| 2.8.2 | Comissões de Marketplace |
| 2.8.3 | Bonificações e Prêmios |
| 2.8.4 | Viagens e Representação |
| 2.8.5 | Participação em Feiras |
| 2.8.6 | Amostras e Demonstrações |

#### 2.9 LOGÍSTICA E EXPEDIÇÃO

| Código | Categoria |
|--------|-----------|
| 2.9.1 | Frete sobre Vendas (Saída) |
| 2.9.2 | Correios (Envios) |
| 2.9.3 | Transportadoras |
| 2.9.4 | MercadoEnvios |
| 2.9.5 | Entrega Local |
| 2.9.6 | Embalagens de Envio |
| 2.9.7 | Seguro de Transporte - Saída |
| 2.9.8 | Armazenagem |
| 2.9.9 | Picking e Packing |
| 2.9.10 | Logística Reversa |

#### 2.10 DESPESAS LEGAIS E CONTÁBEIS

| Código | Categoria |
|--------|-----------|
| 2.10.1 | Honorários Contábeis |
| 2.10.2 | Honorários Advocatícios |
| 2.10.3 | Taxas e Contribuições |
| 2.10.4 | Certidões e Registros |
| 2.10.5 | Multas e Juros |
| 2.10.6 | Despesas Cartorárias |
| 2.10.7 | Anuidades Profissionais |

#### 2.11 DESPESAS FINANCEIRAS

| Código | Categoria |
|--------|-----------|
| 2.11.1 | Juros sobre Empréstimos |
| 2.11.2 | Juros sobre Financiamentos |
| 2.11.3 | Taxa de Administração de Consórcio |
| 2.11.4 | IOF |
| 2.11.5 | Tarifas Bancárias |
| 2.11.6 | Tarifas de Cartão de Crédito |
| 2.11.7 | Tarifas de Pagamento (Mercado Pago, PagSeguro) |
| 2.11.8 | Antecipação de Recebíveis |
| 2.11.9 | Descontos Concedidos (Financeiros) |
| 2.11.10 | Variação Cambial Passiva |
| 2.11.11 | Juros de Mora |

#### 2.12 DESPESAS COM VEÍCULOS

| Código | Categoria |
|--------|-----------|
| 2.12.1 | Combustível |
| 2.12.2 | Manutenção de Veículos |
| 2.12.3 | Seguro de Veículos |
| 2.12.4 | Estacionamento e Pedágios |

#### 2.13 IMPOSTOS SOBRE LUCRO

| Código | Categoria |
|--------|-----------|
| 2.13.1 | IRPJ (Imposto de Renda PJ) |
| 2.13.2 | CSLL (Contribuição Social) |
| 2.13.3 | Adicional de IRPJ |

#### 2.14 OUTRAS DESPESAS OPERACIONAIS

| Código | Categoria |
|--------|-----------|
| 2.14.1 | Despesas com Viagens |
| 2.14.2 | Alimentação e Refeições |
| 2.14.3 | Despesas Médicas e Exames |
| 2.14.4 | Doações e Patrocínios |
| 2.14.5 | Perdas com Inadimplência |
| 2.14.6 | Quebras e Perdas de Estoque |
| 2.14.7 | Perdas em Garantia |
| 2.14.8 | Despesas Eventuais |

#### 2.15 INVESTIMENTOS (P&D E EXPANSÃO)

| Código | Categoria |
|--------|-----------|
| 2.15.1 | Pesquisa e Desenvolvimento |
| 2.15.2 | Expansão de Negócios |
| 2.15.3 | Consultoria Empresarial |
| 2.15.4 | Compra de Ativo Imobilizado |

#### 2.16 DESPESAS INTERCOMPANY

| Código | Categoria |
|--------|-----------|
| 2.16.1 | Serviços Contratados Intercompany |
| 2.16.2 | Aluguel Pago Intercompany |
| 2.16.3 | Rateio de Custos Compartilhados |
| 2.16.4 | Royalties e Licenciamento Interno |

#### Outros

| Categoria |
|-----------|
| Outros Impostos |
| Pagamento Dividendos |

---

## Regras de Negócio

### 1. Classificação de Origem da Venda

A API identifica automaticamente a origem de cada venda:

| Origem | Critério | Categoria de Receita |
|--------|----------|---------------------|
| **ML** | Possui `order_id` do Mercado Livre | 1.1.1 MercadoLibre |
| **BALCÃO** | `SUB_UNIT` contém "point" | 1.1.5 Vendas Diretas/Balcão |
| **LOJA** | Demais casos | 1.1.2 Loja Própria (E-commerce) |

### 2. Tipos de Transação

| Tipo | Tratamento |
|------|------------|
| `SETTLEMENT` | Venda normal - gera receita, comissão e frete |
| `REFUND` | Reembolso - devolução de valores |
| `CHARGEBACK` | Contestação - estorno forçado |
| `CANCELLATION` | Cancelamento - venda cancelada |
| `DISPUTE` | Disputa - mediação em andamento |
| `MONEY_TRANSFER` | Transferência - ignorado (vai para Transferências) |
| `PAYOUT` | Saque - ignorado |

### 3. Cálculo de Valores

Para cada venda (`SETTLEMENT`), a API calcula:

```
Receita = Valor do produto (transaction_amount)
Comissão = Receita + Frete - Valor Líquido
Frete = Custo de envio (quando pago pelo vendedor)
```

### 4. Datas

| Campo | Uso |
|-------|-----|
| Data de Competência | Data do fato gerador (venda ou evento) |
| Data de Pagamento | Data efetiva da liberação/movimentação |
| Data de Vencimento | Igual à Data de Pagamento |

### 5. Separação de Arquivos

| Arquivo | Critério |
|---------|----------|
| **Confirmados** | Transações já liberadas (aparecem no extrato) |
| **Previsão** | Transações pendentes de liberação |
| **Pagamentos** | Pagamentos feitos via Mercado Pago (valores negativos) |
| **Transferências** | PIX, transferências, pagamentos de cartão |

---

## Mapeamento de Categorias

### Categorias Utilizadas pela API

| Chave Interna | Categoria Conta Azul | Tipo |
|---------------|---------------------|------|
| `RECEITA_ML` | 1.1.1 MercadoLibre | Receita (+) |
| `RECEITA_LOJA` | 1.1.2 Loja Própria (E-commerce) | Receita (+) |
| `RECEITA_BALCAO` | 1.1.5 Vendas Diretas/Balcão | Receita (+) |
| `COMISSAO` | 2.8.2 Comissões de Marketplace | Despesa (-) |
| `FRETE_ENVIO` | 2.9.4 MercadoEnvios | Despesa (-) |
| `FRETE_REVERSO` | 2.9.10 Logística Reversa | Despesa (-) |
| `DEVOLUCAO` | 1.2.1 Devoluções e Cancelamentos | Despesa (-) |
| `TRANSFERENCIA` | Transferências | Neutro |
| `PAGAMENTO_CONTA` | 2.1.1 Compra de Mercadorias | Despesa (-) |
| `ESTORNO_FRETE` | 1.3.7 Estorno de Frete sobre Vendas | Receita (+) |
| `ESTORNO_TAXA` | 1.3.4 Descontos e Estornos de Taxas e Tarifas | Receita (+) |
| `DIFAL` | 2.2.3 DIFAL (Diferencial de Alíquota) | Despesa (-) |
| `OUTROS` | 2.14.8 Despesas Eventuais | Despesa (-) |

---

## Exemplos de Uso

### cURL

```bash
curl -X POST "http://localhost:1909/conciliar" \
  -F "dinheiro=@settlement_report.csv" \
  -F "vendas=@collection_report.csv" \
  -F "pos_venda=@after_collection_report.csv" \
  -F "liberacoes=@reserve_release_report.csv" \
  -F "extrato=@account_statement_report.csv" \
  -F "centro_custo=MINHA_EMPRESA" \
  -o conciliacao.zip
```

### Python

```python
import requests

url = "http://localhost:1909/conciliar"

files = {
    'dinheiro': open('settlement_report.csv', 'rb'),
    'vendas': open('collection_report.csv', 'rb'),
    'pos_venda': open('after_collection_report.csv', 'rb'),
    'liberacoes': open('reserve_release_report.csv', 'rb'),
    'extrato': open('account_statement_report.csv', 'rb'),
}

data = {
    'centro_custo': 'MINHA_EMPRESA'
}

response = requests.post(url, files=files, data=data)

if response.status_code == 200:
    with open('conciliacao.zip', 'wb') as f:
        f.write(response.content)

    # Estatísticas nos headers
    print(f"Confirmados: {response.headers.get('X-Stats-Confirmados')}")
    print(f"Previsão: {response.headers.get('X-Stats-Previsao')}")
    print(f"Pagamentos: {response.headers.get('X-Stats-Pagamentos')}")
    print(f"Transferências: {response.headers.get('X-Stats-Transferencias')}")
else:
    print(f"Erro: {response.json()}")
```

### JavaScript (Fetch)

```javascript
const formData = new FormData();
formData.append('dinheiro', dinheiroFile);
formData.append('vendas', vendasFile);
formData.append('pos_venda', posVendaFile);
formData.append('liberacoes', liberacoesFile);
formData.append('extrato', extratoFile);
formData.append('centro_custo', 'MINHA_EMPRESA');

const response = await fetch('http://localhost:1909/conciliar', {
    method: 'POST',
    body: formData
});

if (response.ok) {
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'conciliacao.zip';
    a.click();
}
```

---

## Troubleshooting

### Erro 400 - Arquivo inválido

**Causa:** Arquivo CSV com formato incorreto ou colunas faltando.

**Solução:** Verifique se os arquivos são os relatórios corretos do Mercado Livre e estão no formato CSV.

### Erro 500 - Erro de processamento

**Causa:** Dados inconsistentes entre os relatórios.

**Solução:**
1. Certifique-se de que todos os relatórios são do mesmo período
2. Verifique se os IDs das operações estão presentes em todos os arquivos

### ZIP vazio ou sem arquivos

**Causa:** Nenhuma transação encontrada nos relatórios.

**Solução:** Verifique se os arquivos contêm dados e se o período está correto.

---

## API V2 - Melhorias

A versão 2.0 da API (`api_v2.py`) traz melhorias significativas no processamento e classificação das transações.

### Principais Mudanças

#### 1. EXTRATO como Fonte de Verdade

Na V2, o **EXTRATO** é usado como fonte principal de dados, garantindo que apenas transações que realmente movimentaram a conta sejam processadas.

```
V1: DINHEIRO EM CONTA → processa e cruza com outros
V2: EXTRATO → valida e detalha usando LIBERAÇÕES
```

#### 2. Detalhamento Assertivo para IDs Múltiplos

A V2 resolve o problema de IDs que aparecem múltiplas vezes no extrato (ex: reclamações com devolução).

**Mapeamento EXTRATO → LIBERAÇÕES:**

| EXTRATO | LIBERAÇÕES |
|---------|------------|
| "Liberação de dinheiro" | `payment` |
| "Débito por dívida Reclamações..." | `mediation` |
| "Reembolso..." | `refund` |
| "Dinheiro retido..." | `reserve_for_dispute` |

#### 3. Validação de 100%

A V2 garante que a soma dos lançamentos por ID seja igual ao valor do extrato.

```python
# Validação por ID
soma_lancamentos[op_id] == soma_extrato[op_id]  # Tolerância: R$ 0.05
```

### Funções Principais da V2

| Função | Descrição |
|--------|-----------|
| `buscar_liberacao_por_tipo_e_valor()` | Busca registro específico no LIBERAÇÕES baseado no tipo de transação |
| `detalhar_transacao_assertiva()` | Detalha transação usando mapeamento assertivo |
| `detalhar_liberacao_payment()` | Detalha liberação de pagamento (receita + comissão) |
| `detalhar_refund()` | Detalha reembolso (estornos de taxa e frete) |

### Tratamento do Frete (Vendedor vs Comprador)

A V2.2 diferencia quem pagou o frete consultando `VENDAS.Frete`:

| VENDAS.Frete | Quem Paga | Tratamento |
|--------------|-----------|------------|
| `< 0` (negativo) | Vendedor | Receita = GROSS, Frete = despesa |
| `= 0` | Comprador | Receita = GROSS + SHIPPING (exclui frete) |

**Exemplo - Comprador paga (ID: 131161010175):**
```
Receita:  R$ 39,03  (46,02 - 6,99 = valor produto)
Comissão: R$ -13,14
Frete:    NÃO LANÇA (é repasse)
```

**Exemplo - Vendedor paga:**
```
Receita:  R$ 106,01  (GROSS cheio)
Comissão: R$ -XX,XX
Frete:    R$ -16,41  (despesa real)
```

### Separação CONFIRMADOS vs PREVISÃO

A API separa rigorosamente transações **confirmadas** (presentes no EXTRATO) das **previsões** (ainda não movimentaram a conta):

#### Regra Fundamental

> **CONFIRMADOS:** Somente transações que aparecem no EXTRATO
> **PREVISÃO:** Transações do DINHEIRO EM CONTA que ainda não estão no EXTRATO

#### Tratamento de Pagamentos (SETTLEMENT Negativo)

Transações do tipo `SETTLEMENT` com valor **negativo** no DINHEIRO EM CONTA representam pagamentos de faturas/cobranças do ML (ex: `MELIPAYMENTS-COLLECTIONATTEMPT`).

| Situação | Destino | Motivo |
|----------|---------|--------|
| SETTLEMENT negativo **no EXTRATO** | CONFIRMADOS | Já movimentou a conta |
| SETTLEMENT negativo **só no DINHEIRO EM CONTA** | PREVISÃO | Ainda não debitado |

**Exemplo real:**
```
ID: 130293587397
DINHEIRO EM CONTA: SETTLEMENT = -R$ 195,89
EXTRATO: NÃO ENCONTRADO
→ Vai para PREVISÃO (não para CONFIRMADOS)
```

Esta regra garante que a soma dos arquivos CONFIRMADOS + PAGAMENTOS + TRANSFERÊNCIAS seja **igual ao total do EXTRATO**.

### Documentação Técnica Adicional

Para detalhes completos sobre o fluxo financeiro do Mercado Livre e o mapeamento de campos, consulte:

- **[FLUXO_FINANCEIRO_ML.md](FLUXO_FINANCEIRO_ML.md)** - Documentação completa do ciclo de vida das transações

---

## Contato e Suporte

- **Repositório:** https://github.com/Eryk-dev/apiconciliador
- **Versão:** 2.3.0
