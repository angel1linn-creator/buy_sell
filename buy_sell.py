import streamlit as st
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import time

# 設定網頁標題與寬螢幕版面
st.set_page_config(page_title="台股投信連續買超追蹤儀表板", layout="wide")

@st.cache_data(ttl=3600)  # 快取 1 小時，避免重複頻繁發送請求
def fetch_twse_data(num_days=25):
    """從證交所抓取最近 25 個交易日的投信買超數據，以完整計算連買天數"""
    trading_days = []
    current_date = datetime.now()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # 往回搜尋足夠的交易日（抓 45 天來確保能篩出 25 個實際交易日，避開週末與假日）
    for i in range(45):
        date_str = (current_date - timedelta(days=i)).strftime('%Y%m%d')
        url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=ALL"
        
        try:
            res = requests.get(url, headers=headers).json()
            
            if res.get('stat') == 'OK':
                df = pd.DataFrame(res['data'], columns=res['fields'])
                df['證券代號'] = df['證券代號'].str.strip()
                df['證券名稱'] = df['證券名稱'].str.strip()
                df['投信買賣超股數'] = df['投信買賣超股數'].str.replace(',', '').astype(float)
                df['投信買超張數'] = df['投信買賣超股數'] / 1000
                
                trading_days.append({
                    'date': date_str,
                    'data': df[['證券代號', '證券名稱', '投信買超張數']]
                })
                
                if len(trading_days) == num_days:
                    break
            time.sleep(0.3)
        except Exception:
            continue
            
    if not trading_days:
        return None, None

    # 計算連續買超天數
    latest_day = trading_days[0]
    latest_df = latest_day['data']
    latest_buy = latest_df[latest_df['投信買超張數'] > 0].copy()
    
    consecutive_days = []
    for idx, row in latest_buy.iterrows():
        stock_id = row['證券代號']
        count = 0
        for day in trading_days:
            day_df = day['data']
            record = day_df[day_df['證券代號'] == stock_id]
            # 只要當天有上榜且買超 > 0，天數就 +1
            if not record.empty and record.iloc[0]['投信買超張數'] > 0:
                count += 1
            else:
                break
        consecutive_days.append(count)
        
    latest_buy['投信連買天數'] = consecutive_days
    
    # 1. 長天期排序：由長到短 (天數多 -> 少，買超張數多 -> 少)
    result_desc = latest_buy.sort_values(by=['投信連買天數', '投信買超張數'], ascending=[False, False])
    
    # 2. 短天期排序：由短到長 (天數少 -> 多，買超張數多 -> 少)
    result_asc = latest_buy.sort_values(by=['投信連買天數', '投信買超張數'], ascending=[True, False])
    
    return latest_day['date'], result_desc, result_asc

# 主頁面 UI 佈局
st.title("📊 台股投信「吃豆腐」連續買超追蹤器")
st.caption("同步提供「長天期鎖定排行」與「短天期剛發動排行榜」，精準對應不同操作策略！")

# 側邊欄控制項
st.sidebar.header("篩選條件設定")
min_days = st.sidebar.slider("最低連續買超天數（長天期適用）", min_value=1, max_value=15, value=2)
top_n = st.sidebar.slider("顯示前幾名標的", min_value=5, max_value=50, value=20)

if st.sidebar.button("清除快取並重新整理"):
    st.cache_data.clear()
    st.rerun()

# 載入數據
with st.spinner("正在連線證交所回溯歷史籌碼資料（約需數秒鐘）..."):
    latest_date, df_desc, df_asc = fetch_twse_data(num_days=25)

if df_desc is not None and df_asc is not None:
    st.success(f"最新數據日期：{latest_date} （已成功回溯近 25 個交易日）")
    
    col1, col2 = st.columns([1.2, 0.8])
    
    with col1:
        st.subheader("📋 投信連買排行榜清單")
        
        # 建立分頁籤 (Tab)：切換由長到短 vs 由短到長
        tab1, tab2 = st.tabs(["🔥 長天期排行（由長到短）", "🌱 剛發動短天期排行（由短到長）"])
        
        with tab1:
            filtered_desc = df_desc[df_desc['投信連買天數'] >= min_days].head(top_n)
            st.dataframe(
                filtered_desc[['證券代號', '證券名稱', '投信買超張數', '投信連買天數']],
                column_config={
                    "證券代號": "代號",
                    "證券名稱": "股票名稱",
                    "投信買超張數": st.column_config.NumberColumn("今日買超 (張)", format="%.0f"),
                    "投信連買天數": st.column_config.NumberColumn("連買天數", format="%d 天")
                },
                hide_index=True,
                use_container_width=True
            )
            st.info("""💡 **長天期觀察**：
- 適合查看主力鎖定許久、籌碼安定的權值或題材股。
- 若連買超過 10 天以上需留意高檔結帳風險！""")
            
        with tab2:
            filtered_asc = df_asc.head(top_n)
            st.dataframe(
                filtered_asc[['證券代號', '證券名稱', '投信買超張數', '投信連買天數']],
                column_config={
                    "證券代號": "代號",
                    "證券名稱": "股票名稱",
                    "投信買超張數": st.column_config.NumberColumn("今日買超 (張)", format="%.0f"),
                    "投信連買天數": st.column_config.NumberColumn("連買天數", format="%d 天")
                },
                hide_index=True,
                use_container_width=True
            )
            st.info("""💡 **短天期吃豆腐**：
- 專門用來找**連買 1~3 天**剛點火起跑的中小型股。
- 順勢搭乘內資與投信作帳順風車！""")
        
    with col2:
        st.subheader("📈 個股近 30 日走勢查閱")
        combined_stock_list = df_desc['證券代號'].tolist()
        if combined_stock_list:
            selected_stock = st.selectbox("選擇要檢視 K 線圖的股票：", combined_stock_list)
            
            yf_ticker = f"{selected_stock}.TW"
            stock = yf.Ticker(yf_ticker)
            hist = stock.history(period="1mo")
            
            if not hist.empty:
                st.line_chart(hist['Close'], y_label="收盤價 (NTD)")
                st.caption(f"{selected_stock} 最近一個月收盤價趨勢")
            else:
                st.warning("無法抓取該股票 K 線圖（可能為上櫃股票或代碼異動）。")
else:
    st.error("無法取得證交所數據，請確認網路連線或今日是否為休市日。")