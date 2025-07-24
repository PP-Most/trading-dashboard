"""
Trading Portfolio Dashboard - Combined Sources
=============================================
Analýza výkonnosti trading strategií z SQLite + Excel

Instalace: pip install streamlit pandas plotly openpyxl
Spuštění: streamlit run trading_dashboard.py
"""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os

# Konfigurace
st.set_page_config(
    page_title="Trading Portfolio Dashboard",
    page_icon="📊",
    layout="wide"
)

# Cesty k souborům
DB_PATH = r"C:\Users\ppola\OneDrive\Komoditni_trhy\Autotrader_LIVE\data\tradebook.db3"
EXCEL_PATH = r"C:\Users\ppola\OneDrive\Komoditni_trhy\Autotrader_LIVE\data\portfolio_k_30012024_new.xlsx"
INITIAL_CAPITAL = 50000

def convert_to_date_only(date_series):
    """Konverze datetime na datum bez času - s filtrováním neplatných dat"""
    print(f"\n=== KONVERZE DATUMŮ ===")
    print(f"Celkem řádků k zpracování: {len(date_series)}")
    print(f"Ukázka původních hodnot: {date_series.head().tolist()}")
    
    # Předčištění dat - odstranění timezone před konverzí
    cleaned_series = date_series.copy()
    
    # Konverze na string a čištění timezone značek
    cleaned_values = []
    problematic_found = []
    
    for i, val in enumerate(cleaned_series):
        try:
            if pd.isna(val) or val == '' or str(val).strip() == '':
                cleaned_values.append(None)
                continue
                
            date_str = str(val).strip()
            
            # Detekce roku 1900 - problematické data
            if '1900-' in date_str:
                print(f"ODSTRAŇUJI problematické datum roku 1900 v řádku {i}: '{date_str}'")
                problematic_found.append((i, date_str))
                cleaned_values.append(None)
                continue
            
            # Odstranění timezone značek
            if '+' in date_str:
                date_str = date_str.split('+')[0]
            elif '-' in date_str and date_str.count('-') > 2:  # Má timezone s minus
                parts = date_str.split('-')
                if len(parts) > 3:  # YYYY-MM-DD-HH:MM nebo podobné
                    date_str = '-'.join(parts[:3])  # Zachovat jen YYYY-MM-DD
            if date_str.endswith('Z'):
                date_str = date_str[:-1]
            
            # Odstranit čas - vzít jen datum část
            if ' ' in date_str:
                date_str = date_str.split(' ')[0]
            
            cleaned_values.append(date_str)
            
        except Exception as e:
            print(f"Chyba při čištění řádku {i}: '{val}' -> {e}")
            problematic_found.append((i, val))
            cleaned_values.append(None)
    
    print(f"Předčištění dokončeno. Problematických řádků: {len(problematic_found)}")
    
    # Nyní konverze vyčištěných dat
    try:
        # Konverze s UTC=True pro potlačení timezone warning
        result = pd.to_datetime(cleaned_values, errors='coerce', utc=True)
        
        # Odstranit timezone a převést na lokální čas
        if hasattr(result.dtype, 'tz') and result.dtype.tz is not None:
            result = result.dt.tz_localize(None)
        
        # Převést na datum pouze (odstranit čas)
        result = result.dt.date
        result = pd.to_datetime(result, errors='coerce')
        
        # Filtrovat data mimo rozumný rozsah (2020-2030)
        date_range_mask = (result >= pd.Timestamp('2020-01-01')) & (result <= pd.Timestamp('2030-12-31'))
        result = result.where(date_range_mask, pd.NaT)
        
        valid_count = result.notna().sum()
        print(f"Konverze dokončena. Platných datumů: {valid_count}/{len(result)}")
        if valid_count > 0:
            print(f"Rozsah datumů: {result.min()} až {result.max()}")
        
        return result
        
    except Exception as e:
        print(f"Chyba v konverzi datumů: {e}")
        print("Spouštím manuální fallback...")
        
        # Manuální fallback
        final_dates = []
        for i, cleaned_val in enumerate(cleaned_values):
            try:
                if cleaned_val is None or cleaned_val == '':
                    final_dates.append(pd.NaT)
                else:
                    # Pokus o manuální parsování
                    parsed = pd.to_datetime(cleaned_val, errors='coerce')
                    
                    # Kontrola platnosti
                    if (pd.notna(parsed) and 
                        pd.Timestamp('2020-01-01') <= parsed <= pd.Timestamp('2030-12-31')):
                        final_dates.append(parsed.date())
                    else:
                        final_dates.append(pd.NaT)
                        
            except Exception:
                final_dates.append(pd.NaT)
        
        result = pd.Series([pd.to_datetime(d) if pd.notna(d) else pd.NaT for d in final_dates])
        valid_count = result.notna().sum()
        print(f"Fallback konverze dokončena. Platných datumů: {valid_count}/{len(result)}")
        
        return result

@st.cache_data
def load_combined_data():
    """Načte a spojí data z obou zdrojů"""
    all_data = pd.DataFrame()
    
    # SQLite data
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT strategy, exitDate, "NetP/L" as netPL, entryDate, ticker, 
               quantity, entryPrice, exitPrice, commission
        FROM diary 
        WHERE exitDate IS NOT NULL AND "NetP/L" IS NOT NULL AND strategy IS NOT NULL
        ORDER BY exitDate
        """
        df_sql = pd.read_sql_query(query, conn)
        conn.close()
        
        if len(df_sql) > 0:
            df_sql['source'] = 'SQLite'
            all_data = pd.concat([all_data, df_sql], ignore_index=True)
        print(f"SQLite data: {len(df_sql)} řádků")
        
    except Exception as e:
        print(f"SQLite error: {e}")
    
    # Excel data - všechny sheets
    try:
        if os.path.exists(EXCEL_PATH):
            print(f"Excel soubor nalezen: {EXCEL_PATH}")
            
            # Načtení všech sheets
            excel_file = pd.ExcelFile(EXCEL_PATH)
            sheet_names = excel_file.sheet_names
            print(f"Nalezeno {len(sheet_names)} sheets: {sheet_names}")
            
            excel_data_combined = pd.DataFrame()
            
            for sheet_name in sheet_names:
                try:
                    print(f"\nZpracovávám sheet: {sheet_name}")
                    df_sheet = pd.read_excel(EXCEL_PATH, sheet_name=sheet_name)
                    print(f"Sheet {sheet_name}: {len(df_sheet)} řádků")
                    
                    if len(df_sheet) == 0:
                        print(f"Sheet {sheet_name} je prázdný, přeskakuji")
                        continue
                    
                    print(f"Sloupce v {sheet_name}: {df_sheet.columns.tolist()}")
                    
                    # Map columns pro každý sheet
                    col_map = {}
                    for col in df_sheet.columns:
                        if col == 'Systém':
                            col_map[col] = 'strategy'
                        elif col == 'Symbol':
                            col_map[col] = 'ticker'
                        elif col == 'Typ':
                            col_map[col] = 'possition'
                        elif col == 'Datum':
                            col_map[col] = 'entryDate'
                        elif col == 'Datum.1':
                            col_map[col] = 'exitDate'
                        elif col == 'Počet':
                            col_map[col] = 'quantity'
                        elif col == 'Cena':
                            col_map[col] = 'entryPrice'
                        elif col == 'Cena.1':
                            col_map[col] = 'exitPrice'
                        elif col == '% změna':
                            col_map[col] = 'chg_percent'
                        elif col == 'Komise':
                            col_map[col] = 'commission'
                        elif col == 'Profit/Loss':
                            col_map[col] = 'netPL'
                    
                    print(f"Mapování pro {sheet_name}: {col_map}")
                    df_sheet = df_sheet.rename(columns=col_map)
                    
                    # Kontrola povinných sloupců
                    required_cols = ['strategy', 'exitDate', 'netPL']
                    missing_cols = [col for col in required_cols if col not in df_sheet.columns]
                    
                    if len(missing_cols) == 0:
                        print(f"Sheet {sheet_name}: DATA PŘIJATA - všechny povinné sloupce nalezeny")
                        df_sheet['source'] = f'Excel-{sheet_name}'
                        df_sheet['sheet_name'] = sheet_name
                        excel_data_combined = pd.concat([excel_data_combined, df_sheet], ignore_index=True)
                        print(f"Sheet {sheet_name}: přidáno {len(df_sheet)} řádků")
                    else:
                        print(f"Sheet {sheet_name}: DATA ZAMÍTNUTA - chybí sloupce: {missing_cols}")
                
                except Exception as sheet_error:
                    print(f"Chyba při zpracování sheet {sheet_name}: {sheet_error}")
            
            # Přidání všech Excel dat
            if len(excel_data_combined) > 0:
                all_data = pd.concat([all_data, excel_data_combined], ignore_index=True)
                print(f"\nCELKEM z Excelu přidáno: {len(excel_data_combined)} řádků ze {len(sheet_names)} sheets")
            else:
                print("\nŽádná data z Excel sheets nebyla přijata")
            
        else:
            print(f"Excel soubor NENALEZEN: {EXCEL_PATH}")
        
    except Exception as e:
        print(f"Excel error: {e}")
        import traceback
        print(traceback.format_exc())
    
    if all_data.empty:
        return pd.DataFrame()
    
    # Process data - konverze datumů a čištění
    print(f"\nZpracovávám kombinovaná data: {len(all_data)} řádků")
    all_data['exitDate'] = convert_to_date_only(all_data['exitDate'])
    if 'entryDate' in all_data.columns:
        all_data['entryDate'] = convert_to_date_only(all_data['entryDate'])

    all_data['netPL'] = pd.to_numeric(all_data['netPL'], errors='coerce')
    
    # Odstranění řádků s neplatnými daty
    original_count = len(all_data)
    all_data = all_data.dropna(subset=['exitDate', 'netPL', 'strategy'])
    
    # Dodatečné filtrování datumů (jen pro jistotu)
    all_data = all_data[
        (all_data['exitDate'] >= pd.Timestamp('2020-01-01')) & 
        (all_data['exitDate'] <= pd.Timestamp('2030-12-31'))
    ]
    
    final_count = len(all_data)
    print(f"Po čištění a filtrování: {final_count} řádků (odstraněno {original_count - final_count})")
    
    all_data = all_data.sort_values('exitDate')
    
    if final_count > 0:
        print(f"Finální rozsah datumů: {all_data['exitDate'].min()} až {all_data['exitDate'].max()}")
    
    return all_data

def filter_by_time(df, time_filter, start_date=None, end_date=None):
    """Filtruje data podle času"""
    if time_filter == "All Time" or df.empty:
        return df
    
    now = datetime.now()
    
    if time_filter == "Vlastní období (OD-DO)":
        if start_date and end_date:
            start_ts = pd.Timestamp(start_date)
            end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            return df[(df['exitDate'] >= start_ts) & (df['exitDate'] <= end_ts)]
        return df
    elif time_filter == "YTD":
        start_ts = pd.Timestamp(now.year, 1, 1)
    elif time_filter == "Kalendářní rok":
        start_ts = pd.Timestamp(now.year, 1, 1)
    elif time_filter == "Poslední kalendářní rok":
        start_ts = pd.Timestamp(now.year - 1, 1, 1)
        end_ts = pd.Timestamp(now.year - 1, 12, 31)
        return df[(df['exitDate'] >= start_ts) & (df['exitDate'] <= end_ts)]
    elif time_filter == "Posledních 12 měsíců":
        start_ts = pd.Timestamp(now - timedelta(days=365))
    elif time_filter == "Posledních 6 měsíců":
        start_ts = pd.Timestamp(now - timedelta(days=180))
    elif time_filter == "Poslední 3 měsíce":
        start_ts = pd.Timestamp(now - timedelta(days=90))
    elif time_filter == "Posledních 30 dní":
        start_ts = pd.Timestamp(now - timedelta(days=30))
    elif time_filter == "MTD":
        start_ts = pd.Timestamp(now.year, now.month, 1)
    elif time_filter == "Týden":
        start_ts = pd.Timestamp(now - timedelta(days=7))
    else:
        return df
    
    return df[df['exitDate'] >= start_ts]

def calc_metrics(df):
    """Výpočet portfolio metrik"""
    if df.empty:
        return {}
    
    total_pl = df['netPL'].sum()
    total_pl_pct = (total_pl / INITIAL_CAPITAL) * 100
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
        'total_pl_percent': total_pl_pct,
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
        yaxis='y'
    ))
    
    fig.add_trace(go.Scatter(
        x=df_sorted['exitDate'],
        y=df_sorted['trade_pct'],
        mode='lines+markers',
        name='P&L (%)',
        line=dict(color='orange'),
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

def create_strategy_monthly_heatmap(df, title="Heat mapa strategií podle měsíců"):
    """Vytvoří heat mapu výkonnosti strategií podle měsíců"""
    if df.empty:
        return go.Figure()
    
    # Příprava dat - agregace podle strategie a měsíce
    df_copy = df.copy()
    df_copy['month'] = df_copy['exitDate'].dt.month
    
    # Agregace P&L podle strategie a měsíce
    strategy_monthly = df_copy.groupby(['strategy', 'month'])['netPL'].sum().reset_index()
    
    # Vytvoření pivot tabulky pro heat mapu
    pivot_data = strategy_monthly.pivot(index='strategy', columns='month', values='netPL')
    
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
        textfont={"size": 9},
        showscale=True
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Měsíc",
        yaxis_title="Strategie",
        height=max(400, len(pivot_data.index) * 40),  # Dynamická výška podle počtu strategií
        template='plotly_white',
        font=dict(size=12)
    )
    
    return fig
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
        zmid=0,  # Středová hodnota pro barevné schéma
        colorbar=dict(
            title="P&L (USD)"
        ),
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
    """Graf porovnání strategií"""
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

def show_help():
    """Nápověda k metrikám"""
    with st.expander("ℹ️ Vysvětlení metrik"):
        st.markdown("""
        **💰 Total P&L:** Součet všech P&L z obchodů
        
        **📈 Kumulativní výkonnost:** (Total P&L / 50,000) × 100
        
        **📊 Celkový kapitál:** 50,000 + Total P&L
        
        **🎯 Win Rate:** (Vítězné obchody / Celkem obchodů) × 100
        
        **⚖️ Profit Factor:** |Průměrný zisk / Průměrná ztráta|
        
        **📉 Max Drawdown:** Největší pokles od vrcholu
        
        **🔥 Heat mapa:** Vizualizace měsíční výkonnosti podle let a měsíců
        - 🟢 Zelená = Pozitivní výkonnost v daném měsíci
        - 🔴 Červená = Negativní výkonnost v daném měsíci
        - ⚪ Bílá = Žádné obchody nebo nulový P&L
        """)
        
    with st.expander("📊 Jak číst heat mapy"):
        st.markdown("""
        **🔥 Heat mapa měsíční výkonnosti** - celkový přehled:
        
        📅 **Osa X:** Měsíce v roce (Led, Úno, Bře...)
        📅 **Osa Y:** Roky (2023, 2024...)
        🎨 **Barvy:** 🟢 Zisk / ⚪ Neutrál / 🔴 Ztráta
        
        **🎯 Heat mapa strategií podle měsíců** - detailní analýza:
        
        📅 **Osa X:** Měsíce v roce
        📅 **Osa Y:** Jednotlivé strategie
        🎨 **Barvy:** Stejné jako výše
        
        💡 **Tipy pro analýzu:**
        - 🔍 **Sezónní vzory:** Které měsíce jsou pro jaké strategie nejlepší?
        - ⚖️ **Rozložení rizika:** Jsou všechny strategie ziskové ve stejných měsících?
        - 📈 **Optimalizace:** Kdy aktivovat/deaktivovat konkrétní strategie?
        - 🎯 **Diverzifikace:** Kombinace strategií pro stabilnější výkonnost
        """)
        
    with st.expander("💡 Interpretace heat map"):
        st.markdown("""
        **🟢 Tmavě zelená:** Velmi vysoký zisk v daném měsíci/strategii
        **🟢 Světle zelená:** Mírný zisk
        **⚪ Bílá:** Žádné obchody nebo nulový P&L  
        **🔴 Světle červená:** Mírná ztráta
        **🔴 Tmavě červená:** Vysoká ztráta
        
        **Praktické využití:**
        - Identifikace nejlepších/nejhorších měsíců pro každou strategii
        - Plánování kapitálu podle sezónních trendů
        - Optimalizace portfolio mixu podle měsíčních vzorů
        """)

# HLAVNÍ APLIKACE
def main():
    st.title("📊 Trading Portfolio Dashboard")
    st.subheader("SQLite + Excel - Kombinované zdroje")
    
    # Načtení dat
    with st.spinner("Načítám data..."):
        df = load_combined_data()
    
    if df.empty:
        st.error("Nepodařilo se načíst data")
        st.info(f"SQLite: {DB_PATH}")
        st.info(f"Excel: {EXCEL_PATH}")
        return
    
    # Success
    msg = f"✅ Načteno {len(df)} obchodů"
    if 'source' in df.columns:
        counts = df['source'].value_counts()
        info = " | ".join([f"{k}: {v}" for k, v in counts.items()])
        msg += f" | {info}"
    st.success(msg)
    
    # Debug
    with st.expander("🔧 Debug"):
        if 'source' in df.columns:
            st.write("**Zdroje:**")
            for source, count in df['source'].value_counts().items():
                st.write(f"- {source}: {count}")
        
        st.write(f"**Rozsah:** {df['exitDate'].min()} až {df['exitDate'].max()}")
        st.write("**Čas odstraněn z datumů**")
        
        cols = ['strategy', 'exitDate', 'netPL']
        if 'source' in df.columns:
            cols.append('source')
        st.dataframe(df[cols].head())
    
    # Filtry
    st.sidebar.header("🔧 Filtry")
    
    time_filter = st.sidebar.selectbox(
        "📅 Období:",
        ["All Time", "Vlastní období (OD-DO)", "YTD", "Kalendářní rok", 
         "Poslední kalendářní rok", "Posledních 12 měsíců", "Posledních 6 měsíců", 
         "Poslední 3 měsíce", "Posledních 30 dní", "MTD", "Týden"]
    )
    
    start_date = None
    end_date = None
    if time_filter == "Vlastní období (OD-DO)":
        min_dt = df['exitDate'].min().date()
        max_dt = df['exitDate'].max().date()
        
        col1, col2 = st.sidebar.columns(2)
        with col1:
            start_date = st.date_input("OD:", value=min_dt, min_value=min_dt, max_value=max_dt)
        with col2:
            end_date = st.date_input("DO:", value=max_dt, min_value=min_dt, max_value=max_dt)
    
    strategies = st.sidebar.multiselect(
        "📈 Strategie:",
        options=df['strategy'].unique(),
        default=df['strategy'].unique()
    )
    
    # Filtrování
    filtered_df = filter_by_time(df, time_filter, start_date, end_date)
    filtered_df = filtered_df[filtered_df['strategy'].isin(strategies)]
    
    # Metriky
    metrics = calc_metrics(filtered_df)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("💰 Total P&L", f"${metrics.get('total_pl', 0):,.2f}")
    
    with col2:
        st.metric(
            "📈 Výkonnost",
            f"{metrics.get('total_pl_percent', 0):.2f}%",
            delta=f"${metrics.get('total_pl', 0):,.0f}"
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
    
    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 Overview", "📈 Strategie", "📉 Grafy"])
    
    with tab1:
        st.subheader("Portfolio Performance")
        show_help()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Trading Stats:**")
            st.write(f"Celkem obchodů: {metrics.get('total_trades', 0)}")
            st.write(f"Vítězné: {metrics.get('winning_trades', 0)}")
            st.write(f"Ztrátové: {metrics.get('losing_trades', 0)}")
            st.write(f"Win Rate: {metrics.get('win_rate', 0):.2f}%")
            st.write(f"Výkonnost: {metrics.get('total_pl_percent', 0):.2f}%")
        
        with col2:
            st.write("**Risk Metrics:**")
            st.write(f"Průměrný zisk: ${metrics.get('avg_win', 0):.2f}")
            st.write(f"Průměrná ztráta: ${metrics.get('avg_loss', 0):.2f}")
            st.write(f"Profit Factor: {metrics.get('profit_factor', 0):.2f}")
            st.write(f"Max Drawdown: ${metrics.get('max_drawdown', 0):.2f}")
            st.write(f"Počáteční kapitál: ${INITIAL_CAPITAL:,}")
        
        st.plotly_chart(create_cumulative_chart(filtered_df), use_container_width=True)
        st.plotly_chart(create_individual_chart(filtered_df), use_container_width=True)
    
    with tab2:
        st.subheader("Strategie")
        
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
        st.plotly_chart(create_strategy_chart(filtered_df), use_container_width=True, key="strategy_comparison")
    
    with tab3:
        st.subheader("Grafy jednotlivých strategií")
        
        for i, strategy in enumerate(strategies):
            st.write(f"**{strategy}**")
            strat_data = filtered_df[filtered_df['strategy'] == strategy]
            
            # První řádek - kumulativní a jednotlivé obchody
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(
                    create_cumulative_chart(strat_data, f"Kumulativní - {strategy}"),
                    use_container_width=True,
                    key=f"strategy_cumulative_{i}_{strategy.replace(' ', '_')}"
                )
            with col2:
                st.plotly_chart(
                    create_individual_chart(strat_data, f"Obchody - {strategy}"),
                    use_container_width=True,
                    key=f"strategy_individual_{i}_{strategy.replace(' ', '_')}"
                )
            
            # Druhý řádek - heat mapa pro strategii
            st.plotly_chart(
                create_monthly_heatmap(strat_data, f"Heat mapa - {strategy}"),
                use_container_width=True,
                key=f"strategy_heatmap_{i}_{strategy.replace(' ', '_')}"
            )
            
            st.markdown("---")
    
    # Footer
    st.sidebar.markdown("---")
    st.sidebar.info(f"📊 {len(df)} obchodů")
    st.sidebar.info(f"💰 Kapitál: ${INITIAL_CAPITAL:,}")
    st.sidebar.info("📁 SQLite + Excel")

if __name__ == "__main__":
    main()