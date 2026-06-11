#ITCL_integrated/pipeline.py
from ITCL.pipeline import run_law_pipeline
from ITCL_integrated.run import run_integrated_full_pipeline
from ITCL_integrated.merge import merge_reasoning_with_alignment
from ITCL_integrated.ingest import IntegratedIngestContext, run_full_integrated_ingest
from ITCL_integrated.connect_rs_to_article import ingest_reasoning_steps
import json
from neo4j import GraphDatabase
import os
import dotenv
dotenv.load_dotenv()

URI = os.getenv("NEO4J_URI", "neo4j+s://3dfa7316.databases.neo4j.io")
AUTH = ("neo4j", os.getenv("NEO4J_PASSWORD", "password"))

driver = GraphDatabase.driver(URI, auth=AUTH)

def run_full_analysis_pipeline(
    *,
    driver,
    law_drf_path: str,
    admrul_drf_path: str,
    rule_drf_path: str,
    snapshot:dict,
):
    # --------------------
    # 1) LAW
    # --------------------
    law = run_law_pipeline(
        drf_json_path=law_drf_path,
        snapshot=snapshot,
        law_drf_path=law_drf_path,
    )

    admrul = run_law_pipeline(
        drf_json_path=admrul_drf_path,
        snapshot=snapshot,
        law_drf_path=law_drf_path,   # 🔑 항상 LAW 기준
    )

    rule = run_law_pipeline(
        drf_json_path=rule_drf_path,
        snapshot=snapshot,
        law_drf_path=law_drf_path, 
    )

    # --------------------
    # 2) Integrated LLM
    # --------------------
    integrated = run_integrated_full_pipeline(
        law=law,
        admrul=admrul,
        rule=rule,
    )

    # --------------------
    # 2.5) Merge (LLM 결과 정합)
    # --------------------
    merged_reasoning = merge_reasoning_with_alignment(
        prefix="ITCL_integrated",
        set_key=integrated["set_key"],
    )

    # --------------------
    # 3) Integrated ingest (구조 생성)
    # --------------------
    ctx = IntegratedIngestContext(
        semantic_dict=integrated["semantic"],
        reasoning_dict=integrated["reasoning"],
        reasoning_enriched_path=f"cache/ITCL_integrated/{integrated['set_key']}/05_reasoning_enriched.json",
        set_key=integrated["set_key"],
    )

    run_full_integrated_ingest(driver, ctx, snapshot=snapshot)


    # --------------------
    # 4) 🔗 ReasoningStep → Article / LawTarget 연결
    # --------------------
    ingest_reasoning_steps(
        driver,
        reasoning_json=merged_reasoning,
        set_key=integrated["set_key"],
    )

    return integrated



