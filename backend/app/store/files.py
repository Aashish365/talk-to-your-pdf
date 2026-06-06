import os
import shutil
import aiofiles
from app.config import settings


def session_dir(sid: str) -> str:
    return os.path.join(settings.data_dir, sid)


def pdf_path(sid: str, doc_id: str) -> str:
    return os.path.join(session_dir(sid), f"{doc_id}.pdf")


def md_path(sid: str, doc_id: str) -> str:
    return os.path.join(session_dir(sid), f"{doc_id}.md")


def create_session_dir(sid: str) -> None:
    os.makedirs(session_dir(sid), exist_ok=True)


async def save_upload(sid: str, doc_id: str, data: bytes) -> str:
    path = pdf_path(sid, doc_id)
    async with aiofiles.open(path, "wb") as f:
        await f.write(data)
    return path


def delete_session_dir(sid: str) -> None:
    d = session_dir(sid)
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)
