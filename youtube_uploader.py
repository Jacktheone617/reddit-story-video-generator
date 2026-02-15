"""
YouTube Shorts uploader using the YouTube Data API v3.

Setup (one-time):
1. Go to https://console.cloud.google.com/ and create a project
2. Enable "YouTube Data API v3" (APIs & Services > Library)
3. Configure OAuth consent screen (External, add your email as test user)
4. Create OAuth 2.0 credentials (Desktop app) and download the JSON
5. Save as client_secret.json in the project root
6. First run opens a browser for Google sign-in; token.json is saved for future runs
"""

import os
import time
import httplib2

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
           "https://www.googleapis.com/auth/youtube"]


class YouTubeUploader:
    """Handles OAuth authentication and video uploads to YouTube."""

    def __init__(self, client_secret_path="client_secret.json",
                 token_path="token.json"):
        self.client_secret_path = client_secret_path
        self.token_path = token_path
        self._service = None

    def authenticate(self):
        """
        Load saved credentials or run the OAuth browser flow.

        Returns:
            Authenticated YouTube API service object.
        """
        creds = None

        # Load existing token
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)

        # Refresh or run new flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secret_path, SCOPES)
                creds = flow.run_local_server(port=0)

            # Save for next time
            with open(self.token_path, "w") as f:
                f.write(creds.to_json())

        self._service = build("youtube", "v3", credentials=creds)
        return self._service

    def upload_short(self, video_path, title, description="",
                     tags=None, privacy="private"):
        """
        Upload a video as a YouTube Short (private by default).

        Args:
            video_path: Path to the .mp4 file.
            title: Video title (max 100 chars).
            description: Video description.
            tags: Optional list of tags.
            privacy: "private", "unlisted", or "public".

        Returns:
            Dict with video_id and url on success, None on failure.
        """
        if self._service is None:
            self.authenticate()

        # Ensure #Shorts is in the description
        if "#Shorts" not in description:
            description = description.rstrip() + "\n\n#Shorts"

        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags or ["Reddit", "RedditStories", "Shorts"],
                "categoryId": "22",  # People & Blogs
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(video_path, mimetype="video/mp4",
                                resumable=True, chunksize=10 * 1024 * 1024)

        request = self._service.videos().insert(
            part="snippet,status", body=body, media_body=media)

        # Resumable upload with exponential backoff
        response = None
        retries = 0
        max_retries = 5

        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    print(f"  Uploading... {pct}%")
            except HttpError as e:
                if e.resp.status in (500, 502, 503, 504) and retries < max_retries:
                    retries += 1
                    wait = 2 ** retries
                    print(f"  Server error {e.resp.status}, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"Upload failed: {e}")
                    return None
            except httplib2.HttpLib2Error as e:
                if retries < max_retries:
                    retries += 1
                    wait = 2 ** retries
                    print(f"  Network error, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"Upload failed after {max_retries} retries: {e}")
                    return None

        video_id = response["id"]
        url = f"https://youtube.com/shorts/{video_id}"
        print(f"Upload complete: {url}")
        return {"video_id": video_id, "url": url}

    def make_public(self, video_id):
        """Update a video's privacy status to public."""
        if self._service is None:
            self.authenticate()

        self._service.videos().update(
            part="status",
            body={
                "id": video_id,
                "status": {"privacyStatus": "public"},
            },
        ).execute()
        print(f"Video {video_id} is now public")
