import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Python"))

from tools.search.providers.brave import BraveHTMLProvider

provider = BraveHTMLProvider()
results = provider.search("harga saham Micron Technology hari ini", max_results=5)
print(f"Berhasil! {len(results)} hasil:\n")
for i, r in enumerate(results, 1):
    print(f"{i}. {r['title']}")
    print(f"   {r['snippet'][:100]}")
    print(f"   URL: {r['url']}")
    print()
