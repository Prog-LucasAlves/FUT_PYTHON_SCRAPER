import glob
import os

import pandas as pd

DATA_DIR = "data"
GOLD_DIR = "gold"


def process_data():
    csv_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
    if not csv_files:
        print("Nenhum arquivo CSV encontrado na pasta data.")
        return

    print(f"Encontrados {len(csv_files)} arquivo(s): {[os.path.basename(f) for f in csv_files]}")

    # Concatenar todos os arquivos CSV em um único DataFrame
    df = pd.concat([pd.read_csv(f) for f in csv_files], ignore_index=True)
    print(f"Total de linhas após concatenação: {len(df)}")

    # Remover linhas ao vivo ou com contagem regressiva na coluna "time"
    time_normalized = df["time"].astype(str).str.strip().str.lower()
    mask_invalid = time_normalized.eq("vivo") | time_normalized.eq("ao vivo") | time_normalized.str.startswith("começa em")
    removed = mask_invalid.sum()
    df = df[~mask_invalid].copy()
    print(f"Linhas removidas (vivo / Começa em): {removed}")

    # Remover duplicados
    before_dedup = len(df)
    df = df.drop_duplicates()
    print(f"Linhas removidas (duplicadas): {before_dedup - len(df)}")

    # Formatar datas e horários para ordenação
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df["_sort_time"] = pd.to_datetime(df["time"], format="%H:%M", errors="coerce")
    df = df.sort_values(["date", "_sort_time"]).drop(columns=["_sort_time"])
    df["date"] = df["date"].dt.strftime("%d-%m-%Y")

    # Salvar o arquivo processado
    os.makedirs(GOLD_DIR, exist_ok=True)
    output_file = os.path.join(GOLD_DIR, "betfair_processed.csv")
    df.to_csv(output_file, index=False)
    print(f"Arquivo salvo em: {output_file} ({len(df)} linhas)")


if __name__ == "__main__":
    process_data()
