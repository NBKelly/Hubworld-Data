## pre-requisites: requests_html, bs4

from requests_html import HTMLSession
from bs4 import BeautifulSoup

import re
import pprint

URL = "https://decksmith.app/hubworldaidalon/cards/"

with open("setup/urls.data", "r") as urls:
    IDS = [line.rstrip() for line in urls]

def get_title(soup, card):
    data = soup.find('h1', class_="text-3xl")
    titles = data.find_all("div")

    #"·"
    title = titles[0].get_text().strip()
    if title.startswith('·'):
        title = title[1:]
        card[':uniqueness'] = True
    else:
        card[':uniqueness'] = False
    card[':title'] = title

    if len(titles) == 2:
        subtitle = titles[1].get_text().strip()
        card[':subtitle'] = subtitle

    return card

def get_image_url(soup, card):
    img_url = soup.find('img', class_='rounded-md')['src']
    card[':url'] = img_url
    return card

basic_keys = []
numeric_keys = ["Action Limit", "Draw Limit", "Shard Limit", "Shard Cost", "Barrier", "Presence"]
slugged_keys = ["Faction", "Type", "Collection Icons"]
list_keys = ["Traits"]
list_text_keys = ["Illustrator"]

def slugify(s):
    return re.sub(r'[^a-zA-Z]+', '-', s.lower().strip())

def process_row(row, card):
    text = row.get_text().strip()

    for key in basic_keys:
        if text.startswith(key):
            card[":" + slugify(key)] = text[len(key):].strip()
            return card

    for key in numeric_keys:
        if text.startswith(key):
            card[":" + slugify(key)] = int(text[len(key):].strip())
            return card

    for key in slugged_keys:
        if text.startswith(key):
            card[":" + slugify(key)] = ":" + slugify(text[len(key):].strip())
            return card

    for key in list_keys:
        if text.startswith(key):
            vals = re.split(r'   +', text[len(key):].strip())
            card[":" + slugify(key)] = [":" + slugify(item) for item in vals if re.match(r'[a-zA-Z]', item)]
            return card

    for key in list_text_keys:
        if text.startswith(key):
            vals = re.split(r'   +', text[len(key):].strip())
            card[":" + slugify(key)] = [item for item in vals if re.match(r'[a-zA-Z]', item)]
            return card

    print("Key Mismatch: ")
    print(row)
    print(card)
    exit()

def process_card_text(soup, card):
    texts = soup.find_all("p")

    text_blocks = [t.contents for t in texts][0]
    stripped_text = [t.get_text() for t in texts]

    card[':stripped-text'] = stripped_text[0]
    card[':text'] = "".join(str(t) for t in text_blocks)

    return card

cards = []

for ID in IDS:
    C_URL = URL + ID
    print(C_URL)
    card = {}
    session = HTMLSession()
    page = session.get(C_URL)
    soup = BeautifulSoup(page.content, "html.parser")

    ## get the url for the image
    card = get_image_url(soup, card)

    ## get the title and subtitle
    card = get_title(soup, card)

    ## process the bulk info
    rows = soup.find_all("div", class_='justify-between')
    for row in rows:
        card = process_row(row, card)

    ## get the card text
    card = process_card_text(soup, card)


    cards += [card]
    #print(card)

pprint.pp(cards)
