import streamlit as st
from PIL import Image
import io
from datetime import datetime

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError


st.set_page_config(page_title="Collage Generator", layout="centered")
st.title("📸 Collage Generator")

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_client_config():
    return {
        "web": {
            "client_id": st.secrets["google_oauth"]["client_id"],
            "client_secret": st.secrets["google_oauth"]["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [
                st.secrets["google_oauth"]["redirect_uri"]
            ],
        }
    }


def get_flow():
    return Flow.from_client_config(
        get_client_config(),
        scopes=SCOPES,
        redirect_uri=st.secrets["google_oauth"]["redirect_uri"],
    )


def credentials_to_dict(credentials):
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }


def get_credentials():
    if "credentials" not in st.session_state:
        return None

    credentials = Credentials(**st.session_state["credentials"])

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        st.session_state["credentials"] = credentials_to_dict(credentials)

    return credentials


def login_google():
    flow = get_flow()

    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )

    st.session_state["oauth_state"] = state

    st.link_button("🔐 Login with Google", auth_url)


def handle_oauth_callback():
    query_params = st.query_params

    if "code" in query_params:
        code = query_params["code"]

        flow = get_flow()
        flow.fetch_token(code=code)

        credentials = flow.credentials
        st.session_state["credentials"] = credentials_to_dict(credentials)

        st.query_params.clear()
        st.rerun()


def create_collage(uploaded_files):
    CANVAS_W = 900
    TARGET_ROW_H = 360
    GAP = 8
    BG = (255, 255, 255)

    images = []

    for file in uploaded_files:
        img = Image.open(file).convert("RGB")
        w, h = img.size

        new_w = int(w * TARGET_ROW_H / h)
        new_h = TARGET_ROW_H

        resized = img.resize(
            (new_w, new_h),
            Image.Resampling.LANCZOS
        )

        images.append(resized)

    rows = []
    current_row = []
    current_width = 0

    for img in images:
        next_width = current_width + img.width

        if current_row:
            next_width += GAP

        if next_width > CANVAS_W and current_row:
            rows.append(current_row)
            current_row = [img]
            current_width = img.width
        else:
            current_row.append(img)
            current_width = next_width

    if current_row:
        rows.append(current_row)

    final_rows = []
    canvas_h = 0

    for row in rows:
        total_w = sum(img.width for img in row) + GAP * (len(row) - 1)
        scale = CANVAS_W / total_w

        resized_row = []

        for img in row:
            new_w = int(img.width * scale)
            new_h = int(img.height * scale)

            resized_row.append(
                img.resize(
                    (new_w, new_h),
                    Image.Resampling.LANCZOS
                )
            )

        final_rows.append(resized_row)
        canvas_h += max(img.height for img in resized_row) + GAP

    canvas_h -= GAP

    collage = Image.new("RGB", (CANVAS_W, canvas_h), BG)

    y = 0

    for row in final_rows:
        x = 0

        for img in row:
            collage.paste(img, (x, y))
            x += img.width + GAP

        y += max(img.height for img in row) + GAP

    return collage


def get_or_create_folder(service, folder_name="Collage Output"):
    query = (
        "mimeType='application/vnd.google-apps.folder' "
        f"and name='{folder_name}' "
        "and trashed=false"
    )

    result = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name)",
        pageSize=1
    ).execute()

    folders = result.get("files", [])

    if folders:
        return folders[0]["id"]

    folder_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder"
    }

    folder = service.files().create(
        body=folder_metadata,
        fields="id"
    ).execute()

    return folder["id"]


def upload_to_google_drive(file_buffer, file_name, credentials):
    service = build("drive", "v3", credentials=credentials)

    folder_id = get_or_create_folder(service)

    file_metadata = {
        "name": file_name,
        "parents": [folder_id]
    }

    file_buffer.seek(0)

    media = MediaIoBaseUpload(
        file_buffer,
        mimetype="image/jpeg",
        resumable=False
    )

    service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()


handle_oauth_callback()

credentials = get_credentials()

if credentials is None:
    st.info("กรุณา Login Google ก่อน เพื่อบันทึก Collage เข้า Google Drive")
    login_google()
    st.stop()

st.success("Google Login สำเร็จแล้ว ✅")

if st.button("Logout"):
    st.session_state.pop("credentials", None)
    st.rerun()

uploaded_files = st.file_uploader(
    "Upload images",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True
)

if uploaded_files:
    st.success(f"Uploaded {len(uploaded_files)} image(s)")

    if st.button("Create Collage & Save to Google Drive"):
        with st.spinner("กำลังสร้าง Collage และบันทึกเข้า Google Drive..."):
            try:
                collage = create_collage(uploaded_files)

                st.image(
                    collage,
                    caption="Collage Preview",
                    use_container_width=True
                )

                buffer = io.BytesIO()
                collage.save(buffer, format="JPEG", quality=95)
                buffer.seek(0)

                file_name = datetime.now().strftime(
                    "collage_%Y%m%d_%H%M%S.jpg"
                )

                upload_to_google_drive(
                    buffer,
                    file_name,
                    credentials
                )

                st.success("บันทึก Collage เข้า Google Drive เรียบร้อยแล้ว ✅")

            except HttpError as e:
                st.error("Google Drive Error")
                st.code(str(e))

            except Exception as e:
                st.error("Unexpected Error")
                st.code(str(e))
