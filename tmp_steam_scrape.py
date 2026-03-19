import urllib.request
import re

url = "https://store.steampowered.com/search/results/?term=Next+Fest&count=4"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
}

try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as response:
        html = response.read().decode('utf-8', errors='ignore')
        
        # Steam search results are HTML chunks
        # <a href=".../app/(\d+)/" ...
        # <span class="title">(.*?)</span>
        # <img src="(.*?)"
        
        items = re.findall(r'<a.*?href=\"(https://store\.steampowered\.com/app/(\d+)/.*?)\".*?title\">(.*?)</span>.*?<img.*?src=\"(.*?)\"', html, re.DOTALL)
        
        print(f"Items found: {len(items)}")
        for i, item in enumerate(items):
            link, appid, title, img = item
            print(f"{i+1}. {title} (ID: {appid})")
            print(f"   Link: {link}")
            print(f"   Img: {img}")

except Exception as e:
    print(f"Error: {e}")
