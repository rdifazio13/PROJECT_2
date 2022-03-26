import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import brute
from alpaca_trade_api.rest import REST, TimeFrame
import alpaca_trade_api as tradeapi
plt.style.use("seaborn")

class SOBacktester(): 
    ''' Class for the vectorized backtesting of SO-based trading strategies.

    Attributes
    ==========
    symbol: str
        ticker symbol with which to work with
    periods: int
        time window in days for rolling low/high
    D_mw: int
        time window in days for %D line
    start: str
        start date for data retrieval
    end: str
        end date for data retrieval
    tc: float
        proportional transaction costs per trade
        
        
    Methods
    =======
    get_data:
        retrieves and prepares the data
        
    set_parameters:
        sets one or two new SO parameters
        
    test_strategy:
        runs the backtest for the SO-based strategy
        
    plot_results:
        plots the performance of the strategy compared to buy and hold
        
    update_and_run:
        updates SO parameters and returns the negative absolute performance (for minimization algorithm)
        
    optimize_parameters:
        implements a brute force optimization for the two SO parameters
    '''
    
    def __init__(self, symbol, periods, D_mw, start, end, tc, api):
        self.symbol = symbol
        self.periods = periods
        self.D_mw = D_mw
        self.start = start
        self.end = end
        self.tc = tc
        self.api = api
        self.results = None 
        self.get_data()
        
    def __repr__(self):
        return "SOBacktester(symbol = {}, periods = {}, D_mw = {}, start = {}, end = {}, api = {})".format(self.symbol, self.periods, self.D_mw, self.start, self.end, self.api)
        
    def get_data(self):
        ''' Retrieves and prepares the data.
        '''
        raw = self.api.get_crypto_bars(self.symbol, TimeFrame.Day, self.start, self.end,exchanges=['CBSE']).df
        raw = raw.dropna()
        raw = raw.loc[self.start:self.end]
        raw['returns'] = np.log1p(raw.close.pct_change())
        raw["roll_low"] = raw.low.rolling(self.periods).min()
        raw["roll_high"] = raw.high.rolling(self.periods).max()
        raw["K"] = (raw.close - raw.roll_low) / (raw.roll_high - raw.roll_low) * 100
        raw["D"] = raw.K.rolling(self.D_mw).mean()
        self.data = raw
        
    def set_parameters(self, periods = None, D_mw = None):
        ''' Updates SO parameters and resp. time series.
        '''
        if periods is not None:
            self.periods = periods
            self.data["roll_low"] = self.data.low.rolling(self.periods).min()
            self.data["roll_high"] = self.data.high.rolling(self.periods).max()
            self.data["K"] = (self.data.close - self.data.roll_low) / (self.data.roll_high - self.data.roll_low) * 100
            self.data["D"] = self.data.K.rolling(self.D_mw).mean() 
        if D_mw is not None:
            self.D_mw = D_mw
            self.data["D"] = self.data.K.rolling(self.D_mw).mean()
            
    def test_strategy(self):
        ''' Backtests the trading strategy.
        '''
        data = self.data.copy().dropna()
        data["position"] = np.where(data["K"] > data["D"], 1, -1)
        data["strategy"] = data["position"].shift(1) * data["returns"]
        data.dropna(inplace=True)
        
        # determine when a trade takes place
        data["trades"] = data.position.diff().fillna(0).abs()
        
        # subtract transaction costs from return when trade takes place
        data.strategy = data.strategy - data.trades * self.tc
        
        data["Cumulative Returns Buy and Hold"] = data["returns"].cumsum().apply(np.exp)
        data["Cumulative Returns SO Strategy"] = data["strategy"].cumsum().apply(np.exp)
        self.results = data
        
        perf = data["Cumulative Returns SO Strategy"].iloc[-1] # absolute performance of the strategy
        outperf = perf - data["Cumulative Returns Buy and Hold"].iloc[-1] # out-/underperformance of strategy
        return round(perf, 6), round(outperf, 6)
    
    def plot_results(self):
        ''' Plots the cumulative performance of the trading strategy
        compared to buy and hold.
        '''
        if self.results is None:
            print("No results to plot yet. Run a strategy.")
        else:
            title = "{} | periods = {}, D_mw = {} | TC = {}".format(self.symbol, self.periods, self.D_mw, self.tc)
            self.results[["Cumulative Returns Buy and Hold", "Cumulative Returns SO Strategy"]].plot(title=title, figsize=(12, 8))
        
    def update_and_run(self, SO):
        ''' Updates SO parameters and returns the negative absolute performance (for minimization algorithm).

        Parameters
        ==========
        SO: tuple
            SO parameter tuple
        '''
        self.set_parameters(int(SO[0]), int(SO[1]))
        return -self.test_strategy()[0]
    
    def optimize_parameters(self, periods_range, D_mw_range):
        ''' Finds global maximum given the SO parameter ranges.

        Parameters
        ==========
        periods_range, D_mw_range: tuple
            tuples of the form (start, end, step size)
        '''
        opt = brute(self.update_and_run, (periods_range, D_mw_range), finish=None)
        return opt, -self.update_and_run(opt)
    
    