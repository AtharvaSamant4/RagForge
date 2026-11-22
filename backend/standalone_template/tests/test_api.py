"""Run against the deployed standalone API; real runtime, not mocked responses."""
import os
from pathlib import Path
import httpx

URL=os.environ.get("STANDALONE_URL","http://localhost:8020")
KEY=os.environ.get("STANDALONE_API_KEY") or (Path(__file__).resolve().parents[1]/".standalone-key").read_text().strip()


def test_authenticated_runtime():
    with httpx.Client(base_url=URL,headers={"Authorization":"Bearer "+KEY},timeout=120) as client:
        assert client.get("/health").json()["runtime"]=="standalone"
        assert httpx.get(URL+"/v1/config").status_code==401
        assert client.get("/v1/config").status_code==200
        response=client.post("/v1/query",json={"question":"What is the refund period?"})
        assert response.status_code==200,response.text
        result=response.json()
        for citation in result["citations"]:
            assert citation["quote"] in citation["text"]
            assert citation["document_name"]
