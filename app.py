import streamlit as st
from PIL import Image
import io
from datetime import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


st.set_page_config(
    page_title="Collage Generator",
    layout="centered"
)

st.title("📸 Collage Generator")

uploaded_files = st.file_uploader(
    "Upload images",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True
)

CANVAS_W = 900
TARGET_ROW_H = 360
GAP = 8
BG = (255, 255, 255)


def create_collage(uploaded_files):
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

    collage = Image.new(
        "RGB",
        (CANVAS_W, canvas_h),
        BG
    )

    y = 0

    for row in final_rows:
        x = 0

        row_h = max(img.height for img in row)

        for img in row:
            collage.paste(img, (x, y))
            x += img.width + GAP

        y += row_h + GAP

    return collage


def upload_to_google_drive(file_buffer, file_name):
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )

    service = build(
        "drive",
        "v3",
        credentials=credentials
    )

    folder_id = st.secrets["google_drive"]["folder_id"]

    file_metadata = {
        "name": file_name,
        "parents": [folder_id]
    }

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


if uploaded_files:
    st.success(f"Uploaded {len(uploaded_files)} image(s)")

    if st.button("Create Collage & Save to Google Drive"):
        with st.spinner("กำลังสร้าง Collage และบันทึกเข้า Google Drive..."):
            collage = create_collage(uploaded_files)

            st.image(
                collage,
                caption="Collage Preview",
                use_container_width=True
            )

            buffer = io.BytesIO()

            collage.save(
                buffer,
                format="JPEG",
                quality=95
            )

            buffer.seek(0)

            file_name = datetime.now().strftime(
                "collage_%Y%m%d_%H%M%S.jpg"
            )

            upload_to_google_drive(buffer, file_name)

            st.success("บันทึก Collage เข้า Google Drive เรียบร้อยแล้ว ✅")
