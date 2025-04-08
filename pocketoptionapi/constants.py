import random

ACTIVES = {
    '#AAPL': 5,
    '#AAPL_otc': 170,
    '#AXP': 140,
    '#AXP_otc': 291,
    '#BA': 8,
    '#BA_otc': 292,
    '#CSCO': 154,
    '#CSCO_otc': 427,
    '#FB': 177,
    '#FB_otc': 187,
    '#INTC': 180,
    '#INTC_otc': 190,
    '#JNJ': 144,
    '#JNJ_otc': 296,
    '#JPM': 20,
    '#MCD': 23,
    '#MCD_otc': 175,
    '#MSFT': 24,
    '#MSFT_otc': 176,
    '#PFE': 147,
    '#PFE_otc': 297,
    '#TSLA': 186,
    '#TSLA_otc': 196,
    '#XOM': 153,
    '#XOM_otc': 426,
    '100GBP': 315,
    '100GBP_otc': 403,
    'AEX25': 449,
    'AMZN_otc': 412,
    'AUDCAD': 36,
    'AUDCAD_otc': 67,
    'AUDCHF': 37,
    'AUDCHF_otc': 68,
    'AUDJPY': 38,
    'AUDJPY_otc': 69,
    'AUDNZD_otc': 70,
    'AUDUSD': 40,
    'AUDUSD_otc': 71,
    'AUS200': 305,
    'AUS200_otc': 306,
    'BABA': 183,
    'BABA_otc': 428,
    'BCHEUR': 450,
    'BCHGBP': 451,
    'BCHJPY': 452,
    'BTCGBP': 453,
    'BTCJPY': 454,
    'BTCUSD': 197,
    'CAC40': 455,
    'CADCHF': 41,
    'CADCHF_otc': 72,
    'CADJPY': 42,
    'CADJPY_otc': 73,
    'CHFJPY': 43,
    'CHFJPY_otc': 74,
    'CHFNOK_otc': 457,
    'CITI': 326,
    'CITI_otc': 413,
    'D30EUR': 318,
    'D30EUR_otc': 406,
    'DASH_USD': 209,
    'DJI30': 322,
    'DJI30_otc': 409,
    'DOTUSD': 458,
    'E35EUR': 314,
    'E35EUR_otc': 402,
    'E50EUR': 319,
    'E50EUR_otc': 407,
    'ETHUSD': 272,
    'EURAUD': 44,
    'EURCAD': 45,
    'EURCHF': 46,
    'EURCHF_otc': 77,
    'EURGBP': 47,
    'EURGBP_otc': 78,
    'EURHUF_otc': 460,
    'EURJPY': 48,
    'EURJPY_otc': 79,
    'EURNZD_otc': 80,
    'EURRUB_otc': 200,
    'EURUSD': 1,
    'EURUSD_otc': 66,
    'F40EUR': 316,
    'F40EUR_otc': 404,
    'FDX_otc': 414,
    'GBPAUD': 51,
    'GBPAUD_otc': 81,
    'GBPCAD': 52,
    'GBPCHF': 53,
    'GBPJPY': 54,
    'GBPJPY_otc': 84,
    'GBPUSD': 56,
    'H33HKD': 463,
    'JPN225': 317,
    'JPN225_otc': 405,
    'LNKUSD': 464,
    'NASUSD': 323,
    'NASUSD_otc': 410,
    'NFLX': 182,
    'NFLX_otc': 429,
    'NZDJPY_otc': 89,
    'NZDUSD_otc': 90,
    'SMI20': 466,
    'SP500': 321,
    'SP500_otc': 408,
    'TWITTER': 330,
    'TWITTER_otc': 415,
    'UKBrent': 50,
    'UKBrent_otc': 164,
    'USCrude': 64,
    'USCrude_otc': 165,
    'USDCAD': 61,
    'USDCAD_otc': 91,
    'USDCHF': 62,
    'USDCHF_otc': 92,
    'USDJPY': 63,
    'USDJPY_otc': 93,
    'USDRUB_otc': 199,
    'VISA_otc': 416,
    'XAGEUR': 103,
    'XAGUSD': 65,
    'XAGUSD_otc': 167,
    'XAUEUR': 102,
    'XAUUSD': 2,
    'XAUUSD_otc': 169,
    'XNGUSD': 311,
    'XNGUSD_otc': 399,
    'XPDUSD': 313,
    'XPDUSD_otc': 401,
    'XPTUSD': 312,
    'XPTUSD_otc': 400,

    # Stocks
    'Microsoft_otc': 521,
    'Facebook_OTC': 522,
    'Tesla_otc': 523,
    'Boeing_OTC': 524,
    'American_Express_otc': 525
}


class REGION:
    REGIONS = {
        "EUROPA":  "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket",
        "SEYCHELLES": "wss://api-sc.po.market/socket.io/?EIO=4&transport=websocket",
        "HONGKONG": "wss://api-hk.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER1": "wss://api-spb.po.market/socket.io/?EIO=4&transport=websocket",
        "FRANCE2": "wss://api-fr2.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES4": "wss://api-us4.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES3": "wss://api-us3.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES2": "wss://api-us2.po.market/socket.io/?EIO=4&transport=websocket",
        "DEMO": "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket",
        "DEMO_2": "wss://try-demo-eu.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES": "wss://api-us-north.po.market/socket.io/?EIO=4&transport=websocket",
        "RUSSIA": "wss://api-msk.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER2": "wss://api-l.po.market/socket.io/?EIO=4&transport=websocket",
        "INDIA": "wss://api-in.po.market/socket.io/?EIO=4&transport=websocket",
        "FRANCE": "wss://api-fr.po.market/socket.io/?EIO=4&transport=websocket",
        "FINLAND": "wss://api-fin.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER3": "wss://api-c.po.market/socket.io/?EIO=4&transport=websocket",
        "ASIA": "wss://api-asia.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER4": "wss://api-us-south.po.market/socket.io/?EIO=4&transport=websocket"
    }

    def __getattr__(self, key):
        try:
            return self.REGIONS[key]
        except KeyError:
            raise AttributeError(f"'{self.REGIONS}' object has no attribute '{key}'")

    def get_regions(self, randomize: bool = True):
        if randomize:
            return sorted(list(self.REGIONS.values()), key=lambda k: random.random())
        return list(self.REGIONS.values())
