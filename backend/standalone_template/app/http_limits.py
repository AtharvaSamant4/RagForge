from fastapi import HTTPException
from fastapi.responses import JSONResponse
from .engine.config import settings


class BodyLimit:
    """Bound bytes before JSON or multipart parsing, including chunked requests."""
    def __init__(self,app):
        import threading
        self.app=app;self.upload_slots=threading.BoundedSemaphore(4)

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        upload=scope['method']=='POST' and scope['path'].endswith('/documents')
        maximum=(settings().max_upload_mb+1)*1024**2 if upload else 256*1024
        headers=dict(scope['headers'])
        try:length=int(headers.get(b'content-length',b'0'))
        except ValueError:length=maximum+1
        if not 0<=length<=maximum:
            return await JSONResponse({'detail':'Request exceeds body limit'},413)(scope,receive,send)
        if upload and b'content-length' not in headers:
            return await JSONResponse({'detail':'Content-Length is required for uploads'},411)(scope,receive,send)
        received=0
        async def bounded_receive():
            nonlocal received
            message=await receive()
            received+=len(message.get('body',b''))
            if received>maximum:raise HTTPException(413,'Request exceeds body limit')
            return message
        if upload and not self.upload_slots.acquire(blocking=False):
            return await JSONResponse({'detail':'Upload capacity reached; retry shortly'},429)(scope,receive,send)
        try:return await self.app(scope,bounded_receive,send)
        finally:
            if upload:self.upload_slots.release()
