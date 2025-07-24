"""
Trading Portfolio Dashboard with OneDrive Integration (FIXED)
============================================================
Správná implementace pro OneDrive direct download
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
import base64

# Konfigurace stránky
st.set_page_config(
    page_title="Trading Portfolio Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Konfigurace OneDrive
ONEDRIVE_SHARE_URL = "YOUR_ONEDRIVE_SHARE_URL_HERE"  # Celý share URL z OneDrive
INITIAL_CAPITAL = 50000

def convert_onedrive_url_to_direct(share_url):
    """Konvertuje OneDrive share URL na direct download URL"""
    try:
        # Metoda 1: Klasická konverze
        if "1drv.ms" in share_url:
            # Zkusit přidat download parameter
            if "?" in share_url:
                direct_url = share_url + "&download=1"
            else:
                direct_url = share_url + "?download=1"
            return direct_url
            
        # Metoda 2: onedrive.live.com URL
        elif "onedrive.live.com" in share_url:
            # Nahradit redir s download
            direct_url = share_url.replace("redir?", "download?")
            return direct_url
            
        # Metoda 3: sharepoint URL
        elif "sharepoint.com" in share_url or "-my.sharepoint.com" in share_url:
            # Přidat download=1 parametr
            if "?" in share_url:
                direct_url = share_url + "&download=1"
            else:
                direct_url = share_url + "?download=1"
            return direct_url
            
        return share_url
        
    except Exception as e:
        st.error(f"Chyba při konverzi URL: {e}")
        return share_url

def try_multiple_download_methods(share_url, filename):
    """Zkusí několik metod stažení z OneDrive"""
    
    methods = [
        # Metoda 1: Základní direct link
        convert_onedrive_url_to_direct(share_url),
        
        # Metoda 2: Embed download
        share_url.replace("/s/", "/download/s/") if "/s/" in share_url else None,
        
        # Metoda 3: API endpoint
        share_url.replace("1drv.ms", "api.onedrive.com/v1.0/shares") if "1drv.ms" in share_url else None,
    ]
    
    # Odstranit None hodnoty
    methods = [m for m in methods if m is not None]
    
    for i, url in enumerate(methods, 1):
        st.write(f"🔄 Zkouším metodu {i}: {url[:50]}...")
        
        try:
            response = requests.get(url, stream=True, timeout=30)
            
            # Debug informace
            st.write(f"   Status: {response.status_code}")
            st.write(f"   Content-Type: {response.headers.get('content-type', 'N/A')}")
            st.write(f"   Velikost: {len(response.content)} bytů")
            
            # Zkontrolovat, jestli je to HTML
            if response.content.startswith(b'<!DOCTYPE') or b'<html' in response.content[:500]:
                st.warning(f"   ⚠️ Metoda {i}: HTML odpověď")
                continue
                
            # Zkontrolovat SQLite header
            if response.content.startswith(b'SQLite format 3'):
                st.success(f"   ✅ Metoda {i}: Úspěch! SQLite databáze")
                
                # Uložit soubor
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db3")
                temp_file.write(response.content)
                temp_file.close()
                
                return temp_file.name
                
            else:
                st.warning(f"   ⚠️ Metoda {i}: Neznámý formát")
                # Zobrazit první bytes pro debug
                st.code(f"První bytes: {response.content[:50]}")
                
        except Exception as e:
            st.error(f"   ❌ Metoda {i}: Chyba - {e}")
            continue
    
    return None

def manual_onedrive_config():
    """Ruční konfigurace OneDrive linku"""
    st.subheader("🔧 Konfigurace OneDrive")
    
    with st.expander("📋 Jak získat správný OneDrive link", expanded=True):
        st.markdown("""
        ### Metoda A: Přes webové rozhraní OneDrive
        1. **Jděte na** [onedrive.live.com](https://onedrive.live.com)
        2. **Najděte** soubor `tradebook.db3`
        3. **Klikněte na tři tečky** (...) vedle souboru
        4. **Vyberte "Share"**
        5. **Klikněte "Copy link"**
        6. **Zkopírujte celý URL**
        
        ### Metoda B: Přes desktop aplikaci
        1. **Pravý klik** na soubor v OneDrive složce
        2. **"Share a OneDrive link"**
        3. **Zkopírujte URL**
        
        ### Metoda C: Embed link
        1. **V OneDrive** vyberte soubor
        2. **"Embed"** místo "Share"
        3. **Zkopírujte src URL** z iframe kódu
        """)
    
    # Input pro URL
    user_url = st.text_input(
        "📎 Vložte váš OneDrive share URL:",
        placeholder="https://1drv.ms/u/s!... nebo https://onedrive.live.com/...",
        help="Vložte celý URL, který jste zkopírovali z OneDrive"
    )
    
    if user_url:
        if st.button("🧪 Testovat OneDrive link"):
            with st.spinner("Testuji různé metody stažení..."):
                result = try_multiple_download_methods(user_url, "tradebook.db3")
                
                if result:
                    st.success("🎉 **Úspěch!** OneDrive link funguje!")
                    st.info(f"💾 **Pro použití v aplikaci, zkopírujte tento URL:**")
                    st.code(user_url)
                    
                    # Pokus o načtení dat
                    try:
                        conn = sqlite3.connect(result)
                        df = pd.read_sql_query("SELECT COUNT(*) as count FROM diary", conn)
                        conn.close()
                        os.unlink(result)
                        
                        st.success(f"✅ **Databáze obsahuje {df.iloc[0]['count']} záznamů**")
                        
                    except Exception as e:
                        st.error(f"❌ Chyba při čtení databáze: {e}")
                        if os.path.exists(result):
                            os.unlink(result)
                else:
                    st.error("❌ **Nepodařilo se stáhnout soubor žádnou metodou**")
                    
                    st.markdown("""
                    ### 🛠️ Možná řešení:
                    1. **Zkontrolujte oprávnění** - soubor musí být "Anyone with link can view"
                    2. **Zkuste jiný typ linku** - Share vs Embed
                    3. **Kontaktujte mě** s konkrétním linkem pro další pomoc
                    """)
    
    return user_url

def load_data_from_onedrive():
    """Načte data z OneDrive pomocí konfigurovaného URL"""
    if not ONEDRIVE_SHARE_URL or ONEDRIVE_SHARE_URL == "YOUR_ONEDRIVE_SHARE_URL_HERE":
        st.error("🔗 OneDrive URL není nakonfigurován!")
        
        # Zobrazit konfigurační panel
        configured_url = manual_onedrive_config()
        
        if configured_url:
            # Dočasně použít URL od uživatele
            global ONEDRIVE_SHARE_URL
            ONEDRIVE_SHARE_URL = configured_url
        else:
            return pd.DataFrame()
    
    try:
        temp_db_path = try_multiple_download_methods(ONEDRIVE_SHARE_URL, "tradebook.db3")
        
        if not temp_db_path:
            st.error("❌ Nepodařilo se stáhnout databázi z OneDrive")
            return pd.DataFrame()
        
        # Načíst data z databáze
        conn = sqlite3.connect(temp_db_path)
        
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
        os.unlink(temp_db_path)
        
        # Zpracování dat
        df['exitDate'] = pd.to_datetime(df['exitDate'], errors='coerce')
        df['entryDate'] = pd.to_datetime(df['entryDate'], errors='coerce')
        df['netPL'] = pd.to_numeric(df['netPL'], errors='coerce')
        df = df.dropna(subset=['exitDate', 'netPL'])
        
        return df
        
    except Exception as e:
        st.error(f"Chyba při načítání dat z OneDrive: {e}")
        return pd.DataFrame()

def load_data_from_uploaded_file(uploaded_file):
    """Načte data z nahraného souboru (fallback)"""
    try:
        with open("temp_tradebook.db3", "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        conn = sqlite3.connect("temp_tradebook.db3")
        
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
        
        if os.path.exists("temp_tradebook.db3"):
            os.remove("temp_tradebook.db3")
        
        df['exitDate'] = pd.to_datetime(df['exitDate'], errors='coerce')
        df['entryDate'] = pd.to_datetime(df['entryDate'], errors='coerce')
        df['netPL'] = pd.to_numeric(df['netPL'], errors='coerce')
        df = df.dropna(subset=['exitDate', 'netPL'])
        
        return df
        
    except Exception as e:
        st.error(f"Chyba při zpracování nahraného souboru: {e}")
        return pd.DataFrame()

# Zkrácené verze funkcí pro zobrazení (stejné jako dříve)
def calculate_portfolio_metrics(df):
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
    if df.empty:
        return go.Figure()
    
    df_sorted = df.sort_values('exitDate')
    df_sorted['cumulative_pl'] = df_sorted['netPL'].cumsum()
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_sorted['exitDate'],
        y=df_sorted['cumulative_pl'],
        mode='lines',
        name='Kumulativní P&L'
    ))
    
    fig.update_layout(
        title="Kumulativní P&L",
        xaxis_title="Datum",
        yaxis_title="P&L (USD)",
        template='plotly_white'
    )
    
    return fig

# Hlavní aplikace
def main():
    st.title("📊 Trading Portfolio Dashboard")
    st.subheader("OneDrive Integration - Automatické načítání dat")
    
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
            "Nahrajte tradebook.db3:",
            type=['db3', 'db', 'sqlite']
        )
        
        if uploaded_file is not None:
            df = load_data_from_uploaded_file(uploaded_file)
    
    # Zobrazení dat
    if df.empty:
        if data_source == "🔗 OneDrive (Automaticky)":
            st.info("🔧 Nakonfigurujte OneDrive přístup výše")
        else:
            st.info("📁 Nahrajte soubor v postranním panelu")
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
    strategy_summary = df.groupby('strategy')['netPL'].agg(['sum', 'count']).round(2)
    strategy_summary.columns = ['Celkový P&L', 'Počet obchodů']
    st.dataframe(strategy_summary)

if __name__ == "__main__":
    main()
