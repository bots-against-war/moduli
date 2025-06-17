import abc
import logging
import mimetypes
import uuid
from pathlib import Path
from typing import Any

import aiobotocore.client  # type: ignore
import aiobotocore.session  # type: ignore
import pydantic
from telebot_components.redis_utils.interface import RedisInterface

from telebot_constructor.constants import CONSTRUCTOR_PREFIX

logger = logging.getLogger(__name__)


class Media(pydantic.BaseModel):
    content: bytes
    filename: str | None

    def __str__(self) -> str:
        return f"Media <{len(self.content)} bytes> filename={self.filename!r} mimetype={self.mimetype}"

    def __repr__(self) -> str:
        return str(self)

    @property
    def mimetype(self) -> str | None:
        if self.filename is not None:
            mimetype, _ = mimetypes.guess_type(self.filename)
            return mimetype
        else:
            return None


MediaId = str


class MediaStore(abc.ABC):
    @abc.abstractmethod
    async def save_media(self, owner_id: str, media: Media) -> MediaId | None: ...

    @abc.abstractmethod
    async def load_media(self, owner_id: str, media_id: MediaId) -> Media | None: ...

    @abc.abstractmethod
    async def delete_media(self, owner_id: str, media_id: MediaId) -> bool: ...

    async def setup(self) -> None: ...

    async def cleanup(self) -> None: ...

    def adapter_for(self, owner_id: str) -> "UserSpecificMediaStore":
        return UserSpecificMediaStore(media_store=self, owner_id=owner_id)


class RedisMediaStore(MediaStore):
    """Redis-based store for testing and development, do not use in production!"""

    def __init__(self, redis: RedisInterface) -> None:
        self.redis = redis

    def _content_key(self, owner_id: str, media_id: str) -> str:
        return f"{CONSTRUCTOR_PREFIX}/media/{owner_id}/{media_id}"

    def _filename_key(self, owner_id: str, media_id: str) -> str:
        return f"{CONSTRUCTOR_PREFIX}/media/{owner_id}/filename/{media_id}"

    async def save_media(self, owner_id: str, media: Media) -> MediaId | None:
        media_id = str(uuid.uuid4())
        if not await self.redis.set(
            self._content_key(owner_id=owner_id, media_id=media_id),
            media.content,
        ):
            return None
        if media.filename:
            if not await self.redis.set(
                self._filename_key(owner_id=owner_id, media_id=media_id), media.filename.encode("utf-8")
            ):
                return None
        return media_id

    async def load_media(self, owner_id: str, media_id: MediaId) -> Media | None:
        content = await self.redis.get(self._content_key(owner_id, media_id))
        if content is None:
            return None
        filename = await self.redis.get(self._filename_key(owner_id, media_id))
        return Media(
            content=content,
            filename=filename.decode("utf-8") if filename is not None else None,
        )

    async def delete_media(self, owner_id: str, media_id: MediaId) -> bool:
        return (
            await self.redis.delete(
                self._content_key(owner_id, media_id),
                self._filename_key(owner_id, media_id),
            )
        ) > 0


class AwsS3Credentials(pydantic.BaseModel):
    access_key_id: str
    secret_access_key: str
    region: str
    bucket: str


class AwsS3MediaStore(MediaStore):
    def __init__(self, credentials: AwsS3Credentials) -> None:
        self.credentials = credentials
        self._client: aiobotocore.client.AioBaseClient | None = None

    @property
    def client(self) -> aiobotocore.client.AioBaseClient:
        if self._client is None:
            raise RuntimeError("Attempt to use media store before initialization")
        return self._client

    async def setup(self) -> None:
        if self._client is not None:
            return
        session = aiobotocore.session.get_session()
        # HACK: (aio)botocore forces the use of client as a context manager, but it will not fly with us
        self._client = await session._create_client(
            "s3",
            region_name="us-west-2",
            aws_secret_access_key=self.credentials.secret_access_key,
            aws_access_key_id=self.credentials.access_key_id,
        )
        await self._client.__aenter__()

    async def cleanup(self):
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
        self._client = None

    async def save_media(self, owner_id: str, media: Media) -> MediaId | None:
        media_id = str(uuid.uuid4())

        # see docs at
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/put_object.html
        put_object_kwargs: dict[str, Any] = dict()
        content_type = media.mimetype
        if content_type is not None:
            put_object_kwargs["ContentType"] = content_type
        if media.filename is not None:
            put_object_kwargs["Metadata"] = {"filename": media.filename}

        try:
            resp = await self.client.put_object(  # type: ignore
                Bucket=self.credentials.bucket,
                Key=f"{owner_id}/{media_id}",
                Body=media.content,
                **put_object_kwargs,
            )
            logging.debug("Response from S3: %s", resp)
            return media_id
        except Exception:
            logging.exception("Error putting object in S3 bucket")
            return None

    async def load_media(self, owner_id: str, media_id: MediaId) -> Media | None:
        try:
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/get_object.html
            resp = await self.client.get_object(  # type: ignore
                Bucket=self.credentials.bucket,
                Key=f"{owner_id}/{media_id}",
            )
            body = resp["Body"]
            return Media(content=await body.read(), filename=resp.get("Metadata", {}).get("filename"))
        except Exception as exc:
            if exc.__class__.__name__ != "NoSuchKey":
                logger.exception("Unexpected error getting an object from S3")
            return None

    async def delete_media(self, owner_id: str, media_id: MediaId) -> bool:
        try:
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/delete_object.html
            await self.client.delete_object(  # type: ignore
                Bucket=self.credentials.bucket,
                Key=f"{owner_id}/{media_id}",
            )
            return True
        except Exception as exc:
            if exc.__class__.__name__ != "NoSuchKey":
                logger.exception("Unexpected error getting an object from S3")
            return False


class UserSpecificMediaStore:
    """Thin adapter to use in contexts without easy access to user"""

    def __init__(self, media_store: MediaStore, owner_id: str) -> None:
        self.media_store = media_store
        self.owner_id = owner_id

    async def load_media(self, media_id: MediaId) -> Media | None:
        return await self.media_store.load_media(owner_id=self.owner_id, media_id=media_id)


class FilesystemMediaStore(MediaStore):
    def __init__(self, dir: Path) -> None:
        self._dir = dir
        assert self._dir.exists(), f"{self._dir} does not exist"
        assert self._dir.is_dir(), f"{self._dir} is not a directory"

    def _filename(self, owner_id: str, media_id: MediaId) -> Path:
        owner_dir = self._dir / owner_id
        owner_dir.mkdir(exist_ok=True)
        return owner_dir / media_id

    async def save_media(self, owner_id: str, media: Media) -> MediaId | None:
        media_id = str(uuid.uuid4())
        self._filename(owner_id, media_id).write_bytes(media.content)
        return media_id

    async def load_media(self, owner_id: str, media_id: MediaId) -> Media | None:
        filename = self._filename(owner_id, media_id)
        if not filename.exists():
            return None
        else:
            return Media(
                content=filename.read_bytes(),
                filename=None,
            )

    async def delete_media(self, owner_id: str, media_id: MediaId) -> bool:
        filename = self._filename(owner_id, media_id)
        if not filename.exists():
            return False
        filename.unlink()
        return True
