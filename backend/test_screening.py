"""Fast, offline checks for scoring + chat intent (no DB, no LLM, no network). Run: pytest backend/test_screening.py"""
import screening as s
import chat_engine as c

TEXT = "Rahul Kumar\nrahul@x.com\nBuilt an enterprise RAG application using LangChain on AWS.\n5 years of experience in Python."
REQS = [
    {"name": "Python", "type": "required", "query": ""},
    {"name": "RAG", "type": "required", "query": ""},
    {"name": "Kubernetes", "type": "required", "query": ""},
    {"name": "Experience: 3-5 years", "type": "experience", "query": ""},
]


def analyse(parsed):
    return s.finalize_analysis(parsed, TEXT, "rahul.pdf", REQS, "llm")


def test_fabricated_quote_is_not_trusted():
    parsed = {"requirements": [{"index": 2, "status": "met", "evidence": "Led a Kubernetes migration", "note": ""}]}
    k = next(r for r in analyse(parsed)["requirement_results"] if r["name"] == "Kubernetes")
    assert k["status"] == "missing" and k["evidence"] == ""


def test_literal_skill_in_resume_overrides_model_miss():
    r = next(x for x in analyse({"requirements": []})["requirement_results"] if x["name"] == "RAG")
    assert r["status"] == "met" and "RAG" in r["evidence"]


def test_experience_is_computed_from_years_not_model_opinion():
    out = analyse({"experience_years": 5, "requirements": [{"index": 3, "status": "missing", "evidence": "", "note": ""}]})
    assert next(x for x in out["requirement_results"] if x["type"] == "experience")["status"] == "met"


def test_score_and_tier():
    out = analyse({})  # Python, RAG, experience met; Kubernetes missing -> 3 of 4
    assert out["match_percent"] == 75.0 and out["tier"] == "good"


def test_tier_boundaries():
    assert [s.tier_for(p) for p in (80, 79.9, 65, 45, 44.9)] == ["strong", "good", "good", "partial", "low"]


def test_aliases_do_not_expand_backwards():
    assert s.text_has_term("used AWS Lambda", "aws")
    assert not s.text_has_term("wrote a lambda function", "aws")


def test_chat_intent_follow_ups():
    i = c.heuristic_intent("Which of these have AWS?", [])
    assert i["scope"] == "previous" and i["terms"] == ["AWS"]
    i = c.heuristic_intent("Find other candidates with the same RAG requirement but without AWS", [])
    assert i["terms"] == ["RAG"] and i["exclude_terms"] == ["AWS"] and i["exclude_previous"]
    i = c.heuristic_intent("Find candidates with 5+ years", [])
    assert i["min_years"] == 5 and i["terms"] == []
