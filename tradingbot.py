from lumibot.brokers import Alpaca
from lumibot.backtesting import YahooDataBacktesting
from lumibot.strategies.strategy import Strategy
from lumibot.traders import Trader
from datetime import datetime 
from alpaca_trade_api import REST 
from timedelta import Timedelta 
from finbert_utils import estimate_sentiment
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_KEY="PKMR64OADVAN2MIO8UP9"
API_SECRET="wv7TzSSgKFvM2OnS89WdymwjOqgzzKnbG35JjHMB"
BASE_URL="https://paper-api.alpaca.markets"

ALPACA_CREDS = {
    "API_KEY":API_KEY, 
    "API_SECRET": API_SECRET, 
    "PAPER": True
}

class MLTrader(Strategy): 
    def initialize(self, symbol: str = "VTI", cash_at_risk: float = 0.5): 
        self.symbol = symbol
        self.sleeptime = "2S" 
        self.last_trade = None
        self.cash_at_risk = cash_at_risk
        self.api = REST(key_id=API_KEY, secret_key=API_SECRET, base_url=BASE_URL)
        logger.info("Initialized MLTrader with symbol: %s and cash_at_risk: %f", symbol, cash_at_risk)

    def position_sizing(self): 
        account = self.api.get_account()
        buying_power = float(account.buying_power)
        cash = float(account.cash)
        last_price = self.get_last_price(self.symbol)
        logger.info("Cash: %f, Last Price: %f, Buying Power: %f", cash, last_price, buying_power)

        if last_price is None:
            logger.warning("Last price for %s is None, skipping position sizing.", self.symbol)
            return cash, last_price, 0

        quantity = round(int(cash * self.cash_at_risk) / last_price, 0)
        max_affordable_quantity = int(buying_power / last_price)

        if quantity > max_affordable_quantity:
            quantity = max_affordable_quantity
        
        logger.info("Position sizing - cash: %f, last_price: %f, quantity: %d, max_affordable_quantity: %d", cash, last_price, quantity, max_affordable_quantity)
        return cash, last_price, quantity

    def get_dates(self): 
        today = self.get_datetime()
        three_days_prior = today - Timedelta(days=3)
        logger.info("Getting dates - today: %s, three_days_prior: %s", today, three_days_prior)
        return today.strftime('%Y-%m-%d'), three_days_prior.strftime('%Y-%m-%d')

    def get_sentiment(self): 
        today, three_days_prior = self.get_dates()
        news = self.api.get_news(symbol=self.symbol, start=three_days_prior, end=today) 
        news = [ev.__dict__["_raw"]["headline"] for ev in news]
        probability, sentiment = estimate_sentiment(news)
        logger.info("Sentiment analysis for %s - probability: %f, sentiment: %s", self.symbol, probability, sentiment)
        return probability, sentiment 

    def on_trading_iteration(self):
        logger.info("Processing symbol: %s", self.symbol)
        cash, last_price, quantity = self.position_sizing()
        if last_price is None:
            logger.warning("Skipping %s due to None last price.", self.symbol)
            return

        probability, sentiment = self.get_sentiment()
        logger.info("Symbol: %s, Sentiment: %s, Probability: %f", self.symbol, sentiment, probability)
        if cash > last_price and quantity > 0:
            logger.info("Evaluating sentiment for %s", self.symbol)
            if sentiment == "positive" and probability > 0.9:
                if self.last_trade == "sell":
                    self.sell_all()
                    logger.info("Sold all positions for %s", self.symbol)
                order = self.create_order(
                    self.symbol,
                    quantity,
                    "buy",
                    type="market",
                    take_profit_price=last_price * 1.20,
                    stop_loss_price=last_price * 0.95
                )
                self.submit_order(order)
                self.last_trade = "buy"
                logger.info("Submitted buy order for %s: %s", self.symbol, order)
            elif sentiment == "negative" and probability > 0.9:
                position = self.get_position(self.symbol)
                logger.info("Current position for %s: %s", self.symbol, position)
                if position and hasattr(position, 'quantity') and position.quantity > 0:
                    if self.last_trade == "buy":
                        self.sell_all()
                        logger.info("Sold all positions for %s", self.symbol)
                    if position.quantity > 0:
                        order = self.create_order(
                            self.symbol,
                            position.quantity,
                            "sell",
                            type="market",
                            take_profit_price=last_price * 0.8,
                            stop_loss_price=last_price * 1.05
                        )
                        self.submit_order(order)
                        self.last_trade = "sell"
                        logger.info("Submitted sell order for %s: %s", self.symbol, order)

start_date = datetime(2024, 6, 13)
end_date = datetime(2024, 6, 15)  # Shortened time period for quicker testing
broker = Alpaca(ALPACA_CREDS) 
strategy = MLTrader(name='mlstrat', broker=broker, parameters={"symbol": "VTI", "cash_at_risk": 0.5})
# strategy.backtest(
#     YahooDataBacktesting, 
#     start_date, 
#     end_date, 
#     parameters={"symbol": "SPY", "cash_at_risk": 0.5}
# )


trader = Trader()
trader.add_strategy(strategy)
trader.run_all()
