"""
Trading Portfolio Dashboard - Hybrid Solution
============================================
SQLite z Google Drive + Excel z OneDrive
Nejspolehlivější kombinace!
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

# URLs - hybrid solution
EXCEL_ONEDRIVE_URL = "https://1drv.ms/x/c/1E57DA124B7D1AC2/EclafUsS2lcggB6gUwiAAAABuX9tM0jgj1UUoSBDHmp_FA?e=SYk93C&download=1"
INITIAL_CAPITAL = 50000

# Session state
if 'sqlite_file_id' not in st.session_state:
    st.session_state.sqlite_file_id = "1lJOenIKGQYGa9eyIkwJGldNOltuK31Kw"  # Z předchozího testu

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
        st.error(f"Chyba při stahování {file_type} z Google Drive: {e}")
        return None

def load_sqlite_from_google_drive(file_id):
    """Načte SQLite z Google Drive"""
    try:
        with st.spinner("Načítám SQLite z Google Drive..."):
            sqlite_content = download_from_google_drive(file_id, "SQLite")
            
            if not sqlite_content or not sqlite_content.startswith(b'SQLite format 3'):
                st.error("❌ Neplatný SQLite soubor z Google Drive")
                return pd.DataFrame()
            
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
            st.success(f"✅ SQLite (Google Drive): {len(df)} záznamů")
            return df
            
    except Exception as e:
        st.error(f"Chyba při zpracování SQLite z Google Drive: {e}")
        return pd.DataFrame()

def load_excel_from_onedrive():
    """Načte Excel z OneDrive"""
    try:
        with st.spinner("Načítám Excel z OneDrive..."):
            response = requests.get(EXCEL_ONEDRIVE_URL, stream=True, timeout=30)
            response.raise_for_status()
            
            if response.content.startswith(b'<!DOCTYPE') or b'<html' in response.content[:500]:
                st.error("❌ Excel: OneDrive vrací HTML místo souboru")
                return pd.DataFrame()
            
            # Načíst Excel z bytes
            excel_file = io.BytesIO(response.content)
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
            
            st.success(f"✅ Excel (OneDrive): {len(combined_data)} záznamů")
            return combined_data
            
    except Exception as e:
        st.error(f"Chyba při načítání Excel z OneDrive: {e}")
        return pd.DataFrame()

def convert_dates(date_series):
    """Konverze datumů"""
    try:
        result = pd.to_datetime(date_series, errors='coerce', utc=True)
        if hasattr(result.dtype, 'tz') and result.dtype.tz is not None:
            result = result.dt.tz_localize(None)
        return result
    except:
        return pd.to_datetime(date_series, errors='coerce')

@st.cache_data
def load_combined_data(sqlite_file_id):
    """Načte a spojí data z obou zdrojů - OPRAVENÁ LOGIKA"""
    all_data = pd.DataFrame()
    
    # SQLite z Google Drive
    if sqlite_file_id:
        st.write("🔄 Načítám SQLite z Google Drive...")
        sqlite_df = load_sqlite_from_google_drive(sqlite_file_id)
        if not sqlite_df.empty:
            all_data = pd.concat([all_data, sqlite_df], ignore_index=True)
    
    # Excel z OneDrive (POZOR: ne z Google Drive!)
    st.write("🔄 Načítám Excel z OneDrive...")
    excel_df = load_excel_from_onedrive()  # SPRÁVNÁ FUNKCE
    if not excel_df.empty:
        all_data = pd.concat([all_data, excel_df], ignore_index=True)
    
    if all_data.empty:
        return pd.DataFrame()
    
    # Zpracování dat
    all_data['exitDate'] = convert_dates(all_data['exitDate'])
    if 'entryDate' in all_data.columns:
        all_data['entryDate'] = convert_dates(all_data['entryDate'])
    
    all_data['netPL'] = pd.to_numeric(all_data['netPL'], errors='coerce')
    all_data = all_data.dropna(subset=['exitDate', 'netPL', 'strategy'])
    
    # Odstranit duplikáty (pokud jsou stejné obchody v obou souborech)
    all_data = all_data.drop_duplicates(subset=['strategy', 'exitDate', 'netPL'], keep='first')
    
    all_data = all_data.sort_values('exitDate')
    
    return all_data

def calc_metrics(df):
    """Výpočet základních metrik"""
    if df.empty:
        return {}
    
    total_pl = df['netPL'].sum()
    total_trades = len(df)
    wins = len(df[df['netPL'] > 0])
    losses = len(df[df['netPL'] < 0])
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    
    avg_win = df[df['netPL'] > 0]['netPL'].mean() if wins > 0 else 0
    avg_loss = df[df['netPL'] < 0]['netPL'].mean() if losses > 0 else 0
    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    
    # Drawdown
    df_sorted = df.sort_values('exitDate')
    df_sorted['cum_pl'] = df_sorted['netPL'].cumsum()
    df_sorted['running_max'] = df_sorted['cum_pl'].expanding().max()
    df_sorted['dd'] = df_sorted['cum_pl'] - df_sorted['running_max']
    max_dd = df_sorted['dd'].min()
    
    return {
        'total_pl': total_pl,
        'total_pl_percent': (total_pl / INITIAL_CAPITAL) * 100,
        'total_capital': INITIAL_CAPITAL + total_pl,
        'total_trades': total_trades,
        'winning_trades': wins,
        'losing_trades': losses,
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'max_drawdown': max_dd
    }

def create_cumulative_chart(df, title="Kumulativní P&L"):
    """Graf kumulativního P&L"""
    if df.empty:
        return go.Figure()
    
    df_sorted = df.sort_values('exitDate')
    df_sorted['cum_pl'] = df_sorted['netPL'].cumsum()
    df_sorted['cum_pct'] = (df_sorted['cum_pl'] / INITIAL_CAPITAL) * 100
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df_sorted['exitDate'],
        y=df_sorted['cum_pl'],
        mode='lines',
        name='P&L (USD)',
        line=dict(color='blue', width=2),
        yaxis='y'
    ))
    
    fig.add_trace(go.Scatter(
        x=df_sorted['exitDate'],
        y=df_sorted['cum_pct'],
        mode='lines',
        name='P&L (%)',
        line=dict(color='orange', width=2),
        yaxis='y2'
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Datum",
        yaxis=dict(title="P&L (USD)", side="left", color="blue"),
        yaxis2=dict(title="P&L (%)", side="right", overlaying="y", color="orange"),
        hovermode='x unified',
        height=600
    )
    
    return fig

def create_individual_chart(df, title="Jednotlivé obchody"):
    """Graf jednotlivých obchodů"""
    if df.empty:
        return go.Figure()
    
    df_sorted = df.sort_values('exitDate')
    df_sorted['trade_pct'] = (df_sorted['netPL'] / INITIAL_CAPITAL) * 100
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df_sorted['exitDate'],
        y=df_sorted['netPL'],
        mode='lines+markers',
        name='P&L (USD)',
        line=dict(color='blue'),
        marker=dict(size=4),
        yaxis='y'
    ))
    
    fig.add_trace(go.Scatter(
        x=df_sorted['exitDate'],
        y=df_sorted['trade_pct'],
        mode='lines+markers',
        name='P&L (%)',
        line=dict(color='orange'),
        marker=dict(size=4),
        yaxis='y2'
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Datum",
        yaxis=dict(title="P&L (USD)", side="left", color="blue"),
        yaxis2=dict(title="P&L (%)", side="right", overlaying="y", color="orange"),
        hovermode='x unified',
        height=600
    )
    
    return fig

def create_monthly_heatmap(df, title="Heat mapa měsíční výkonnosti"):
    """Vytvoří heat mapu výkonnosti podle měsíců a let"""
    if df.empty:
        return go.Figure()
    
    # Příprava dat - agregace podle roku a měsíce
    df_copy = df.copy()
    df_copy['year'] = df_copy['exitDate'].dt.year
    df_copy['month'] = df_copy['exitDate'].dt.month
    
    # Agregace P&L podle roku a měsíce
    monthly_data = df_copy.groupby(['year', 'month'])['netPL'].sum().reset_index()
    
    # Vytvoření pivot tabulky pro heat mapu
    pivot_data = monthly_data.pivot(index='year', columns='month', values='netPL')
    
    # Doplnění chybějících měsíců nulami
    for month in range(1, 13):
        if month not in pivot_data.columns:
            pivot_data[month] = 0
    
    # Seřazení sloupců (měsíců)
    pivot_data = pivot_data.reindex(columns=sorted(pivot_data.columns))
    
    # Doplnění NaN hodnot nulami
    pivot_data = pivot_data.fillna(0)
    
    # Názvy měsíců pro osu X
    month_names = ['Led', 'Úno', 'Bře', 'Dub', 'Kvě', 'Čer', 
                   'Čvc', 'Srp', 'Zář', 'Říj', 'Lis', 'Pro']
    
    # Vytvoření heat mapy
    fig = go.Figure(data=go.Heatmap(
        z=pivot_data.values,
        x=month_names,
        y=pivot_data.index,
        colorscale=[
            [0, 'darkred'],
            [0.25, 'red'], 
            [0.4, 'lightcoral'],
            [0.5, 'white'],
            [0.6, 'lightgreen'],
            [0.75, 'green'],
            [1, 'darkgreen']
        ],
        zmid=0,
        colorbar=dict(title="P&L (USD)"),
        hovertemplate='<b>%{y}</b><br>' +
                      'Měsíc: %{x}<br>' +
                      'P&L: $%{z:,.0f}<br>' +
                      '<extra></extra>',
        text=[[f"${val:,.0f}" if val != 0 else "" for val in row] for row in pivot_data.values],
        texttemplate="%{text}",
        textfont={"size": 10},
        showscale=True
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Měsíc",
        yaxis_title="Rok",
        height=400,
        template='plotly_white',
        font=dict(size=12)
    )
    
    return fig

def create_strategy_chart(df):
    """Vytvoří graf porovnání strategií"""
    if df.empty:
        return go.Figure()
    
    totals = df.groupby('strategy')['netPL'].sum().sort_values(ascending=True)
    
    fig = go.Figure(go.Bar(
        y=totals.index,
        x=totals.values,
        orientation='h',
        marker_color=['red' if x < 0 else 'green' for x in totals.values]
    ))
    
    fig.update_layout(
        title="P&L podle strategií",
        xaxis_title="P&L (USD)",
        yaxis_title="Strategie"
    )
    
    return fig

def filter_by_time(df, time_filter):
    """Základní časový filtr"""
    if time_filter == "All Time" or df.empty:
        return df
    
    now = datetime.now()
    
    if time_filter == "YTD":
        start_date = pd.Timestamp(now.year, 1, 1)
    elif time_filter == "Posledních 12 měsíců":
        start_date = pd.Timestamp(now - timedelta(days=365))
    elif time_filter == "Posledních 6 měsíců":
        start_date = pd.Timestamp(now - timedelta(days=180))
    elif time_filter == "Poslední 3 měsíce":
        start_date = pd.Timestamp(now - timedelta(days=90))
    elif time_filter == "MTD":
        start_date = pd.Timestamp(now.year, now.month, 1)
    elif time_filter == "Týden":
        start_date = pd.Timestamp(now - timedelta(days=7))
    else:
        return df
    
    return df[df['exitDate'] >= start_date]

# HLAVNÍ APLIKACE
def main():
    st.title("📊 Trading Portfolio Dashboard")
    st.subheader("🎯 Hybrid Solution: SQLite (Google Drive) + Excel (OneDrive)")
    
    st.info("💡 **Nejspolehlivější řešení**: SQLite z Google Drive + Excel z OneDrive")
    
    # Status overview
    col1, col2 = st.columns(2)
    
    with col1:
        st.success("✅ **Excel z OneDrive**")
        st.write("Automaticky nakonfigurován")
        st.code("portfolio_k_30012024_new.xlsx")
    
    with col2:
        if st.session_state.sqlite_file_id and st.session_state.sqlite_file_id != "":
            st.success("✅ **SQLite z Google Drive**")
            st.code(f"File ID: {st.session_state.sqlite_file_id}")
        else:
            st.warning("⚠️ **SQLite z Google Drive**")
            st.write("Potřeba nakonfigurovat")
    
    # Konfigurace SQLite (pokud není nastaveno)
    if not st.session_state.sqlite_file_id or st.session_state.sqlite_file_id == "":
        st.header("🔧 Konfigurace SQLite (Google Drive)")
        
        with st.expander("📋 Jak získat Google Drive File ID", expanded=True):
            st.markdown("""
            **Postup:**
            1. **Nahrajte** `tradebook.db3` na Google Drive
            2. **Pravý klik** → "Get link" 
            3. **Změňte na** "Anyone with the link can view"
            4. **Zkopírujte link** - vypadá takto:
               ```
               https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs/view
               ```
            5. **File ID** je část mezi `/d/` a `/view`: `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs`
            """)
        
        sqlite_input = st.text_area(
            "Vložte Google Drive link nebo File ID pro SQLite:",
            placeholder="https://drive.google.com/file/d/1BxiMVs... nebo jen File ID",
            height=100,
            key="sqlite_setup_input"
        )
        
        if sqlite_input:
            extracted_id = extract_google_drive_id(sqlite_input)
            new_id = extracted_id if extracted_id else sqlite_input.strip()
            
            if new_id != st.session_state.sqlite_file_id:
                st.session_state.sqlite_file_id = new_id
                st.success(f"✅ SQLite File ID uložen: `{new_id}`")
                st.rerun()
    
    # Načtení dat
    if st.session_state.sqlite_file_id:
        st.header("📊 Dashboard")
        
        if st.button("🚀 Načíst data z obou zdrojů", type="primary"):
            st.info("📊 **Hybrid načítání**: SQLite (Google Drive) + Excel (OneDrive)")
            
            with st.container():
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("🔄 **Zdroj 1: SQLite z Google Drive**")
                    st.code(f"File ID: {st.session_state.sqlite_file_id}")
                
                with col2:
                    st.write("🔄 **Zdroj 2: Excel z OneDrive**")
                    st.code("OneDrive URL (automaticky)")
            
            df = load_combined_data(st.session_state.sqlite_file_id)
            
            if df.empty:
                st.error("❌ Nepodařilo se načíst žádná data")
                st.info("💡 Zkontrolujte Google Drive File ID a OneDrive přístup")
                return
            
            # Success
            msg = f"✅ Načteno {len(df)} obchodů"
            if 'source' in df.columns:
                counts = df['source'].value_counts()
                info = " | ".join([f"{k}: {v}" for k, v in counts.items()])
                msg += f" | {info}"
            st.success(msg)
            
            # Sidebar filtry
            st.sidebar.header("🔧 Filtry")
            
            time_filter = st.sidebar.selectbox(
                "📅 Období:",
                ["All Time", "YTD", "Posledních 12 měsíců", "Posledních 6 měsíců", 
                 "Poslední 3 měsíce", "MTD", "Týden"],
                key="time_filter_hybrid"
            )
            
            strategies = st.sidebar.multiselect(
                "📈 Strategie:",
                options=df['strategy'].unique(),
                default=df['strategy'].unique(),
                key="strategies_hybrid"
            )
            
            # Filtrování
            filtered_df = filter_by_time(df, time_filter)
            filtered_df = filtered_df[filtered_df['strategy'].isin(strategies)]
            
            # Základní metriky
            metrics = calc_metrics(filtered_df)
            
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                st.metric("💰 Total P&L", f"${metrics.get('total_pl', 0):,.2f}")
            
            with col2:
                st.metric(
                    "📈 Výkonnost",
                    f"{metrics.get('total_pl_percent', 0):.2f}%"
                )
            
            with col3:
                st.metric("📊 Kapitál", f"${metrics.get('total_capital', INITIAL_CAPITAL):,.2f}")
            
            with col4:
                st.metric(
                    "🎯 Win Rate",
                    f"{metrics.get('win_rate', 0):.1f}%",
                    delta=f"{metrics.get('winning_trades', 0)}/{metrics.get('total_trades', 0)}"
                )
            
            with col5:
                st.metric("📉 Max DD", f"${metrics.get('max_drawdown', 0):,.2f}")
            
            # Tab organizace
            tab1, tab2, tab3 = st.tabs(["📊 Overview", "📈 Strategie", "🔥 Heat Mapy"])
            
            with tab1:
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**Trading Stats:**")
                    st.write(f"Celkem obchodů: {metrics.get('total_trades', 0)}")
                    st.write(f"Vítězné: {metrics.get('winning_trades', 0)}")
                    st.write(f"Ztrátové: {metrics.get('losing_trades', 0)}")
                    st.write(f"Win Rate: {metrics.get('win_rate', 0):.2f}%")
                
                with col2:
                    st.write("**Risk Metrics:**")
                    st.write(f"Průměrný zisk: ${metrics.get('avg_win', 0):.2f}")
                    st.write(f"Průměrná ztráta: ${metrics.get('avg_loss', 0):.2f}")
                    st.write(f"Profit Factor: {metrics.get('profit_factor', 0):.2f}")
                    st.write(f"Max Drawdown: ${metrics.get('max_drawdown', 0):.2f}")
                
                st.plotly_chart(create_cumulative_chart(filtered_df), use_container_width=True, key="hybrid_cumulative")
                st.plotly_chart(create_individual_chart(filtered_df), use_container_width=True, key="hybrid_individual")
            
            with tab2:
                # Tabulka strategií
                strategy_data = []
                for strategy in filtered_df['strategy'].unique():
                    strat_df = filtered_df[filtered_df['strategy'] == strategy]
                    strat_metrics = calc_metrics(strat_df)
                    strategy_data.append({
                        'Strategie': strategy,
                        'P&L (USD)': f"${strat_metrics['total_pl']:,.2f}",
                        'P&L (%)': f"{strat_metrics['total_pl_percent']:.2f}%",
                        'Obchody': strat_metrics['total_trades'],
                        'Win Rate': f"{strat_metrics['win_rate']:.1f}%",
                        'Profit Factor': f"{strat_metrics['profit_factor']:.2f}"
                    })
                
                st.dataframe(pd.DataFrame(strategy_data), use_container_width=True)
                st.plotly_chart(create_strategy_chart(filtered_df), use_container_width=True, key="hybrid_strategy")
            
            with tab3:
                st.plotly_chart(create_monthly_heatmap(filtered_df), use_container_width=True, key="hybrid_heatmap")
            
            # Debug
            with st.expander("🔧 Debug"):
                if 'source' in df.columns:
                    st.write("**Zdroje:**")
                    for source, count in df['source'].value_counts().items():
                        st.write(f"- {source}: {count}")
                
                st.dataframe(df[['strategy', 'exitDate', 'netPL', 'source']].head(10))
        
        # Footer
        st.sidebar.markdown("---")
        st.sidebar.info("🎯 Hybrid Solution")
        st.sidebar.info("📊 SQLite (Google Drive)")
        st.sidebar.info("📈 Excel (OneDrive)")
        
        # Refresh tlačítko
        if st.sidebar.button("🔄 Aktualizovat data"):
            st.cache_data.clear()
            st.rerun()

if __name__ == "__main__":
    main()
