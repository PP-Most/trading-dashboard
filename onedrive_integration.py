"""
Trading Portfolio Dashboard - Google Drive Solution
==================================================
Google Drive je spolehlivější pro binární soubory než OneDrive
"""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import requests
import tempfile
import io
import re

# Konfigurace
st.set_page_config(
    page_title="Trading Portfolio Dashboard",
    page_icon="📊",
    layout="wide"
)

# Google Drive - nahraďte YOUR_FILE_ID skutečným ID
SQLITE_GDRIVE_ID = "YOUR_SQLITE_GDRIVE_FILE_ID"  # ID z Google Drive linku
EXCEL_GDRIVE_ID = "YOUR_EXCEL_GDRIVE_FILE_ID"    # ID z Google Drive linku

# OneDrive fallback
EXCEL_ONEDRIVE_URL = "https://1drv.ms/x/c/1E57DA124B7D1AC2/EclafUsS2lcggB6gUwiAAAABuX9tM0jgj1UUoSBDHmp_FA?e=SYk93C&download=1"

INITIAL_CAPITAL = 50000

def extract_google_drive_id(url):
    """Extrahuje file ID z Google Drive URL"""
    patterns = [
        r'/file/d/([a-zA-Z0-9-_]+)',
        r'id=([a-zA-Z0-9-_]+)',
        r'/open\?id=([a-zA-Z0-9-_]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def download_from_google_drive(file_id, file_type="file"):
    """Stáhne soubor z Google Drive"""
    try:
        # Google Drive direct download URL
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        
        with st.spinner(f"Stahuji {file_type} z Google Drive..."):
            session = requests.Session()
            response = session.get(download_url, stream=True)
            
            # Pro větší soubory může Google vyžadovat confirmation
            if "virus scan warning" in response.text.lower() or len(response.content) < 1000:
                # Najít confirmation token
                for line in response.text.split('\n'):
                    if 'confirm=' in line and 'download' in line:
                        # Extrahovat token
                        start = line.find('confirm=') + 8
                        end = line.find('&', start)
                        if end == -1:
                            end = line.find('"', start)
                        if end != -1:
                            confirm_token = line[start:end]
                            download_url = f"https://drive.google.com/uc?export=download&confirm={confirm_token}&id={file_id}"
                            response = session.get(download_url, stream=True)
                            break
            
            response.raise_for_status()
            
            # Zkontrolovat content-type
            content_type = response.headers.get('content-type', '')
            if 'html' in content_type.lower() and file_type == "SQLite":
                st.error(f"❌ {file_type}: Google Drive vrací HTML místo souboru")
                return None
            
            return response.content
            
    except Exception as e:
        st.error(f"Chyba při stahování {file_type} z Google Drive: {e}")
        return None

def setup_google_drive():
    """Konfigurace Google Drive file IDs"""
    st.subheader("🔧 Konfigurace Google Drive")
    
    with st.expander("📋 Jak získat Google Drive file ID", expanded=True):
        st.markdown("""
        **Postup pro oba soubory:**
        
        1. **Nahrajte soubory na Google Drive**
        2. **Pravý klik na soubor** → "Get link" 
        3. **Změňte na "Anyone with the link can view"**
        4. **Zkopírujte link** - vypadá takto:
           ```
           https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs/view?usp=sharing
           ```
        5. **File ID** je část mezi `/d/` a `/view`: `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs`
        """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**📊 SQLite databáze:**")
        sqlite_input = st.text_input(
            "SQLite Google Drive link:",
            placeholder="https://drive.google.com/file/d/1BxiMVs... nebo přímo ID",
            help="Celý Google Drive link nebo jen file ID pro SQLite",
            key="sqlite_input"
        )
        
        sqlite_file_id = None
        if sqlite_input:
            # Zkusit extrahovat ID z URL nebo použít přímo
            extracted_id = extract_google_drive_id(sqlite_input)
            sqlite_file_id = extracted_id if extracted_id else sqlite_input
            st.code(f"File ID: {sqlite_file_id}")
    
    with col2:
        st.write("**📈 Excel soubor:**")
        excel_input = st.text_input(
            "Excel Google Drive link:",
            placeholder="https://drive.google.com/file/d/1BxiMVs... nebo přímo ID",
            help="Celý Google Drive link nebo jen file ID pro Excel",
            key="excel_input"
        )
        
        excel_file_id = None
        if excel_input:
            extracted_id = extract_google_drive_id(excel_input)
            excel_file_id = extracted_id if extracted_id else excel_input
            st.code(f"File ID: {excel_file_id}")
    
    # Test tlačítko
    if st.button("🧪 Testovat Google Drive linky"):
        success_count = 0
        
        if sqlite_file_id:
            sqlite_content = download_from_google_drive(sqlite_file_id, "SQLite")
            if sqlite_content and sqlite_content.startswith(b'SQLite format 3'):
                st.success("✅ SQLite databáze OK")
                success_count += 1
            else:
                st.error("❌ SQLite databáze problém")
        
        if excel_file_id:
            excel_content = download_from_google_drive(excel_file_id, "Excel")
            if excel_content and (excel_content.startswith(b'PK\x03\x04') or len(excel_content) > 10000):
                st.success("✅ Excel soubor OK")
                success_count += 1
            else:
                st.error("❌ Excel soubor problém")
        
        if success_count == 2:
            st.success("🎉 Oba soubory jsou přístupné!")
            return sqlite_file_id, excel_file_id
    
    return sqlite_file_id, excel_file_id

def load_data_from_google_drive(sqlite_id, excel_id):
    """Načte data z Google Drive"""
    all_data = pd.DataFrame()
    
    # SQLite z Google Drive
    if sqlite_id:
        try:
            sqlite_content = download_from_google_drive(sqlite_id, "SQLite")
            
            if sqlite_content and sqlite_content.startswith(b'SQLite format 3'):
                # Uložit do dočasného souboru
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db3")
                temp_file.write(sqlite_content)
                temp_file.close()
                
                # Načíst data
                conn = sqlite3.connect(temp_file.name)
                query = """
                SELECT strategy, exitDate, "NetP/L" as netPL, entryDate, ticker, 
                       quantity, entryPrice, exitPrice, commission
                FROM diary 
                WHERE exitDate IS NOT NULL AND "NetP/L" IS NOT NULL AND strategy IS NOT NULL
                ORDER BY exitDate
                """
                df_sql = pd.read_sql_query(query, conn)
                conn.close()
                os.unlink(temp_file.name)
                
                df_sql['source'] = 'SQLite'
                all_data = pd.concat([all_data, df_sql], ignore_index=True)
                st.success(f"✅ SQLite: {len(df_sql)} záznamů")
                
        except Exception as e:
            st.error(f"Chyba při načítání SQLite: {e}")
    
    # Excel z Google Drive
    if excel_id:
        try:
            excel_content = download_from_google_drive(excel_id, "Excel")
            
            if excel_content:
                # Načíst Excel z bytes
                excel_file = io.BytesIO(excel_content)
                excel_data = pd.read_excel(excel_file, sheet_name=None)
                
                excel_data_combined = pd.DataFrame()
                
                for sheet_name, df_sheet in excel_data.items():
                    if len(df_sheet) == 0:
                        continue
                    
                    # Mapování sloupců
                    col_map = {
                        'Systém': 'strategy',
                        'Symbol': 'ticker',
                        'Typ': 'position',
                        'Datum': 'entryDate',
                        'Datum.1': 'exitDate',
                        'Počet': 'quantity',
                        'Cena': 'entryPrice',
                        'Cena.1': 'exitPrice',
                        '% změna': 'chg_percent',
                        'Komise': 'commission',
                        'Profit/Loss': 'netPL'
                    }
                    
                    df_sheet = df_sheet.rename(columns=col_map)
                    
                    # Kontrola povinných sloupců
                    required_cols = ['strategy', 'exitDate', 'netPL']
                    missing_cols = [col for col in required_cols if col not in df_sheet.columns]
                    
                    if len(missing_cols) == 0:
                        df_sheet['source'] = f'Excel-{sheet_name}'
                        excel_data_combined = pd.concat([excel_data_combined, df_sheet], ignore_index=True)
                
                all_data = pd.concat([all_data, excel_data_combined], ignore_index=True)
                st.success(f"✅ Excel: {len(excel_data_combined)} záznamů")
                
        except Exception as e:
            st.error(f"Chyba při načítání Excel: {e}")
    
    # Zpracování dat
    if not all_data.empty:
        all_data['exitDate'] = pd.to_datetime(all_data['exitDate'], errors='coerce')
        all_data['netPL'] = pd.to_numeric(all_data['netPL'], errors='coerce')
        all_data = all_data.dropna(subset=['exitDate', 'netPL', 'strategy'])
        all_data = all_data.sort_values('exitDate')
    
    return all_data

def calc_metrics(df):
    """Výpočet základních metrik"""
    if df.empty:
        return {}
    
    total_pl = df['netPL'].sum()
    total_trades = len(df)
    wins = len(df[df['netPL'] > 0])
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    
    return {
        'total_pl': total_pl,
        'total_pl_percent': (total_pl / INITIAL_CAPITAL) * 100,
        'total_capital': INITIAL_CAPITAL + total_pl,
        'total_trades': total_trades,
        'winning_trades': wins,
        'win_rate': win_rate
    }

def create_simple_chart(df):
    """Jednoduchý kumulativní graf"""
    if df.empty:
        return go.Figure()
    
    df_sorted = df.sort_values('exitDate')
    df_sorted['cum_pl'] = df_sorted['netPL'].cumsum()
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_sorted['exitDate'],
        y=df_sorted['cum_pl'],
        mode='lines',
        name='Kumulativní P&L',
        line=dict(color='blue', width=2)
    ))
    
    fig.update_layout(
        title="Kumulativní P&L",
        xaxis_title="Datum",
        yaxis_title="P&L (USD)",
        height=500
    )
    
    return fig

# HLAVNÍ APLIKACE
def main():
    st.title("📊 Trading Portfolio Dashboard")
    st.subheader("Google Drive Solution")
    
    st.info("💡 **Google Drive** je spolehlivější než OneDrive pro binární soubory (.db3)")
    
    # Konfigurace Google Drive
    sqlite_id, excel_id = setup_google_drive()
    
    if not sqlite_id or not excel_id:
        st.warning("⚠️ Nakonfigurujte Google Drive file IDs pro pokračování")
        return
    
    # Načtení dat
    if st.button("🚀 Načíst data z Google Drive", type="primary"):
        with st.spinner("Načítám data z Google Drive..."):
            df = load_data_from_google_drive(sqlite_id, excel_id)
        
        if df.empty:
            st.error("❌ Nepodařilo se načíst žádná data")
            return
        
        # Success
        msg = f"✅ Načteno {len(df)} obchodů"
        if 'source' in df.columns:
            counts = df['source'].value_counts()
            info = " | ".join([f"{k}: {v}" for k, v in counts.items()])
            msg += f" | {info}"
        st.success(msg)
        
        # Základní metriky
        metrics = calc_metrics(df)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("💰 Total P&L", f"${metrics.get('total_pl', 0):,.2f}")
        
        with col2:
            st.metric("📊 Celkový kapitál", f"${metrics.get('total_capital', INITIAL_CAPITAL):,.2f}")
        
        with col3:
            st.metric("🎯 Win Rate", f"{metrics.get('win_rate', 0):.1f}%")
        
        # Graf
        st.plotly_chart(create_simple_chart(df), use_container_width=True)
        
        # Debug
        with st.expander("🔧 Debug"):
            if 'source' in df.columns:
                st.write("**Zdroje:**")
                for source, count in df['source'].value_counts().items():
                    st.write(f"- {source}: {count}")
            
            st.dataframe(df[['strategy', 'exitDate', 'netPL', 'source']].head())

if __name__ == "__main__":
    main()
