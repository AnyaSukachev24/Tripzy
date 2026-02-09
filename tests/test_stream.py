import requests
import json
# import sseclient

url = "http://127.0.0.1:8000/api/stream"
payload = {"prompt": "i want to go with my husband to honey moon. about 2 weeks, up to 5000 $ for both of us. give me ideas", "thread_id": "debug_complex"}
headers = {"Content-Type": "application/json"}

print(f"Connecting to {url}...")
try:
    with requests.post(url, json=payload, headers=headers, stream=True) as r:
        print(f"Status Code: {r.status_code}")
        if r.status_code != 200:
            print(f"Error: {r.text}")
            exit(1)
            
        print("--- Stream Content ---")
        for line in r.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                print(decoded_line)
except Exception as e:
    print(f"Exception: {e}")
