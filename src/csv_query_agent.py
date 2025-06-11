import pandas as pd
import os
from langchain.llms.base import LLM
from langchain.callbacks.manager import CallbackManagerForLLMRun
from typing import Optional, List, Any

class MockLLM(LLM):
    """
    Mock LLM para demonstração sem necessidade de API keys.
    """
    @property
    def _llm_type(self) -> str:
        return "mock"
    
    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        return "Análise genérica..."

class CSVQueryAgent:
    """
    Agente para responder perguntas sobre dados CSV usando lógica baseada em regras.
    """
    
    def __init__(self, cabecalho_path: str, itens_path: str):
        self.cabecalho_path = cabecalho_path
        self.itens_path = itens_path
        self.df_cabecalho = None
        self.df_itens = None
        self.df_consolidated = None
        self.llm = MockLLM()

    def load_data(self):
        """
        Carrega os dados dos arquivos CSV somente se ainda não foram carregados.
        """
        if self.df_cabecalho is not None and self.df_itens is not None:
            return

        if os.path.exists(self.cabecalho_path):
            self.df_cabecalho = pd.read_csv(self.cabecalho_path, sep=',', decimal='.')
        else:
            self.df_cabecalho = pd.DataFrame()

        if os.path.exists(self.itens_path):
            self.df_itens = pd.read_csv(self.itens_path, sep=',', decimal='.')
        else:
            self.df_itens = pd.DataFrame()
        
        if not self.df_cabecalho.empty and not self.df_itens.empty:
            self.df_consolidated = pd.merge(
                self.df_cabecalho, self.df_itens,
                on='CHAVE DE ACESSO', how='inner', suffixes=('_cab', '_item')
            )
        else:
            self.df_consolidated = self.df_cabecalho.copy()
            
    def query_data(self, question: str) -> str:
        """
        Responde a uma pergunta sobre os dados usando uma série de regras.
        """
        self.load_data()

        if self.df_cabecalho.empty:
            return "Nenhum dado para analisar. Por favor, faça o upload de um arquivo primeiro."
            
        try:
            question_lower = question.lower()
            
            if "fornecedor" in question_lower and "maior" in question_lower:
                return self._get_top_supplier()
            elif "item" in question_lower and ("maior volume" in question_lower or "mais entregue" in question_lower):
                return self._get_top_item_by_volume()
            elif "valor total" in question_lower:
                return self._get_total_invoice_value()
            elif "valor médio" in question_lower:
                return self._get_average_invoice_value()
            elif "quantos documentos" in question_lower and "venda" in question_lower:
                return self._get_sales_document_count()
            elif "quantos documentos" in question_lower and "compra" in question_lower:
                return self._get_purchase_document_count()
            elif "setores" in question_lower:
                return self._get_unique_sectors()
            else:
                return self._general_analysis(question)
                
        except Exception as e:
            return f"Erro ao processar a pergunta: {str(e)}"
    
    def _get_top_supplier(self) -> str:
        fornecedores = self.df_cabecalho.groupby('RAZÃO SOCIAL EMITENTE')['VALOR NOTA FISCAL'].sum().sort_values(ascending=False)
        top_supplier = fornecedores.head(1)
        if top_supplier.empty:
            return "Não foi possível encontrar o fornecedor com maior montante."
        return f"O fornecedor com maior montante recebido é {top_supplier.index[0]} com um total de R$ {top_supplier.iloc[0]:,.2f}."

    def _get_top_item_by_volume(self) -> str:
        if self.df_itens.empty:
            return "Não há dados de itens para analisar o volume."
        produtos = self.df_itens.groupby('DESCRIÇÃO DO PRODUTO/SERVIÇO')['QUANTIDADE'].sum().sort_values(ascending=False)
        top_product = produtos.head(1)
        if top_product.empty:
            return "Não foi possível encontrar o item com maior volume."
        return f"O item com maior volume entregue é {top_product.index[0]} com um total de {int(top_product.iloc[0])} unidades."

    def _get_total_invoice_value(self) -> str:
        total_value = self.df_cabecalho['VALOR NOTA FISCAL'].sum()
        return f"O valor total de todas as notas fiscais é de R$ {total_value:,.2f}."

    def _get_average_invoice_value(self) -> str:
        mean_value = self.df_cabecalho['VALOR NOTA FISCAL'].mean()
        return f"O valor médio por nota fiscal é de R$ {mean_value:,.2f}."

    def _get_sales_document_count(self) -> str:
        if self.df_itens.empty:
            return "Não há dados de itens para classificar as operações."
        sales_cfops = self.df_itens['CFOP'].astype(str).str.startswith(('5', '6', '7'))
        unique_invoices = self.df_itens[sales_cfops]['CHAVE DE ACESSO'].nunique()
        return f"Foram encontrados {unique_invoices} documentos de venda."

    def _get_purchase_document_count(self) -> str:
        if self.df_itens.empty:
            return "Não há dados de itens para classificar as operações."
        purchase_cfops = self.df_itens['CFOP'].astype(str).str.startswith(('1', '2', '3'))
        unique_invoices = self.df_itens[purchase_cfops]['CHAVE DE ACESSO'].nunique()
        return f"Foram encontrados {unique_invoices} documentos de compra."
        
    def _get_unique_sectors(self) -> str:
        if self.df_itens.empty:
            return "Não há dados de itens para classificar os setores."
        
        sector_rules = {
            "49": "Editorial/Gráfico", "85": "Eletrônicos/Elétricos", "73": "Metalúrgico",
            "39": "Plásticos", "84": "Máquinas e Equipamentos", "87": "Veículos",
            "90": "Instrumentos de Precisão"
        }
        
        def classify_sector(ncm_code: str) -> str:
            ncm_str = str(ncm_code)
            for prefix, sector in sector_rules.items():
                if ncm_str.startswith(prefix):
                    return sector
            return None

        sectors = self.df_itens['CÓDIGO NCM/SH'].apply(classify_sector).dropna().unique()
        
        if len(sectors) == 0:
            return "Nenhum setor conhecido foi identificado nos produtos."
            
        return f"Os setores encontrados nos documentos são: {', '.join(sectors)}."

    def _general_analysis(self, question: str) -> str:
        total_notas = len(self.df_cabecalho)
        total_itens = len(self.df_itens)
        valor_total = self.df_cabecalho['VALOR NOTA FISCAL'].sum()
        periodo_inicio = self.df_cabecalho['DATA EMISSÃO'].min()
        periodo_fim = self.df_cabecalho['DATA EMISSÃO'].max()

        return (
            f"Não encontrei uma resposta específica para '{question}', mas aqui está um resumo geral dos dados:\n\n"
            f"- Total de notas fiscais: {total_notas}\n"
            f"- Total de itens: {total_itens}\n"
            f"- Valor total das notas: R$ {valor_total:,.2f}\n"
            f"- Período: de {periodo_inicio} a {periodo_fim}"
        )

class IntegratedFiscalAgent:
    def __init__(self, cabecalho_path: str, itens_path: str):
        self.csv_agent = CSVQueryAgent(cabecalho_path, itens_path)
        
    def process_query(self, query: str) -> str:
        return self.csv_agent.query_data(query)