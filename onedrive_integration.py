"""
Trading Portfolio Dashboard with OneDrive Integration
====================================================
Support pro Excel i SQLite soubory z OneDrive
"""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np
import re
import os
import requests
import tempfile
import io

# Konfigurace stránky
st.set_page_config(
    page_title="Trading Portfolio Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Konfigurace
INITIAL_CAPITAL = 50000

# Session state pro OneDrive URL
if 'onedrive_url' not in st.session_state:
    st.session_state.onedrive_url = "YOUR_ONEDRIVE_SHARE_URL_HERE"

def convert_onedrive_url_to_direct(share_url):
    """Konvertuje OneDrive share URL na direct download URL"""
    try:
        if "1drv.ms" in share_url:
            if "?" in share_url:
                direct_url = share_url + "&download=1"
            else:
                direct_url = share_url + "?download=1"
            return direct_url
        elif "onedrive.live.com" in share_url:
            direct_url = share_url.replace("redir?", "download?")
            return direct_url
        elif "sharepoint.com" in share_url or "-my.sharepoint.com" in share_url:
            if "?" in share_url:
                direct_url = share_url + "&download=1"
            else:
                direct_url = share_url + "?download=1"
            return direct_url
        return share_url
    except Exception as e:
        st.error(f"Chyba při konverzi URL: {e}")
        return share_url

def detect_file_type(content, content_type):
    """Detekuje typ souboru podle obsahu a content-type"""
    
    # SQLite databáze
    if content.startswith(b'SQLite format 3'):
        return 'sqlite'
    
    # Excel soubory
    if (content_type and 'spreadsheet' in content_type.lower()) or \
       (content_type and 'excel' in content_type.lower()) or \
       content.startswith(b'PK\x03\x04'):  # ZIP signature (Excel je ZIP archiv)
        return 'excel'
    
    # CSV soubory
    if content_type and 'csv' in content_type.lower():
        return 'csv'
    
    return 'unknown'

def load_data_from_excel_content(content):
    """Načte data z Excel obsahu"""
    try:
        # Načíst Excel z bytes
        excel_file = io.BytesIO(content)
        
        # Najít sheet s daty (zkusit různé možné názvy)
        possible_sheets = ['diary', 'trades', 'Sheet1', 'Data', 'Portfolio']
        
        # Načíst všechny sheets
        try:
            excel_data = pd.read_excel(excel_file, sheet_name=None)  # Načte všechny sheets
            st.write(f"🔍 **Nalezené sheets:** {list(excel_data.keys())}")
        except Exception as e:
            st.error(f"Chyba při čtení Excel souboru: {e}")
            return pd.DataFrame()
        
        # Najít správný sheet
        target_df = None
        for sheet_name in possible_sheets:
            if sheet_name in excel_data:
                target_df = excel_data[sheet_name]
                st.success(f"✅ **Použit sheet:** {sheet_name}")
                break
        
        # Pokud nenajde specifický sheet, použij první
        if target_df is None and excel_data:
            first_sheet = list(excel_data.keys())[0]
            target_df = excel_data[first_sheet]
            st.info(f"📋 **Použit první sheet:** {first_sheet}")
        
        if target_df is None:
            st.error("❌ Žádný vhodný sheet nenalezen")
            return pd.DataFrame()
        
        # Zobrazit ukázku dat pro debug
        st.write("**🔍 Ukázka načtených dat:**")
        st.write(f"**Sloupce:** {list(target_df.columns)}")
        st.dataframe(target_df.head())
        
        # Mapování sloupců (pokusit se najít správné sloupce)
        column_mapping = {}
        
        # Najít sloupce podle názvů
        for col in target_df.columns:
            col_lower = str(col).lower()
            
            if 'strategy' in col_lower or 'strategie' in col_lower:
                column_mapping['strategy'] = col
            elif 'exit' in col_lower and 'date' in col_lower:
                column_mapping['exitDate'] = col
            elif 'entry' in col_lower and 'date' in col_lower:
                column_mapping['entryDate'] = col
            elif 'net' in col_lower and ('p' in col_lower or 'l' in col_lower):
                column_mapping['netPL'] = col
            elif col_lower in ['pl', 'p&l', 'profit', 'netpl']:
                column_mapping['netPL'] = col
            elif 'ticker' in col_lower or 'symbol' in col_lower:
                column_mapping['ticker'] = col
            elif 'quantity' in col_lower or 'qty' in col_lower:
                column_mapping['quantity'] = col
            elif 'entry' in col_lower and 'price' in col_lower:
                column_mapping['entryPrice'] = col
            elif 'exit' in col_lower and 'price' in col_lower:
                column_mapping['exitPrice'] = col
            elif 'comm' in col_lower:
                column_mapping['commission'] = col
        
        st.write(f"**🔗 Mapování sloupců:** {column_mapping}")
        
        # Zkontrolovat, jestli máme potřebné sloupce
        required_columns = ['strategy', 'exitDate', 'netPL']
        missing_columns = [col for col in required_columns if col not in column_mapping]
        
        if missing_columns:
            st.error(f"❌ **Chybí sloupce:** {missing_columns}")
            st.info("💡 **Tip:** Ujistěte se, že Excel obsahuje sloupce: strategy, exitDate, NetP/L")
            return pd.DataFrame()
        
        # Přejmenovat sloupce
        df = target_df.rename(columns={v: k for k, v in column_mapping.items()})
        
        # Základní čištění dat
        df = df[df['strategy'].notna()]
        df = df[df['exitDate'].notna()]
        df = df[df['netPL'].notna()]
        
        # Konverze typů
        df['exitDate'] = pd.to_datetime(df['exitDate'], errors='coerce')
        if 'entryDate' in df.columns:
            df['entryDate'] = pd.to_datetime(df['entryDate'], errors='coerce')
        df['netPL'] = pd.to_numeric(df['netPL'], errors='coerce')
        
        # Konečné čištění
        df = df.dropna(subset=['exitDate', 'netPL'])
        
        st.success(f"✅ **Úspěšně načteno {len(df)} záznamů z Excel souboru!**")
        
        return df
        
    except Exception as e:
        st.error(f"Chyba při zpracování Excel souboru: {e}")
        return pd.DataFrame()

def load_data_from_sqlite_content(content):
    """Načte data z SQLite obsahu"""
    try:
        # Uložit do dočasného souboru
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db3")
        temp_file.write(content)
        temp_file.close()
        
        # Načíst data z databáze
        conn = sqlite3.connect(temp_file.name)
        
        query = """
        SELECT 
            strategy,
            exitDate,
            "NetP/L" as netPL,
            entryDate,
            ticker,
            quantity,
            entryPrice,
            exitPrice,
            commission
        FROM diary 
        WHERE exitDate IS NOT NULL 
        AND "NetP/L" IS NOT NULL 
        AND strategy IS NOT NULL
        ORDER BY exitDate
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        # Vyčistit dočasný soubor
        os.unlink(temp_file.name)
        
        # Zpracování dat
        df['exitDate'] = pd.to_datetime(df['exitDate'], errors='coerce')
        df['entryDate'] = pd.to_datetime(df['entryDate'], errors='coerce')
        df['netPL'] = pd.to_numeric(df['netPL'], errors='coerce')
        df = df.dropna(subset=['exitDate', 'netPL'])
        
        return df
        
    except Exception as e:
        st.error(f"Chyba při zpracování SQLite souboru: {e}")
        return pd.DataFrame()

def try_download_and_process(share_url, filename):
    """Zkusí stáhnout a zpracovat soubor z OneDrive"""
    
    methods = [
        convert_onedrive_url_to_direct(share_url),
        share_url.replace("/s/", "/download/s/") if "/s/" in share_url else None,
    ]
    
    methods = [m for m in methods if m is not None]
    
    for i, url in enumerate(methods, 1):
        st.write(f"🔄 **Zkouším metodu {i}:** {url[:60]}...")
        
        try:
            response = requests.get(url, stream=True, timeout=30)
            
            # Debug informace
            st.write(f"   📊 **Status:** {response.status_code}")
            st.write(f"   📋 **Content-Type:** {response.headers.get('content-type', 'N/A')}")
            st.write(f"   📏 **Velikost:** {len(response.content):,} bytů")
            
            if response.status_code != 200:
                st.warning(f"   ⚠️ Status {response.status_code}")
                continue
                
            # Zkontrolovat, jestli je to HTML (error page)
            if response.content.startswith(b'<!DOCTYPE') or b'<html' in response.content[:500]:
                st.warning(f"   ⚠️ Metoda {i}: HTML odpověď (pravděpodobně error page)")
                continue
            
            # Detekovat typ souboru
            content_type = response.headers.get('content-type', '')
            file_type = detect_file_type(response.content, content_type)
            
            st.info(f"   🔍 **Detekovaný typ:** {file_type}")
            
            if file_type == 'sqlite':
                st.success(f"   ✅ Metoda {i}: SQLite databáze!")
                return load_data_from_sqlite_content(response.content)
                
            elif file_type == 'excel':
                st.success(f"   ✅ Metoda {i}: Excel soubor!")
                return load_data_from_excel_content(response.content)
                
            else:
                st.warning(f"   ⚠️ Metoda {i}: Nepodporovaný formát")
                st.code(f"První bytes: {response.content[:100]}")
                
        except Exception as e:
            st.error(f"   ❌ Metoda {i}: Chyba - {e}")
            continue
    
    return pd.DataFrame()

def manual_onedrive_config():
    """Ruční konfigurace OneDrive linku"""
    st.subheader("🔧 Konfigurace OneDrive")
    
    with st.expander("📋 Jak získat správný OneDrive link", expanded=True):
        st.markdown("""
        ### ✅ Doporučený postup:
        1. **Jděte na** [onedrive.live.com](https://onedrive.live.com)
        2. **Najděte** váš soubor (`.db3` nebo `.xlsx`)
        3. **Klikněte na tři tečky** (...) vedle souboru
        4. **Vyberte "Share"**
        5. **Nastavte "Anyone with the link can view"**
        6. **Zkopírujte celý URL**
        
        ### 📊 Podporované formáty:
        - **SQLite databáze** (`.db3`, `.sqlite`)
        - **Excel soubory** (`.xlsx`, `.xls`)
        - **CSV soubory** (`.csv`)
        """)
    
    # Input pro URL
    user_url = st.text_input(
        "📎 Vložte váš OneDrive share URL:",
        value=st.session_state.onedrive_url if st.session_state.onedrive_url != "YOUR_ONEDRIVE_SHARE_URL_HERE" else "",
        placeholder="https://1drv.ms/... (Excel nebo SQLite soubor)",
        help="URL na váš OneDrive soubor s trading daty"
    )
    
    if user_url and user_url != st.session_state.onedrive_url:
        st.session_state.onedrive_url = user_url
    
    if user_url:
        if st.button("🧪 Testovat OneDrive link"):
            with st.spinner("Testuji stažení a zpracování souboru..."):
                result_df = try_download_and_process(user_url, "trading_data")
                
                if not result_df.empty:
                    st.success("🎉 **Úspěch!** Data byla načtena!")
                    st.info(f"📊 **Načteno:** {len(result_df)} záznamů")
                    st.info(f"📈 **Strategie:** {', '.join(result_df['strategy'].unique())}")
                    
                    # Uložit úspěšný URL
                    st.session_state.onedrive_url = user_url
                    st.session_state.onedrive_working = True
                    
                    return user_url, result_df
                else:
                    st.error("❌ **Nepodařilo se načíst data**")
                    st.markdown("""
                    ### 🛠️ Možná řešení:
                    1. **Zkontrolujte oprávnění** - soubor musí být veřejně přístupný
                    2. **Zkontrolujte formát** - podporujeme Excel a SQLite
                    3. **Zkontrolujte obsah** - musí obsahovat sloupce strategy, exitDate, NetP/L
                    """)
    
    return user_url, pd.DataFrame()

def load_data_from_onedrive():
    """Načte data z OneDrive pomocí konfigurovaného URL"""
    onedrive_url = st.session_state.onedrive_url
    
    if not onedrive_url or onedrive_url == "YOUR_ONEDRIVE_SHARE_URL_HERE":
        st.error("🔗 OneDrive URL není nakonfigurován!")
        configured_url, test_df = manual_onedrive_config()
        return test_df
    
    # Pokusit se načíst data
    df = try_download_and_process(onedrive_url, "trading_data")
    
    if df.empty:
        st.error("❌ Nepodařilo se načíst data z OneDrive")
        # Zobrazit konfigurační panel pro opravu
        configured_url, test_df = manual_onedrive_config()
        return test_df
    
    return df

def load_data_from_uploaded_file(uploaded_file):
    """Načte data z nahraného souboru (fallback)"""
    try:
        file_extension = uploaded_file.name.split('.')[-1].lower()
        
        if file_extension in ['xlsx', 'xls']:
            # Excel soubor
            return load_data_from_excel_content(uploaded_file.read())
        
        elif file_extension in ['db3', 'db', 'sqlite']:
            # SQLite databáze
            return load_data_from_sqlite_content(uploaded_file.read())
        
        else:
            st.error(f"❌ Nepodporovaný formát: {file_extension}")
            return pd.DataFrame()
        
    except Exception as e:
        st.error(f"Chyba při zpracování nahraného souboru: {e}")
        return pd.DataFrame()

def calculate_portfolio_metrics(df):
    """Vypočítá portfolio metriky"""
    if df.empty:
        return {}
    
    total_pl = df['netPL'].sum()
    total_pl_percent = (total_pl / INITIAL_CAPITAL) * 100
    total_trades = len(df)
    winning_trades = len(df[df['netPL'] > 0])
    win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
    
    return {
        'total_pl': total_pl,
        'total_pl_percent': total_pl_percent,
        'total_capital': INITIAL_CAPITAL + total_pl,
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'win_rate': win_rate
    }

def create_simple_chart(df):
    """Vytvoří jednoduchý kumulativní graf"""
    if df.empty:
        return go.Figure()
    
    df_sorted = df.sort_values('exitDate')
    df_sorted['cumulative_pl'] = df_sorted['netPL'].cumsum()
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_sorted['exitDate'],
        y=df_sorted['cumulative_pl'],
        mode='lines+markers',
        name='Kumulativní P&L',
        line=dict(color='#1f77b4', width=3),
        marker=dict(size=4)
    ))
    
    fig.update_layout(
        title="📈 Kumulativní P&L",
        xaxis_title="Datum",
        yaxis_title="P&L (USD)",
        template='plotly_white',
        height=500
    )
    
    return fig

# Hlavní aplikace
def main():
    st.title("📊 Trading Portfolio Dashboard")
    st.subheader("OneDrive Integration - Support pro Excel i SQLite")
    
    st.sidebar.header("📁 Zdroj dat")
    
    data_source = st.sidebar.radio(
        "Vyberte zdroj dat:",
        ["🔗 OneDrive (Automaticky)", "📁 Nahrát soubor"]
    )
    
    df = pd.DataFrame()
    
    if data_source == "🔗 OneDrive (Automaticky)":
        # OneDrive načítání
        df = load_data_from_onedrive()
        
        if not df.empty:
            last_update = datetime.now().strftime("%H:%M:%S")
            st.sidebar.success(f"✅ Data načtena z OneDrive\n🕐 {last_update}")
            
            if st.sidebar.button("🔄 Aktualizovat"):
                st.rerun()
    
    else:
        # Fallback upload
        uploaded_file = st.sidebar.file_uploader(
            "Nahrajte soubor:",
            type=['db3', 'db', 'sqlite', 'xlsx', 'xls'],
            help="SQLite databáze nebo Excel soubor"
        )
        
        if uploaded_file is not None:
            with st.spinner("Zpracovávám nahraný soubor..."):
                df = load_data_from_uploaded_file(uploaded_file)
    
    # Zobrazení dat
    if df.empty:
        if data_source == "🔗 OneDrive (Automaticky)":
            st.info("🔧 Nakonfigurujte OneDrive přístup výše")
        else:
            st.info("📁 Nahrajte Excel nebo SQLite soubor v postranním panelu")
        return
    
    st.success(f"✅ Načteno {len(df)} obchodů ze strategií: {', '.join(df['strategy'].unique())}")
    
    # Základní metriky
    metrics = calculate_portfolio_metrics(df)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("💰 Total P&L", f"${metrics.get('total_pl', 0):,.2f}")
    
    with col2:
        st.metric("📊 Celkový kapitál", f"${metrics.get('total_capital', INITIAL_CAPITAL):,.2f}")
    
    with col3:
        st.metric("🎯 Win Rate", f"{metrics.get('win_rate', 0):.1f}%")
    
    # Graf
    st.subheader("📈 Kumulativní P&L")
    fig = create_simple_chart(df)
    st.plotly_chart(fig, use_container_width=True)
    
    # Tabulka strategií
    st.subheader("📋 Přehled strategií")
    if not df.empty:
        strategy_summary = df.groupby('strategy')['netPL'].agg(['sum', 'count']).round(2)
        strategy_summary.columns = ['Celkový P&L ($)', 'Počet obchodů']
        st.dataframe(strategy_summary, use_container_width=True)
    
    # Debug informace
    with st.expander("🔧 Debug informace"):
        st.write("**Struktura dat:**")
        st.write(f"Počet řádků: {len(df)}")
        st.write(f"Sloupce: {list(df.columns)}")
        if not df.empty:
            st.write("**Ukázka dat:**")
            st.dataframe(df.head())

if __name__ == "__main__":
    main()
