import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_upgrade_preserves_legacy_projects_documents_and_vectors(tmp_path):
    root=Path(__file__).resolve().parents[2]
    database=tmp_path/"legacy.db"
    env={**os.environ,"DATABASE_URL":"sqlite:///"+database.as_posix(),"EMBEDDING_PROVIDER":"local"}
    command=[sys.executable,"-m","alembic","-c","backend/alembic.ini","upgrade"]
    subprocess.run(command+["0001"],cwd=root,env=env,capture_output=True,text=True,check=True)
    source=tmp_path/"original-source.txt";source.write_bytes(b"private pre-migration source")
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("INSERT INTO users VALUES (?,?,?,?)",("u","legacy@example.com","disabled",1.0))
        db.execute("INSERT INTO projects (id,owner_id,name,description,pipeline,pipeline_version,widget,widget_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?)",("p","u","Legacy project","existing work",json.dumps({"strategy":"hybrid"}),1,"{}",None,1.0))
        db.execute("INSERT INTO documents (id,project_id,name,kind,storage_name,sha256,size_bytes,status,error,chunk_count,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",("d","p","old.txt","txt","original-source.txt","a"*64,27,"ready",None,1,"{}",1.0))
        vector=json.dumps([0.0]*384)
        db.execute("INSERT INTO chunks (id,project_id,document_id,ordinal,text,locator,embedding,embedding_model,pipeline_version) VALUES (?,?,?,?,?,?,?,?,?)",("c","p","d",0,"existing private passage","{}",vector,"local:hash-v1:384",1))
    subprocess.run(command+["head"],cwd=root,env=env,capture_output=True,text=True,check=True)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT name,index_profile,index_generation FROM projects").fetchone()==("Legacy project",None,0)
        assert db.execute("SELECT text,embedding,embedding_model FROM chunks").fetchone()==("existing private passage",vector,"local:hash-v1:384")
        assert db.execute("SELECT status FROM documents").fetchone()==("ready",)
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()==("0002",)
    assert source.read_bytes()==b"private pre-migration source"
