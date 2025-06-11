from flask import Blueprint, request, jsonify
import os
import sys
import zipfile
import rarfile
import shutil
# O pandas não é mais necessário aqui, pois a identificação será pelo nome do arquivo.
# import pandas as pd 

# Adiciona o diretório src ao path para importar os agentes
current_dir = os.path.dirname(__file__)
src_dir = os.path.dirname(current_dir)
sys.path.insert(0, src_dir)

from fiscal_agent import FiscalDocumentAgent
from csv_query_agent import IntegratedFiscalAgent

fiscal_bp = Blueprint("fiscal", __name__)

UPLOAD_FOLDER = os.path.join(src_dir, "uploads")
DATA_FOLDER = os.path.join(src_dir, "data")

# Garante que os diretórios existam
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATA_FOLDER, exist_ok=True)

# --- GERENCIAMENTO DE ESTADO CENTRALIZADO ---
# Mantemos esta melhoria: as variáveis são dinâmicas.
global_cabecalho_path = None
global_itens_path = None
classification_agent = None
query_agent = None

def update_agents_with_new_data(cabecalho_path, itens_path):
    """
    Função central que atualiza o estado da aplicação com os novos dados.
    """
    global classification_agent, query_agent, global_cabecalho_path, global_itens_path
    
    global_cabecalho_path = cabecalho_path
    global_itens_path = itens_path
    
    classification_agent = FiscalDocumentAgent(cabecalho_path, itens_path)
    query_agent = IntegratedFiscalAgent(cabecalho_path, itens_path)
    print(f"Agentes atualizados com os arquivos: {cabecalho_path} e {itens_path}")

@fiscal_bp.route("/upload", methods=["POST"])
def upload_file():
    """
    Endpoint para upload. Extrai arquivos e os identifica pelo NOME.
    """
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "Nenhum arquivo enviado"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "Nenhum arquivo selecionado"}), 400

    shutil.rmtree(UPLOAD_FOLDER)
    os.makedirs(UPLOAD_FOLDER)
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    extracted_csv_paths = []
    try:
        if zipfile.is_zipfile(filepath):
            with zipfile.ZipFile(filepath, "r") as zip_ref:
                zip_ref.extractall(UPLOAD_FOLDER)
        elif rarfile.is_rarfile(filepath):
             with rarfile.RarFile(filepath, "r") as rar_ref:
                rar_ref.extractall(UPLOAD_FOLDER)
        elif filepath.endswith(".csv"):
             # Adiciona o arquivo CSV único à lista para ser processado
             extracted_csv_paths.append(filepath)
        else:
            return jsonify({"status": "error", "message": "Formato de arquivo não suportado. Use .zip, .rar ou .csv."}), 400

        if not extracted_csv_paths:
            for root, _, files in os.walk(UPLOAD_FOLDER):
                for f in files:
                    if f.endswith(".csv"):
                        extracted_csv_paths.append(os.path.join(root, f))
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao extrair o arquivo: {str(e)}"}), 500
        
    # --- LÓGICA DE IDENTIFICAÇÃO REVERTIDA PARA O MÉTODO ORIGINAL (POR NOME) ---
    found_cabecalho = None
    found_itens = None
    
    # Validação para garantir que pelo menos um CSV foi encontrado
    if not extracted_csv_paths:
        return jsonify({"status": "error", "message": "Nenhum arquivo CSV encontrado dentro do arquivo compactado."}), 400

    for path in extracted_csv_paths:
        filename_lower = os.path.basename(path).lower()
        if "cabecalho" in filename_lower:
            found_cabecalho = path
        elif "itens" in filename_lower:
            found_itens = path

    # Se a identificação foi bem-sucedida, processa os arquivos
    if found_cabecalho and found_itens:
        shutil.rmtree(DATA_FOLDER)
        os.makedirs(DATA_FOLDER)
        
        # Usa o nome original do arquivo ao copiar, para clareza
        new_cabecalho_path = os.path.join(DATA_FOLDER, os.path.basename(found_cabecalho))
        new_itens_path = os.path.join(DATA_FOLDER, os.path.basename(found_itens))
        shutil.copy(found_cabecalho, new_cabecalho_path)
        shutil.copy(found_itens, new_itens_path)
        
        update_agents_with_new_data(new_cabecalho_path, new_itens_path)
        
        return jsonify({"status": "success", "message": "Arquivos processados e agentes atualizados!"})
    else:
        return jsonify({"status": "error", "message": "Não foi possível encontrar os arquivos de 'cabecalho' e 'itens' dentro do arquivo enviado. Verifique os nomes dos arquivos."}), 400

@fiscal_bp.route("/stats", methods=["GET"])
def get_stats():
    """
    Endpoint para buscar as estatísticas. Usa as variáveis globais de estado.
    """
    if not global_cabecalho_path or not os.path.exists(global_cabecalho_path) or not classification_agent:
        empty_stats = {
            "total_notas": 0, "total_itens": 0, "valor_total": 0.0, "valor_medio": 0.0
        }
        return jsonify({"status": "success", "stats": empty_stats})

    try:
        classification_agent.load_data()
        
        df_cabecalho = classification_agent.df_cabecalho
        df_itens = classification_agent.df_itens

        stats = {
            "total_notas": len(df_cabecalho),
            "total_itens": len(df_itens),
            "valor_total": float(df_cabecalho["VALOR NOTA FISCAL"].sum()),
            "valor_medio": float(df_cabecalho["VALOR NOTA FISCAL"].mean()),
        }
        return jsonify({"status": "success", "stats": stats})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao calcular estatísticas: {str(e)}"}), 500

@fiscal_bp.route("/classify", methods=["POST"])
def classify_documents():
    """
    Endpoint para disparar a classificação dos documentos carregados.
    """
    if not classification_agent:
        return jsonify({"status": "error", "message": "Nenhum arquivo foi carregado para classificar. Faça o upload primeiro."}), 400
    try:
        classification_agent.process_documents()
        return jsonify({"status": "success", "message": "Documentos classificados com sucesso!"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao classificar documentos: {str(e)}"}), 500

@fiscal_bp.route("/query", methods=["POST"])
def query_documents():
    """
    Endpoint para fazer perguntas em linguagem natural sobre os dados.
    """
    if not query_agent:
        return jsonify({"status": "error", "message": "Nenhum arquivo foi carregado para consultar. Faça o upload primeiro."}), 400
    
    data = request.get_json()
    question = data.get("question", "")
    
    if not question:
        return jsonify({"status": "error", "message": "Pergunta não fornecida"}), 400
    
    try:
        if any(keyword in question.lower() for keyword in ["classificação", "cfop", "setor", "centro de custo"]):
            answer = classification_agent.query_documents(question)
        else:
            answer = query_agent.process_query(question)
        
        return jsonify({"status": "success", "question": question, "answer": answer})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao processar consulta: {str(e)}"}), 500

@fiscal_bp.route("/examples", methods=["GET"])
def get_example_questions():
    """
    Retorna uma lista de perguntas de exemplo para o frontend.
    """
    examples = [
        "Qual é o fornecedor com maior valor total de notas?",
        "Qual item teve maior volume de compra?",
        "Qual o valor total das notas fiscais?",
        "Qual o valor médio por nota fiscal?",
        "Resuma os dados presentes.",
        "Quantos documentos são de venda?",
        "Quantos documentos são de compra?",
        "Liste os setores encontrados nos documentos."
    ]
    return jsonify({"status": "success", "examples": examples})