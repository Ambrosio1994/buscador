import sqlite3
import os
import sys

# Garante que o diretório principal está no PYTHONPATH para importar os módulos
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database
from search import normalizar_consulta, stemizar_texto
from config import DATABASE_PATH

def executar_migracao():
    print("Iniciando migração de pré-normalização e stemming do texto...")
    
    if not os.path.exists(DATABASE_PATH):
        print("Banco de dados não encontrado. Nada para migrar.")
        return

    with database.get_connection(DATABASE_PATH) as conn:
        # Garante que a estrutura do banco está atualizada (colunas e novas tabelas FTS5)
        database.criar_banco(conn)
        
        # Seleciona todas as páginas do banco
        cursor = conn.execute("SELECT id, text, text_normalized, text_stemmed FROM pages;")
        paginas = cursor.fetchall()
        
        total = len(paginas)
        print(f"Encontradas {total} páginas totais no banco.")
        
        contador = 0
        for row in paginas:
            pid = row["id"]
            texto_bruto = row["text"]
            texto_norm = row["text_normalized"]
            texto_stem = row["text_stemmed"]
            
            mudou = False
            if texto_norm is None:
                texto_norm = normalizar_consulta(texto_bruto)
                mudou = True
            if texto_stem is None:
                texto_stem = stemizar_texto(texto_norm)
                mudou = True
                
            if mudou:
                conn.execute(
                    "UPDATE pages SET text_normalized = ?, text_stemmed = ? WHERE id = ?;",
                    (texto_norm, texto_stem, pid)
                )
                contador += 1
                if contador % 100 == 0 or contador == total:
                    print(f"Progresso: {contador} páginas migradas...")
        
        # Reconstrói os índices external-content pelo comando suportado do FTS5.
        print("Sincronizando índices virtuais FTS5...")
        conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild');")
        conn.execute("INSERT INTO pages_stemmed_fts(pages_stemmed_fts) VALUES('rebuild');")
        database.atualizar_vocabulario(conn)
        
        # Validação
        cursor_val = conn.execute(
            "SELECT COUNT(*) AS total FROM pages WHERE text_normalized IS NULL OR text_stemmed IS NULL;"
        )
        nulos = cursor_val.fetchone()["total"]
        if nulos == 0:
            print("Validação concluída: todas as páginas estão normalizadas e stemizadas.")
        else:
            print(f"Erro: ainda restam {nulos} páginas com colunas nulas.")

if __name__ == "__main__":
    executar_migracao()
