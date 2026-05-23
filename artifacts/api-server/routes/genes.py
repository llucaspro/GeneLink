import requests as http_req
from flask import Blueprint, request, jsonify
from routes.auth import token_required
from db.connection import get_connection

genes_bp = Blueprint("genes", __name__)

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_TIMEOUT = 15


@genes_bp.route("/search-gene", methods=["GET"])
@token_required
def search_gene():
    query = (request.args.get("q") or "").strip()
    max_results = min(int(request.args.get("max", 20)), 50)

    if not query:
        return jsonify({"error": "Search query is required"}), 400
    if len(query) < 2:
        return jsonify({"error": "Query must be at least 2 characters"}), 400

    try:
        search_resp = http_req.get(
            f"{NCBI_BASE}/esearch.fcgi",
            params={
                "db": "gene",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
            },
            timeout=NCBI_TIMEOUT,
        )
        search_resp.raise_for_status()
        search_data = search_resp.json()
    except http_req.exceptions.Timeout:
        return jsonify({"error": "NCBI API timeout. Please try again."}), 504
    except http_req.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach NCBI API. Check your connection."}), 502
    except Exception as e:
        return jsonify({"error": f"NCBI search request failed: {str(e)}"}), 502

    esearch = search_data.get("esearchresult", {})
    id_list = esearch.get("idlist", [])
    total = int(esearch.get("count", 0))

    if not id_list:
        _log_search(request.user_id, query, 0)
        return jsonify({"results": [], "total": 0, "query": query})

    try:
        summary_resp = http_req.get(
            f"{NCBI_BASE}/esummary.fcgi",
            params={
                "db": "gene",
                "id": ",".join(id_list),
                "retmode": "json",
            },
            timeout=NCBI_TIMEOUT,
        )
        summary_resp.raise_for_status()
        summary_data = summary_resp.json()
    except http_req.exceptions.Timeout:
        return jsonify({"error": "NCBI summary API timeout. Please try again."}), 504
    except Exception as e:
        return jsonify({"error": f"NCBI summary request failed: {str(e)}"}), 502

    result_map = summary_data.get("result", {})
    genes = []
    for gene_id in id_list:
        if gene_id not in result_map:
            continue
        g = result_map[gene_id]
        if isinstance(g, str):
            continue
        organism = g.get("organism", {})
        genes.append({
            "id": gene_id,
            "name": g.get("name") or "N/A",
            "description": g.get("description") or "No description available",
            "organism_common": organism.get("commonname") or "",
            "organism_scientific": organism.get("scientificname") or "N/A",
            "chromosome": g.get("chromosome") or "N/A",
            "location": g.get("maplocation") or "",
            "status": g.get("status") or "",
            "summary": (g.get("summary") or "")[:600],
            "uid": g.get("uid") or gene_id,
        })

    _log_search(request.user_id, query, len(genes))
    return jsonify({"results": genes, "total": total, "query": query, "returned": len(genes)})


@genes_bp.route("/search-history", methods=["GET"])
@token_required
def search_history():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT query, result_count, searched_at FROM gene_searches
               WHERE user_id = %s ORDER BY searched_at DESC LIMIT 20""",
            (request.user_id,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception:
        return jsonify([])


def _log_search(user_id, query, count):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO gene_searches (user_id, query, result_count) VALUES (%s, %s, %s)",
            (user_id, query, count),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass
