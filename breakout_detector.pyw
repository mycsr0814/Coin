import time
import threading
import winsound
import tkinter as tk
from tkinter import Canvas, Toplevel
from tkinter.scrolledtext import ScrolledText # 로그창용 위젯
import requests
import calendar
from datetime import datetime, timedelta
import pandas as pd
from alpaca_trade_api.rest import REST, TimeFrame

# ==========================================
# [설정] API 키 입력 (필수!)
# ==========================================
API_KEY = "PKTAEIKHKTXRTM43ZNJWNKRVOU"
SECRET_KEY = "3kaUm9aMyXUKrHgtCB3TaJ1iwJgsyAuAXhD1PVQEc7Nn"

BASE_URL = "https://paper-api.alpaca.markets"
DATA_URL = "https://data.alpaca.markets"

# API 연결 설정
api = REST(API_KEY, SECRET_KEY, BASE_URL)

# ==========================================
# [NEW] 서머타임(DST) 계산기
# ==========================================
def get_market_info():
    now = datetime.now()
    year = now.year
    
    c = calendar.monthcalendar(year, 3)
    second_sunday_mar = c[1][6] if c[0][6] != 0 else c[2][6]
    dst_start = datetime(year, 3, second_sunday_mar, 2) 

    c = calendar.monthcalendar(year, 11)
    first_sunday_nov = c[0][6] if c[0][6] != 0 else c[1][6]
    dst_end = datetime(year, 11, first_sunday_nov, 2) 

    is_dst = dst_start <= now < dst_end

    if is_dst:
        return {
            "is_dst": True,
            "pre_start_hour": 17,
            "reg_start_hour": 22,
            "reg_start_min": 30,
            "notice_text": "※ 서머타임 적용 중: 데이장(09:00 ~ 17:00) 미작동"
        }
    else:
        return {
            "is_dst": False,
            "pre_start_hour": 18,
            "reg_start_hour": 23,
            "reg_start_min": 30,
            "notice_text": "※ 표준시간(겨울): 데이장(10:00 ~ 18:00) 미작동"
        }

# ==========================================
# 1. 스크리너 (거래량 상위 종목 조회)
# ==========================================
def get_hot_stocks(log_func=None):
    try:
        headers = {"APCA-API-KEY-ID": API_KEY, "APCA-API-SECRET-KEY": SECRET_KEY}
        params = {"by": "volume", "top": 50} 
        response = requests.get(
            f"{DATA_URL}/v1beta1/screener/stocks/most-actives",
            headers=headers, params=params, timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            if log_func: log_func(f"[스크리너] 거래량 상위 50종목 갱신 완료")
            return [s['symbol'] for s in data['most_actives']]
        return []
    except Exception as e:
        if log_func: log_func(f"[스크리너 에러] {e}")
        return []

# ==========================================
# 2. 감시 로직 (로그 기능 추가)
# ==========================================
def check_surge(watch_list, cooldowns, alert_callback=None, log_func=None):
    if not watch_list: return
    try:
        # log_func(f"[감시] {len(watch_list)}개 종목 시세 조회 중...") # 너무 자주 찍히면 주석 처리
        
        bars = api.get_bars(watch_list, TimeFrame.Minute, limit=10).df
        if bars.empty: return

        if 'symbol' not in bars.columns: bars = bars.reset_index()

        market_info = get_market_info()
        pre_start = market_info["pre_start_hour"]
        reg_start_h = market_info["reg_start_hour"]
        
        now = datetime.now()
        is_pre_market = False
        
        # 단순화된 프리장 체크
        if pre_start <= now.hour < reg_start_h:
            is_pre_market = True

        if is_pre_market:
            VOL_MULTIPLIER = 2.5
            PRICE_THRESHOLD = 2.0
        else:
            VOL_MULTIPLIER = 3.0
            PRICE_THRESHOLD = 2.0

        for symbol in watch_list:
            if symbol in cooldowns:
                if datetime.now() < cooldowns[symbol]:
                    continue 
                else:
                    del cooldowns[symbol] 

            df = bars[bars['symbol'] == symbol]
            if len(df) < 5: continue

            curr = df.iloc[-1]
            prev_avg_vol = df['volume'].iloc[:-1].mean()
            if prev_avg_vol == 0: prev_avg_vol = 1

            pct_change = ((curr['close'] - curr['open']) / curr['open']) * 100
            
            # 조건 충족 시
            if curr['volume'] > prev_avg_vol * VOL_MULTIPLIER and pct_change >= PRICE_THRESHOLD:
                if log_func: log_func(f"[급등 포착] {symbol} : +{pct_change:.2f}% (거래량 폭증)")
                
                if alert_callback:
                    alert_callback(symbol, curr['close'], pct_change)
                cooldowns[symbol] = datetime.now() + timedelta(minutes=5)

    except Exception as e:
        if log_func: log_func(f"[로직 에러] {e}")

# ==========================================
# 3. GUI 클래스
# ==========================================
class BreakoutDetectorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🔥 급등주 감지기")
        self.root.geometry("480x700") 
        self.root.configure(bg='#f2f4f6') 
        
        self.is_running = False
        self.watch_list = []
        self.cooldowns = {} 
        self.last_scan_time = datetime.now() - timedelta(minutes=2)
        
        # 로그창 관련 변수
        self.log_window = None
        self.log_text = None

        self.setup_ui()
        
    def setup_ui(self):
        header_frame = tk.Frame(self.root, bg='#ffffff', height=70)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        # [로그 버튼 추가]
        self.log_btn = tk.Button(
            header_frame, text="LOG", 
            font=("Arial", 10, "bold"), bg='#e5e8eb', fg='#333d4b',
            relief=tk.FLAT, cursor='hand2',
            command=self.open_log_window
        )
        self.log_btn.pack(side=tk.RIGHT, padx=15)

        title_label = tk.Label(
            header_frame, text="실시간 급등 감지", 
            font=("Pretendard Variable", 20, "bold"), 
            fg='#191f28', bg='#ffffff'
        )
        title_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        self.status_frame = tk.Frame(self.root, bg='#f2f4f6')
        self.status_frame.pack(fill=tk.X, padx=20, pady=20)
        
        self.status_label = tk.Label(
            self.status_frame, text="현재 대기 중이에요", 
            font=("맑은 고딕", 16, "bold"), fg='#333d4b', bg='#f2f4f6', anchor="w"
        )
        self.status_label.pack(fill=tk.X)
        
        self.watch_count_label = tk.Label(
            self.status_frame, text="시작 버튼을 눌러주세요", 
            font=("맑은 고딕", 11), fg='#8b95a1', bg='#f2f4f6', anchor="w"
        )
        self.watch_count_label.pack(fill=tk.X, pady=(5,0))
        
        market_info = get_market_info()
        self.notice_label = tk.Label(
            self.status_frame, 
            text=market_info["notice_text"], 
            font=("맑은 고딕", 10), fg='#f04452', bg='#f2f4f6', anchor="w"
        )
        self.notice_label.pack(fill=tk.X, pady=(5,0))
        
        self.start_button = tk.Button(
            self.root, text="감지 시작하기", 
            font=("맑은 고딕", 14, "bold"),
            bg='#3182f6', fg='white', 
            relief=tk.FLAT, cursor='hand2',
            activebackground='#1b64da', activeforeground='white',
            command=self.toggle_detection
        )
        self.start_button.pack(fill=tk.X, padx=20, pady=(0, 20), ipady=10)
        
        list_frame = tk.Frame(self.root, bg='#f2f4f6')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        
        self.canvas = Canvas(list_frame, bg='#f2f4f6', highlightthickness=0)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.canvas.yview)
        
        self.scrollable_frame = tk.Frame(self.canvas, bg='#f2f4f6')
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", width=420)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        self.empty_label = tk.Label(
            self.scrollable_frame,
            text="급등주가 발견되면\n여기에 카드로 알려드려요 🚀",
            font=("맑은 고딕", 11), fg='#8b95a1', bg='#f2f4f6', justify=tk.CENTER
        )
        self.empty_label.pack(pady=60)

    # ==========================================
    # [NEW] 로그 윈도우 기능
    # ==========================================
    def open_log_window(self):
        if self.log_window is None or not self.log_window.winfo_exists():
            self.log_window = Toplevel(self.root)
            self.log_window.title("시스템 로그")
            self.log_window.geometry("400x300")
            
            # 스크롤 가능한 텍스트 위젯
            self.log_text = ScrolledText(self.log_window, state='disabled', font=("Consolas", 9))
            self.log_text.pack(fill=tk.BOTH, expand=True)
            self.log_window.protocol("WM_DELETE_WINDOW", self.close_log_window)
        else:
            self.log_window.lift()

    def close_log_window(self):
        self.log_window.destroy()
        self.log_window = None
        self.log_text = None

    def add_log(self, message):
        """ 로그 메시지를 GUI 스레드에서 안전하게 추가 """
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        full_msg = f"{timestamp} {message}\n"
        print(full_msg.strip()) # 콘솔에도 출력

        # 로그창이 열려있으면 텍스트 추가
        if self.log_window and self.log_text:
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, full_msg)
            self.log_text.see(tk.END) # 맨 아래로 스크롤
            self.log_text.config(state='disabled')

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
    def add_stock_card(self, symbol, price, pct_change):
        try:
            if hasattr(self, 'empty_label') and self.empty_label.winfo_exists():
                self.empty_label.destroy()
            
            card = tk.Frame(self.scrollable_frame, bg='#ffffff', bd=0, padx=20, pady=20)
            
            top_frame = tk.Frame(card, bg='#ffffff')
            top_frame.pack(fill=tk.X)
            
            tk.Label(top_frame, text=symbol, font=("Arial", 16, "bold"), fg='#191f28', bg='#ffffff').pack(side=tk.LEFT)
            tk.Label(top_frame, text=datetime.now().strftime('%H:%M'), font=("Arial", 10), fg='#8b95a1', bg='#ffffff').pack(side=tk.RIGHT, pady=(4,0))
            
            bottom_frame = tk.Frame(card, bg='#ffffff')
            bottom_frame.pack(fill=tk.X, pady=(10, 0))
            
            tk.Label(bottom_frame, text=f"${price:.2f}", font=("Arial", 14), fg='#333d4b', bg='#ffffff').pack(side=tk.LEFT)
            tk.Label(bottom_frame, text=f"+{pct_change:.2f}%", font=("Arial", 14, "bold"), fg='#f04452', bg='#ffffff').pack(side=tk.RIGHT)
            
            children = self.scrollable_frame.winfo_children()
            
            if len(children) >= 2:
                card.pack(fill=tk.X, pady=(0, 12), before=children[-2])
            else:
                card.pack(fill=tk.X, pady=(0, 12))
                
            if len(children) > 30:
                children[0].destroy()

            self.scrollable_frame.update_idletasks()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            self.canvas.yview_moveto(0) 

        except Exception as e:
            self.safe_log(f"GUI 카드 생성 에러: {e}")

    def play_alert_sound(self):
        def beep():
            winsound.Beep(1000, 150)
            time.sleep(0.05)
            winsound.Beep(1000, 150)
        threading.Thread(target=beep, daemon=True).start()
            
    # 스레드 안전한 로그 호출용 헬퍼
    def safe_log(self, message):
        self.root.after(0, lambda: self.add_log(message))

    def safe_alert_callback(self, symbol, price, pct_change):
        self.root.after(0, lambda: self.play_alert_sound())
        self.root.after(0, lambda: self.add_stock_card(symbol, price, pct_change))
        
    def toggle_detection(self):
        if not self.is_running:
            self.is_running = True
            self.start_button.config(text="중지하기", bg='#f04452')
            self.status_label.config(text="실시간 감시 중... 👀")
            self.watch_count_label.config(text="시장을 스캔하고 있습니다")
            self.add_log("=== 감시 시작 ===")
            
            thread = threading.Thread(target=self.detection_loop, daemon=True)
            thread.start()
        else:
            self.is_running = False
            self.start_button.config(text="다시 시작하기", bg='#3182f6')
            self.status_label.config(text="감시가 중지되었어요")
            self.watch_count_label.config(text="대기 중")
            self.add_log("=== 감시 중지 ===")
            
    def detection_loop(self):
        self.safe_log("백그라운드 스레드 시작됨")
        while self.is_running:
            try:
                # 1분마다 종목 리스트 갱신
                if datetime.now() - self.last_scan_time >= timedelta(minutes=1):
                    # 로그 함수를 인자로 전달
                    new_list = get_hot_stocks(log_func=self.safe_log)
                    if new_list:
                        self.watch_list = new_list
                        self.root.after(0, lambda l=len(new_list): 
                            self.watch_count_label.config(text=f"{l}개 종목을 지켜보고 있어요"))
                        self.safe_log(f"감시 리스트 업데이트: {len(new_list)}개")
                    else:
                        self.safe_log("종목 리스트 가져오기 실패 또는 0개")
                    self.last_scan_time = datetime.now()

                # 급등 감지 (로그 함수 전달)
                check_surge(
                    self.watch_list,
                    self.cooldowns,
                    alert_callback=self.safe_alert_callback,
                    log_func=self.safe_log 
                )
                time.sleep(1)

            except Exception as e:
                self.safe_log(f"루프 치명적 에러: {e}")
                print(f"Loop Error: {e}")
                time.sleep(1)

if __name__ == "__main__":
    root = tk.Tk()
    app = BreakoutDetectorGUI(root)
    root.mainloop()