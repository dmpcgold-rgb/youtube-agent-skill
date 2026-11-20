#!/usr/bin/env python3
"""YouTube agent CLI: local draft queue, explicit approval, optional YouTube API.

Standard library for prepare/list/approve; OAuth client packages are needed only for API calls.
No command uploads or publishes without a separate approval covering the exact video and metadata.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUEUE = ROOT / ".youtube-agent" / "queue.json"

def digest(job):
    fields = {k: job[k] for k in ("video", "title", "description", "privacy", "tags")}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def load_queue(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Queue must be a JSON object")
    return data

def save_queue(path, queue):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(queue, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def create_job(video, title, description, privacy, tags):
    video_path = Path(video).expanduser().resolve()
    if not video_path.is_file():
        raise ValueError("Video file does not exist: " + str(video_path))
    if not title.strip() or len(title) > 100:
        raise ValueError("Video title must be 1-100 characters")
    if len(description) > 5000:
        raise ValueError("Description exceeds YouTube's 5000-character limit")
    if privacy not in ("private", "unlisted", "public"):
        raise ValueError("Invalid privacy")
    job = {
        "video": str(video_path), "title": title.strip(), "description": description,
        "privacy": privacy, "tags": tags, "status": "draft", "created_at": utcnow(),
        "approved_digest": None, "uploaded_video_id": None,
    }
    return job

def prepare(queue, video, title, description, privacy, tags):
    job = create_job(video, title, description, privacy, tags)
    key = digest(job)[:16]
    # A duplicate submission never preserves a previous approval.
    job["id"] = key
    queue[key] = job
    return key

def approve(queue, key, confirmation):
    job = queue[key]
    if job["status"] == "uploaded":
        raise ValueError("Already uploaded")
    expected = "APPROVE " + key
    if confirmation != expected:
        raise ValueError("Approval requires typing exactly: " + expected)
    if not Path(job["video"]).is_file():
        raise ValueError("Video no longer exists")
    job["approved_digest"] = digest(job)
    job["status"] = "approved"
    job["approved_at"] = utcnow()

def can_upload(job):
    return (job.get("status") == "approved" and
            job.get("approved_digest") == digest(job) and
            Path(job["video"]).is_file() and
            not job.get("uploaded_video_id"))

def youtube_service(client_secret, token_file, scopes):
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("Install API dependencies: pip install -r agent/requirements.txt") from exc
    credentials = None
    if token_file.exists():
        credentials = Credentials.from_authorized_user_file(str(token_file), scopes)
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid or not set(scopes).issubset(set(credentials.scopes or [])):
        if not client_secret.is_file():
            raise ValueError("OAuth client JSON missing: " + str(client_secret))
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), scopes)
        credentials = flow.run_local_server(port=0)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(credentials.to_json(), encoding="utf-8")
    try:
        os.chmod(token_file, 0o600)
    except OSError:
        pass
    return build("youtube", "v3", credentials=credentials)

def channel_summary(client_secret, token_file):
    youtube = youtube_service(client_secret, token_file, ["https://www.googleapis.com/auth/youtube.readonly"])
    channel = youtube.channels().list(part="snippet,statistics", mine=True).execute()
    for item in channel.get("items", []):
        print(json.dumps({
            "channel": item["snippet"]["title"],
            "subscribers": item.get("statistics", {}).get("subscriberCount"),
            "views": item.get("statistics", {}).get("viewCount"),
            "videos": item.get("statistics", {}).get("videoCount"),
        }, indent=2, ensure_ascii=False))
    if not channel.get("items"):
        print("No accessible YouTube channel for this OAuth account")

def upload(queue, key, client_secret, token_file):
    job = queue[key]
    if not can_upload(job):
        raise ValueError("Upload blocked: approve the current metadata and verify local video file")
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError("Install API dependencies: pip install -r agent/requirements.txt") from exc
    youtube = youtube_service(client_secret, token_file, ["https://www.googleapis.com/auth/youtube.upload"])
    body = {"snippet": {"title": job["title"], "description": job["description"],
                        "tags": job["tags"]},
            "status": {"privacyStatus": job["privacy"]}}
    media = MediaFileUpload(job["video"], resumable=True, chunksize=8 * 1024 * 1024)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    job["uploaded_video_id"] = response["id"]
    job["status"] = "uploaded"
    job["uploaded_at"] = utcnow()
    print("Uploaded: https://www.youtube.com/watch?v=" + response["id"])

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    p.add_argument("--client-secret", type=Path, default=ROOT / "client_secret.json")
    p.add_argument("--token", type=Path, default=ROOT / ".youtube-agent" / "token.json")
    sub = p.add_subparsers(dest="command", required=True)
    create = sub.add_parser("prepare", help="Create an unpublished draft")
    create.add_argument("video")
    create.add_argument("--title", required=True)
    create.add_argument("--description", default="")
    create.add_argument("--description-file", type=Path)
    create.add_argument("--privacy", choices=("private", "unlisted", "public"), default="private")
    create.add_argument("--tag", action="append", default=[])
    sub.add_parser("list", help="Show local queue, no network")
    appr = sub.add_parser("approve", help="Explicitly approve exact metadata and video path")
    appr.add_argument("job_id")
    appr.add_argument("--confirm", required=True, help="Exact phrase: APPROVE <job_id>")
    push = sub.add_parser("upload", help="Upload ONLY an approved job")
    push.add_argument("job_id")
    sub.add_parser("channel", help="Read authenticated channel summary")
    a = p.parse_args(argv)
    try:
        q = load_queue(a.queue)
        if a.command == "prepare":
            description = a.description_file.read_text(encoding="utf-8") if a.description_file else a.description
            key = prepare(q, a.video, a.title, description, a.privacy, a.tag)
            save_queue(a.queue, q)
            print("Draft " + key + " created. Check it with: list; approve with: approve " + key + " --confirm 'APPROVE " + key + "'")
        elif a.command == "list":
            for key, job in q.items():
                print(key, job["status"], job["privacy"], repr(job["title"]), job["video"])
            if not q:
                print("No jobs")
        elif a.command == "approve":
            approve(q, a.job_id, a.confirm)
            save_queue(a.queue, q)
            print("Approved " + a.job_id + ". No upload performed.")
        elif a.command == "upload":
            upload(q, a.job_id, a.client_secret, a.token)
            save_queue(a.queue, q)
        elif a.command == "channel":
            channel_summary(a.client_secret, a.token)
    except (ValueError, KeyError, OSError, RuntimeError) as e:
        p.exit(1, "Error: " + str(e) + "\n")

if __name__ == "__main__":
    main()
