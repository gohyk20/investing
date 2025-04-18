from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import sys


def save_login_context():
    #login and save context for use
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://quickfs.net/")
        input("Press Enter after loggin in...")
        context.storage_state(path="state.json")


def get_pages(url):
    #use playwright to load the page javascript, get overview then balance sheet and cash flow
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state="state.json")
        page = context.new_page()
        page.goto(url)
        page.wait_for_selector("#ovr-table")  # wait for the page to load, both table and pe ratio
        page.wait_for_function("""()=>{
                const pe = document.querySelector('#ks-pe')
                return pe && pe.textContent.length > 0}""")
        overview_html = page.content()
        page.click(".selectDropdown") #click the dropdown to load balance sheet
        page.click("a#bs")
        page.wait_for_selector("#bs-table")
        bs_html = page.content()
        page.click(".selectDropdown") #click the dropdown to load cash flow
        page.click("a#cf")
        page.wait_for_selector("#cf-table")
        cf_html = page.content()

    #parse the overview html with BeautifulSoup
    soup = BeautifulSoup(overview_html, 'html.parser')
    bs = BeautifulSoup(bs_html, 'html.parser')
    cf = BeautifulSoup(cf_html, 'html.parser')
    #print(soup.prettify())

    return soup, bs, cf


def parse_pages(soup, bs, cf):
    #from the overview table, get ROIC, EPS, Revenue, and P/E ration
    PEratio = float(soup.select_one("#ks-pe").text)
    ROIC = []
    EPS = []
    REVENUE = []
    table_data = soup.select("#ovr-table > tbody > tr")
    for row in table_data:
        if row.contents[0].text == "Revenue": #first column is the name of the metric
            for d in row.contents[1:]:
                REVENUE.append(int(d.text.replace(',', '')))
        elif row.contents[0].text == "Earnings Per Share":
            for d in row.contents[1:]:
                EPS.append(float(d.text.strip('$')))
        elif row.contents[0].text == "Return on Invested Capital":
            for d in row.contents[1:]:
                if d.text != "-":
                    ROIC.append(float(d.text.strip("%")))
    print(f"ROIC: {ROIC}")
    print(f"EPS: {EPS}")
    print(f"REVENUE: {REVENUE}")
    print(f"PEratio: {PEratio}")


    #parse balance sheet for equity
    EQUITY = []
    table_data = bs.select("#bs-table >tbody > tr")
    for row in table_data:
        if row.contents[0].text == "Total Assets": #first column is the name of the metric
            for d in row.contents[1:]:
                if d.text != "-":
                    EQUITY.append(int(d.text.replace(',', '')))
    print(f"EQUITY: {EQUITY}")


    #parse cash flow for free cash flow
    FCF = []
    table_data = cf.select("#cf-table >tbody > tr")
    for row in table_data:
        if row.contents[0].text == "Free Cash Flow": #first column is the name of the metric
            for d in row.contents[1:-1]: #last column is trailing twelve months
                if d.text != "-":
                    FCF.append(int(d.text.replace(',', '')))
    print(f"FCF: {FCF}")

    #calculate average ROIC
    print(f"\naverage ROIC (last 3 years): {sum(ROIC[-3:])/3:.2f}%")
    print(f"average ROIC (last 5 years): {sum(ROIC[-5:])/3:.2f}%")
    print(f"average ROIC (last {len(ROIC)} years): {sum(ROIC)/len(ROIC):.2f}%")

    #calculate 1-5-10 year annual growth rates for revenue, equity, fcf, and eps
    print(f"\nRevenue growth rate:")
    print(f"past one year: {calculate_growth_rate(1, REVENUE[-2], REVENUE[-1])*100:.2f}%")
    print(f"past five years: {calculate_growth_rate(5, REVENUE[-6], REVENUE[-1])*100:.2f}%")
    print(f"past {len(REVENUE)-1} years: {calculate_growth_rate(len(REVENUE)-1, REVENUE[0], REVENUE[-1])*100:.2f}%")
    print(f"\nEquity growth rate:")
    print(f"past one year: {calculate_growth_rate(1, EQUITY[-2], EQUITY[-1])*100:.2f}%")
    print(f"past five years: {calculate_growth_rate(5, EQUITY[-6], EQUITY[-1])*100:.2f}%")
    print(f"past {len(EQUITY)-1} years: {calculate_growth_rate(len(EQUITY)-1, EQUITY[0], EQUITY[-1])*100:.2f}%")
    print(f"\nEPS growth rate:")
    print(f"past one year: {calculate_growth_rate(1, EPS[-2], EPS[-1])*100:.2f}%")
    print(f"past five years: {calculate_growth_rate(5, EPS[-6], EPS[-1])*100:.2f}%")
    print(f"past {len(EPS)-1} years: {calculate_growth_rate(len(EPS)-1, EPS[0], EPS[-1])*100:.2f}%")
    print(f"\nFCF growth rate:")
    print(f"past one year: {calculate_growth_rate(1, FCF[-2], FCF[-1])*100:.2f}%")
    print(f"past five years: {calculate_growth_rate(5, FCF[-6], FCF[-1])*100:.2f}%")
    print(f"past {len(FCF)-1} years: {calculate_growth_rate(len(FCF)-1, FCF[0], FCF[-1])*100:.2f}%")

    #calculate sticker price and MOS price
    print("\ncalculating sticker price...")
    sticker_price = calculate_sticker_price(
        EPS[-1],
        calculate_growth_rate(len(EQUITY)-1, EQUITY[0], EQUITY[-1]), #growth rate take equity growth rate, change to others if needed
        min(PEratio, calculate_growth_rate(len(EQUITY)-1, EQUITY[0], EQUITY[-1])*200), #take lower of pe ratio or growth rate * 2
        0.15 #15% return
    )
    print(f"sticker price: ${sticker_price:.2f}")
    print(f"Margin of safety price: ${sticker_price*0.5:.2f}") #50% of sticker price


def calculate_growth_rate(years, start, end):
    #calculate annual growth between start and end
    #end = start * growth_rate^years
    growth = (end/start)**(1/years) - 1
    return growth


def calculate_sticker_price(eps, growth, pe, return_rate):
    print(f"EPS: {eps}, growth: {growth}, PE: {pe}, return_rate: {return_rate}")
    estimated_future_price = eps * (1+growth)**10 * pe #calculate price after ten years
    sticker_price = estimated_future_price / (1+return_rate)**10 #if u want it to earn return_rate amount every year
    return sticker_price



if __name__ == "__main__":
    #save_login_context() #run this once to save the login context
    sys.stdout = open('logfile.txt', 'w') #for saving the outputs
    url = "https://quickfs.net/company/YUM:US" #set this url of the correct company
    print(f"scraping {url}...\n")
    soup, bs, cf = get_pages(url)
    report = parse_pages(soup, bs, cf)

