# All imports needed for trading bot
import tda # Importation of TDA API from their website
# Importing of authentication components of API
from tda.auth import easy_client
from tda.client import Client
from tda.streaming import StreamClient
from tda.orders.equities import equity_buy_market
from tda.orders.equities import equity_sell_market
import atexit
import pytz # Ensuring of correct time zone when trading the NYSE
import datetime
from datetime import timedelta
import asyncio # Ensures that the bot will continue running even when the new data constantly comes in from Ameritrade 
from contextlib import suppress
import json
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager # Connects bot to Chrome for access to TDA
import ta # Technical analysis package for tracking stocks
import numpy as np
import pandas as pd
import math
import logging
import locale
import threading
import time
import sys
import os
import httpx 
from config import api_key, redirect_uri, token_path
#Creation of Bar class to update the data for a stock to be looked back upon by the bot, data fills in as stock is tracked
class Bar:
    open = 0
    close = 0 
    high = 0
    low = 0
    volume = 0
    date = datetime.datetime.now()
    def __init__(self):
        self.open = 0
        self.close = 0
        self.high = 0 
        self.low = 0
        self.volume = 0
        self.date = datetime.datetime.now()

# Creation of trading bot 
class Bot:
    barsize = 45 # time frame of the bar that we are tracking
    currentbar = Bar() # reading of bar class for what the stock currently reads
    bars = []
    client = ''
    account_id = 0
    accountSize = 10000 # amount of money in the account for the testing
    firstTime= True # Bool to check if position already exists in that stock
    rsi = [] # Passing the bot calculation for RSI (indicator) we are tracking
    rsiPeriod = 14
    stream_client = ''
    status = None
    initialbartime = datetime.datetime.now().astimezone(pytz.timezone("America/New_York"))
    def __init__(self):
        try:
            #Global vars
            API_KEY = GO4TJYDKMQSORHTWAI4TNG26RVQQRSG3 # My API key from app
            REDIRECT_URI = 'https://localhost' #URL from my app
            TOKEN_PATH = token_path
            # Create a new client from our info above, causes chrome to open to log in
            self.client = tda.auth.easy_client(API_KEY,
                REDIRECT_URI,
                TOKEN_PATH,
                self.make_webdriver)
            # To place trades we must specify the account ID
            r = self.client.get_accounts() # saving of account data 
            assert r.status_code == 200, r.raise_for_status()
            data = r.json()
            self.account_id = data[0]['securitiesAccount']['accountId']
            self.accountSize = data[0]['securitiesAccount']['currentBalances']['cashBalance'] #Account size updated based on our account info
            self.stream_client = StreamClient(self.client, account_id=self.account_id)
            print("Successfully logged in to your TD Ameritrade Account.")
            #Get symbol info
            self.symbol = input("Enter the symbol you want to trade : ")
            #Get bar size
            self.barsize = int(input("Enter the barsize you want to trade in minutes : "))
            self.stream_client = StreamClient(self.client, account_id=self.account_id) # Collect stock data 
            asyncio.run(self.read_stream()) #Data ingested by system without stopped the running of app
        except Exception as e:
            print(e)
    #Collection of updates from TDA to collect info for stock we selected above
    async def read_stream(self):
        try:
            await self.stream_client.login()
            await self.stream_client.quality_of_service(StreamClient.QOSLevel.EXPRESS)
            await self.stream_client.chart_equity_subs([self.symbol])
            self.stream_client.add_chart_equity_handler(self.onBarUpdate) # Call function to analyze the indicator(s) that we want to trade based on 
            print("Streaming real-time data now.")
            while True:
                try:
                    await self.stream_client.handle_message()
                except Exception as e:
                    print(e)
        except Exception as e:
            print(e)
    #OnBarUpdate: Processes every new change in price of the stock we are tracking
    def onBarUpdate(self,msg):
        try:
            msg = json.dumps(msg, indent=4)
            msg = json.loads(msg)
            #Retrieve Bar 
            for bar in msg['content']:
                # Check The Strategy
                bartime = datetime.datetime.fromtimestamp(msg['timestamp'] / 1000).astimezone(pytz.timezone("America/New_York"))
                # How many minutes have passed 
                minutes_diff = (bartime-self.initialbartime).total_seconds() / 60.0
                self.currentBar.date = bartime
                #On Bar Close
                if (minutes_diff > 0 and math.floor(minutes_diff) % self.barsize == 0): # Has time passed since we started tracking and is the divisible by the barsize that we wanted
                    self.initialbartime = bartime 
                    #Calculate RSI
                    closes = []
                    for histbar in self.bars:
                        closes.append(histbar.close)
                    self.close_array = pd.Series(np.asarray(closes))
                    if (len(self.bars) > 0):
                        #Calculate RSI using the TA package for technical analysis
                        self.rsi = ta.momentum.rsi(self.close_array,self.rsiPeriod, True)
                        #Print last rsi
                        print('RSI: ' + str(self.rsi[len(self.rsi)-1])) #Give us the most recent RSI for the ticker 
                        print(self.inPosition) # Tell us if we are currently in a position or not
                        # If the last reported RSI <= 30, and self.inPosition is False, then we will submit a buy order
                        if self.rsi[len(self.rsi)-1] <= 30 and not self.inPosition: 
                            #Submit a buy order
                            order = tda.orders.equities.equity_buy_market(self.symbol,1)
                            r = self.client.place_order(self.account_id, order)
                            assert r.status_code == httpx.codes.OK, r.raise_for_status()
                            order_id = Utils(client, account_id).extract_order_id(r)
                            # make sure that order went through 
                            assert order_id is not None, "oh no buy order did not go through"  
                            print("bought a share")
                            self.inPosition = True #Sets inPosition to True so that only one trade is executed
                        #If the RSI >= 70 and we are in a position, sell position
                        if self.rsi[len(self.rsi)-1] >= 70 and self.inPosition:
                            #Submit a sell order
                            order = tda.orders.equities.equity_sell_market(self.symbol,1)
                            r = self.client.place_order(self.account_id, order)
                            assert r.status_code == httpx.codes.OK, r.raise_for_status()
                            order_id = Utils(client, account_id).extract_order_id(r)
                            # make sure that order went through 
                            assert order_id is not None, "oh no sell order did not go through"   
                            print("sold a share")
                            self.inPosition = False
                    #Bar closed append
                    self.currentBar.close = bar['CLOSE_PRICE']
                    print("New bar!")
                    self.bars.append(self.currentBar)
                    self.currentBar = Bar()
                    self.currentBar.open = bar['OPEN_PRICE']
                #Build  realtime bar
                if (self.currentBar.open == 0):
                    self.currentBar.open = bar['OPEN_PRICE']
                if (self.currentBar.high == 0 or bar['HIGH_PRICE'] > self.currentBar.high):
                    self.currentBar.high = bar['HIGH_PRICE']
                if (self.currentBar.low == 0 or bar['LOW_PRICE'] < self.currentBar.low):
                    self.currentBar.low = bar['LOW_PRICE']
        except Exception as e:
            print(e)        
    #Connect to TD Ameritrade OAUTH Login
    def make_webdriver(self):
        # Import selenium here because it's slow to import
        from selenium import webdriver
        driver = webdriver.Chrome(ChromeDriverManager().install())
        atexit.register(lambda: driver.quit())
        return driver
#Start Bot
bot = Bot()

