## pre-requisites: requests_html, bs4

from requests_html import HTMLSession
from bs4 import BeautifulSoup

import os
import re
import pprint
import threading
import queue

URL = "https://decksmith.app/hubworldaidalon/cards/prime-collective/"

with open("setup/urls.data", "r") as urls:
    IDS = [line.rstrip() for line in urls]

def slugify(s):
    return re.sub(r'[^a-zA-Z]+', '-', s.lower().strip())

def unslug(s):
    return re.sub(r'-', ' ', s[1:]).capitalize()

def unslug_title(s):
    return re.sub(r'-', ' ', s[1:]).title()

def fix_quotes(s):
    return s.replace('"', '\\"')

def tokenize(s):
    s = s.replace('(Action Action)', '[Click][Click]')
    s = s.replace('(Action)', '[Click]')
    s = s.replace('(Instant)', '[Instant]')
    s = s.replace('(Reaction)', '[Reaction]')
    s = s.replace('(Confront)', '[Confront]')
    s = s.replace('(Discover)', '[Discover]')
    s = s.replace('Shard', '[Credit]')
    s = s.replace('Heat', '[Heat]')
    return s

def get_title(soup, card):
    data = soup.find('h1', class_="text-3xl")
    titles = data.find_all("div")
    if len(titles) == 2:
        subtitle = titles[1].get_text().strip()
        card[':subtitle'] = subtitle
        subtitle = ": " + subtitle
    else:
        subtitle = ""
        card[':subtitle'] = ""
    #"·"

    title = titles[0].get_text().strip()
    if title.startswith('·'):
        title = title[1:]
        card[':uniqueness'] = True
    else:
        card[':uniqueness'] = False

    card[':title'] = title + subtitle
    card[':stripped-title'] = title + subtitle
    card[':alias'] = title
    card[':id'] = slugify(title + subtitle)


    return card

download_queue = queue.Queue()

def download_worker():
    while True:
        cmd = download_queue.get()
        if cmd is None:
            break
        print(cmd[0])
        os.system(cmd[1])
        download_queue.task_done()

NUM_WORKERS = 4
threads = []
for _ in range(NUM_WORKERS):
    t = threading.Thread(target=download_worker, daemon=True)
    t.start()
    threads.append(t)

def get_image_url(soup, card):
    img_url = soup.find('img', class_='rounded-md')['src']
    card[':url'] = img_url
    return card

basic_keys = []
numeric_keys = ["Action Limit", "Draw Limit", "Shard Limit", "Shard Cost", "Barrier", "Presence"]
slugged_keys = ["Affiliation", "Type", "Collection Icons", "Set"]
list_keys = ["Traits"]
list_text_keys = ["Illustrator"]

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
            if text.startswith("Affiliation Icons"):
                return card
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
            card[":" + slugify(key)] = ', '.join(item for item in vals if re.match(r'[a-zA-Z]', item))
            return card

    print("Key Mismatch: ")
    print(row)
    print(card)
    print(text)
    exit()

def process_card_text(soup, card):
    texts = soup.find_all("p")

    text_blocks = [t.contents for t in texts][0]
    stripped_text = [t.get_text() for t in texts]

    card[':stripped-text'] = tokenize(fix_quotes(stripped_text[0]))
    card[':text'] = tokenize(fix_quotes("".join(str(t) for t in text_blocks)))

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

## now we have a set of all the cards... what can we do with that?
## lets try and produce something that looks like edn format

def format_key(v):
    if v == ":traits":
        return ":subtypes"
    return v

def format_value(v):
    if isinstance(v, str):
        if v.startswith(":"):
            return v
        return '"' + v + '"'
    if str(v).isnumeric():
        return str(v)
    if v == True:
        return "true"
    if v == False:
        return "nil"
    # it's a list
    return "[" + " ".join(format_value(val) for val in v) + "]"

def format_card(card, deck_lim=True):
    keys = sorted(card.keys())
    lines = []
    if deck_lim:
        if card.get(':type') == ":seeker" or card.get(':type') == ":agent":
            lines += [":deck-limit 1"]
        else:
            lines += [":deck-limit 2"]
    for key in keys:
        lines += [format_key(key) + " " + format_value(card[key])]
    return "{" + "\n ".join(lines) + "}"

code = 1000
position = 1

def stripped_card(card):
    c = dict(card)
    c.pop(':illustrator', None)
    c.pop(':url', None)
    return c

def format_set(card, code, position):
    set_card = {':card-id': card[':id'],
                ':code': "0" + str(code + position),
                ':position': position,
                ':illustrator': card.get(':illustrator', ["(unknown)"]),
                ':quantity': 1 if card[':type'] == ":seeker" or card[':type'] == ":agent" else 2,
                ':set-id': 'pre-release'}
    return format_card(set_card, deck_lim=None)

set_cards = []

types = set()
subtypes = set()
factions = set()

def set_identities(card):
    if card[':type'] == ":seeker":
        card[':base-link'] = 0
        card[':influence-limit'] = 15
        card[':minimum-deck-size'] = 36
    return card



for card in cards:
    card[":faction"] = card[":affiliation"]
    card.pop(":affiliation", None)
    card.pop(":set", None)
    formatted_card = format_card(stripped_card(card))
    f = open("edn/cards/" + card[':id'] + ".edn", "w")
    f.write(formatted_card + "\n")
    f.close()

    set_cards += [format_set(card, code, position)]
    card = set_identities(card)
#    print(card)
    types.add(card[':type'])
    factions.add(card[':faction'])
    for s in card[':traits']:
        subtypes.add(s)

    #print()
    download_queue.put(["Downloading " + card[':url'] + "...", 'wget -q -O img/' + "0" + str(code + position) + ".webp \"" + card[':url'] + '"'])
    position += 1
#    print(format_card(card))

download_queue.join()
for _ in threads:
    download_queue.put(None)
for t in threads:
    t.join()

# write the set-cards file
print("Writing set-cards/pre-release.edn...")
f = open("edn/set-cards/pre-release.edn", "w")
f.write("[\n " + "\n ".join(set_cards) + "]\n")
f.close()

# write the sets file
print("Writing sets.edn...")
sets = ['{:code "pre-release"\n  :cycle-id "pre-release"\n  :id "pre-release"\n  :name "Pre-Release"\n  :set-type :data-pack\n  :position 1\n  :size 25\n:data-release nil}']
f = open("edn/sets.edn", "w")
f.write("[" + "\n  ".join(sets) + "]\n")
f.close()

# write the cycles file
print("Writing cycles.edn...")
cycles = ['{:id "pre-release"\n  :name "Pre-Release"\n  :position 0\n  :rotated false\n  :size 1}']
f = open("edn/cycles.edn", "w")
f.write("[" + "\n  ".join(cycles) + "]\n")
f.close()

# write the formats file
print("Writing formats.edn...")
formats = ['{:id "pre-release"\n  :name "Pre-Release"\n  :sets ["pre-release"]\n  :mwl nil}']
f = open("edn/formats.edn", "w")
f.write("[" + "\n  ".join(formats) + "]\n")
f.close()

# write the types file
print("Writing types.edn...")
types_str = "(" + "\n ".join("{:id " + type + "\n  :name " + unslug(type) + "}" for type in sorted(types)) + ")\n"
f = open("edn/types.edn", "w")
f.write(types_str)
f.close()

# write the types file
print("Writing subtypes.edn...")
subtypes_str = "(" + "\n ".join("{:id " + type + "\n  :name \"" + unslug(type) + "\"}" for type in subtypes) + ")\n"
f = open("edn/subtypes.edn", "w")
f.write(subtypes_str)
f.close()

print("Writing factions.edn...")
factions_str = "(" + "\n ".join("{:id " + type + "\n  :name \"" + unslug_title(type) + "\"}" for type in factions) + ")\n"
f = open("edn/factions.edn", "w")
f.write(factions_str)
f.close()
