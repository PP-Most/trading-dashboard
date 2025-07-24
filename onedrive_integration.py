"""
Trading Portfolio Dashboard with OneDrive Integration
===================================================
Automaticky načítá data z OneDrive pro všechny uživatele
"""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np
import re
import os
import requests
import tempfile

# Konfigurace stránky
st.set_page_config(
    page_title="Trading Portfolio Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Konfigurace OneDrive
ONEDRIVE_DB_URL = "https://1drv.ms/u/c/1E57DA124B7D1AC2/EcIafUsS2lcggB65vgEAAAABH7q1wQjrpas2WCmb9yDT_Q?e=9yRO0i?download=1"  # Nahradit skutečným linkem
ONEDRIVE_EXCEL_URL = "https://1drv.ms/x/c/1E57DA124B7D1AC2/EcIafUsS2lcggB6aUwIAAAAB023T3-I_9HJWuT0tGWt9tw?e=5SnbeW?download=1"  # Pokud chcete i Excel
INITIAL_CAPITAL = 50000

def download_file_from_onedrive(url, filename):
    """Stáhne soubor z OneDrive pomocí sdíleného linku"""
    try:
        with st.spinner(f"Stahuji {filename} z OneDrive..."):
            # Konverze OneDrive share linku na přímý download link
            if "1drv.ms" in url or "onedrive.live.com" in url:
                # Získat přímý download link
                if "?download=1" not in url:
                    url = url.replace("?e=", "?download=1&e=")
            
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            # Uložit do dočasného souboru
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{filename.split('.')[-1]}")
            
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            
            temp_file.close()
            return temp_file.name
            
    except Exception as e:
        st.error(f"Chyba při stahování {filename}: {e}")
        return None

def safe_datetime_conversion(date_series):
    """Bezpečná konverze datetime s více formáty včetně timezone"""
    try:
        result = pd.to_datetime(date_series, utc=True, errors='coerce')
        if result.dt.tz is not None:
            result = result.dt.tz_localize(None)
        return result
    except Exception as e:
        try:
            pattern = r'\+\d{2}:\d{2}$'
            cleaned_series = date_series.astype(str).str.replace(pattern, '', regex=True)
            result = pd.to_datetime(cleaned_series, errors='coerce')
            return result
        except Exception as e2:
            try:
                converted = []
                for date_str in date_series:
                    try:
                        if pd.isna(date_str) or date_str == '':
                            converted.append(pd.NaT)
                        else:
                            date_str = str(date_str).strip()
                            if '+' in date_str:
                                date_str = date_str.split('+')[0]
                            elif date_str.endswith('Z'):
                                date_str = date_str[:-1]
                            if '.' in date_str and len(date_str.split('.')[-1]) > 3:
                                date_str = date_str.split('.')[0]
                            converted.append(pd.to_datetime(date_str))
                    except Exception:
                        converted.append(pd.NaT)
                
                return pd.Series(converted)
            except Exception:
                return date_series

@st.cache_data(ttl=300)  # Cache na 5 minut
def load_data_from_onedrive():
    """Načte data z OneDrive"""
    if not ONEDRIVE_DB_URL or ONEDRIVE_DB_URL == "YOUR_ONEDRIVE_DIRECT_LINK_HERE":
        st.error("🔗 OneDrive link není nakonfigurován!")
        st.info("Kontaktujte administrátora pro nastavení přístupu k datům.")
        return pd.DataFrame()
    
    try:
        # Stáhnout databázi z OneDrive
        temp_db_path = download_file_from_onedrive(ONEDRIVE_DB_URL, "tradebook.db3")
        
        if not temp_db_path:
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
        df['exitDate'] = safe_datetime_conversion(df['exitDate'])
        df['entryDate'] = safe_datetime_conversion(df['entryDate'])
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
        
        df['exitDate'] = safe_datetime_conversion(df['exitDate'])
        df['entryDate'] = safe_datetime_conversion(df['entryDate'])
        df['netPL'] = pd.to_numeric(df['netPL'], errors='coerce')
        df = df.dropna(subset=['exitDate', 'netPL'])
        
        return df
        
    except Exception as e:
        st.error(f"Chyba při zpracování nahraného souboru: {e}")
        return pd.DataFrame()

def filter_data_by_time(df, time_filter):
    """Filtruje data podle časového období"""
    if time_filter == "All Time" or df.empty:
        return df
    
    if not pd.api.types.is_datetime64_any_dtype(df['exitDate']):
        st.error("Sloupec exitDate není datetime typ. Zkontrolujte data.")
        return df
    
    now = datetime.now()
    
    try:
        if hasattr(df['exitDate'].dtype, 'tz') and df['exitDate'].dtype.tz is not None:
            df = df.copy()
            df['exitDate'] = df['exitDate'].dt.tz_localize(None)
    except:
        pass
    
    if time_filter == "Kalendářní rok":
        start_date = pd.Timestamp(now.year, 1, 1)
    elif time_filter == "Posledních 12 měsíců":
        start_date = pd.Timestamp(now - timedelta(days=365))
    elif time_filter == "YTD":
        start_date = pd.Timestamp(now.year, 1, 1)
    elif time_filter == "Poslední kalendářní měsíc":
        if now.month == 1:
            start_date = pd.Timestamp(now.year - 1, 12, 1)
            end_date = pd.Timestamp(now.year - 1, 12, 31)
        else:
            start_date = pd.Timestamp(now.year, now.month - 1, 1)
            end_date = pd.Timestamp(now.year, now.month, 1) - timedelta(days=1)
        return df[(df['exitDate'] >= start_date) & (df['exitDate'] <= pd.Timestamp(end_date))]
    elif time_filter == "MTD":
        start_date = pd.Timestamp(now.year, now.month, 1)
    elif time_filter == "Týden":
        start_date = pd.Timestamp(now - timedelta(days=7))
    else:
        return df
    
    try:
        return df[df['exitDate'] >= start_date]
    except Exception as e:
        st.error(f"Chyba při filtrování dat: {e}")
        return df

def calculate_portfolio_metrics(df):
    """Vypočítá portfolio metriky"""
    if df.empty:
        return {}
    
    total_pl = df['netPL'].sum()
    total_pl_percent = (total_pl / INITIAL_CAPITAL) * 100
    total_trades = len(df)
    winning_trades = len(df[df['netPL'] > 0])
    losing_trades = len(df[df['netPL'] < 0])
    win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
    
    avg_win = df[df['netPL'] > 0]['netPL'].mean() if winning_trades > 0 else 0
    avg_loss = df[df['netPL'] < 0]['netPL'].mean() if losing_trades > 0 else 0
    
    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    
    df_sorted = df.sort_values('exitDate')
    df_sorted['cumulative_pl'] = df_sorted['netPL'].cumsum()
    df_sorted['running_max'] = df_sorted['cumulative_pl'].expanding().max()
    df_sorted['drawdown'] = df_sorted['cumulative_pl'] - df_sorted['running_max']
    max_drawdown = df_sorted['drawdown'].min()
    
    return {
        'total_pl': total_pl,
        'total_pl_percent': total_pl_percent,
        'total_capital': INITIAL_CAPITAL + total_pl,
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'losing_trades': losing_trades,
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'max_drawdown': max_drawdown
    }

def calculate_strategy_metrics(df):
    """Vypočítá metriky pro jednotlivé strategie"""
    strategy_metrics = {}
    
    for strategy in df['strategy'].unique():
        strategy_data = df[df['strategy'] == strategy]
        strategy_metrics[strategy] = calculate_portfolio_metrics(strategy_data)
    
    return strategy_metrics

def create_cumulative_pl_chart(df, title="Kumulativní P&L"):
    """Vytvoří graf kumulativního P&L s USD a %"""
    if df.empty:
        return go.Figure()
    
    df_sorted = df.sort_values('exitDate')
    df_sorted['cumulative_pl'] = df_sorted['netPL'].cumsum()
    df_sorted['cumulative_percent'] = (df_sorted['cumulative_pl'] / INITIAL_CAPITAL) * 100
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df_sorted['exitDate'],
        y=df_sorted['cumulative_pl'],
        mode='lines',
        name='P&L (USD)',
        line=dict(color='#1f77b4', width=2),
        yaxis='y'
    ))
    
    fig.add_trace(go.Scatter(
        x=df_sorted['exitDate'],
        y=df_sorted['cumulative_percent'],
        mode='lines',
        name='P&L (%)',
        line=dict(color='#ff7f0e', width=2),
        yaxis='y2'
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Datum",
        yaxis=dict(
            title="Kumulativní P&L (USD)",
            side="left",
            color='#1f77b4'
        ),
        yaxis2=dict(
            title="Kumulativní P&L (%)",
            side="right",
            overlaying="y",
            color='#ff7f0e'
        ),
        hovermode='x unified',
        template='plotly_white',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        height=600
    )
    
    return fig

def create_individual_trades_chart(df, title="Jednotlivé obchody P&L"):
    """Vytvoří graf jednotlivých obchodů"""
    if df.empty:
        return go.Figure()
    
    df_sorted = df.sort_values('exitDate')
    df_sorted['trade_percent'] = (df_sorted['netPL'] / INITIAL_CAPITAL) * 100
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df_sorted['exitDate'],
        y=df_sorted['netPL'],
        mode='lines+markers',
        name='P&L (USD)',
        line=dict(color='#1f77b4', width=2),
        marker=dict(size=4),
        yaxis='y'
    ))
    
    fig.add_trace(go.Scatter(
        x=df_sorted['exitDate'],
        y=df_sorted['trade_percent'],
        mode='lines+markers',
        name='P&L (%)',
        line=dict(color='#ff7f0e', width=2),
        marker=dict(size=4),
        yaxis='y2'
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Datum",
        yaxis=dict(
            title="P&L jednotlivých obchodů (USD)",
            side="left",
            color='#1f77b4'
        ),
        yaxis2=dict(
            title="P&L jednotlivých obchodů (%)",
            side="right",
            overlaying="y",
            color='#ff7f0e'
        ),
        hovermode='x unified',
        template='plotly_white',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        height=600
    )
    
    return fig

def create_strategy_comparison_chart(df):
    """Vytvoří graf porovnání strategií"""
    if df.empty:
        return go.Figure()
    
    strategy_totals = df.groupby('strategy')['netPL'].sum().sort_values(ascending=True)
    
    fig = go.Figure(go.Bar(
        y=strategy_totals.index,
        x=strategy_totals.values,
        orientation='h',
        marker_color=['red' if x < 0 else 'green' for x in strategy_totals.values]
    ))
    
    fig.update_layout(
        title="Celkový P&L podle strategií",
        xaxis_title="P&L (USD)",
        yaxis_title="Strategie",
        template='plotly_white'
    )
    
    return fig

def create_strategy_cumulative_chart(df, strategy):
    """Vytvoří kumulativní graf pro konkrétní strategii"""
    strategy_data = df[df['strategy'] == strategy]
    return create_cumulative_pl_chart(strategy_data, f"Kumulativní P&L - {strategy}")

def create_strategy_individual_chart(df, strategy):
    """Vytvoří graf jednotlivých obchodů pro konkrétní strategii"""
    strategy_data = df[df['strategy'] == strategy]
    return create_individual_trades_chart(strategy_data, f"Jednotlivé obchody - {strategy}")

# Hlavní aplikace
def main():
    st.title("📊 Trading Portfolio Dashboard")
    st.subheader("Analýza výkonnosti trading strategií v reálném čase")
    
    # Sidebar s možnostmi načítání
    st.sidebar.header("📁 Zdroj dat")
    
    data_source = st.sidebar.radio(
        "Vyberte zdroj dat:",
        ["🔗 OneDrive (Automaticky)", "📁 Nahrát soubor"]
    )
    
    df = pd.DataFrame()
    
    if data_source == "🔗 OneDrive (Automaticky)":
        # Automatické načtení z OneDrive
        df = load_data_from_onedrive()
        
        if not df.empty:
            last_update = datetime.now().strftime("%H:%M:%S")
            st.sidebar.success(f"✅ Data načtena z OneDrive\n🕐 Poslední aktualizace: {last_update}")
            
            # Tlačítko pro refresh
            if st.sidebar.button("🔄 Aktualizovat data"):
                st.cache_data.clear()
                st.rerun()
    
    else:
        # Fallback - upload souboru
        st.sidebar.info("💡 Nahrajte svůj tradebook.db3 soubor")
        uploaded_file = st.sidebar.file_uploader(
            "Nahrajte tradebook.db3 soubor:",
            type=['db3', 'db', 'sqlite'],
            help="Nahrajte SQLite databázi s trading daty"
        )
        
        if uploaded_file is not None:
            with st.spinner("Zpracovávám nahraný soubor..."):
                df = load_data_from_uploaded_file(uploaded_file)
    
    if df.empty:
        if data_source == "🔗 OneDrive (Automaticky)":
            st.warning("⚠️ Nepodařilo se načíst data z OneDrive")
            st.info("🔧 **Pro administrátory**: Nakonfigurujte OneDrive linky v kódu")
            
            with st.expander("📋 Konfigurace OneDrive"):
                st.markdown("""
                **Kroky pro nastavení:**
                1. Na OneDrive klikněte pravým na soubor tradebook.db3
                2. Vyberte "Share" → "Copy link"
                3. Nahraďte `YOUR_ONEDRIVE_DIRECT_LINK_HERE` v kódu
                4. Redeploy aplikaci
                """)
        else:
            st.info("📁 Nahrajte soubor tradebook.db3 v postranním panelu")
        
        st.markdown("""
        ### 🚀 Jak používat Trading Dashboard:
        
        **Automatický režim (OneDrive):**
        - Data se načítají automaticky z cloudu
        - Všichni uživatelé vidí stejná data
        - Aktualizace každých 5 minut
        
        **Ruční režim (Upload):**
        - Nahrajte vlastní databázi
        - Soukromá analýza vašich dat
        """)
        return
    
    st.success(f"✅ Data úspěšně načtena! Celkem {len(df)} obchodů ze strategií: {', '.join(df['strategy'].unique())}")
    
    # Debug informace
    with st.expander("🔧 Debug informace"):
        st.write("**Datové typy:**")
        st.write(f"exitDate: {df['exitDate'].dtype}")
        st.write(f"netPL: {df['netPL'].dtype}")
        st.write(f"Datum rozsah: {df['exitDate'].min()} až {df['exitDate'].max()}")
        if len(df) > 0:
            st.write("**Ukázka dat:**")
            st.dataframe(df[['strategy', 'exitDate', 'netPL']].head())
    
    # Sidebar s filtry
    st.sidebar.header("🔧 Nastavení")
    
    time_filter = st.sidebar.selectbox(
        "📅 Časové období:",
        ["All Time", "Kalendářní rok", "Posledních 12 měsíců", "YTD", 
         "Poslední kalendářní měsíc", "MTD", "Týden"]
    )
    
    selected_strategies = st.sidebar.multiselect(
        "📈 Vyberte strategie:",
        options=df['strategy'].unique(),
        default=df['strategy'].unique()
    )
    
    # Filtrování dat
    filtered_df = filter_data_by_time(df, time_filter)
    filtered_df = filtered_df[filtered_df['strategy'].isin(selected_strategies)]
    
    # Hlavní metriky
    col1, col2, col3, col4 = st.columns(4)
    
    metrics = calculate_portfolio_metrics(filtered_df)
    
    with col1:
        st.metric(
            "💰 Total P&L", 
            f"${metrics.get('total_pl', 0):,.2f}",
            delta=f"{metrics.get('total_pl_percent', 0):.2f}%"
        )
    
    with col2:
        st.metric(
            "📊 Celkový kapitál",
            f"${metrics.get('total_capital', INITIAL_CAPITAL):,.2f}"
        )
    
    with col3:
        st.metric(
            "🎯 Win Rate",
            f"{metrics.get('win_rate', 0):.1f}%",
            delta=f"{metrics.get('winning_trades', 0)} / {metrics.get('total_trades', 0)}"
        )
    
    with col4:
        st.metric(
            "📉 Max Drawdown",
            f"${metrics.get('max_drawdown', 0):,.2f}"
        )
    
    # Záložky
    tab1, tab2, tab3 = st.tabs(["🏦 Portfolio Overview", "📈 Strategie", "📊 Grafy"])
    
    with tab1:
        st.subheader("Portfolio Performance")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Trading Statistics")
            st.write(f"**Celkem obchodů:** {metrics.get('total_trades', 0)}")
            st.write(f"**Winning trades:** {metrics.get('winning_trades', 0)}")
            st.write(f"**Losing trades:** {metrics.get('losing_trades', 0)}")
            st.write(f"**Win Rate:** {metrics.get('win_rate', 0):.2f}%")
        
        with col2:
            st.subheader("⚖️ Risk Metrics")
            st.write(f"**Průměrný zisk:** ${metrics.get('avg_win', 0):.2f}")
            st.write(f"**Průměrná ztráta:** ${metrics.get('avg_loss', 0):.2f}")
            st.write(f"**Profit Factor:** {metrics.get('profit_factor', 0):.2f}")
            st.write(f"**Max Drawdown:** ${metrics.get('max_drawdown', 0):.2f}")
        
        # Grafy
        st.subheader("📈 Kumulativní P&L (USD + %)")
        fig1 = create_cumulative_pl_chart(filtered_df)
        st.plotly_chart(fig1, use_container_width=True, key="portfolio_cumulative_chart")
        
        st.subheader("📊 Jednotlivé obchody P&L (USD + %)")
        fig2 = create_individual_trades_chart(filtered_df)
        st.plotly_chart(fig2, use_container_width=True, key="portfolio_individual_chart")
    
    with tab2:
        st.subheader("Výkonnost jednotlivých strategií")
        
        strategy_metrics = calculate_strategy_metrics(filtered_df)
        
        strategy_summary = []
        for strategy, metrics in strategy_metrics.items():
            strategy_summary.append({
                'Strategie': strategy,
                'P&L (USD)': f"${metrics['total_pl']:,.2f}",
                'P&L (%)': f"{metrics['total_pl_percent']:.2f}%",
                'Obchody': metrics['total_trades'],
                'Win Rate': f"{metrics['win_rate']:.1f}%",
                'Profit Factor': f"{metrics['profit_factor']:.2f}"
            })
        
        strategy_df = pd.DataFrame(strategy_summary)
        st.dataframe(strategy_df, use_container_width=True)
        
        st.subheader("📊 Porovnání strategií")
        fig = create_strategy_comparison_chart(filtered_df)
        st.plotly_chart(fig, use_container_width=True, key="strategy_comparison_chart")
    
    with tab3:
        st.subheader("Grafy pro jednotlivé strategie")
        
        for i, strategy in enumerate(selected_strategies):
            st.subheader(f"📈 {strategy}")
            
            st.write("**Kumulativní P&L:**")
            fig1 = create_strategy_cumulative_chart(filtered_df, strategy)
            st.plotly_chart(fig1, use_container_width=True, key=f"strategy_cumulative_{i}_{strategy}")
            
            st.write("**Jednotlivé obchody:**")
            fig2 = create_strategy_individual_chart(filtered_df, strategy)
            st.plotly_chart(fig2, use_container_width=True, key=f"strategy_individual_{i}_{strategy}")
            
            if strategy != selected_strategies[-1]:
                st.markdown("---")
    
    # Footer
    st.sidebar.markdown("---")
    st.sidebar.info(f"📊 Dashboard pro analýzu {len(df)} obchodů")
    st.sidebar.info(f"💰 Počáteční kapitál: ${INITIAL_CAPITAL:,}")
    
    if data_source == "🔗 OneDrive (Automaticky)":
        st.sidebar.info("🔄 Data se aktualizují každých 5 minut")

if __name__ == "__main__":
    main()