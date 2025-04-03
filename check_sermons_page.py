import urllib.request

# Access the sermons page to trigger our debug logging
try:
    with urllib.request.urlopen('http://localhost:5022/sermons') as response:
        html = response.read()
    print("Successfully accessed sermons page")
except Exception as e:
    print(f"Error accessing page: {e}")