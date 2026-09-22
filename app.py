import os
import re
import hmac
import hashlib
import base64
import time
import uuid
from functools import wraps

from flask import Flask, jsonify, request
from supabase import create_client, Client


app = Flask(__name__)

# =========================================================
# CONFIG
# =========================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_TOKEN_SECRET = os.getenv("ADMIN_TOKEN_SECRET")

STORAGE_BUCKET = "pdfs"

ADMIN_TOKEN_EXPIRY_SECONDS = 7 * 24 * 60 * 60


# =========================================================
# SUPABASE
# =========================================================

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        supabase = create_client(
            SUPABASE_URL,
            SUPABASE_SERVICE_KEY
        )
        print("[SUPABASE] Client initialized successfully.")
    except Exception as e:
        print(
            "[SUPABASE] Client initialization failed:",
            str(e)
        )
else:
    print(
        "[SUPABASE] SUPABASE_URL or "
        "SUPABASE_SERVICE_KEY is missing."
    )


# =========================================================
# RESPONSE HELPERS
# =========================================================

def success_response(data=None, message=None):
    response = {
        "success": True,
        "data": data
    }

    if message is not None:
        response["message"] = message

    return jsonify(response)


def error_response(message, status_code=500):
    return jsonify({
        "success": False,
        "error": message
    }), status_code


def check_supabase():
    return supabase is not None


# =========================================================
# ADMIN TOKEN
# =========================================================

def create_admin_token():
    if not ADMIN_TOKEN_SECRET:
        raise RuntimeError(
            "ADMIN_TOKEN_SECRET is not configured."
        )

    timestamp = str(int(time.time()))

    payload = f"admin:{timestamp}"

    signature = hmac.new(
        ADMIN_TOKEN_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    raw_token = f"{payload}:{signature}"

    return base64.urlsafe_b64encode(
        raw_token.encode("utf-8")
    ).decode("utf-8")


def verify_admin_token(token):
    if not token:
        return False

    if not ADMIN_TOKEN_SECRET:
        return False

    try:
        decoded = base64.urlsafe_b64decode(
            token.encode("utf-8")
        ).decode("utf-8")

        parts = decoded.split(":")

        if len(parts) != 3:
            return False

        role, timestamp_text, provided_signature = parts

        if role != "admin":
            return False

        timestamp = int(timestamp_text)

        current_time = int(time.time())

        if current_time - timestamp > ADMIN_TOKEN_EXPIRY_SECONDS:
            return False

        if timestamp > current_time + 60:
            return False

        payload = f"{role}:{timestamp_text}"

        expected_signature = hmac.new(
            ADMIN_TOKEN_SECRET.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(
            provided_signature,
            expected_signature
        )

    except Exception:
        return False


def require_admin(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        authorization = request.headers.get(
            "Authorization",
            ""
        )

        if not authorization.startswith("Bearer "):
            return error_response(
                "Admin authorization required.",
                401
            )

        token = authorization[7:].strip()

        if not verify_admin_token(token):
            return error_response(
                "Invalid or expired admin token.",
                401
            )

        return function(*args, **kwargs)

    return wrapper


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "success": True,
        "app": "GK Tricks Hindi API",
        "status": "online"
    })


@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "success": True,
        "status": "healthy"
    })


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route("/api/admin/login", methods=["POST"])
def admin_login():

    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return error_response(
            "Admin credentials are not configured.",
            500
        )

    if not ADMIN_TOKEN_SECRET:
        return error_response(
            "ADMIN_TOKEN_SECRET is not configured.",
            500
        )

    try:
        body = request.get_json(
            silent=True
        ) or {}

        email = str(
            body.get("email", "")
        ).strip()

        password = str(
            body.get("password", "")
        )

        email_ok = hmac.compare_digest(
            email,
            ADMIN_EMAIL
        )

        password_ok = hmac.compare_digest(
            password,
            ADMIN_PASSWORD
        )

        if not email_ok or not password_ok:

            return error_response(
                "Invalid admin email or password.",
                401
            )

        token = create_admin_token()

        return success_response(
            {
                "token": token,
                "expires_in": ADMIN_TOKEN_EXPIRY_SECONDS
            },
            message="Admin login successful."
        )

    except Exception as e:

        print(
            "[API] admin login error:",
            str(e)
        )

        return error_response(
            "Admin login failed.",
            500
        )


# =========================================================
# ADMIN - LIST PDFs
# =========================================================

@app.route(
    "/api/admin/pdfs",
    methods=["GET"]
)
@require_admin
def admin_get_pdfs():

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
            .order(
                "created_at",
                desc=True
            )
            .execute()
        )

        return success_response(
            result.data
        )

    except Exception as e:

        print(
            "[API] admin PDF list error:",
            str(e)
        )

        return error_response(
            "Unable to load admin PDFs.",
            500
        )


# =========================================================
# ADMIN - UPLOAD PDF
# =========================================================

@app.route(
    "/api/admin/pdfs/upload",
    methods=["POST"]
)
@require_admin
def admin_upload_pdf():

    if not check_supabase():
        return error_response(
            "Supabase is not configured.",
            500
        )

    uploaded_file = request.files.get("file")

    if uploaded_file is None:
        return error_response(
            "PDF file is required.",
            400
        )

    original_filename = (
        uploaded_file.filename or ""
    ).strip()

    if not original_filename:
        return error_response(
            "Invalid PDF filename.",
            400
        )

    if not original_filename.lower().endswith(".pdf"):
        return error_response(
            "Only PDF files are allowed.",
            400
        )

    title = request.form.get(
        "title",
        ""
    ).strip()

    subject = request.form.get(
        "subject",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    is_featured_text = request.form.get(
        "is_featured",
        "false"
    ).strip().lower()

    is_published_text = request.form.get(
        "is_published",
        "true"
    ).strip().lower()

    if not title:
        return error_response(
            "PDF title is required.",
            400
        )

    if not subject:
        return error_response(
            "PDF subject is required.",
            400
        )

    is_featured = (
        is_featured_text
        in ["true", "1", "yes", "on"]
    )

    is_published = (
        is_published_text
        not in ["false", "0", "no", "off"]
    )

    # -----------------------------------------------------
    # SAFE FILE NAME
    # -----------------------------------------------------

    safe_name = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        original_filename
    )

    safe_name = safe_name.strip(
        "._"
    )

    if not safe_name:
        safe_name = "document.pdf"

    unique_id = str(
        uuid.uuid4()
    )

    storage_path = (
        f"pdfs/{unique_id}_{safe_name}"
    )

    try:

        # -------------------------------------------------
        # READ FILE
        # -------------------------------------------------

        file_bytes = uploaded_file.read()

        if not file_bytes:
            return error_response(
                "Uploaded PDF is empty.",
                400
            )

        # -------------------------------------------------
        # UPLOAD TO SUPABASE STORAGE
        # -------------------------------------------------

        supabase.storage \
            .from_(STORAGE_BUCKET) \
            .upload(
                storage_path,
                file_bytes,
                {
                    "content-type": "application/pdf",
                    "cache-control": "3600",
                    "upsert": "false"
                }
            )

        # -------------------------------------------------
        # PUBLIC URL
        # -------------------------------------------------

        file_url = (
            supabase
            .storage
            .from_(STORAGE_BUCKET)
            .get_public_url(
                storage_path
            )
        )

        # -------------------------------------------------
        # INSERT METADATA
        # -------------------------------------------------

        insert_data = {
            "title": title,
            "subject": subject,
            "description": description,
            "file_url": file_url,
            "thumbnail_url": None,
            "is_featured": is_featured,
            "is_published": is_published,
            "download_count": 0
        }

        result = (
            supabase
            .table("pdfs")
            .insert(insert_data)
            .execute()
        )

        if not result.data:

            # DB insert failed after Storage upload.
            try:
                supabase.storage \
                    .from_(STORAGE_BUCKET) \
                    .remove([
                        storage_path
                    ])
            except Exception as cleanup_error:
                print(
                    "[API] Storage cleanup failed:",
                    str(cleanup_error)
                )

            return error_response(
                "PDF metadata could not be saved.",
                500
            )

        created_pdf = result.data[0]

        return success_response(
            created_pdf,
            message="PDF uploaded successfully."
        )

    except Exception as e:

        print(
            "[API] PDF upload error:",
            str(e)
        )

        # Try to remove Storage file if upload succeeded
        # but a later step failed.
        try:
            supabase.storage \
                .from_(STORAGE_BUCKET) \
                .remove([
                    storage_path
                ])
        except Exception:
            pass

        return error_response(
            "PDF upload failed.",
            500
        )


# =========================================================
# ADMIN - DELETE PDF
# =========================================================

@app.route(
    "/api/admin/pdfs/<pdf_id>",
    methods=["DELETE"]
)
@require_admin
def admin_delete_pdf(pdf_id):

    if not check_supabase():
        return error_response(
            "Supabase is not configured.",
            500
        )

    try:

        # -------------------------------------------------
        # GET PDF
        # -------------------------------------------------

        result = (
            supabase
            .table("pdfs")
            .select(
                "id,file_url"
            )
            .eq("id", pdf_id)
            .limit(1)
            .execute()
        )

        if not result.data:
            return error_response(
                "PDF not found.",
                404
            )

        pdf = result.data[0]

        file_url = pdf.get(
            "file_url"
        )

        # -------------------------------------------------
        # DELETE STORAGE FILE
        # -------------------------------------------------

        if file_url:

            marker = (
                f"/storage/v1/object/public/"
                f"{STORAGE_BUCKET}/"
            )

            if marker in file_url:

                storage_path = (
                    file_url
                    .split(marker, 1)[1]
                )

                if storage_path:

                    try:
                        supabase.storage \
                            .from_(STORAGE_BUCKET) \
                            .remove([
                                storage_path
                            ])
                    except Exception as storage_error:

                        print(
                            "[API] Storage delete warning:",
                            str(storage_error)
                        )

        # -------------------------------------------------
        # DELETE DATABASE ROW
        # -------------------------------------------------

        (
            supabase
            .table("pdfs")
            .delete()
            .eq("id", pdf_id)
            .execute()
        )

        return success_response(
            {
                "id": pdf_id
            },
            message="PDF deleted successfully."
        )

    except Exception as e:

        print(
            "[API] PDF delete error:",
            str(e)
        )

        return error_response(
            "PDF deletion failed.",
            500
        )


# =========================================================
# PUBLIC - GET ALL PUBLISHED PDFs
# =========================================================

@app.route(
    "/api/pdfs",
    methods=["GET"]
)
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
            .eq(
                "is_published",
                True
            )
            .order(
                "created_at",
                desc=True
            )
            .execute()
        )

        return success_response(
            result.data
        )

    except Exception as e:

        print(
            "[API] /api/pdfs error:",
            str(e)
        )

        return error_response(
            "Unable to load PDFs.",
            500
        )


# =========================================================
# PUBLIC - GET SINGLE PDF
# =========================================================

@app.route(
    "/api/pdfs/<pdf_id>",
    methods=["GET"]
)
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
            .eq(
                "id",
                pdf_id
            )
            .eq(
                "is_published",
                True
            )
            .limit(1)
            .execute()
        )

        if not result.data:

            return error_response(
                "PDF not found.",
                404
            )

        return success_response(
            result.data[0]
        )

    except Exception as e:

        print(
            "[API] /api/pdfs/<id> error:",
            str(e)
        )

        return error_response(
            "Unable to load PDF.",
            500
        )


# =========================================================
# PUBLIC - SUBJECTS
# =========================================================

@app.route(
    "/api/subjects",
    methods=["GET"]
)
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
            .eq(
                "is_published",
                True
            )
            .execute()
        )

        subjects = sorted({
            item.get(
                "subject",
                ""
            ).strip()
            for item in result.data
            if item.get("subject")
        })

        return success_response(
            subjects
        )

    except Exception as e:

        print(
            "[API] /api/subjects error:",
            str(e)
        )

        return error_response(
            "Unable to load subjects.",
            500
        )


# =========================================================
# PUBLIC - PDFs BY SUBJECT
# =========================================================

@app.route(
    "/api/subjects/<path:subject>/pdfs",
    methods=["GET"]
)
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
            .eq(
                "subject",
                subject
            )
            .eq(
                "is_published",
                True
            )
            .order(
                "created_at",
                desc=True
            )
            .execute()
        )

        return success_response(
            result.data
        )

    except Exception as e:

        print(
            "[API] subject PDFs error:",
            str(e)
        )

        return error_response(
            "Unable to load subject PDFs.",
            500
        )


# =========================================================
# PUBLIC - SEARCH
# =========================================================

@app.route(
    "/api/search",
    methods=["GET"]
)
def search_pdfs():

    if not check_supabase():
        return error_response(
            "Supabase is not configured.",
            500
        )

    query = request.args.get(
        "q",
        ""
    ).strip()

    if not query:
        return success_response([])

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

        search_pattern = (
            f"%{query}%"
        )

        result = (
            supabase
            .table("pdfs")
            .select(
                "id,title,subject,description,"
                "file_url,thumbnail_url,"
                "is_featured,is_published,"
                "download_count,created_at"
            )
            .eq(
                "is_published",
                True
            )
            .or_(
                f"title.ilike.{search_pattern},"
                f"subject.ilike.{search_pattern},"
                f"description.ilike.{search_pattern}"
            )
            .order(
                "created_at",
                desc=True
            )
            .execute()
        )

        return success_response(
            result.data
        )

    except Exception as e:

        print(
            "[API] search error:",
            str(e)
        )

        return error_response(
            "Search failed.",
            500
        )


# =========================================================
# PUBLIC - FEATURED
# =========================================================

@app.route(
    "/api/featured",
    methods=["GET"]
)
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
            .eq(
                "is_featured",
                True
            )
            .eq(
                "is_published",
                True
            )
            .order(
                "created_at",
                desc=True
            )
            .execute()
        )

        return success_response(
            result.data
        )

    except Exception as e:

        print(
            "[API] featured error:",
            str(e)
        )

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
# 500
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
        port=int(
            os.getenv(
                "PORT",
                5000
            )
        ),
        debug=False
    )
