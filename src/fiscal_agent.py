# Agente de Classificação e Organização de Documentos Fiscais

import pandas as pd
import sqlite3
import os
from typing import Dict, List, Tuple

class CFOPClassifier:
    """
    Classe para classificação de documentos fiscais baseada no CFOP.
    """
    
    def __init__(self):
        self.cfop_rules = {
            # Vendas
            "5": "Venda",
            "6": "Venda Interestadual", 
            "7": "Venda para Exterior",
            
            # Compras
            "1": "Compra",
            "2": "Compra Interestadual",
            "3": "Compra do Exterior",
            
            # Específicos por CFOP
            "5101": "Venda de produção do estabelecimento",
            "5102": "Venda de mercadoria adquirida ou recebida de terceiros",
            "5403": "Venda de mercadoria sujeita ao regime de substituição tributária",
            "6101": "Venda de produção do estabelecimento",
            "6102": "Venda de mercadoria adquirida ou recebida de terceiros",
            "6403": "Venda de mercadoria sujeita ao regime de substituição tributária",
            "1101": "Compra para industrialização",
            "1102": "Compra para comercialização",
            "2101": "Compra para industrialização",
            "2102": "Compra para comercialização",
            "2949": "Outra entrada de mercadoria ou prestação de serviço não especificada",
        }
        
        self.sector_rules = {
            # Baseado em NCM/SH
            "49": "Editorial/Gráfico",
            "85": "Eletrônicos/Elétricos", 
            "73": "Metalúrgico",
            "39": "Plásticos",
            "84": "Máquinas e Equipamentos",
            "87": "Veículos",
            "90": "Instrumentos de Precisão",
        }
    
    def classify_by_cfop(self, cfop: str) -> Dict[str, str]:
        """
        Classifica um documento baseado no CFOP.
        """
        cfop_str = str(cfop)
        
        # Verifica regras específicas primeiro
        if cfop_str in self.cfop_rules:
            operation_type = self.cfop_rules[cfop_str]
        else:
            # Verifica pelo primeiro dígito
            first_digit = cfop_str[0]
            operation_type = self.cfop_rules.get(first_digit, "Operação não classificada")
        
        # Determina centro de custo baseado no tipo de operação
        if "Venda" in operation_type:
            cost_center = "Receitas"
        elif "Compra" in operation_type:
            cost_center = "Custos"
        else:
            cost_center = "Outros"
            
        return {
            "tipo_operacao": operation_type,
            "centro_custo": cost_center,
            "cfop": cfop_str
        }
    
    def classify_by_sector(self, ncm_code: str) -> str:
        """
        Classifica o setor baseado no código NCM.
        """
        ncm_str = str(ncm_code)
        
        # Verifica os dois primeiros dígitos do NCM
        for prefix, sector in self.sector_rules.items():
            if ncm_str.startswith(prefix):
                return sector
                
        return "Setor não classificado"

class DocumentOrganizer:
    """
    Classe para organização e armazenamento de documentos classificados.
    """
    
    def __init__(self, db_path: str = "documentos_fiscais.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """
        Inicializa o banco de dados SQLite.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS documentos_classificados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chave_acesso TEXT UNIQUE,
                cfop TEXT,
                tipo_operacao TEXT,
                centro_custo TEXT,
                setor TEXT,
                razao_social_emitente TEXT,
                nome_destinatario TEXT,
                valor_total REAL,
                data_emissao TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def store_classified_document(self, document_data: Dict):
        """
        Armazena um documento classificado no banco de dados.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO documentos_classificados 
            (chave_acesso, cfop, tipo_operacao, centro_custo, setor, 
             razao_social_emitente, nome_destinatario, valor_total, data_emissao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            document_data['chave_acesso'],
            document_data['cfop'],
            document_data['tipo_operacao'],
            document_data['centro_custo'],
            document_data['setor'],
            document_data['razao_social_emitente'],
            document_data['nome_destinatario'],
            document_data['valor_total'],
            document_data['data_emissao']
        ))
        
        conn.commit()
        conn.close()
    
    def get_documents_by_criteria(self, criteria: Dict) -> List[Dict]:
        """
        Recupera documentos baseado em critérios específicos.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT * FROM documentos_classificados WHERE 1=1"
        params = []
        
        if 'tipo_operacao' in criteria:
            query += " AND tipo_operacao = ?"
            params.append(criteria['tipo_operacao'])
            
        if 'centro_custo' in criteria:
            query += " AND centro_custo = ?"
            params.append(criteria['centro_custo'])
            
        if 'setor' in criteria:
            query += " AND setor = ?"
            params.append(criteria['setor'])
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        
        # Converte para lista de dicionários
        columns = ['id', 'chave_acesso', 'cfop', 'tipo_operacao', 'centro_custo', 
                  'setor', 'razao_social_emitente', 'nome_destinatario', 
                  'valor_total', 'data_emissao', 'created_at']
        
        return [dict(zip(columns, row)) for row in results]

class FiscalDocumentAgent:
    """
    Agente principal para classificação e organização de documentos fiscais.
    """
    
    def __init__(self, cabecalho_path: str, itens_path: str):
        self.classifier = CFOPClassifier()
        self.organizer = DocumentOrganizer()
        self.cabecalho_path = cabecalho_path
        self.itens_path = itens_path
        self.df_cabecalho = None
        self.df_itens = None
        
    def load_data(self):
        """
        Carrega os dados dos arquivos CSV.
        """
        if os.path.exists(self.cabecalho_path) and os.path.exists(self.itens_path):
            self.df_cabecalho = pd.read_csv(self.cabecalho_path)
            self.df_itens = pd.read_csv(self.itens_path)
        else:
            raise FileNotFoundError(f"Arquivos CSV não encontrados: {self.cabecalho_path} ou {self.itens_path}")
        
    def process_documents(self):
        """
        Processa e classifica todos os documentos.
        """
        self.load_data()
        
        # Agrupa itens por chave de acesso para obter informações consolidadas
        itens_grouped = self.df_itens.groupby('CHAVE DE ACESSO').agg({
            'CFOP': 'first',  # Pega o primeiro CFOP (pode ser melhorado)
            'CÓDIGO NCM/SH': 'first',  # Pega o primeiro NCM
            'VALOR TOTAL': 'sum'  # Soma todos os valores dos itens
        }).reset_index()
        
        # Merge com dados do cabeçalho
        merged_data = pd.merge(
            self.df_cabecalho, 
            itens_grouped, 
            on='CHAVE DE ACESSO', 
            how='left'
        )
        
        processed_count = 0
        
        for _, row in merged_data.iterrows():
            try:
                # Classifica por CFOP
                cfop_classification = self.classifier.classify_by_cfop(row['CFOP'])
                
                # Classifica por setor
                sector = self.classifier.classify_by_sector(row['CÓDIGO NCM/SH'])
                
                # Prepara dados para armazenamento
                document_data = {
                    'chave_acesso': row['CHAVE DE ACESSO'],
                    'cfop': str(row['CFOP']),
                    'tipo_operacao': cfop_classification['tipo_operacao'],
                    'centro_custo': cfop_classification['centro_custo'],
                    'setor': sector,
                    'razao_social_emitente': row['RAZÃO SOCIAL EMITENTE'],
                    'nome_destinatario': row['NOME DESTINATÁRIO'],
                    'valor_total': row['VALOR TOTAL'],
                    'data_emissao': row['DATA EMISSÃO']
                }
                
                # Armazena no banco de dados
                self.organizer.store_classified_document(document_data)
                processed_count += 1
                
            except Exception as e:
                print(f"Erro ao processar documento {row['CHAVE DE ACESSO']}: {e}")
                continue
        
        print(f"Processados {processed_count} documentos com sucesso.")
        
    def query_documents(self, query_text: str) -> str:
        """
        Responde a consultas sobre os documentos classificados.
        """
        query_lower = query_text.lower()
        
        if "venda" in query_lower:
            docs = self.organizer.get_documents_by_criteria({'tipo_operacao': 'Venda'})
            return f"Encontrados {len(docs)} documentos de venda."
            
        elif "compra" in query_lower:
            docs = self.organizer.get_documents_by_criteria({'centro_custo': 'Custos'})
            return f"Encontrados {len(docs)} documentos de compra."
            
        elif "setor" in query_lower:
            # Lista todos os setores únicos
            conn = sqlite3.connect(self.organizer.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT setor FROM documentos_classificados")
            setores = [row[0] for row in cursor.fetchall()]
            conn.close()
            return f"Setores encontrados: {', '.join(setores)}"
            
        else:
            return "Consulta não reconhecida. Tente perguntas sobre 'venda', 'compra' ou 'setor'."

if __name__ == "__main__":
    # Exemplo de uso
    agent = FiscalDocumentAgent(
        cabecalho_path='/home/ubuntu/upload/202401_NFs_Cabecalho.csv',
        itens_path='/home/ubuntu/upload/202401_NFs_Itens.csv'
    )
    
    print("Processando documentos...")
    agent.process_documents()
    
    print("\nTestando consultas:")
    print(agent.query_documents("Quantos documentos de venda temos?"))
    print(agent.query_documents("Quantos documentos de compra temos?"))
    print(agent.query_documents("Quais setores estão presentes?"))

