import os
from flask import Flask, jsonify, request
from supabase import create_client, Client

app = Flask(__name__)

# =========================================================
# SUPABASE CONFIG
# =========================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        supabase = create_client(
            SUPABASE_URL,
            SUPABASE_SERVICE_KEY
        )
        print("[SUPABASE] Client initialized successfully.")
    except Exception as e:
        print("[SUPABASE] Client initialization failed:", str(e))
else:
    print("[SUPABASE] Environment variables are missing.")


# =========================================================
# HELPERS
# =========================================================

def success_response(data):
    return jsonify({
        "success": True,
        "data": data
    })


def error_response(message, status_code=500):
    return jsonify({
        "success": False,
        "error": message
    }), status_code


def check_supabase():
    if supabase is None:
        return False
    return True


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/")
def home():
    return jsonify({
        "success": True,
        "app": "GK Tricks Hindi API",
        "status": "online"
    })


@app.route("/health")
def health():
    return jsonify({
        "success": True,
        "status": "healthy"
    })


# =========================================================
# GET ALL PUBLISHED PDFs
# =========================================================

@app.route("/api/pdfs", methods=["GET"])
def get_pdfs():
    if not check_supabase():
        return error_response(
            "Supabase is not configured.",
            500
        )

    try:
        result = (
            supabase
            .table("pdfs")
            .select(
                "id,title,subject,description,"
                "file_url,thumbnail_url,"
                "is_featured,is_published,"
                "download_count,created_at"
            )
            .eq("is_published", True)
            .order("created_at", desc=True)
            .execute()
        )

        return success_response(result.data)

    except Exception as e:
        print("[API] /api/pdfs error:", str(e))
        return error_response(
            "Unable to load PDFs.",
            500
        )


# =========================================================
# GET SINGLE PDF
# =========================================================

@app.route("/api/pdfs/<pdf_id>", methods=["GET"])
def get_pdf(pdf_id):
    if not check_supabase():
        return error_response(
            "Supabase is not configured.",
            500
        )

    try:
        result = (
            supabase
            .table("pdfs")
            .select(
                "id,title,subject,description,"
                "file_url,thumbnail_url,"
                "is_featured,is_published,"
                "download_count,created_at"
            )
            .eq("id", pdf_id)
            .eq("is_published", True)
            .limit(1)
            .execute()
        )

        if not result.data:
            return error_response(
                "PDF not found.",
                404
            )

        return success_response(result.data[0])

    except Exception as e:
        print("[API] /api/pdfs/<id> error:", str(e))
        return error_response(
            "Unable to load PDF.",
            500
        )


# =========================================================
# GET SUBJECTS
# =========================================================

@app.route("/api/subjects", methods=["GET"])
def get_subjects():
    if not check_supabase():
        return error_response(
            "Supabase is not configured.",
            500
        )

    try:
        result = (
            supabase
            .table("pdfs")
            .select("subject")
            .eq("is_published", True)
            .execute()
        )

        subjects = sorted({
            item.get("subject", "").strip()
            for item in result.data
            if item.get("subject")
        })

        return success_response(subjects)

    except Exception as e:
        print("[API] /api/subjects error:", str(e))
        return error_response(
            "Unable to load subjects.",
            500
        )


# =========================================================
# GET PDFs BY SUBJECT
# =========================================================

@app.route("/api/subjects/<path:subject>/pdfs", methods=["GET"])
def get_pdfs_by_subject(subject):
    if not check_supabase():
        return error_response(
            "Supabase is not configured.",
            500
        )

    try:
        result = (
            supabase
            .table("pdfs")
            .select(
                "id,title,subject,description,"
                "file_url,thumbnail_url,"
                "is_featured,is_published,"
                "download_count,created_at"
            )
            .eq("subject", subject)
            .eq("is_published", True)
            .order("created_at", desc=True)
            .execute()
        )

        return success_response(result.data)

    except Exception as e:
        print("[API] subject PDFs error:", str(e))
        return error_response(
            "Unable to load subject PDFs.",
            500
        )


# =========================================================
# SEARCH PDFs
# =========================================================

@app.route("/api/search", methods=["GET"])
def search_pdfs():
    if not check_supabase():
        return error_response(
            "Supabase is not configured.",
            500
        )

    query = request.args.get("q", "").strip()

    if not query:
        return success_response([])

    # Basic protection against malformed PostgREST filter input.
    query = (
        query
        .replace("%", "")
        .replace(",", " ")
        .replace("(", " ")
        .replace(")", " ")
    )

    if not query:
        return success_response([])

    try:
        search_pattern = f"%{query}%"

        result = (
            supabase
            .table("pdfs")
            .select(
                "id,title,subject,description,"
                "file_url,thumbnail_url,"
                "is_featured,is_published,"
                "download_count,created_at"
            )
            .eq("is_published", True)
            .or_(
                f"title.ilike.{search_pattern},"
                f"subject.ilike.{search_pattern},"
                f"description.ilike.{search_pattern}"
            )
            .order("created_at", desc=True)
            .execute()
        )

        return success_response(result.data)

    except Exception as e:
        print("[API] search error:", str(e))
        return error_response(
            "Search failed.",
            500
        )


# =========================================================
# FEATURED PDFs
# =========================================================

@app.route("/api/featured", methods=["GET"])
def get_featured():
    if not check_supabase():
        return error_response(
            "Supabase is not configured.",
            500
        )

    try:
        result = (
            supabase
            .table("pdfs")
            .select(
                "id,title,subject,description,"
                "file_url,thumbnail_url,"
                "is_featured,is_published,"
                "download_count,created_at"
            )
            .eq("is_featured", True)
            .eq("is_published", True)
            .order("created_at", desc=True)
            .execute()
        )

        return success_response(result.data)

    except Exception as e:
        print("[API] featured error:", str(e))
        return error_response(
            "Unable to load featured PDFs.",
            500
        )


# =========================================================
# 404
# =========================================================

@app.errorhandler(404)
def not_found(error):
    return error_response(
        "API endpoint not found.",
        404
    )


# =========================================================
# ERROR HANDLER
# =========================================================

@app.errorhandler(500)
def internal_error(error):
    return error_response(
        "Internal server error.",
        500
    )


# =========================================================
# LOCAL RUN
# =========================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=False
    )