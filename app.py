import json
import os
import tempfile
import threading
import time
import uuid
import zipfile

from flask import Flask, Response, jsonify, render_template, request, send_file

from converter import download_mp3

app = Flask(__name__)

# In-memory job store: job_id -> {status, messages, zip_path, error}
jobs: dict = {}
jobs_lock = threading.Lock()


def run_download(job_id: str, url: str) -> None:
    with jobs_lock:
        jobs[job_id] = {
            "status": "running",
            "messages": [],
            "zip_path": None,
            "error": None,
        }

    seen_titles: set = set()

    def log(msg: str) -> None:
        with jobs_lock:
            jobs[job_id]["messages"].append(msg)

    def progress_hook(d: dict) -> None:
        title = d.get("info_dict", {}).get("title") or os.path.basename(
            d.get("filename", "unknown")
        )
        if d["status"] == "downloading" and title not in seen_titles:
            seen_titles.add(title)
            log(f"Downloading: {title}")
        elif d["status"] == "finished":
            log(f"Converting:  {title}")

    try:
        tmp_dir = tempfile.mkdtemp()
        log(f"Starting download for: {url}")
        files = download_mp3(url, tmp_dir, progress_hooks=[progress_hook])

        if not files:
            raise RuntimeError("No files were downloaded. Check the URL and try again.")

        log("Creating zip archive...")
        zip_fd, zip_path = tempfile.mkstemp(suffix=".zip")
        os.close(zip_fd)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                if os.path.exists(f):
                    arcname = os.path.relpath(f, tmp_dir)
                    zf.write(f, arcname)

        with jobs_lock:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["zip_path"] = zip_path
            jobs[job_id]["messages"].append(
                f"Done! {len(files)} track(s) ready to download."
            )

    except Exception as exc:
        with jobs_lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(exc)
            jobs[job_id]["messages"].append(f"Error: {exc}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    job_id = str(uuid.uuid4())
    thread = threading.Thread(target=run_download, args=(job_id, url), daemon=True)
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/progress/<job_id>")
def progress(job_id: str):
    def generate():
        last_idx = 0
        while True:
            time.sleep(0.4)
            with jobs_lock:
                job = jobs.get(job_id)
                if job is None:
                    yield f"data: {json.dumps({'status': 'error', 'error': 'Job not found'})}\n\n"
                    return
                new_msgs = job["messages"][last_idx:]
                last_idx = len(job["messages"])
                status = job["status"]
                error = job["error"]

            for msg in new_msgs:
                yield f"data: {json.dumps({'msg': msg})}\n\n"

            if status == "done":
                yield f"data: {json.dumps({'status': 'done'})}\n\n"
                return
            if status == "error":
                yield f"data: {json.dumps({'status': 'error', 'error': error})}\n\n"
                return

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/download/<job_id>")
def download_zip(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job or job["status"] != "done":
        return jsonify({"error": "Job not ready or not found"}), 404

    zip_path = job["zip_path"]
    if not os.path.exists(zip_path):
        return jsonify({"error": "Zip file missing"}), 500

    return send_file(
        zip_path,
        as_attachment=True,
        download_name="mp3s.zip",
        mimetype="application/zip",
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
