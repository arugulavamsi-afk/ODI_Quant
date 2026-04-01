"""
NSE Stock Universe — NIFTY 100 (NIFTY 50 + NIFTY Next 50)
~105 liquid large-cap stocks across all major sectors.
Stocks that don't meet the MIN_VOLUME / MIN_PRICE filter in config.py
are automatically skipped during analysis.
"""

STOCK_UNIVERSE = {

    # ── IT / Technology ───────────────────────────────────────────────────────
    "TCS.NS":        {"name": "Tata Consultancy Services",  "sector": "IT"},
    "INFY.NS":       {"name": "Infosys",                    "sector": "IT"},
    "WIPRO.NS":      {"name": "Wipro",                      "sector": "IT"},
    "HCLTECH.NS":    {"name": "HCL Technologies",           "sector": "IT"},
    "TECHM.NS":      {"name": "Tech Mahindra",              "sector": "IT"},
    "LTIM.NS":       {"name": "LTIMindtree",                "sector": "IT"},
    "LTTS.NS":       {"name": "L&T Technology Services",    "sector": "IT"},
    "OFSS.NS":       {"name": "Oracle Financial Services",  "sector": "IT"},
    "PERSISTENT.NS": {"name": "Persistent Systems",         "sector": "IT"},
    "NAUKRI.NS":     {"name": "Info Edge (Naukri)",         "sector": "IT"},

    # ── Banking ───────────────────────────────────────────────────────────────
    "HDFCBANK.NS":   {"name": "HDFC Bank",                  "sector": "Banking"},
    "ICICIBANK.NS":  {"name": "ICICI Bank",                 "sector": "Banking"},
    "AXISBANK.NS":   {"name": "Axis Bank",                  "sector": "Banking"},
    "KOTAKBANK.NS":  {"name": "Kotak Mahindra Bank",        "sector": "Banking"},
    "SBIN.NS":       {"name": "State Bank of India",        "sector": "Banking"},
    "INDUSINDBK.NS": {"name": "IndusInd Bank",              "sector": "Banking"},
    "BANKBARODA.NS": {"name": "Bank of Baroda",             "sector": "Banking"},
    "CANBK.NS":      {"name": "Canara Bank",                "sector": "Banking"},
    "PNB.NS":        {"name": "Punjab National Bank",       "sector": "Banking"},
    "UNIONBANK.NS":  {"name": "Union Bank of India",        "sector": "Banking"},
    "FEDERALBNK.NS": {"name": "Federal Bank",               "sector": "Banking"},
    "IDFCFIRSTB.NS": {"name": "IDFC First Bank",            "sector": "Banking"},

    # ── Finance / NBFC / Insurance ────────────────────────────────────────────
    "BAJFINANCE.NS": {"name": "Bajaj Finance",              "sector": "Finance"},
    "BAJAJFINSV.NS": {"name": "Bajaj Finserv",              "sector": "Finance"},
    "HDFCLIFE.NS":   {"name": "HDFC Life Insurance",        "sector": "Finance"},
    "SBILIFE.NS":    {"name": "SBI Life Insurance",         "sector": "Finance"},
    "ICICIPRULI.NS": {"name": "ICICI Prudential Life",      "sector": "Finance"},
    "HDFCAMC.NS":    {"name": "HDFC Asset Management",      "sector": "Finance"},
    "CHOLAFIN.NS":   {"name": "Cholamandalam Investment",   "sector": "Finance"},
    "SHRIRAMFIN.NS": {"name": "Shriram Finance",            "sector": "Finance"},
    "PFC.NS":        {"name": "Power Finance Corporation",  "sector": "Finance"},
    "RECLTD.NS":     {"name": "REC Limited",                "sector": "Finance"},
    "BAJAJHLDNG.NS": {"name": "Bajaj Holdings",             "sector": "Finance"},
    "IRFC.NS":       {"name": "Indian Railway Finance Corp","sector": "Finance"},

    # ── Auto & Auto Ancillaries ───────────────────────────────────────────────
    "MARUTI.NS":     {"name": "Maruti Suzuki",              "sector": "Auto"},
    "TATAMOTORS.NS": {"name": "Tata Motors",                "sector": "Auto"},
    "BAJAJ-AUTO.NS": {"name": "Bajaj Auto",                 "sector": "Auto"},
    "EICHERMOT.NS":  {"name": "Eicher Motors",              "sector": "Auto"},
    "HEROMOTOCO.NS": {"name": "Hero MotoCorp",              "sector": "Auto"},
    "M&M.NS":        {"name": "Mahindra & Mahindra",        "sector": "Auto"},
    "TVSMOTOR.NS":   {"name": "TVS Motor Company",          "sector": "Auto"},
    "MOTHERSON.NS":  {"name": "Samvardhana Motherson",      "sector": "Auto"},
    "MRF.NS":        {"name": "MRF",                        "sector": "Auto"},
    "BOSCHLTD.NS":   {"name": "Bosch India",                "sector": "Auto"},

    # ── Pharma / Healthcare ───────────────────────────────────────────────────
    "SUNPHARMA.NS":  {"name": "Sun Pharmaceutical",         "sector": "Pharma"},
    "DRREDDY.NS":    {"name": "Dr. Reddy's Laboratories",   "sector": "Pharma"},
    "CIPLA.NS":      {"name": "Cipla",                      "sector": "Pharma"},
    "DIVISLAB.NS":   {"name": "Divi's Laboratories",        "sector": "Pharma"},
    "LUPIN.NS":      {"name": "Lupin",                      "sector": "Pharma"},
    "TORNTPHARM.NS": {"name": "Torrent Pharmaceuticals",    "sector": "Pharma"},
    "AUROPHARMA.NS": {"name": "Aurobindo Pharma",           "sector": "Pharma"},
    "ZYDUSLIFE.NS":  {"name": "Zydus Lifesciences",         "sector": "Pharma"},
    "APOLLOHOSP.NS": {"name": "Apollo Hospitals",           "sector": "Healthcare"},
    "MAXHEALTH.NS":  {"name": "Max Healthcare Institute",   "sector": "Healthcare"},

    # ── FMCG / Consumer Staples ───────────────────────────────────────────────
    "HINDUNILVR.NS": {"name": "Hindustan Unilever",         "sector": "FMCG"},
    "ITC.NS":        {"name": "ITC",                        "sector": "FMCG"},
    "NESTLEIND.NS":  {"name": "Nestle India",               "sector": "FMCG"},
    "BRITANNIA.NS":  {"name": "Britannia Industries",       "sector": "FMCG"},
    "ASIANPAINT.NS": {"name": "Asian Paints",               "sector": "FMCG"},
    "COLPAL.NS":     {"name": "Colgate-Palmolive India",    "sector": "FMCG"},
    "GODREJCP.NS":   {"name": "Godrej Consumer Products",   "sector": "FMCG"},
    "MARICO.NS":     {"name": "Marico",                     "sector": "FMCG"},
    "DABUR.NS":      {"name": "Dabur India",                "sector": "FMCG"},
    "TATACONSUM.NS": {"name": "Tata Consumer Products",     "sector": "FMCG"},
    "VBL.NS":        {"name": "Varun Beverages",            "sector": "FMCG"},

    # ── Energy / Power / Oil & Gas ────────────────────────────────────────────
    "RELIANCE.NS":   {"name": "Reliance Industries",        "sector": "Energy"},
    "ONGC.NS":       {"name": "Oil & Natural Gas Corp",     "sector": "Energy"},
    "BPCL.NS":       {"name": "Bharat Petroleum",           "sector": "Energy"},
    "IOC.NS":        {"name": "Indian Oil Corporation",     "sector": "Energy"},
    "POWERGRID.NS":  {"name": "Power Grid Corp",            "sector": "Energy"},
    "NTPC.NS":       {"name": "NTPC",                       "sector": "Energy"},
    "TATAPOWER.NS":  {"name": "Tata Power",                 "sector": "Energy"},
    "ADANIGREEN.NS": {"name": "Adani Green Energy",         "sector": "Energy"},
    "ADANIPOWER.NS": {"name": "Adani Power",                "sector": "Energy"},
    "JSWENERGY.NS":  {"name": "JSW Energy",                 "sector": "Energy"},
    "GAIL.NS":       {"name": "GAIL India",                 "sector": "Energy"},
    "PETRONET.NS":   {"name": "Petronet LNG",               "sector": "Energy"},
    "NHPC.NS":       {"name": "NHPC",                       "sector": "Energy"},

    # ── Metals & Mining ───────────────────────────────────────────────────────
    "TATASTEEL.NS":  {"name": "Tata Steel",                 "sector": "Metals"},
    "HINDALCO.NS":   {"name": "Hindalco Industries",        "sector": "Metals"},
    "JSWSTEEL.NS":   {"name": "JSW Steel",                  "sector": "Metals"},
    "SAIL.NS":       {"name": "Steel Authority of India",   "sector": "Metals"},
    "COALINDIA.NS":  {"name": "Coal India",                 "sector": "Metals"},
    "VEDL.NS":       {"name": "Vedanta",                    "sector": "Metals"},
    "NMDC.NS":       {"name": "NMDC",                       "sector": "Metals"},
    "HINDZINC.NS":   {"name": "Hindustan Zinc",             "sector": "Metals"},

    # ── Infra / Cement / Capital Goods ───────────────────────────────────────
    "LT.NS":         {"name": "Larsen & Toubro",            "sector": "Infra"},
    "ADANIPORTS.NS": {"name": "Adani Ports & SEZ",          "sector": "Infra"},
    "ULTRACEMCO.NS": {"name": "UltraTech Cement",           "sector": "Infra"},
    "GRASIM.NS":     {"name": "Grasim Industries",          "sector": "Infra"},
    "AMBUJACEM.NS":  {"name": "Ambuja Cements",             "sector": "Infra"},
    "ADANIENT.NS":   {"name": "Adani Enterprises",          "sector": "Infra"},
    "SIEMENS.NS":    {"name": "Siemens India",              "sector": "Infra"},
    "ABB.NS":        {"name": "ABB India",                  "sector": "Infra"},
    "BEL.NS":        {"name": "Bharat Electronics",         "sector": "Infra"},
    "BHEL.NS":       {"name": "Bharat Heavy Electricals",   "sector": "Infra"},
    "HAVELLS.NS":    {"name": "Havells India",              "sector": "Infra"},
    "POLYCAB.NS":    {"name": "Polycab India",              "sector": "Infra"},
    "PIDILITIND.NS": {"name": "Pidilite Industries",        "sector": "Infra"},

    # ── Consumer Discretionary / Retail ──────────────────────────────────────
    "TITAN.NS":      {"name": "Titan Company",              "sector": "Consumer"},
    "DMART.NS":      {"name": "Avenue Supermarts (DMart)",  "sector": "Consumer"},
    "TRENT.NS":      {"name": "Trent",                      "sector": "Consumer"},
    "PAGEIND.NS":    {"name": "Page Industries",            "sector": "Consumer"},
    "VOLTAS.NS":     {"name": "Voltas",                     "sector": "Consumer"},
    "IRCTC.NS":      {"name": "IRCTC",                      "sector": "Consumer"},

    # ── Telecom ───────────────────────────────────────────────────────────────
    "BHARTIARTL.NS": {"name": "Bharti Airtel",              "sector": "Telecom"},

    # ── New-age / Internet ────────────────────────────────────────────────────
    "ZOMATO.NS":     {"name": "Zomato",                     "sector": "Consumer"},
    "NYKAA.NS":      {"name": "FSN E-Commerce (Nykaa)",     "sector": "Consumer"},

    # ── Media ─────────────────────────────────────────────────────────────────
    "SUNTV.NS":      {"name": "Sun TV Network",             "sector": "Media"},

}
