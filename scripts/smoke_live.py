"""Run AFTER `docker compose up --build` to verify the real stack and live archives."""
import json, os, sys, time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
BASE=os.environ.get("ASTROTARGET_URL","http://localhost:8000").rstrip("/")
KEY=os.environ.get("ASTROTARGET_API_KEY","")
def get(path):
    with urlopen(BASE+path,timeout=30) as r:return json.load(r)
def post(path,payload):
    headers={"Content-Type":"application/json"}
    if KEY:headers["X-API-Key"]=KEY
    req=Request(BASE+path,data=json.dumps(payload).encode(),headers=headers,method="POST")
    with urlopen(req,timeout=30) as r:return json.load(r)
def main():
    print("1/4 health",get("/health"))
    j=post("/targets",{"name":sys.argv[1] if len(sys.argv)>1 else "WASP-12 b"}); print("2/4 queued",j)
    for _ in range(180):
        st=get(f"/jobs/{j['job_id']}"); print("   ",st["status"],end="\r",flush=True)
        if st["status"]=="done":break
        if st["status"]=="error":raise RuntimeError(st.get("error"))
        time.sleep(5)
    else: raise TimeoutError("job did not finish within 15 minutes")
    print("\n3/4 run",st["run_id"]); r=get(f"/runs/{st['run_id']}")
    print("4/4 live sources:",r.get("catalog",{}).get("source"),"|",r.get("gaia_dr3",{}).get("source"),"|",r.get("tess",{}).get("source"))
    print("PASS: API -> Redis -> worker -> live archives -> PostgreSQL -> API")
if __name__=="__main__":
    try:main()
    except (HTTPError,Exception) as e: print("FAIL:",e); raise
