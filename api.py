"""
API do Super Conciliador - Mercado Livre -> Conta Azul

Endpoint:
    POST /conciliar - Recebe os relatórios CSV e retorna um ZIP com os arquivos processados

Arquivos esperados (form-data):
    - dinheiro: settlement report (obrigatório)
    - vendas: collection report (obrigatório)
    - pos_venda: after_collection report (obrigatório)
    - liberacoes: reserve-release report (obrigatório)
    - extrato: account_statement report (obrigatório)
    - retirada: withdraw report (opcional)
"""

import pandas as pd
import numpy as np
import os
import re
import io
import zipfile
import tempfile
import shutil
from datetime import datetime
from typing import Optional, Dict, List, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font

app = FastAPI(
    title="Super Conciliador API",
    description="API para conciliação de relatórios Mercado Livre com Conta Azul",
    version="1.0.0"
)


# ==============================================================================
# FUNÇÕES DE PROCESSAMENTO (Adaptadas do CONCILIADOR_V3.PY)
# ==============================================================================

def clean_id(val) -> str:
    """Limpa IDs removendo .0 e espaços"""
    if pd.isna(val):
        return ""
    return str(val).replace('.0', '').strip()


def clean_float_extrato(val) -> float:
    """Converte valor do extrato (formato brasileiro) para float"""
    if isinstance(val, str):
        val = val.replace('.', '').replace(',', '.')
    return float(val)


def processar_conciliacao(arquivos: Dict[str, pd.DataFrame], centro_custo: str = "NETAIR") -> Dict[str, Any]:
    """
    Processa a conciliação dos relatórios do Mercado Livre.

    Args:
        arquivos: Dicionário com DataFrames dos relatórios
        centro_custo: Centro de custo para os lançamentos (padrão: NETAIR)

    Returns:
        Dicionário com os DataFrames processados e estatísticas
    """

    dinheiro = arquivos['dinheiro']
    vendas = arquivos['vendas']
    pos_venda = arquivos['pos_venda']
    liberacoes = arquivos['liberacoes']
    extrato = arquivos['extrato']

    # ==============================================================================
    # LIMPEZA E INTELIGÊNCIA
    # ==============================================================================

    # Normalizar IDs
    dinheiro['op_id'] = dinheiro['SOURCE_ID'].apply(clean_id)
    vendas['op_id'] = vendas['Número da transação do Mercado Pago (operation_id)'].apply(clean_id)
    pos_venda['op_id'] = pos_venda['ID da transação (operation_id)'].apply(clean_id)

    # Mapas de descrições e valores reais
    map_desc_vendas = vendas.set_index('op_id')['Descrição da operação (reason)'].to_dict()
    map_desc_pos_venda = pos_venda.set_index('op_id')['Motivo detalhado (reason_detail)'].to_dict()

    # Mapas de Valores Reais (Vendas)
    map_valor_produto = vendas.set_index('op_id')['Valor do produto (transaction_amount)'].to_dict()
    map_custo_envio_real = vendas.set_index('op_id')['Frete (shipping_cost)'].to_dict()
    map_status_envio = vendas.set_index('op_id')['Status do envio (shipment_status)'].to_dict()
    map_data_venda = vendas.set_index('op_id')['Data da compra (date_created)'].to_dict()
    map_data_liberacao_vendas = vendas.set_index('op_id')['Data de liberação do dinheiro (date_released)'].to_dict()

    # Mapa de Comissões (Tarifas) do Relatório Financeiro
    map_taxa_comissao = {}
    df_vendas_fin = dinheiro[dinheiro['TRANSACTION_TYPE'] == 'SETTLEMENT']
    for _, row in df_vendas_fin.iterrows():
        op_id = row['op_id']
        fee_total = float(row.get('FEE_AMOUNT', 0.0))
        shipping_fee = float(row.get('SHIPPING_FEE_AMOUNT', 0.0))
        pure_commission = fee_total - shipping_fee
        map_taxa_comissao[op_id] = pure_commission

    # Mapa de datas de cancelamento
    map_cancelamentos = {}
    df_cancelamentos = dinheiro[dinheiro['TRANSACTION_TYPE'].isin(['CHARGEBACK', 'REFUND', 'CANCELLATION', 'DISPUTE'])]

    for _, row in df_cancelamentos.iterrows():
        op_id = row['op_id']
        data_cancel = pd.to_datetime(row['TRANSACTION_DATE'])
        if op_id not in map_cancelamentos:
            map_cancelamentos[op_id] = data_cancel

    # Processar liberações
    if 'RECORD_TYPE' in liberacoes.columns:
        liberacoes = liberacoes[liberacoes['RECORD_TYPE'] != 'available_balance'].copy()
    elif 'SOURCE_ID' in liberacoes.columns:
        liberacoes = liberacoes[liberacoes['SOURCE_ID'].notna() & (liberacoes['SOURCE_ID'] != '')].copy()

    # Mapas de datas reais de liberação
    map_real_release_dates = {}
    liberacoes_por_opid = {}

    if 'SOURCE_ID' in liberacoes.columns and 'DATE' in liberacoes.columns:
        for _, row in liberacoes.iterrows():
            try:
                op_id = clean_id(row['SOURCE_ID'])
                if op_id:
                    data_real = pd.to_datetime(row['DATE'])
                    desc = str(row.get('DESCRIPTION', '')).lower()

                    if desc == 'payment' and op_id not in map_real_release_dates:
                        map_real_release_dates[op_id] = data_real

                    if op_id not in liberacoes_por_opid:
                        liberacoes_por_opid[op_id] = []
                    liberacoes_por_opid[op_id].append({
                        'date': data_real,
                        'description': desc,
                        'credit': float(row.get('NET_CREDIT_AMOUNT', 0)),
                        'debit': float(row.get('NET_DEBIT_AMOUNT', 0))
                    })
            except:
                continue

    # ==============================================================================
    # CONFIGURAÇÃO DO PLANO DE CONTAS (CONTA AZUL)
    # ==============================================================================
    CA_CATS = {
        'RECEITA_ML': "1.1.1 MercadoLibre",
        'RECEITA_LOJA': "1.1.2 Loja Própria (E-commerce)",
        'RECEITA_BALCAO': "1.1.5 Vendas Diretas/Balcão",
        'COMISSAO': "2.8.2 Comissões de Marketplace",
        'FRETE_ENVIO': "2.9.4 MercadoEnvios",
        'FRETE_REVERSO': "2.9.10 Logística Reversa",
        'DEVOLUCAO': "1.2.1 Devoluções e Cancelamentos",
        'TRANSFERENCIA': "Transferências",
        'PAGAMENTO_CONTA': "2.1.1 Compra de Mercadorias",
        'ESTORNO_FRETE': "1.3.7 Estorno de Frete sobre Vendas",
        'ESTORNO_TAXA': "1.3.4 Descontos e Estornos de Taxas e Tarifas",
        'DIFAL': "2.2.3 DIFAL (Diferencial de Alíquota)",
        'OUTROS': "2.14.8 Despesas Eventuais"
    }
    CENTRO_CUSTO = centro_custo

    # Mapa de origem da venda
    map_origem_venda = {}

    if 'Número da venda no Mercado Livre (order_id)' in vendas.columns:
        for _, row in vendas.iterrows():
            op_id = clean_id(row.get('Número da transação do Mercado Pago (operation_id)', ''))
            order_id = row.get('Número da venda no Mercado Livre (order_id)', '')
            if op_id and pd.notna(order_id) and str(order_id).strip() != '':
                map_origem_venda[op_id] = 'ML'

    if 'SUB_UNIT' in dinheiro.columns:
        for _, row in dinheiro.iterrows():
            op_id = clean_id(row.get('SOURCE_ID', ''))
            sub_unit = str(row.get('SUB_UNIT', '')).lower()
            if op_id and op_id not in map_origem_venda:
                if 'point' in sub_unit:
                    map_origem_venda[op_id] = 'BALCAO'
                else:
                    map_origem_venda[op_id] = 'LOJA'

    def get_categoria_receita(op_id):
        origem = map_origem_venda.get(op_id, 'LOJA')
        if origem == 'ML':
            return CA_CATS['RECEITA_ML']
        elif origem == 'BALCAO':
            return CA_CATS['RECEITA_BALCAO']
        else:
            return CA_CATS['RECEITA_LOJA']

    # ==============================================================================
    # PROCESSAMENTO UNIFICADO
    # ==============================================================================
    rows_conta_azul_confirmados = []
    rows_conta_azul_previsao = []
    rows_pagamento_conta = []
    rows_transferencias = []

    # Preparar EXTRATO
    extrato['Valor'] = extrato['TRANSACTION_NET_AMOUNT'].apply(clean_float_extrato)
    extrato['Data'] = pd.to_datetime(extrato['RELEASE_DATE'], dayfirst=True)
    extrato['DataStr'] = extrato['Data'].dt.strftime('%d/%m/%Y')
    extrato['ID'] = extrato['REFERENCE_ID'].astype(str).str.replace('.0', '').str.strip()

    # Criar mapa de detalhamento do LIBERAÇÕES
    if 'RECORD_TYPE' in liberacoes.columns:
        df_releases = liberacoes[liberacoes['RECORD_TYPE'] == 'release'].copy()
    else:
        df_releases = liberacoes.copy()

    # Mapa de proporções para payments
    map_proporcoes = {}
    for _, row in df_releases.iterrows():
        try:
            op_id = clean_id(row['SOURCE_ID'])
            desc_type = str(row.get('DESCRIPTION', '')).lower()
            if desc_type == 'payment' and op_id:
                val_liquido = float(row.get('NET_CREDIT_AMOUNT', 0.0)) - float(row.get('NET_DEBIT_AMOUNT', 0.0))
                val_mp_fee = float(row.get('MP_FEE_AMOUNT', 0.0))
                val_financing_fee = float(row.get('FINANCING_FEE_AMOUNT', 0.0)) if 'FINANCING_FEE_AMOUNT' in row.index else 0.0
                val_comissao = val_mp_fee + val_financing_fee

                val_shipping_lib = float(row.get('SHIPPING_FEE_AMOUNT', 0.0)) if 'SHIPPING_FEE_AMOUNT' in row.index else 0.0

                if op_id in map_custo_envio_real:
                    val_frete_vendedor = float(map_custo_envio_real[op_id])
                    val_gross = float(row.get('GROSS_AMOUNT', 0.0))
                    val_net = float(row.get('NET_CREDIT_AMOUNT', 0.0)) - float(row.get('NET_DEBIT_AMOUNT', 0.0))
                    val_mp_fee_lib = float(row.get('MP_FEE_AMOUNT', 0.0))

                    if val_frete_vendedor > 0:
                        val_frete_vendedor = 0.0
                    elif val_frete_vendedor < 0:
                        if abs(val_gross - val_net) < 0.10 and abs(val_mp_fee_lib) < 0.10:
                            val_frete_vendedor = 0.0
                else:
                    val_gross = float(row.get('GROSS_AMOUNT', 0.0))
                    val_net = float(row.get('NET_CREDIT_AMOUNT', 0.0)) - float(row.get('NET_DEBIT_AMOUNT', 0.0))
                    val_mp_fee = float(row.get('MP_FEE_AMOUNT', 0.0))
                    val_fin_fee = float(row.get('FINANCING_FEE_AMOUNT', 0.0))

                    soma_sem_frete = val_gross + val_mp_fee + val_fin_fee
                    if abs(soma_sem_frete - val_net) < 0.10:
                        val_frete_vendedor = 0.0
                    else:
                        val_frete_vendedor = val_shipping_lib

                val_financing = float(row.get('FINANCING_FEE_AMOUNT', 0.0))

                if op_id in map_valor_produto:
                    val_receita_real = float(map_valor_produto[op_id])
                else:
                    val_gross = float(row.get('GROSS_AMOUNT', 0.0))
                    val_shipping_gross = float(row.get('SHIPPING_FEE_AMOUNT', 0.0))

                    if val_frete_vendedor != 0:
                        val_receita_real = val_gross + val_financing
                    else:
                        val_receita_real = val_gross + val_shipping_gross + val_financing

                if val_liquido != 0:
                    map_proporcoes[op_id] = {
                        'receita': val_receita_real,
                        'liquido': val_liquido,
                        'comissao': val_comissao,
                        'frete': val_frete_vendedor
                    }
        except:
            continue

    # Mapa de detalhamento para refunds
    map_refunds = {}
    for _, row in df_releases.iterrows():
        try:
            op_id = clean_id(row['SOURCE_ID'])
            desc_type = str(row.get('DESCRIPTION', '')).lower()
            if desc_type == 'refund' and op_id:
                val_liquido = float(row.get('NET_CREDIT_AMOUNT', 0.0)) - float(row.get('NET_DEBIT_AMOUNT', 0.0))
                val_bruto = float(row.get('GROSS_AMOUNT', 0.0))
                val_mp_fee = float(row.get('MP_FEE_AMOUNT', 0.0))
                val_financing_fee = float(row.get('FINANCING_FEE_AMOUNT', 0.0))
                val_frete = float(row.get('SHIPPING_FEE_AMOUNT', 0.0))

                if op_id not in map_refunds:
                    map_refunds[op_id] = []
                map_refunds[op_id].append({
                    'bruto': val_bruto,
                    'liquido': val_liquido,
                    'mp_fee': val_mp_fee,
                    'financing_fee': val_financing_fee,
                    'frete': val_frete
                })
        except:
            continue

    # Processar EXTRATO linha por linha
    for _, row in extrato.iterrows():
        try:
            op_id = row['ID']
            tipo_transacao = str(row.get('TRANSACTION_TYPE', ''))
            val = row['Valor']
            data_str = row['DataStr']
            tipo_lower = tipo_transacao.lower()

            if abs(val) < 0.01:
                continue

            final_desc = f"{op_id} - {tipo_transacao[:50]}"

            # TRANSFERÊNCIAS
            if 'ransfer' in tipo_lower:
                is_pix_recebido = 'pix recebid' in tipo_lower
                is_interno = 'netparts' in tipo_lower or 'jonathan' in tipo_lower or 'netair' in tipo_lower

                if is_pix_recebido and not is_interno and val > 0:
                    rows_conta_azul_confirmados.append({
                        'ID Operação': op_id,
                        'Data de Competência': data_str,
                        'Data de Pagamento': data_str,
                        'Categoria': get_categoria_receita(op_id),
                        'Valor': val,
                        'Centro de Custo': CENTRO_CUSTO,
                        'Descrição': final_desc,
                        'Observações': "PIX recebido (venda)"
                    })
                else:
                    rows_transferencias.append({
                        'ID Operação': op_id,
                        'Data de Competência': data_str,
                        'Data de Pagamento': data_str,
                        'Categoria': CA_CATS['TRANSFERENCIA'],
                        'Valor': val,
                        'Centro de Custo': "",
                        'Descrição': final_desc,
                        'Observações': tipo_transacao
                    })
                continue

            # LIBERAÇÃO DE DINHEIRO CANCELADA
            if 'liberação de dinheiro cancelada' in tipo_lower or 'liberacao de dinheiro cancelada' in tipo_lower:
                categoria_cancel = CA_CATS['ESTORNO_TAXA'] if val > 0 else CA_CATS['DEVOLUCAO']
                obs_cancel = "Estorno Liberação Cancelada" if val > 0 else "Liberação cancelada"
                rows_conta_azul_confirmados.append({
                    'ID Operação': op_id,
                    'Data de Competência': data_str,
                    'Data de Pagamento': data_str,
                    'Categoria': categoria_cancel,
                    'Valor': val,
                    'Centro de Custo': CENTRO_CUSTO,
                    'Descrição': final_desc,
                    'Observações': obs_cancel
                })
                continue

            # LIBERAÇÃO DE DINHEIRO (ou transação com detalhamento no arquivo de liberações)
            # Verifica se é liberação OU se tem dados no map_proporcoes (venda com PIX no extrato)
            is_liberacao = 'liberação de dinheiro' in tipo_lower or 'liberacao de dinheiro' in tipo_lower
            has_proporcoes = op_id in map_proporcoes

            if is_liberacao or has_proporcoes:
                if op_id in map_proporcoes:
                    props = map_proporcoes[op_id]
                    val_receita = props['receita']
                    val_frete = props['frete']
                    val_comissao = val - val_receita - val_frete

                    if abs(val_receita) > 0.01:
                        rows_conta_azul_confirmados.append({
                            'ID Operação': op_id,
                            'Data de Competência': data_str,
                            'Data de Pagamento': data_str,
                            'Categoria': get_categoria_receita(op_id),
                            'Valor': round(val_receita, 2),
                            'Centro de Custo': CENTRO_CUSTO,
                            'Descrição': final_desc,
                            'Observações': "Receita de venda"
                        })

                    if abs(val_comissao) > 0.01:
                        cat_comissao = CA_CATS['ESTORNO_TAXA'] if val_comissao > 0 else CA_CATS['COMISSAO']
                        obs_comissao = "Estorno de Taxa" if val_comissao > 0 else "Tarifa Mercado Livre"
                        rows_conta_azul_confirmados.append({
                            'ID Operação': op_id,
                            'Data de Competência': data_str,
                            'Data de Pagamento': data_str,
                            'Categoria': cat_comissao,
                            'Valor': round(val_comissao, 2),
                            'Centro de Custo': CENTRO_CUSTO,
                            'Descrição': final_desc,
                            'Observações': obs_comissao
                        })

                    if abs(val_frete) > 0.01:
                        rows_conta_azul_confirmados.append({
                            'ID Operação': op_id,
                            'Data de Competência': data_str,
                            'Data de Pagamento': data_str,
                            'Categoria': CA_CATS['FRETE_ENVIO'],
                            'Valor': round(val_frete, 2),
                            'Centro de Custo': CENTRO_CUSTO,
                            'Descrição': final_desc,
                            'Observações': "Frete de envio"
                        })
                else:
                    rows_conta_azul_confirmados.append({
                        'ID Operação': op_id,
                        'Data de Competência': data_str,
                        'Data de Pagamento': data_str,
                        'Categoria': get_categoria_receita(op_id),
                        'Valor': val,
                        'Centro de Custo': CENTRO_CUSTO,
                        'Descrição': final_desc,
                        'Observações': "Liberação de venda"
                    })
                continue

            # REEMBOLSO
            if tipo_transacao.strip().startswith('Reembolso'):
                if op_id in map_refunds and len(map_refunds[op_id]) > 0:
                    ref = map_refunds[op_id][0]
                    val_liquido_ref = ref['liquido']

                    if val_liquido_ref != 0:
                        prop_bruto = ref['bruto'] / val_liquido_ref if val_liquido_ref != 0 else 0
                        prop_mp_fee = ref['mp_fee'] / val_liquido_ref if val_liquido_ref != 0 else 0
                        prop_financing_fee = ref['financing_fee'] / val_liquido_ref if val_liquido_ref != 0 else 0
                        prop_frete = ref['frete'] / val_liquido_ref if val_liquido_ref != 0 else 0

                        val_bruto = val * prop_bruto
                        val_mp_fee = val * prop_mp_fee
                        val_financing_fee = val * prop_financing_fee
                        val_frete = val * prop_frete

                        if abs(val_bruto) > 0.01:
                            cat_bruto = CA_CATS['ESTORNO_TAXA'] if val_bruto > 0 else CA_CATS['DEVOLUCAO']
                            obs_bruto = "Estorno de Devolução (disputa)" if val_bruto > 0 else "Devolução de produto"
                            rows_conta_azul_confirmados.append({
                                'ID Operação': op_id,
                                'Data de Competência': data_str,
                                'Data de Pagamento': data_str,
                                'Categoria': cat_bruto,
                                'Valor': round(val_bruto, 2),
                                'Centro de Custo': CENTRO_CUSTO,
                                'Descrição': final_desc,
                                'Observações': obs_bruto
                            })

                        if abs(val_mp_fee) > 0.01:
                            cat_mp_fee = CA_CATS['ESTORNO_TAXA'] if val_mp_fee > 0 else CA_CATS['COMISSAO']
                            obs_mp_fee = "Estorno Taxa Mercado Livre" if val_mp_fee > 0 else "Taxa Mercado Livre (disputa)"
                            rows_conta_azul_confirmados.append({
                                'ID Operação': op_id,
                                'Data de Competência': data_str,
                                'Data de Pagamento': data_str,
                                'Categoria': cat_mp_fee,
                                'Valor': round(val_mp_fee, 2),
                                'Centro de Custo': CENTRO_CUSTO,
                                'Descrição': final_desc,
                                'Observações': obs_mp_fee
                            })

                        if abs(val_financing_fee) > 0.01:
                            cat_fin_fee = CA_CATS['ESTORNO_TAXA'] if val_financing_fee > 0 else CA_CATS['COMISSAO']
                            obs_fin_fee = "Estorno Taxa Parcelamento" if val_financing_fee > 0 else "Taxa Parcelamento (disputa)"
                            rows_conta_azul_confirmados.append({
                                'ID Operação': op_id,
                                'Data de Competência': data_str,
                                'Data de Pagamento': data_str,
                                'Categoria': cat_fin_fee,
                                'Valor': round(val_financing_fee, 2),
                                'Centro de Custo': CENTRO_CUSTO,
                                'Descrição': final_desc,
                                'Observações': obs_fin_fee
                            })

                        if abs(val_frete) > 0.01:
                            cat_frete = CA_CATS['ESTORNO_FRETE'] if val_frete > 0 else CA_CATS['FRETE_ENVIO']
                            obs_frete = "Estorno de Frete" if val_frete > 0 else "Frete (disputa)"
                            rows_conta_azul_confirmados.append({
                                'ID Operação': op_id,
                                'Data de Competência': data_str,
                                'Data de Pagamento': data_str,
                                'Categoria': cat_frete,
                                'Valor': round(val_frete, 2),
                                'Centro de Custo': CENTRO_CUSTO,
                                'Descrição': final_desc,
                                'Observações': obs_frete
                            })
                    else:
                        categoria_reemb = CA_CATS['ESTORNO_TAXA'] if val > 0 else CA_CATS['DEVOLUCAO']
                        obs_reemb = "Estorno de Taxas" if val > 0 else "Reembolso"
                        rows_conta_azul_confirmados.append({
                            'ID Operação': op_id,
                            'Data de Competência': data_str,
                            'Data de Pagamento': data_str,
                            'Categoria': categoria_reemb,
                            'Valor': val,
                            'Centro de Custo': CENTRO_CUSTO,
                            'Descrição': final_desc,
                            'Observações': obs_reemb
                        })
                else:
                    categoria_reemb = CA_CATS['ESTORNO_TAXA'] if val > 0 else CA_CATS['DEVOLUCAO']
                    obs_reemb = "Estorno de Taxas" if val > 0 else "Reembolso"
                    rows_conta_azul_confirmados.append({
                        'ID Operação': op_id,
                        'Data de Competência': data_str,
                        'Data de Pagamento': data_str,
                        'Categoria': categoria_reemb,
                        'Valor': val,
                        'Centro de Custo': CENTRO_CUSTO,
                        'Descrição': final_desc,
                        'Observações': obs_reemb
                    })
                continue

            # DINHEIRO RETIDO
            if 'dinheiro retido' in tipo_lower:
                rows_conta_azul_confirmados.append({
                    'ID Operação': op_id,
                    'Data de Competência': data_str,
                    'Data de Pagamento': data_str,
                    'Categoria': CA_CATS['DEVOLUCAO'],
                    'Valor': val,
                    'Centro de Custo': CENTRO_CUSTO,
                    'Descrição': final_desc,
                    'Observações': "Dinheiro retido (disputa)"
                })
                continue

            # OUTRAS CATEGORIAS
            if 'difal' in tipo_lower:
                categoria = CA_CATS['DIFAL']
                obs = "DIFAL"
            elif 'imposto interestadual' in tipo_lower:
                categoria = CA_CATS['DIFAL']
                obs = "Imposto Interestadual"
            elif 'pagamento de contas' in tipo_lower:
                categoria = CA_CATS['PAGAMENTO_CONTA']
                obs = "Pagamento de Conta via MP"
            elif 'pagamento' in tipo_lower or 'qr' in tipo_lower:
                if val < 0:
                    categoria = CA_CATS['PAGAMENTO_CONTA']
                    obs = "Pagamento PIX enviado"
                else:
                    categoria = get_categoria_receita(op_id)
                    obs = "Pagamento PIX recebido"
            elif 'entrada' in tipo_lower:
                categoria = get_categoria_receita(op_id)
                obs = "Entrada de dinheiro"
            elif 'débito' in tipo_lower or 'divida' in tipo_lower:
                if 'reclama' in tipo_lower:
                    categoria = CA_CATS['DEVOLUCAO']
                    obs = "Débito Reclamação ML"
                elif 'envio' in tipo_lower:
                    categoria = CA_CATS['FRETE_ENVIO']
                    obs = "Débito Envio ML"
                elif 'aliquota' in tipo_lower or 'difal' in tipo_lower:
                    categoria = CA_CATS['DIFAL']
                    obs = "DIFAL via Débito"
                elif 'imposto' in tipo_lower:
                    categoria = CA_CATS['DIFAL']
                    obs = "Imposto Interestadual"
                elif 'troca' in tipo_lower:
                    categoria = CA_CATS['DEVOLUCAO']
                    obs = "Débito Troca Produto"
                else:
                    categoria = CA_CATS['OUTROS']
                    obs = "Débito/Dívida ML"
            elif 'bônus' in tipo_lower or 'bonus' in tipo_lower:
                categoria = CA_CATS['ESTORNO_FRETE']
                obs = "Bônus de envio"
            elif 'compra' in tipo_lower:
                categoria = CA_CATS['PAGAMENTO_CONTA']
                obs = "Compra Mercado Livre"
            elif 'reembolso' in tipo_lower:
                categoria = CA_CATS['DEVOLUCAO']
                obs = "Reembolso"
            else:
                categoria = CA_CATS['OUTROS']
                obs = "Outros"

            rows_conta_azul_confirmados.append({
                'ID Operação': op_id,
                'Data de Competência': data_str,
                'Data de Pagamento': data_str,
                'Categoria': categoria,
                'Valor': val,
                'Centro de Custo': CENTRO_CUSTO,
                'Descrição': final_desc,
                'Observações': obs
            })

        except Exception as e:
            continue

    # ==============================================================================
    # PROCESSAMENTO DO DINHEIRO EM CONTA (PREVISÕES)
    # ==============================================================================

    for _, row in dinheiro.iterrows():
        op_id = row['op_id']
        tipo_op = row['TRANSACTION_TYPE']

        if op_id in liberacoes_por_opid:
            continue

        data_origem_obj = pd.to_datetime(row['TRANSACTION_DATE'])
        if op_id in map_data_venda:
            data_origem_obj = pd.to_datetime(map_data_venda[op_id], dayfirst=True)
        data_competencia = data_origem_obj.strftime('%d/%m/%Y')

        try:
            if pd.notna(row.get('MONEY_RELEASE_DATE')):
                data_prev = pd.to_datetime(row['MONEY_RELEASE_DATE'])
                data_caixa = data_prev.strftime('%d/%m/%Y')
            elif op_id in map_data_liberacao_vendas:
                data_prev = pd.to_datetime(map_data_liberacao_vendas[op_id], dayfirst=True)
                data_caixa = data_prev.strftime('%d/%m/%Y')
            else:
                data_caixa = ""
        except:
            data_caixa = ""

        id_pedido = str(row.get('EXTERNAL_REFERENCE', '')).replace('.0', '').strip()
        if not id_pedido or id_pedido == 'nan':
            id_pedido = str(row.get('ORDER_ID', '')).replace('.0', '').strip()
        desc_part = f"Pedido {id_pedido}" if id_pedido and id_pedido != 'nan' else f"Op {op_id}"
        final_desc = f"{op_id} - {desc_part}"

        if tipo_op == 'SETTLEMENT':
            val_receita = float(map_valor_produto.get(op_id, row['TRANSACTION_AMOUNT']))
            val_frete_real = float(map_custo_envio_real.get(op_id, 0.0))
            if op_id not in map_valor_produto:
                val_frete_real = float(row['SHIPPING_FEE_AMOUNT'])

            if val_receita < 0:
                data_pag_competencia = data_caixa if data_caixa else data_competencia
                rows_pagamento_conta.append({
                    'ID Operação': op_id,
                    'Data de Competência': data_pag_competencia,
                    'Data de Pagamento': data_caixa,
                    'Categoria': CA_CATS['PAGAMENTO_CONTA'],
                    'Valor': val_receita,
                    'Centro de Custo': CENTRO_CUSTO,
                    'Descrição': final_desc,
                    'Observações': f"{op_id} - Pagamento via Mercado Pago"
                })
                continue

            rows_conta_azul_previsao.append({
                'ID Operação': op_id,
                'Data de Competência': data_competencia,
                'Data de Pagamento': data_caixa,
                'Categoria': get_categoria_receita(op_id),
                'Valor': val_receita,
                'Centro de Custo': CENTRO_CUSTO,
                'Descrição': final_desc,
                'Observações': "Receita de venda (PREVISÃO)"
            })

            val_liquido = float(row['REAL_AMOUNT'])
            if val_frete_real > 0:
                val_frete_real = -val_frete_real
            val_comissao = round(val_receita + val_frete_real - val_liquido, 2)

            if abs(val_comissao) > 0.01:
                rows_conta_azul_previsao.append({
                    'ID Operação': op_id,
                    'Data de Competência': data_competencia,
                    'Data de Pagamento': data_caixa,
                    'Categoria': CA_CATS['COMISSAO'],
                    'Valor': -abs(val_comissao),
                    'Centro de Custo': CENTRO_CUSTO,
                    'Descrição': final_desc,
                    'Observações': "Tarifa (PREVISÃO)"
                })

            if val_frete_real != 0:
                rows_conta_azul_previsao.append({
                    'ID Operação': op_id,
                    'Data de Competência': data_competencia,
                    'Data de Pagamento': data_caixa,
                    'Categoria': CA_CATS['FRETE_ENVIO'],
                    'Valor': val_frete_real,
                    'Centro de Custo': CENTRO_CUSTO,
                    'Descrição': final_desc,
                    'Observações': "Frete (PREVISÃO)"
                })

        elif tipo_op in ['CHARGEBACK', 'REFUND', 'CANCELLATION', 'DISPUTE']:
            val_receita = float(row['TRANSACTION_AMOUNT'])
            rows_conta_azul_previsao.append({
                'ID Operação': op_id,
                'Data de Competência': data_competencia,
                'Data de Pagamento': data_competencia,
                'Categoria': CA_CATS['DEVOLUCAO'],
                'Valor': val_receita if val_receita < 0 else -val_receita,
                'Centro de Custo': CENTRO_CUSTO,
                'Descrição': final_desc,
                'Observações': f"{tipo_op} (PREVISÃO)"
            })

        elif 'PAYOUT' in str(tipo_op).upper() or 'RETIRADA' in str(tipo_op).upper() or tipo_op == 'MONEY_TRANSFER':
            continue

        else:
            rows_conta_azul_previsao.append({
                'ID Operação': op_id,
                'Data de Competência': data_competencia,
                'Data de Pagamento': data_competencia,
                'Categoria': CA_CATS['OUTROS'],
                'Valor': row['REAL_AMOUNT'],
                'Centro de Custo': "",
                'Descrição': final_desc,
                'Observações': f"Verificar - {tipo_op}"
            })

    # Estatísticas de origem
    origens_count = {'ML': 0, 'LOJA': 0, 'BALCAO': 0}
    for origem in map_origem_venda.values():
        origens_count[origem] = origens_count.get(origem, 0) + 1

    return {
        'confirmados': rows_conta_azul_confirmados,
        'previsao': rows_conta_azul_previsao,
        'pagamentos': rows_pagamento_conta,
        'transferencias': rows_transferencias,
        'stats': {
            'confirmados': len(rows_conta_azul_confirmados),
            'previsao': len(rows_conta_azul_previsao),
            'pagamentos': len(rows_pagamento_conta),
            'transferencias': len(rows_transferencias),
            'origens': origens_count
        }
    }


def gerar_csv_conta_azul(rows: List[Dict], output_path: str) -> bool:
    """Gera arquivo CSV no formato Conta Azul"""
    if not rows:
        return False

    df = pd.DataFrame(rows)

    if df.empty:
        return False

    df['Valor'] = df['Valor'].round(2)
    df = df[df['Valor'] != 0]
    df['Data de Vencimento'] = df['Data de Pagamento']

    df['Cliente/Fornecedor'] = "MERCADO LIVRE"
    df['CNPJ/CPF Cliente/Fornecedor'] = "03007331000141"

    cols = ['Data de Competência', 'Data de Vencimento', 'Data de Pagamento', 'Valor',
            'Categoria', 'Descrição', 'Cliente/Fornecedor', 'CNPJ/CPF Cliente/Fornecedor',
            'Centro de Custo', 'Observações']

    for c in cols:
        if c not in df.columns:
            df[c] = ""

    df[cols].to_csv(output_path, index=False, sep=';', encoding='utf-8-sig')
    return True


def gerar_xlsx_completo(rows: List[Dict], output_path: str) -> bool:
    """Gera arquivo XLSX com todas as transações"""
    if not rows:
        return False

    df = pd.DataFrame(rows)

    if df.empty:
        return False

    df['Valor'] = df['Valor'].round(2)
    df = df[df['Valor'] != 0]
    df['Data de Vencimento'] = df['Data de Pagamento']

    df['Cliente/Fornecedor'] = "MERCADO LIVRE"
    df['CNPJ/CPF Cliente/Fornecedor'] = "03007331000141"

    cols = ['Data de Competência', 'Data de Vencimento', 'Data de Pagamento', 'Valor',
            'Categoria', 'Descrição', 'Cliente/Fornecedor', 'CNPJ/CPF Cliente/Fornecedor',
            'Centro de Custo', 'Observações']

    for c in cols:
        if c not in df.columns:
            df[c] = ""

    wb = Workbook()
    ws = wb.active
    ws.title = "Importação Conta Azul"

    header_font = Font(bold=True)

    for col_idx, col_name in enumerate(cols, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font

    for row_idx, row_data in enumerate(df[cols].values, 2):
        for col_idx, value in enumerate(row_data, 1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column].width = adjusted_width

    wb.save(output_path)
    return True


def gerar_xlsx_resumo(rows: List[Dict], output_path: str) -> bool:
    """Gera arquivo XLSX com dados agrupados por Data de Pagamento e Categoria"""
    if not rows:
        return False

    df = pd.DataFrame(rows)

    if df.empty:
        return False

    df['Valor'] = df['Valor'].round(2)
    df = df[df['Valor'] != 0]
    df['Data de Vencimento'] = df['Data de Pagamento']

    df['Cliente/Fornecedor'] = "MERCADO LIVRE"
    df['CNPJ/CPF Cliente/Fornecedor'] = "03007331000141"

    df_grouped = df.groupby(['Data de Pagamento', 'Categoria'], as_index=False).agg({
        'Data de Competência': 'first',
        'Data de Vencimento': 'first',
        'Valor': 'sum',
        'Descrição': lambda x: f"Resumo {len(x)} transações",
        'Cliente/Fornecedor': 'first',
        'CNPJ/CPF Cliente/Fornecedor': 'first',
        'Centro de Custo': 'first',
        'Observações': lambda x: f"{len(x)} lançamentos agrupados"
    })

    df_grouped = df_grouped.sort_values('Data de Pagamento')

    cols = ['Data de Competência', 'Data de Vencimento', 'Data de Pagamento', 'Valor',
            'Categoria', 'Descrição', 'Cliente/Fornecedor', 'CNPJ/CPF Cliente/Fornecedor',
            'Centro de Custo', 'Observações']

    wb = Workbook()
    ws = wb.active
    ws.title = "Importação Conta Azul"

    header_font = Font(bold=True)

    for col_idx, col_name in enumerate(cols, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font

    for row_idx, row_data in enumerate(df_grouped[cols].values, 2):
        for col_idx, value in enumerate(row_data, 1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column].width = adjusted_width

    wb.save(output_path)
    return True


# ==============================================================================
# ENDPOINTS DA API
# ==============================================================================

@app.get("/")
async def root():
    """Endpoint de health check"""
    return {
        "status": "online",
        "service": "Super Conciliador API",
        "version": "1.0.0"
    }


@app.post("/conciliar")
async def conciliar(
    dinheiro: UploadFile = File(..., description="Arquivo settlement (dinheiro em conta)"),
    vendas: UploadFile = File(..., description="Arquivo collection (vendas)"),
    pos_venda: UploadFile = File(..., description="Arquivo after_collection (pós venda)"),
    liberacoes: UploadFile = File(..., description="Arquivo reserve-release (liberações)"),
    extrato: UploadFile = File(..., description="Arquivo account_statement (extrato)"),
    retirada: Optional[UploadFile] = File(None, description="Arquivo withdraw (retirada) - opcional"),
    centro_custo: str = Form("NETAIR", description="Centro de custo para os lançamentos")
):
    """
    Processa os relatórios do Mercado Livre e retorna um ZIP com os arquivos de importação.

    ## Arquivos de entrada (CSV):
    - **dinheiro**: settlement report (obrigatório)
    - **vendas**: collection report (obrigatório)
    - **pos_venda**: after_collection report (obrigatório)
    - **liberacoes**: reserve-release report (obrigatório)
    - **extrato**: account_statement report (obrigatório)
    - **retirada**: withdraw report (opcional)

    ## Parâmetros adicionais:
    - **centro_custo**: Centro de custo para os lançamentos (padrão: NETAIR)

    ## Arquivos de saída (ZIP):
    - IMPORTACAO_CONTA_AZUL_CONFIRMADOS.csv
    - IMPORTACAO_CONTA_AZUL_CONFIRMADOS.xlsx
    - IMPORTACAO_CONTA_AZUL_CONFIRMADOS_RESUMO.xlsx
    - IMPORTACAO_CONTA_AZUL_PREVISAO.csv
    - IMPORTACAO_CONTA_AZUL_PREVISAO.xlsx
    - IMPORTACAO_CONTA_AZUL_PREVISAO_RESUMO.xlsx
    - PAGAMENTO_CONTAS.csv
    - PAGAMENTO_CONTAS.xlsx
    - TRANSFERENCIAS.csv
    - TRANSFERENCIAS.xlsx
    """

    temp_dir = tempfile.mkdtemp()

    try:
        # Carregar DataFrames dos arquivos enviados
        arquivos = {}

        # Função auxiliar para ler CSV com detecção automática de separador
        async def ler_csv(upload_file: UploadFile, key: str, skip_rows: int = 0, clean_json: bool = False):
            content = await upload_file.read()
            content_str = content.decode('utf-8')

            if clean_json:
                # Remove campos JSON mal formatados (METADATA com aspas internas não escapadas)
                # Pattern captura desde "{ até }" incluindo JSON aninhado
                content_str = re.sub(r'"\{[^}]*(?:\{[^}]*\}[^}]*)*\}"', '""', content_str)

            # Detectar separador automaticamente (verifica primeira linha após skip_rows)
            lines = content_str.split('\n')
            header_line = lines[skip_rows] if len(lines) > skip_rows else lines[0]

            # Conta ocorrências de ; e , na linha de cabeçalho (fora de aspas)
            sep = ';' if header_line.count(';') > header_line.count(',') else ','

            return pd.read_csv(
                io.StringIO(content_str),
                sep=sep,
                skiprows=skip_rows,
                on_bad_lines='skip',
                index_col=False
            )

        # Carregar arquivos obrigatórios
        try:
            arquivos['dinheiro'] = await ler_csv(dinheiro, 'dinheiro', clean_json=True)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erro ao processar arquivo 'dinheiro': {str(e)}")

        try:
            arquivos['vendas'] = await ler_csv(vendas, 'vendas')
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erro ao processar arquivo 'vendas': {str(e)}")

        try:
            arquivos['pos_venda'] = await ler_csv(pos_venda, 'pos_venda')
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erro ao processar arquivo 'pos_venda': {str(e)}")

        try:
            arquivos['liberacoes'] = await ler_csv(liberacoes, 'liberacoes', clean_json=True)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erro ao processar arquivo 'liberacoes': {str(e)}")

        try:
            arquivos['extrato'] = await ler_csv(extrato, 'extrato', skip_rows=3)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erro ao processar arquivo 'extrato': {str(e)}")

        # Arquivo opcional
        if retirada:
            try:
                arquivos['retirada'] = await ler_csv(retirada, 'retirada')
            except:
                arquivos['retirada'] = pd.DataFrame()
        else:
            arquivos['retirada'] = pd.DataFrame()

        # Processar conciliação
        try:
            resultado = processar_conciliacao(arquivos, centro_custo=centro_custo)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao processar conciliação: {str(e)}")

        # Gerar arquivos de saída
        arquivos_gerados = []

        # CSVs
        if gerar_csv_conta_azul(resultado['confirmados'], os.path.join(temp_dir, 'IMPORTACAO_CONTA_AZUL_CONFIRMADOS.csv')):
            arquivos_gerados.append('IMPORTACAO_CONTA_AZUL_CONFIRMADOS.csv')

        if gerar_csv_conta_azul(resultado['previsao'], os.path.join(temp_dir, 'IMPORTACAO_CONTA_AZUL_PREVISAO.csv')):
            arquivos_gerados.append('IMPORTACAO_CONTA_AZUL_PREVISAO.csv')

        if gerar_csv_conta_azul(resultado['pagamentos'], os.path.join(temp_dir, 'PAGAMENTO_CONTAS.csv')):
            arquivos_gerados.append('PAGAMENTO_CONTAS.csv')

        if gerar_csv_conta_azul(resultado['transferencias'], os.path.join(temp_dir, 'TRANSFERENCIAS.csv')):
            arquivos_gerados.append('TRANSFERENCIAS.csv')

        # XLSXs Completos
        if gerar_xlsx_completo(resultado['confirmados'], os.path.join(temp_dir, 'IMPORTACAO_CONTA_AZUL_CONFIRMADOS.xlsx')):
            arquivos_gerados.append('IMPORTACAO_CONTA_AZUL_CONFIRMADOS.xlsx')

        if gerar_xlsx_completo(resultado['previsao'], os.path.join(temp_dir, 'IMPORTACAO_CONTA_AZUL_PREVISAO.xlsx')):
            arquivos_gerados.append('IMPORTACAO_CONTA_AZUL_PREVISAO.xlsx')

        if gerar_xlsx_completo(resultado['pagamentos'], os.path.join(temp_dir, 'PAGAMENTO_CONTAS.xlsx')):
            arquivos_gerados.append('PAGAMENTO_CONTAS.xlsx')

        if gerar_xlsx_completo(resultado['transferencias'], os.path.join(temp_dir, 'TRANSFERENCIAS.xlsx')):
            arquivos_gerados.append('TRANSFERENCIAS.xlsx')

        # XLSXs Resumidos
        if gerar_xlsx_resumo(resultado['confirmados'], os.path.join(temp_dir, 'IMPORTACAO_CONTA_AZUL_CONFIRMADOS_RESUMO.xlsx')):
            arquivos_gerados.append('IMPORTACAO_CONTA_AZUL_CONFIRMADOS_RESUMO.xlsx')

        if gerar_xlsx_resumo(resultado['previsao'], os.path.join(temp_dir, 'IMPORTACAO_CONTA_AZUL_PREVISAO_RESUMO.xlsx')):
            arquivos_gerados.append('IMPORTACAO_CONTA_AZUL_PREVISAO_RESUMO.xlsx')

        if not arquivos_gerados:
            raise HTTPException(status_code=500, detail="Nenhum arquivo foi gerado. Verifique os dados de entrada.")

        # Criar ZIP em memória
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for arquivo in arquivos_gerados:
                file_path = os.path.join(temp_dir, arquivo)
                zip_file.write(file_path, arquivo)

        zip_buffer.seek(0)

        # Gerar nome do arquivo com timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"conciliacao_{timestamp}.zip"

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Stats-Confirmados": str(resultado['stats']['confirmados']),
                "X-Stats-Previsao": str(resultado['stats']['previsao']),
                "X-Stats-Pagamentos": str(resultado['stats']['pagamentos']),
                "X-Stats-Transferencias": str(resultado['stats']['transferencias']),
            }
        )

    finally:
        # Limpar diretório temporário
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/health")
async def health_check():
    """Endpoint de health check detalhado"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "dependencies": {
            "pandas": pd.__version__,
            "numpy": np.__version__
        }
    }


# ==============================================================================
# EXECUÇÃO
# ==============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=1909)
