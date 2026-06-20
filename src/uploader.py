# FILE: src/uploader.py
# UPDATED: Works with GitHub Secrets (no local files needed)

import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from pathlib import Path

# YouTube API scope for uploading videos
YOUTUBE_UPLOAD_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]

def get_authenticated_service():
    """
    Gets authenticated YouTube service using credentials from GitHub Secrets.
    Falls back to local files only if environment variables are not set.
    """
    # Check if we have credentials in environment variables (GitHub Secrets)
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    # If all environment variables exist, use them (GitHub Actions mode)
    if client_id and client_secret and refresh_token:
        print("🔑 Using YouTube credentials from environment variables (GitHub Secrets).")
        try:
            credentials = Credentials(
                token=None,  # Will be refreshed
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
                token_uri="https://oauth2.googleapis.com/token"
            )

            # Refresh token to ensure it's valid
            if credentials and credentials.expired:
                credentials.refresh(Request())

            print("✅ YouTube authentication successful!")
            return build('youtube', 'v3', credentials=credentials)

        except Exception as e:
            print(f"❌ ERROR: Failed to authenticate with environment credentials: {e}")
            raise

    # Fallback: Use local files (local development mode)
    print("⚠️ No environment credentials found. Falling back to local files.")
    try:
        CREDENTIALS_FILE = Path('credentials.json')
        CLIENT_SECRETS_FILE = Path('client_secrets.json')

        credentials = None

        if CREDENTIALS_FILE.exists():
            print("INFO: Found existing credentials file.")
            credentials = Credentials.from_authorized_user_file(str(CREDENTIALS_FILE), YOUTUBE_UPLOAD_SCOPE)

        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                print("INFO: Refreshing expired credentials...")
                credentials.refresh(Request())
            else:
                print("INFO: Starting new authentication flow...")
                if not CLIENT_SECRETS_FILE.exists():
                    raise FileNotFoundError(f"CRITICAL ERROR: {CLIENT_SECRETS_FILE} not found.")

                from google_auth_oauthlib.flow import InstalledAppFlow
                flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), scopes=YOUTUBE_UPLOAD_SCOPE)
                credentials = flow.run_local_server(port=0)

            with open(CREDENTIALS_FILE, 'w') as f:
                f.write(credentials.to_json())
            print(f"INFO: Credentials saved to {CREDENTIALS_FILE}")

        return build('youtube', 'v3', credentials=credentials)

    except Exception as e:
        print(f"❌ ERROR: YouTube authentication failed: {e}")
        raise


def upload_to_youtube(video_path, title, description, tags, thumbnail_path=None):
    """Uploads a video to YouTube with the given metadata and optionally a thumbnail."""
    print(f"⬆️ Uploading '{video_path}' to YouTube...")
    try:
        youtube = get_authenticated_service()

        request_body = {
            'snippet': {
                'title': title[:100],  # YouTube title limit is 100 characters
                'description': description[:5000],  # YouTube description limit is 5000
                'tags': [tag.strip() for tag in tags.split(',') if tag.strip()],
                'categoryId': '22'  # 22 = People & Blogs (good for MrBeast-style)
            },
            'status': {
                'privacyStatus': 'public',  # 'private', 'public', or 'unlisted'
                'selfDeclaredMadeForKids': False
            }
        }

        media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)

        request = youtube.videos().insert(
            part=','.join(request_body.keys()),
            body=request_body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"📤 Uploaded {int(status.progress() * 100)}%.")

        video_id = response.get('id')
        print(f"✅ Video uploaded successfully! Video ID: {video_id}")

        # Upload thumbnail if provided
        if thumbnail_path and Path(thumbnail_path).exists():
            print(f"⬆️ Uploading thumbnail '{thumbnail_path}'...")
            try:
                thumbnail_media = MediaFileUpload(str(thumbnail_path))
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=thumbnail_media
                ).execute()
                print("✅ Thumbnail uploaded successfully!")
            except Exception as e:
                print(f"⚠️ Could not upload thumbnail: {e}")
        else:
            print("⚠️ No thumbnail file found. Skipping thumbnail upload.")

        return video_id

    except Exception as e:
        print(f"❌ ERROR: Failed to upload to YouTube. {e}")
        raise
