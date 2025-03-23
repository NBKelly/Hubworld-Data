#scrape and download
python3 setup/scrape.py
mogrify -format png img/*.webp
rm img/*.webp
clj -X:combine
