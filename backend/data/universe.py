"""
NSE Stock Universe - Nifty 500 subset
~50 well-known liquid NSE stocks covering major sectors
"""

STOCK_UNIVERSE = {
    # IT
    "TCS.NS": {"name": "Tata Consultancy Services", "sector": "IT"},
    "INFY.NS": {"name": "Infosys", "sector": "IT"},
    "WIPRO.NS": {"name": "Wipro", "sector": "IT"},
    "HCLTECH.NS": {"name": "HCL Technologies", "sector": "IT"},
    "TECHM.NS": {"name": "Tech Mahindra", "sector": "IT"},

    # Banking
    "HDFCBANK.NS": {"name": "HDFC Bank", "sector": "Banking"},
    "ICICIBANK.NS": {"name": "ICICI Bank", "sector": "Banking"},
    "AXISBANK.NS": {"name": "Axis Bank", "sector": "Banking"},
    "KOTAKBANK.NS": {"name": "Kotak Mahindra Bank", "sector": "Banking"},
    "SBIN.NS": {"name": "State Bank of India", "sector": "Banking"},
    "BANKBARODA.NS": {"name": "Bank of Baroda", "sector": "Banking"},

    # Auto
    "MARUTI.NS": {"name": "Maruti Suzuki", "sector": "Auto"},
    "TATAMOTORS.NS": {"name": "Tata Motors", "sector": "Auto"},
    "BAJAJ-AUTO.NS": {"name": "Bajaj Auto", "sector": "Auto"},
    "EICHERMOT.NS": {"name": "Eicher Motors", "sector": "Auto"},
    "HEROMOTOCO.NS": {"name": "Hero MotoCorp", "sector": "Auto"},

    # Pharma
    "SUNPHARMA.NS": {"name": "Sun Pharmaceutical", "sector": "Pharma"},
    "DRREDDY.NS": {"name": "Dr. Reddy's Laboratories", "sector": "Pharma"},
    "CIPLA.NS": {"name": "Cipla", "sector": "Pharma"},
    "DIVISLAB.NS": {"name": "Divi's Laboratories", "sector": "Pharma"},

    # FMCG
    "HINDUNILVR.NS": {"name": "Hindustan Unilever", "sector": "FMCG"},
    "ITC.NS": {"name": "ITC", "sector": "FMCG"},
    "NESTLEIND.NS": {"name": "Nestle India", "sector": "FMCG"},
    "BRITANNIA.NS": {"name": "Britannia Industries", "sector": "FMCG"},

    # Energy
    "RELIANCE.NS": {"name": "Reliance Industries", "sector": "Energy"},
    "ONGC.NS": {"name": "Oil & Natural Gas Corp", "sector": "Energy"},
    "BPCL.NS": {"name": "Bharat Petroleum", "sector": "Energy"},
    "IOC.NS": {"name": "Indian Oil Corporation", "sector": "Energy"},

    # Metals
    "TATASTEEL.NS": {"name": "Tata Steel", "sector": "Metals"},
    "HINDALCO.NS": {"name": "Hindalco Industries", "sector": "Metals"},
    "JSWSTEEL.NS": {"name": "JSW Steel", "sector": "Metals"},
    "SAIL.NS": {"name": "Steel Authority of India", "sector": "Metals"},

    # Infra
    "LT.NS": {"name": "Larsen & Toubro", "sector": "Infra"},
    "ADANIPORTS.NS": {"name": "Adani Ports", "sector": "Infra"},
    "ULTRACEMCO.NS": {"name": "UltraTech Cement", "sector": "Infra"},

    # Finance
    "BAJFINANCE.NS": {"name": "Bajaj Finance", "sector": "Finance"},
    "BAJAJFINSV.NS": {"name": "Bajaj Finserv", "sector": "Finance"},
    "HDFCLIFE.NS": {"name": "HDFC Life Insurance", "sector": "Finance"},

    # Telecom
    "BHARTIARTL.NS": {"name": "Bharti Airtel", "sector": "Telecom"},
    "IDEA.NS": {"name": "Vodafone Idea", "sector": "Telecom"},

    # Additional liquid stocks
    "ASIANPAINT.NS": {"name": "Asian Paints", "sector": "FMCG"},
    "TITAN.NS": {"name": "Titan Company", "sector": "Consumer"},
    "POWERGRID.NS": {"name": "Power Grid Corp", "sector": "Energy"},
    "NTPC.NS": {"name": "NTPC", "sector": "Energy"},
    "COALINDIA.NS": {"name": "Coal India", "sector": "Metals"},
    "GRASIM.NS": {"name": "Grasim Industries", "sector": "Infra"},
    "INDUSINDBK.NS": {"name": "IndusInd Bank", "sector": "Banking"},
    "M&M.NS": {"name": "Mahindra & Mahindra", "sector": "Auto"},
    "APOLLOHOSP.NS": {"name": "Apollo Hospitals", "sector": "Healthcare"},
    "TATACONSUM.NS": {"name": "Tata Consumer Products", "sector": "FMCG"},
}
