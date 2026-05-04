import time
import requests

BASE_URL = "http://127.0.0.1:8000"

token = input("Enter admin token: ").strip()

headers = {
    "Authorization": f"Bearer {token}"
}

start1 = time.time()
r1 = requests.get(f"{BASE_URL}/exams", headers=headers)
end1 = time.time()

start2 = time.time()
r2 = requests.get(f"{BASE_URL}/exams", headers=headers)
end2 = time.time()

print("First request source:", r1.json().get("source"))
print("First request time:", end1 - start1)

print("Second request source:", r2.json().get("source"))
print("Second request time:", end2 - start2)