"""
Trading Portfolio Dashboard - Fresh Setup
=========================================
Čerstvé nastavení obou zdrojů s ověřením
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

INITIAL_CAPITAL = 50000

# Session state
if 'sqlite_file_id' not in st.session_state:
    st.session_state.sqlite_file_id = ""

if 'onedrive_url' not in st.session_state:
    st.session_state.onedrive_url = ""

if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False

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

def test_google_drive_access(file_id):
    """Test přístupu k Google Drive souboru"""
    try:
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        
        response = requests.head(download_url, timeout=10)  # Jen hlavičky
        
        if response.status_code == 200:
            return True, "OK"
        else:
            return False, f"Status: {response.status_code}"
            
    except Exception as e:
        return False, str(e)

def test_onedrive_access(url):
    """Test přístupu k OneDrive souboru"""
    try:
        response = requests.head(url, timeout=10)  # Jen hlavičky
        
        if response.status_code == 200:
            return True, "OK"
        else:
            return False, f"Status: {response.status_code}"
            
    except Exception as e:
        return False, str(e)

def download_from_google_drive(file_id):
    """Stáhne soubor z Google Drive"""
    try:
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        
        session = requests.Session()
        response = session.get(download_url, stream=True)
        
        # Pro větší soubory může Google vyžadovat confirmation
        if "virus scan warning" in response.text.lower() or len(response.content) < 1000:
            for line in response.text.split('\n'):
                if 'confirm=' in line and 'download' in line:
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
        return response.content
        
    except Exception as e:
        raise Exception(f"Google Drive download failed: {e}")

def download_from_onedrive(url):
    """Stáhne soubor z OneDrive"""
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        if response.content.startswith(b'<!DOCTYPE') or b'<html' in response.content[:500]:
            raise Exception("OneDrive returned HTML instead of file")
        
        return response.content
        
    except Exception as e:
        raise Exception(f"OneDrive download failed: {e}")

def load_sqlite_data(file_id):
    """Načte SQLite data"""
    try:
        sqlite_content = download_from_google_drive(file_id)
        
        if not sqlite_content.startswith(b'SQLite format 3'):
            raise Exception("Downloaded file is not SQLite database")
        
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
        df = pd.read_sql_query(query, conn)
        conn.close()
        os.unlink(temp_file.name)
        
        df['source'] = 'SQLite-GoogleDrive'
        return df
        
    except Exception as e:
        raise Exception(f"SQLite processing failed: {e}")

def load_excel_data(url):
    """Načte Excel data"""
    try:
        excel_content = download_from_onedrive(url)
        
        # Načíst Excel z bytes
        excel_file = io.BytesIO(excel_content)
        excel_data = pd.read_excel(excel_file, sheet_name=None)
        
        combined_data = pd.DataFrame()
        
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
                df_sheet['source'] = f'Excel-OneDrive-{sheet_name}'
                df_sheet['sheet_name'] = sheet_name
                combined_data = pd.concat([combined_data, df_sheet], ignore_index=True)
        
        return combined_data
        
    except Exception as e:
        raise Exception(f"Excel processing failed: {e}")

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
    """Jednoduchý graf"""
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
    st.subheader("🔧 Fresh Setup - Nové nastavení zdrojů")
    
    st.info("💡 **Čerstvé nastavení**: Nakonfigurujte oba zdroje znovu s ověřením přístupu")
    
    # KROK 1: Google Drive SQLite
    st.header("📊 Krok 1: SQLite z Google Drive")
    
    with st.expander("📋 Jak nahrát SQLite na Google Drive", expanded=True):
        st.markdown("""
        **Postup:**
        1. **Nahrajte** `tradebook.db3` na Google Drive
        2. **Pravý klik** → "Get link"
        3. **Změňte na** "Anyone with the link can view"
        4. **Zkopírujte link**
        """)
    
    sqlite_input = st.text_area(
        "Google Drive link pro SQLite:",
        value=st.session_state.sqlite_file_id,
        placeholder="https://drive.google.com/file/d/1BxiMVs... nebo jen File ID",
        height=80,
        key="sqlite_fresh_input"
    )
    
    sqlite_file_id = None
    if sqlite_input:
        extracted_id = extract_google_drive_id(sqlite_input)
        sqlite_file_id = extracted_id if extracted_id else sqlite_input.strip()
        
        if sqlite_file_id != st.session_state.sqlite_file_id:
            st.session_state.sqlite_file_id = sqlite_file_id
        
        st.code(f"File ID: {sqlite_file_id}")
        
        # Test přístupu
        if st.button("🧪 Testovat SQLite přístup", key="test_sqlite"):
            with st.spinner("Testuji Google Drive přístup..."):
                success, message = test_google_drive_access(sqlite_file_id)
                
                if success:
                    st.success(f"✅ SQLite přístup OK: {message}")
                else:
                    st.error(f"❌ SQLite přístup problém: {message}")
    
    # KROK 2: OneDrive Excel
    st.header("📈 Krok 2: Excel z OneDrive")
    
    with st.expander("📋 Jak nahrát Excel na OneDrive", expanded=True):
        st.markdown("""
        **Postup:**
        1. **Nahrajte** `portfolio_k_30012024_new.xlsx` na OneDrive
        2. **Pravý klik** → "Share"
        3. **Změňte na** "Anyone with the link can view"
        4. **Zkopírujte link** a přidejte `?download=1` na konec
        """)
    
    onedrive_input = st.text_area(
        "OneDrive link pro Excel:",
        value=st.session_state.onedrive_url,
        placeholder="https://1drv.ms/x/... nebo celý OneDrive URL",
        height=80,
        key="onedrive_fresh_input"
    )
    
    if onedrive_input:
        # Automaticky přidat download parameter pokud není
        if "?download=1" not in onedrive_input and "&download=1" not in onedrive_input:
            if "?" in onedrive_input:
                onedrive_url = onedrive_input + "&download=1"
            else:
                onedrive_url = onedrive_input + "?download=1"
        else:
            onedrive_url = onedrive_input
        
        if onedrive_url != st.session_state.onedrive_url:
            st.session_state.onedrive_url = onedrive_url
        
        st.code(f"URL: {onedrive_url[:60]}...")
        
        # Test přístupu
        if st.button("🧪 Testovat Excel přístup", key="test_excel"):
            with st.spinner("Testuji OneDrive přístup..."):
                success, message = test_onedrive_access(onedrive_url)
                
                if success:
                    st.success(f"✅ Excel přístup OK: {message}")
                else:
                    st.error(f"❌ Excel přístup problém: {message}")
    
    # KROK 3: Načtení dat
    st.header("🚀 Krok 3: Načtení dat")
    
    if not st.session_state.sqlite_file_id or not st.session_state.onedrive_url:
        st.warning("⚠️ Nakonfigurujte oba zdroje výše")
        return
    
    if st.button("📊 Načíst data z obou zdrojů", type="primary"):
        all_data = pd.DataFrame()
        
        # SQLite
        try:
            with st.spinner("Načítám SQLite z Google Drive..."):
                sqlite_df = load_sqlite_data(st.session_state.sqlite_file_id)
                if not sqlite_df.empty:
                    all_data = pd.concat([all_data, sqlite_df], ignore_index=True)
                    st.success(f"✅ SQLite: {len(sqlite_df)} záznamů")
        except Exception as e:
            st.error(f"❌ SQLite chyba: {e}")
        
        # Excel
        try:
            with st.spinner("Načítám Excel z OneDrive..."):
                excel_df = load_excel_data(st.session_state.onedrive_url)
                if not excel_df.empty:
                    all_data = pd.concat([all_data, excel_df], ignore_index=True)
                    st.success(f"✅ Excel: {len(excel_df)} záznamů")
        except Exception as e:
            st.error(f"❌ Excel chyba: {e}")
        
        if all_data.empty:
            st.error("❌ Nepodařilo se načíst žádná data")
            return
        
        # Zpracování dat
        all_data['exitDate'] = pd.to_datetime(all_data['exitDate'], errors='coerce')
        all_data['netPL'] = pd.to_numeric(all_data['netPL'], errors='coerce')
        all_data = all_data.dropna(subset=['exitDate', 'netPL', 'strategy'])
        all_data = all_data.sort_values('exitDate')
        
        # Odstranit duplikáty
        all_data = all_data.drop_duplicates(subset=['strategy', 'exitDate', 'netPL'], keep='first')
        
        st.session_state.data_loaded = True
        
        # Success
        msg = f"✅ Načteno {len(all_data)} obchodů"
        if 'source' in all_data.columns:
            counts = all_data['source'].value_counts()
            info = " | ".join([f"{k}: {v}" for k, v in counts.items()])
            msg += f" | {info}"
        st.success(msg)
        
        # Základní metriky
        metrics = calc_metrics(all_data)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("💰 Total P&L", f"${metrics.get('total_pl', 0):,.2f}")
        
        with col2:
            st.metric("📊 Celkový kapitál", f"${metrics.get('total_capital', INITIAL_CAPITAL):,.2f}")
        
        with col3:
            st.metric("🎯 Win Rate", f"{metrics.get('win_rate', 0):.1f}%")
        
        # Graf
        st.plotly_chart(create_simple_chart(all_data), use_container_width=True)
        
        # Debug
        with st.expander("🔧 Debug"):
            if 'source' in all_data.columns:
                st.write("**Zdroje:**")
                for source, count in all_data['source'].value_counts().items():
                    st.write(f"- {source}: {count}")
            
            st.dataframe(all_data[['strategy', 'exitDate', 'netPL', 'source']].head(10))

if __name__ == "__main__":
    main()
